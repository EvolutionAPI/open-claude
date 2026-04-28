"""
Seed script — registers _v2-mock in plugins_installed for Step 2 manual testing.

Run from the workspace root:
    python plugins/_v2-mock/seed-dev.py

This directly inserts a row so the plugin-ui-registry endpoint returns the mock
without going through the full install flow.  Remove the row when Step 3 lands.
"""

import json
import os
import sys
from pathlib import Path

# Allow importing dashboard backend modules
WORKSPACE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(WORKSPACE / "dashboard" / "backend"))

manifest = {
    "schema_version": "2.0",
    "id": "_v2-mock",
    "name": "v2 Mock Plugin",
    "version": "0.1.0",
    "description": "Minimal v2 plugin for host renderer validation.",
    "author": "EvoNexus Engineering",
    "license": "MIT",
    "min_evonexus_version": "0.34.0",
    "tier": "essential",
    "capabilities": ["ui_pages"],
    "ui_entry_points": {
        "pages": [
            {
                "id": "home",
                "label": "Home",
                "path": "home",
                "bundle": "dist/pages/home.js",
                "icon": "Home",
                "order": 1,
                "sidebar_group": "v2-mock-group",
            }
        ],
        "sidebar_groups": [
            {
                "id": "v2-mock-group",
                "label": "v2 Mock",
                "order": 999,
                "collapsible": True,
            }
        ],
    },
}

install_manifest = {"manifest": manifest, "installed_at": "2026-04-27T00:00:00Z"}

# Write .install-manifest.json into the plugin directory
plugin_dir = WORKSPACE / "plugins" / "_v2-mock"
plugin_dir.mkdir(parents=True, exist_ok=True)
(plugin_dir / ".install-manifest.json").write_text(
    json.dumps(install_manifest, indent=2), encoding="utf-8"
)
print(f"Wrote {plugin_dir / '.install-manifest.json'}")

# Insert / replace row in DB
try:
    from db import get_db_engine
    from sqlalchemy import text

    engine = get_db_engine()
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT OR REPLACE INTO plugins_installed
                  (slug, name, version, description, enabled, status,
                   capabilities_disabled, manifest_json)
                VALUES
                  (:slug, :name, :version, :description, 1, 'active',
                   '{}', :manifest_json)
                """
            ),
            {
                "slug": "_v2-mock",
                "name": manifest["name"],
                "version": manifest["version"],
                "description": manifest["description"],
                "manifest_json": json.dumps(manifest),
            },
        )
        conn.commit()
    print("Inserted _v2-mock into plugins_installed (DB).")
except Exception as exc:
    print(f"DB insert skipped (tables may not exist yet): {exc}")
    print("The .install-manifest.json is written — that is enough for the registry.")

print("\nDone. Navigate to /plugins-ui/_v2-mock/home in the dashboard.")
