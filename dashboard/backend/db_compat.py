from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import create_engine, text

from runtime_config import database_backend, database_uri, sqlite_path_from_uri


@dataclass
class CompatRow:
    keys_list: list[str]
    values_list: list[Any]

    def __getitem__(self, item: int | str) -> Any:
        if isinstance(item, int):
            return self.values_list[item]
        idx = self.keys_list.index(item)
        return self.values_list[idx]

    def keys(self) -> list[str]:
        return list(self.keys_list)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except Exception:
            return default

    def items(self):
        return list(zip(self.keys_list, self.values_list))

    def __iter__(self):
        return iter(self.items())

    def __len__(self) -> int:
        return len(self.values_list)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.items())


def _translate_qmark_sql(sql: str, params: Iterable[Any] | dict[str, Any] | None) -> tuple[str, dict[str, Any] | tuple[Any, ...]]:
    if params is None:
        return sql, {}
    if isinstance(params, dict):
        return sql, params

    values = list(params)
    if "?" not in sql:
        return sql, tuple(values)

    chunks = sql.split("?")
    translated: list[str] = [chunks[0]]
    bind: dict[str, Any] = {}
    for idx, chunk in enumerate(chunks[1:]):
        key = f"p{idx}"
        translated.append(f":{key}")
        translated.append(chunk)
        if idx < len(values):
            bind[key] = values[idx]
    return "".join(translated), bind


@lru_cache(maxsize=8)
def _engine_for(database_url: str):
    return create_engine(database_url, pool_pre_ping=True, future=True)


class CompatCursor:
    def __init__(self, connection: "CompatConnection"):
        self._connection = connection
        self._rows: list[CompatRow] = []
        self._index = 0
        self.rowcount = -1
        self._last_result = None

    def execute(self, sql: str, params: Iterable[Any] | dict[str, Any] | None = None):
        if self._connection.backend == "sqlite":
            bind = params if isinstance(params, dict) else tuple(params or ())  # type: ignore[arg-type]
            cursor = self._connection._raw.execute(sql, bind)
            keys = [desc[0] for desc in cursor.description] if cursor.description else []
            self._rows = [CompatRow(keys, list(row)) for row in cursor.fetchall()] if keys else []
            self.rowcount = cursor.rowcount
            self._index = 0
            self._last_result = cursor
            return self

        translated_sql, bind = _translate_qmark_sql(sql, params)
        result = self._connection._conn.execute(text(translated_sql), bind)  # type: ignore[arg-type]
        keys = list(result.keys()) if result.returns_rows else []
        self._rows = [CompatRow(keys, list(row)) for row in result.fetchall()] if keys else []
        self.rowcount = result.rowcount
        self._index = 0
        self._last_result = result
        return self

    def fetchone(self) -> CompatRow | None:
        if self._index >= len(self._rows):
            return None
        row = self._rows[self._index]
        self._index += 1
        return row

    def fetchall(self) -> list[CompatRow]:
        if self._index >= len(self._rows):
            return []
        remaining = self._rows[self._index :]
        self._index = len(self._rows)
        return remaining


class CompatConnection:
    def __init__(self, database_url: str | None = None, timeout: int = 30):
        self.database_url = database_url or database_uri()
        self.backend = database_backend(self.database_url)
        self._raw = None
        self._engine = None
        self._conn = None
        self._transaction = None

        if self.backend == "sqlite":
            sqlite_path = sqlite_path_from_uri(self.database_url)
            if sqlite_path is None:
                sqlite_path = Path(self.database_url.removeprefix("sqlite:///"))
            self._raw = sqlite3.connect(str(sqlite_path), timeout=timeout)
        else:
            self._engine = _engine_for(self.database_url)
            self._conn = self._engine.connect()
            self._transaction = self._conn.begin()

    def cursor(self) -> CompatCursor:
        return CompatCursor(self)

    def execute(self, sql: str, params: Iterable[Any] | dict[str, Any] | None = None):
        return self.cursor().execute(sql, params)

    def executescript(self, script: str):
        statements = [statement.strip() for statement in script.split(";") if statement.strip()]
        for statement in statements:
            self.execute(statement)
        return self

    def commit(self) -> None:
        if self.backend == "sqlite":
            assert self._raw is not None
            self._raw.commit()
            return
        if self._conn is not None and self._transaction is not None:
            self._transaction.commit()
            self._transaction = self._conn.begin()

    def rollback(self) -> None:
        if self.backend == "sqlite":
            assert self._raw is not None
            self._raw.rollback()
            return
        if self._conn is not None and self._transaction is not None:
            self._transaction.rollback()
            self._transaction = self._conn.begin()

    def close(self) -> None:
        if self.backend == "sqlite":
            if self._raw is not None:
                self._raw.close()
            return
        if self._transaction is not None:
            try:
                self._transaction.commit()
            except Exception:
                try:
                    self._transaction.rollback()
                except Exception:
                    pass
        if self._conn is not None:
            self._conn.close()

    def __enter__(self) -> "CompatConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()
        return False


def connect_dashboard_db(database_url: str | None = None, timeout: int = 30) -> CompatConnection:
    return CompatConnection(database_url=database_url, timeout=timeout)
