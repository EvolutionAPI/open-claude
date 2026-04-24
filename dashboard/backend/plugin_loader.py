"""Plugin installer skeleton — validates and previews plugin installs.

Step 2 scope: discover, validate, conflict check, env-var warning, version check,
and preview. Actual install/uninstall (file copy, SQL migration, heartbeat sync)
is wired in later steps.

Vault conditions implemented here:
  C6 — only https:// source URLs (enforced by PluginManifest.source_url validator).
  C7 — tarfile.extractall(filter='data') prevents zip-slip attacks.
"""

from __future__ import annotations

import logging
import re
import shutil
import sqlite3
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from dashboard.backend.plugin_schema import PluginManifest

logger = logging.getLogger(__name__)

WORKSPACE = Path(__file__).resolve().parent.parent.parent
PLUGINS_DIR = WORKSPACE / "plugins"
STAGING_DIR = PLUGINS_DIR / ".staging"

# Scheduler PID file location (ADR-2 — matches scheduler.py:PID_FILE)
SCHEDULER_PID_FILE = WORKSPACE / "ADWs" / "logs" / "scheduler.pid"

# Semver comparison (major.minor.patch only)
_VER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")

# Allowed tarball source URL schemes (Vault C6 — schema-level, also enforced here)
_ALLOWED_SCHEMES = frozenset({"https"})


def _reload_scheduler() -> str | None:
    """Send SIGHUP to the running scheduler to trigger a hot-reload of routines.

    ADR-2: If the scheduler PID file is absent or the process is gone,
    returns an error key to be stored in plugins.last_error — install is NOT
    blocked (AC28).

    Returns:
        None on success, or a string error key on failure.
    """
    import os as _os
    import signal as _signal

    if not SCHEDULER_PID_FILE.exists():
        logger.info("Scheduler PID file not found — marking routine_activation_pending")
        return "routine_activation_pending"

    try:
        pid = int(SCHEDULER_PID_FILE.read_text().strip())
    except (ValueError, OSError) as exc:
        logger.warning("Could not read scheduler PID file: %s", exc)
        return "routine_activation_pending"

    try:
        _os.kill(pid, 0)  # liveness check
    except ProcessLookupError:
        logger.info("Scheduler PID %s is stale — marking routine_activation_pending", pid)
        return "routine_activation_pending"
    except PermissionError:
        logger.warning("No permission to signal scheduler PID %s", pid)
        return "scheduler_permission_denied"

    try:
        _os.kill(pid, _signal.SIGHUP)
        logger.info("SIGHUP sent to scheduler PID %s", pid)
        return None
    except OSError as exc:
        logger.warning("Failed to send SIGHUP to scheduler PID %s: %s", pid, exc)
        return f"sighup_failed:{exc}"


class PluginError(Exception):
    """Base class for plugin operation errors."""


class ConflictError(PluginError):
    """Raised when a plugin slug or namespace already exists."""


class VersionError(PluginError):
    """Raised when plugin requires a newer EvoNexus version."""


def _parse_version(v: str) -> tuple[int, int, int]:
    m = _VER_RE.match(v)
    if not m:
        return (0, 0, 0)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _current_evonexus_version() -> str:
    """Read version from pyproject.toml at workspace root."""
    toml_path = WORKSPACE / "pyproject.toml"
    if not toml_path.exists():
        return "0.0.0"
    for line in toml_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("version") and "=" in line:
            raw = line.split("=", 1)[1].strip().strip('"').strip("'")
            if _VER_RE.match(raw):
                return raw
    return "0.0.0"


def _get_db() -> sqlite3.Connection:
    db_path = WORKSPACE / "dashboard" / "data" / "evonexus.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


class PluginInstaller:
    """Validates a plugin directory and previews what would be installed."""

    def discover(self) -> List[Dict[str, Any]]:
        """Return list of currently installed plugins (stub — populated in step 9)."""
        installed: List[Dict[str, Any]] = []
        if not PLUGINS_DIR.exists():
            return installed
        for d in sorted(PLUGINS_DIR.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                manifest_path = d / "plugin.yaml"
                if manifest_path.exists():
                    try:
                        m = PluginManifest.__config__  # noqa: just trigger import
                    except Exception:
                        pass
                    installed.append({"slug": d.name, "path": str(d)})
        return installed

    def validate(self, plugin_dir: Path) -> PluginManifest:
        """Load and validate plugin.yaml from plugin_dir.

        Args:
            plugin_dir: Directory containing plugin.yaml.

        Returns:
            Validated PluginManifest.

        Raises:
            FileNotFoundError: No plugin.yaml.
            ValidationError: Invalid manifest.
        """
        from dashboard.backend.plugin_schema import load_plugin_manifest
        return load_plugin_manifest(Path(plugin_dir))

    def check_conflicts(self, manifest: PluginManifest) -> None:
        """Raise ConflictError if slug or namespace is already in use.

        Checks:
        1. `plugins/{slug}/` directory already exists.
        2. Any `.claude/agents/plugin-{slug}-*.md` files exist.
        3. DB table `plugins` has a row with this slug (future-safe, table may not exist yet).

        Args:
            manifest: Validated PluginManifest.

        Raises:
            ConflictError: If any conflict is detected.
        """
        slug = manifest.id

        # 1. Filesystem: plugin directory already installed
        plugin_dir = PLUGINS_DIR / slug
        if plugin_dir.exists():
            raise ConflictError(
                f"Plugin directory already exists: {plugin_dir}. "
                "Uninstall first or use update."
            )

        # 2. Namespace: any agent files with this plugin prefix
        agents_dir = WORKSPACE / ".claude" / "agents"
        if agents_dir.exists():
            existing = list(agents_dir.glob(f"plugin-{slug}-*.md"))
            if existing:
                raise ConflictError(
                    f"Plugin namespace collision: found {len(existing)} agent file(s) "
                    f"with prefix 'plugin-{slug}-' in .claude/agents/. "
                    "These may be leftover from a previous install. Remove them first."
                )

        # 3. DB: plugins table (if it exists)
        try:
            conn = _get_db()
            try:
                row = conn.execute(
                    "SELECT id FROM plugins WHERE slug = ? LIMIT 1", (slug,)
                ).fetchone()
                if row:
                    raise ConflictError(
                        f"Plugin '{slug}' is already registered in the database. "
                        "Uninstall first or use update."
                    )
            except sqlite3.OperationalError:
                # Table doesn't exist yet (step 9 creates it) — no conflict
                pass
            finally:
                conn.close()
        except ConflictError:
            raise
        except Exception as exc:
            logger.warning("Could not check DB for plugin conflict: %s", exc)

    def _check_env_vars(self, manifest: PluginManifest) -> List[str]:
        """Return list of missing env vars declared in env_vars_needed.

        AC26: missing env vars are warnings, NOT blockers.
        """
        import os
        missing = [v for v in manifest.env_vars_needed if not os.environ.get(v)]
        if missing:
            logger.warning(
                "Plugin '%s' declares env_vars_needed=%s but these are not set: %s. "
                "Install will proceed but the plugin may not function correctly.",
                manifest.id,
                manifest.env_vars_needed,
                missing,
            )
        return missing

    def _check_version(self, manifest: PluginManifest) -> None:
        """Raise VersionError if current EvoNexus version is too old.

        Args:
            manifest: Validated PluginManifest with min_evonexus_version.

        Raises:
            VersionError: If installed EvoNexus < manifest.min_evonexus_version.
        """
        current = _current_evonexus_version()
        required = manifest.min_evonexus_version
        if _parse_version(current) < _parse_version(required):
            raise VersionError(
                f"Plugin '{manifest.id}' requires EvoNexus >= {required}, "
                f"but installed version is {current}."
            )

    def preview(self, plugin_dir: str | Path) -> Dict[str, Any]:
        """Validate and preview a plugin install without writing anything.

        Args:
            plugin_dir: Path to a local directory containing plugin.yaml,
                        or a string path.

        Returns:
            Dict with keys:
                manifest: serialized PluginManifest
                warnings: list of warning strings
                conflicts: list of conflict error strings (non-empty means blocked)
                version_ok: bool
        """
        plugin_dir = Path(plugin_dir)
        result: Dict[str, Any] = {
            "manifest": None,
            "warnings": [],
            "conflicts": [],
            "version_ok": True,
        }

        # Validate manifest
        try:
            manifest = self.validate(plugin_dir)
        except FileNotFoundError as exc:
            result["conflicts"].append(str(exc))
            return result
        except ValidationError as exc:
            result["conflicts"].append(f"Invalid plugin.yaml: {exc}")
            return result

        result["manifest"] = manifest.model_dump()

        # Conflict check
        try:
            self.check_conflicts(manifest)
        except ConflictError as exc:
            result["conflicts"].append(str(exc))

        # Env vars (warnings only)
        missing_env = self._check_env_vars(manifest)
        for var in missing_env:
            result["warnings"].append(f"Environment variable not set: {var}")

        # Version check
        try:
            self._check_version(manifest)
        except VersionError as exc:
            result["version_ok"] = False
            result["conflicts"].append(str(exc))

        return result

    @staticmethod
    def fetch_from_tarball(url: str, staging_slug: str) -> Path:
        """Download and extract a plugin tarball from a remote URL.

        Vault condition C7: uses tarfile.extractall(filter='data') to prevent
        zip-slip path traversal attacks.

        Args:
            url: HTTPS URL to a .tar.gz plugin archive.
            source_url scheme is already validated by PluginManifest.source_url.
            staging_slug: Unique identifier for the staging directory.

        Returns:
            Path to the extracted plugin directory in .staging/.

        Raises:
            ValueError: If URL scheme is not https.
            RuntimeError: On download or extraction failure.
        """
        from urllib.parse import urlparse
        import urllib.request

        parsed = urlparse(url)
        if parsed.scheme not in _ALLOWED_SCHEMES:
            raise ValueError(
                f"Only https:// URLs are permitted for plugin sources. Got: {url}"
            )

        STAGING_DIR.mkdir(parents=True, exist_ok=True)
        staging_dir = STAGING_DIR / staging_slug

        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        staging_dir.mkdir(parents=True)

        # Download to temp file
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            logger.info("Fetching plugin archive from %s", url)
            urllib.request.urlretrieve(url, tmp_path)  # noqa: S310 — scheme validated above

            # Vault C7: filter='data' strips absolute paths and .. components
            with tarfile.open(tmp_path, "r:gz") as tf:
                tf.extractall(staging_dir, filter="data")  # type: ignore[call-arg]

            logger.info("Extracted plugin archive to %s", staging_dir)
            return staging_dir

        except Exception as exc:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise RuntimeError(f"Failed to fetch/extract plugin from {url}: {exc}") from exc
        finally:
            tmp_path.unlink(missing_ok=True)


class PluginUninstaller:
    """Stubs for uninstall flow (wired up in steps 4+)."""

    def preview(self, slug: str) -> Dict[str, Any]:
        """Return what would be removed for slug."""
        plugin_dir = PLUGINS_DIR / slug
        return {
            "slug": slug,
            "exists": plugin_dir.exists(),
            "path": str(plugin_dir),
        }


class PluginUpdater:
    """Stubs for update flow (wired up in steps 4+)."""

    def preview(self, plugin_dir: str | Path, current_slug: str) -> Dict[str, Any]:
        """Return diff between current install and new plugin_dir."""
        installer = PluginInstaller()
        return installer.preview(plugin_dir)
