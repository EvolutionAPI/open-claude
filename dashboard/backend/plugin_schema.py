"""Pydantic v2 schema for plugin.yaml manifest validation."""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

WORKSPACE = Path(__file__).resolve().parent.parent.parent

# Slug: starts and ends with alphanum, interior may have hyphens, 3-64 chars
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")

# Allowed asset extensions for plugin icon / avatar (Wave 2.0).
# SVG is intentionally excluded — XSS surface, no sanitizer in v2.0.
_ALLOWED_ASSET_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp"})

# Hex SHA256 pattern (64 chars)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# Semver: MAJOR.MINOR.PATCH with optional pre-release/build metadata
_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))"
    r"?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)

# Allowed source URL schemes (Vault condition C6)
_ALLOWED_SOURCE_SCHEMES = frozenset({"https"})

# Allowed claude hook events (PRD AC-15)
_VALID_HOOK_EVENTS = frozenset(
    {"PreToolUse", "PostToolUse", "Stop", "SubagentStop"}
)


class Capability(str, Enum):
    """Declared plugin capability enum."""

    agents = "agents"
    skills = "skills"
    rules = "rules"
    heartbeats = "heartbeats"
    sql_migrations = "sql_migrations"
    widgets = "widgets"
    claude_hooks = "claude_hooks"
    readonly_data = "readonly_data"
    # v1a extension — seed host-managed rows on install, tagged with
    # source_plugin so uninstall can clean them without touching user rows.
    goals = "goals"
    tasks = "tasks"
    triggers = "triggers"


class WidgetSpec(BaseModel):
    """Single UI widget declared in plugin.yaml."""

    id: Annotated[str, Field(min_length=1, max_length=100)]
    label: Annotated[str, Field(min_length=1, max_length=200)]
    route: Annotated[str, Field(min_length=1, max_length=500)]
    icon: Optional[str] = None

    @field_validator("id")
    @classmethod
    def id_pattern(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9-]+$", v):
            raise ValueError(f"Widget id '{v}' must match ^[a-z0-9-]+$")
        return v


class ClaudeHookSpec(BaseModel):
    """Single claude hook declaration in plugin.yaml."""

    event: str
    handler_path: str

    @field_validator("event")
    @classmethod
    def event_must_be_valid(cls, v: str) -> str:
        if v not in _VALID_HOOK_EVENTS:
            raise ValueError(
                f"claude_hook event '{v}' not in allowed set: {sorted(_VALID_HOOK_EVENTS)}"
            )
        return v

    @field_validator("handler_path")
    @classmethod
    def handler_path_must_be_safe(cls, v: str) -> str:
        """Vault condition C2: handler_path must not escape plugin directory."""
        # Reject absolute paths and obvious traversal patterns.
        # Full realpath check happens at install time in plugin_loader.py.
        if Path(v).is_absolute():
            raise ValueError(
                f"handler_path '{v}' must be relative (no absolute paths allowed)"
            )
        # Reject sequences that could traverse upward
        parts = Path(v).parts
        depth = 0
        for part in parts:
            if part == "..":
                depth -= 1
                if depth < 0:
                    raise ValueError(
                        f"handler_path '{v}' contains path traversal sequence"
                    )
            else:
                depth += 1
        return v


class ReadonlyQuery(BaseModel):
    """A named read-only SQL query exposed by the plugin."""

    id: Annotated[str, Field(min_length=1, max_length=100)]
    description: Annotated[str, Field(min_length=1, max_length=500)]
    sql: Annotated[str, Field(min_length=1)]

    @field_validator("id")
    @classmethod
    def id_pattern(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9_]+$", v):
            raise ValueError(
                f"ReadonlyQuery id '{v}' must match ^[a-z0-9_]+$"
            )
        return v

    @field_validator("sql")
    @classmethod
    def sql_must_be_readonly(cls, v: str) -> str:
        """Reject obvious write statements (full enforcement in plugin_migrator.py)."""
        stripped = v.strip().upper()
        write_keywords = ("INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "ATTACH")
        for kw in write_keywords:
            if stripped.startswith(kw):
                raise ValueError(
                    f"ReadonlyQuery sql must be SELECT-only; found '{kw}' statement"
                )
        return v


def _validate_asset_path(v: str) -> str:
    """Shared validator for icon / avatar path fields (Wave 2.0).

    Rules (ADR decisions 2, 3, 6):
    - Must be relative (no leading slash)
    - Must not contain path traversal sequences (..)
    - Must start with 'ui/' (ensures serving by existing endpoint)
    - Must use forward slashes only
    - Extension must be in _ALLOWED_ASSET_EXTENSIONS (rejects .svg)
    - External URLs (http/https) are rejected
    """
    if v.startswith(("http://", "https://")):
        raise ValueError(
            f"Asset path '{v}' must be a relative path inside the plugin tarball. "
            "External URLs are not supported in v2.0."
        )
    if v.startswith("/"):
        raise ValueError(f"Asset path '{v}' must be relative (no leading slash).")
    # Reject backslash (Windows-style paths)
    if "\\" in v:
        raise ValueError(f"Asset path '{v}' must use forward slashes only.")
    # Reject traversal sequences
    parts = Path(v).parts
    depth = 0
    for part in parts:
        if part == "..":
            depth -= 1
            if depth < 0:
                raise ValueError(
                    f"Asset path '{v}' contains path traversal sequence '..'."
                )
        else:
            depth += 1
    # Must start with ui/
    if not v.startswith("ui/"):
        raise ValueError(
            f"Asset path '{v}' must start with 'ui/' so it is served by the "
            "existing /plugins/<slug>/ui/<path> endpoint."
        )
    # Extension whitelist
    ext = Path(v).suffix.lower()
    if ext not in _ALLOWED_ASSET_EXTENSIONS:
        raise ValueError(
            f"Asset '{v}' has extension '{ext}' which is not allowed. "
            f"Allowed extensions: {sorted(_ALLOWED_ASSET_EXTENSIONS)}. "
            "SVG is rejected due to XSS risk (see ADR decision 6)."
        )
    return v


class PluginMetadata(BaseModel):
    """Optional visual identity metadata for a plugin (Wave 2.0).

    Declared under ``metadata:`` in plugin.yaml.  All fields are optional
    at the struct level; icon is required when the metadata block is present.
    """

    icon: str
    icon_sha256: Optional[str] = None

    @field_validator("icon")
    @classmethod
    def icon_path_valid(cls, v: str) -> str:
        return _validate_asset_path(v)

    @field_validator("icon_sha256")
    @classmethod
    def icon_sha256_pattern(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not _SHA256_RE.match(v):
            raise ValueError(
                f"icon_sha256 '{v}' must be a 64-character lowercase hex SHA256."
            )
        return v


class PluginAgentEntry(BaseModel):
    """Optional per-agent metadata that enriches the agent scan (Wave 2.0).

    Declared under ``agents:`` in plugin.yaml.  ``file`` is the key used to
    match against the scanned agent .md files in ``agents/`` directory.
    Existence of ``file`` in the tarball is validated at install time (not
    here) to avoid coupling schema to filesystem state.
    """

    file: str
    avatar: Optional[str] = None
    avatar_sha256: Optional[str] = None

    @field_validator("file")
    @classmethod
    def file_path_relative(cls, v: str) -> str:
        """file must be relative and not traverse up."""
        if v.startswith("/"):
            raise ValueError(f"agents[].file '{v}' must be relative.")
        if "\\" in v:
            raise ValueError(f"agents[].file '{v}' must use forward slashes.")
        parts = Path(v).parts
        depth = 0
        for part in parts:
            if part == "..":
                depth -= 1
                if depth < 0:
                    raise ValueError(
                        f"agents[].file '{v}' contains path traversal sequence '..'."
                    )
            else:
                depth += 1
        return v

    @field_validator("avatar")
    @classmethod
    def avatar_path_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_asset_path(v)
        return v

    @field_validator("avatar_sha256")
    @classmethod
    def avatar_sha256_pattern(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not _SHA256_RE.match(v):
            raise ValueError(
                f"avatar_sha256 '{v}' must be a 64-character lowercase hex SHA256."
            )
        return v


class PluginManifest(BaseModel):
    """Full plugin.yaml manifest schema for v1a."""

    # --- Identity ---
    id: Annotated[str, Field(min_length=3, max_length=64)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    version: Annotated[str, Field(min_length=5, max_length=50)]
    description: Annotated[str, Field(min_length=1, max_length=1000)]
    author: Annotated[str, Field(min_length=1, max_length=200)]
    license: Annotated[str, Field(min_length=1, max_length=100)]
    homepage: Optional[str] = None

    # --- Compatibility ---
    min_evonexus_version: Annotated[str, Field(min_length=5, max_length=50)]
    tier: Annotated[str, Field(pattern=r"^essential$")] = "essential"

    # --- Capabilities ---
    capabilities: List[Capability] = Field(default_factory=list)

    # --- Environment variables (Vault condition R2) ---
    env_vars_needed: List[str] = Field(default_factory=list)

    # --- Conflict declarations ---
    conflicts: Dict[str, Any] = Field(default_factory=dict)

    # --- UI extensions (v1a: widgets only) ---
    ui_entry_points: Optional[Dict[str, Any]] = None

    # --- Dependencies (empty in v1a) ---
    dependencies: Dict[str, str] = Field(default_factory=dict)

    # --- Claude hooks (step 8, validated here for schema completeness) ---
    claude_hooks: List[ClaudeHookSpec] = Field(default_factory=list)

    # --- Readonly data queries (step 8+, validated here for completeness) ---
    readonly_data: List[ReadonlyQuery] = Field(default_factory=list)

    # --- Source URL (for remote installs, Vault condition C6) ---
    source_url: Optional[str] = None

    # --- Wave 2.0: Plugin & Agent identity (icon + avatar) ---
    # Both optional — existing plugins without these fields are unaffected.
    metadata: Optional[PluginMetadata] = None
    agents: Optional[List[PluginAgentEntry]] = None

    @field_validator("id")
    @classmethod
    def slug_pattern(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError(
                f"Plugin id '{v}' must match ^[a-z0-9][a-z0-9-]{{1,62}}[a-z0-9]$"
            )
        return v

    @field_validator("version", "min_evonexus_version")
    @classmethod
    def semver_pattern(cls, v: str) -> str:
        if not _SEMVER_RE.match(v):
            raise ValueError(
                f"Version '{v}' must be valid semver (e.g. 1.0.0)"
            )
        return v

    @field_validator("conflicts")
    @classmethod
    def conflicts_values_not_empty(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        for key, val in v.items():
            if val == "" or val is None:
                raise ValueError(
                    f"conflicts entry '{key}' must have a non-empty value"
                )
        return v

    @field_validator("source_url")
    @classmethod
    def source_url_scheme(cls, v: Optional[str]) -> Optional[str]:
        """Vault condition C6: only https:// source URLs allowed."""
        if v is None:
            return v
        from urllib.parse import urlparse
        parsed = urlparse(v)
        if parsed.scheme not in _ALLOWED_SOURCE_SCHEMES:
            raise ValueError(
                f"source_url scheme '{parsed.scheme}' not allowed. "
                f"Only {sorted(_ALLOWED_SOURCE_SCHEMES)} permitted."
            )
        return v

    @model_validator(mode="after")
    def tier_must_be_essential_in_v1a(self) -> "PluginManifest":
        if self.tier != "essential":
            raise ValueError("v1a only supports tier='essential'")
        return self

    @model_validator(mode="after")
    def readonly_queries_use_slug_prefix(self) -> "PluginManifest":
        """ADR-4 / Vault F8: SQL queries must only reference {slug_under}_* tables.

        Extracts table names after FROM/JOIN keywords and rejects any that do not
        start with the plugin's slug prefix (hyphens replaced with underscores).
        """
        if not self.readonly_data:
            return self
        slug_under = self.id.replace("-", "_") + "_"
        # Regex: capture identifier after FROM or JOIN (ignoring subqueries / CTEs)
        _TABLE_RE = re.compile(
            r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
            re.IGNORECASE,
        )
        for query in self.readonly_data:
            tables = _TABLE_RE.findall(query.sql)
            for table in tables:
                if not table.lower().startswith(slug_under):
                    raise ValueError(
                        f"ReadonlyQuery '{query.id}' references table '{table}' "
                        f"which does not start with required prefix '{slug_under}'. "
                        "All plugin queries must only access the plugin's own tables."
                    )
        return self

def load_plugin_manifest(plugin_dir: Path) -> PluginManifest:
    """Load and validate plugin.yaml from a plugin directory.

    Args:
        plugin_dir: Path to the installed plugin directory (must contain plugin.yaml).

    Returns:
        Validated PluginManifest instance.

    Raises:
        FileNotFoundError: If plugin.yaml does not exist.
        pydantic.ValidationError: If the manifest is invalid.
    """
    import yaml

    manifest_path = plugin_dir / "plugin.yaml"
    if not manifest_path.exists():
        raise FileNotFoundError(f"plugin.yaml not found in {plugin_dir}")

    with open(manifest_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    return PluginManifest.model_validate(raw)
