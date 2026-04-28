"""Audit ORM model metadata vs live DB schema.

Usage:
    DATABASE_URL='postgresql://postgres:root@localhost:5432/evonexus' \\
        uv run python scripts/audit_schema_drift.py

Output: tables with MISSING columns (in ORM but absent in DB),
        EXTRA columns (in DB but absent in ORM), and TYPE mismatches.
Exit 0 = clean, exit 1 = drift found.
"""

from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# Resolve project root so imports work regardless of CWD
# ---------------------------------------------------------------------------
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, inspect, text
import sqlalchemy as sa

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///dashboard/backend/dashboard.db")

engine = create_engine(DATABASE_URL)
insp = inspect(engine)

# ---------------------------------------------------------------------------
# Import ORM metadata WITHOUT starting the Flask app (avoids seed_roles crash)
# ---------------------------------------------------------------------------
os.environ.setdefault("FLASK_ENV", "production")  # suppress debug noise

# Import only the models module — no app.create_all() happens
import dashboard.backend.models as m  # noqa: E402

drift_found = False
report: list[str] = []

db_tables = set(insp.get_table_names())

for table_name, table in sorted(m.db.metadata.tables.items()):
    orm_cols: dict[str, str] = {c.name: str(c.type) for c in table.columns}

    if table_name not in db_tables:
        report.append(f"MISSING TABLE: {table_name}")
        drift_found = True
        continue

    db_col_info = insp.get_columns(table_name)
    db_cols: dict[str, str] = {c["name"]: str(c["type"]) for c in db_col_info}

    missing = sorted(set(orm_cols) - set(db_cols))
    extra = sorted(set(db_cols) - set(orm_cols))
    type_mismatches: list[str] = []

    for col in sorted(set(orm_cols) & set(db_cols)):
        orm_t = orm_cols[col].upper().split("(")[0].strip()
        db_t = db_cols[col].upper().split("(")[0].strip()
        # Normalize common aliases
        aliases = {
            "VARCHAR": "STRING",
            "TEXT": "TEXT",
            "INTEGER": "INTEGER",
            "INT": "INTEGER",
            "BIGINT": "INTEGER",
            "SMALLINT": "INTEGER",
            "BOOLEAN": "BOOLEAN",
            "BOOL": "BOOLEAN",
            "FLOAT": "FLOAT",
            "DOUBLE PRECISION": "FLOAT",
            "REAL": "FLOAT",
            "DATETIME": "DATETIME",
            "TIMESTAMP WITHOUT TIME ZONE": "DATETIME",
            "TIMESTAMP WITH TIME ZONE": "DATETIME",
        }
        orm_norm = aliases.get(orm_t, orm_t)
        db_norm = aliases.get(db_t, db_t)
        if orm_norm != db_norm:
            type_mismatches.append(f"      col '{col}': ORM={orm_t} DB={db_t}")

    if missing or extra or type_mismatches:
        drift_found = True
        report.append(f"\nTABLE: {table_name}")
        if missing:
            report.append(f"  MISSING in DB (in ORM, absent in DB): {missing}")
        if extra:
            report.append(f"  EXTRA in DB (in DB, absent in ORM):   {extra}")
        if type_mismatches:
            report.append("  TYPE MISMATCHES:")
            report.extend(type_mismatches)

# Tables in DB not mentioned in ORM metadata at all (non-ORM tables are expected)
orm_table_names = set(m.db.metadata.tables.keys())
db_only = sorted(db_tables - orm_table_names)
if db_only:
    report.append(f"\nDB-ONLY tables (non-ORM, expected): {db_only}")

if report:
    print("\n".join(report))
else:
    print("OK — zero drift found between ORM and DB schema.")

sys.exit(1 if drift_found else 0)
