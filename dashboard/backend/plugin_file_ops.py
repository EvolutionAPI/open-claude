"""File operations for plugin install/uninstall.

Handles:
- Copying plugin knowledge-layer files with namespace enforcement (plugin-{slug}-*)
- SHA256 manifest (.install-manifest.json) write and verification
- Rules index marker blocks in .claude/rules/_plugins-index.md
- Reverse (uninstall) removal from manifest

ADR reference: architecture-plugins.md step 4
Plan reference: plan-plugins-v1a.md step 4 (AC8, AC9, AC14, AC23, RF9, R7)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

WORKSPACE = Path(__file__).resolve().parent.parent.parent

# Marker pattern for rules index blocks
_MARKER_START = "<!-- PLUGIN:{slug}:START -->"
_MARKER_END = "<!-- PLUGIN:{slug}:END -->"
_MARKER_BLOCK_RE = re.compile(
    r"<!-- PLUGIN:([^:]+):START -->.+?<!-- PLUGIN:\1:END -->",
    re.DOTALL,
)

RULES_INDEX_PATH = WORKSPACE / ".claude" / "rules" / "_plugins-index.md"

# Manifest filename inside each installed plugin dir
MANIFEST_FILENAME = ".install-manifest.json"


# ---------------------------------------------------------------------------
# SHA256 helpers
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    """Compute SHA256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Namespace enforcement
# ---------------------------------------------------------------------------

def _enforce_namespace(filename: str, slug: str, category: str) -> str:
    """Return the namespaced destination filename.

    For agents/skills/commands/rules, the file must be named `plugin-{slug}-{original}`.
    If already prefixed correctly, returns as-is. Otherwise prepends the prefix.

    Args:
        filename: Source filename (e.g., 'my-agent.md').
        slug: Plugin slug (e.g., 'pm-essentials').
        category: 'agents', 'skills', 'commands', or 'rules'.

    Returns:
        Namespaced filename (e.g., 'plugin-pm-essentials-my-agent.md').
    """
    prefix = f"plugin-{slug}-"
    if filename.startswith(prefix):
        return filename
    return prefix + filename


# ---------------------------------------------------------------------------
# copy_with_manifest
# ---------------------------------------------------------------------------

def copy_with_manifest(
    source_dir: Path,
    dest_dir: Path,
    slug: str,
    category: str,
    manifest_list: List[Dict[str, Any]],
    glob_pattern: str = "*.md",
) -> List[Dict[str, Any]]:
    """Copy files from source_dir to dest_dir with namespace enforcement.

    For each matched file:
    1. Computes SHA256 of source.
    2. Determines namespaced destination filename (plugin-{slug}-*).
    3. Copies to dest_dir.
    4. Appends a record to manifest_list.

    Args:
        source_dir: Directory containing files to copy (e.g., plugin/agents/).
        dest_dir: Destination directory (e.g., .claude/agents/).
        slug: Plugin slug.
        category: Category label for the manifest record (agents, skills, etc.).
        manifest_list: Accumulated list — records are appended in place.
        glob_pattern: Pattern for source files (default '*.md').

    Returns:
        List of newly added manifest records (same objects appended to manifest_list).

    Raises:
        FileNotFoundError: If source_dir does not exist.
        ValueError: If realpath of dest file escapes dest_dir (path traversal guard).
    """
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_root = str(dest_dir.resolve()) + "/"

    added: List[Dict[str, Any]] = []
    for src_file in sorted(source_dir.glob(glob_pattern)):
        if not src_file.is_file():
            continue

        dest_name = _enforce_namespace(src_file.name, slug, category)
        dest_file = dest_dir / dest_name

        # Path traversal guard: realpath must stay inside dest_dir
        real_dest = str(dest_file.resolve())
        if not real_dest.startswith(dest_root):
            raise ValueError(
                f"Path traversal detected: '{dest_name}' resolves outside dest_dir. "
                f"dest={real_dest}, root={dest_root}"
            )

        sha256 = _sha256_file(src_file)
        shutil.copy2(src_file, dest_file)

        record = {
            "src": str(src_file),
            "dest": str(dest_file),
            "sha256": sha256,
            "category": category,
        }
        manifest_list.append(record)
        added.append(record)

        logger.debug("Copied %s → %s (sha256=%s...)", src_file.name, dest_name, sha256[:12])

    return added


# ---------------------------------------------------------------------------
# write_manifest / read_manifest
# ---------------------------------------------------------------------------

def write_manifest(plugin_dir: Path, manifest_data: List[Dict[str, Any]]) -> Path:
    """Write .install-manifest.json to plugin_dir.

    Args:
        plugin_dir: The installed plugin directory.
        manifest_data: List of file records produced by copy_with_manifest().

    Returns:
        Path to the written manifest file.
    """
    manifest_path = plugin_dir / MANIFEST_FILENAME
    payload = {
        "version": 1,
        "files": manifest_data,
    }
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Wrote install manifest: %s (%d files)", manifest_path, len(manifest_data))
    return manifest_path


def read_manifest(plugin_dir: Path) -> Optional[Dict[str, Any]]:
    """Read .install-manifest.json from plugin_dir. Returns None if missing."""
    manifest_path = plugin_dir / MANIFEST_FILENAME
    if not manifest_path.exists():
        return None
    with open(manifest_path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Atomic file write helper (AC33 — TOCTOU prevention)
# ---------------------------------------------------------------------------

def _atomic_write(path: Path, content: str) -> None:
    """Write *content* to *path* atomically using a temp file + os.replace().

    Creates a NamedTemporaryFile in the same directory as *path* so that
    os.replace() is a same-filesystem rename (POSIX: atomic). On failure the
    temporary file is cleaned up before re-raising.

    Args:
        path: Target file path. Parent directory must already exist.
        content: UTF-8 text to write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Rules index (marker-delimited blocks)
# ---------------------------------------------------------------------------

def _build_block(slug: str, rule_filenames: List[str]) -> str:
    """Build a marker-delimited block for the rules index."""
    start = _MARKER_START.format(slug=slug)
    end = _MARKER_END.format(slug=slug)
    inner_lines = "\n".join(
        f"@{fn}" for fn in sorted(rule_filenames)
    )
    return f"{start}\n{inner_lines}\n{end}"


def append_rules_index(slug: str, rule_filenames: List[str]) -> None:
    """Append or replace a plugin's block in _plugins-index.md.

    If a block for this slug already exists, it is replaced (idempotent).
    Other plugins' blocks are preserved.

    Args:
        slug: Plugin slug.
        rule_filenames: List of rule filenames to reference (e.g., ['my-rule.md']).
    """
    RULES_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)

    existing = RULES_INDEX_PATH.read_text(encoding="utf-8") if RULES_INDEX_PATH.exists() else ""

    new_block = _build_block(slug, rule_filenames)

    # Check if block for this slug already exists
    pattern = re.compile(
        rf"<!-- PLUGIN:{re.escape(slug)}:START -->.+?<!-- PLUGIN:{re.escape(slug)}:END -->",
        re.DOTALL,
    )
    if pattern.search(existing):
        # Replace existing block
        updated = pattern.sub(new_block, existing)
    else:
        # Append new block
        sep = "\n" if existing and not existing.endswith("\n") else ""
        updated = existing + sep + new_block + "\n"

    _atomic_write(RULES_INDEX_PATH, updated)
    logger.info("Updated rules index for plugin '%s' (%d rules)", slug, len(rule_filenames))


def remove_rules_index(slug: str) -> None:
    """Remove a plugin's block from _plugins-index.md.

    Preserves other plugins' blocks. No-op if the index file or block doesn't exist.

    Args:
        slug: Plugin slug whose block should be removed.
    """
    if not RULES_INDEX_PATH.exists():
        return

    content = RULES_INDEX_PATH.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"\n?<!-- PLUGIN:{re.escape(slug)}:START -->.+?<!-- PLUGIN:{re.escape(slug)}:END -->\n?",
        re.DOTALL,
    )
    updated = pattern.sub("", content)
    _atomic_write(RULES_INDEX_PATH, updated)
    logger.info("Removed rules index block for plugin '%s'", slug)


# ---------------------------------------------------------------------------
# reverse_remove_from_manifest (uninstall)
# ---------------------------------------------------------------------------

def reverse_remove_from_manifest(manifest_path: Path) -> None:
    """Delete files listed in .install-manifest.json in reverse order.

    Iterates the manifest file list in reverse (last-copied → first), deleting
    each dest file. If a file is already missing, logs a WARNING and continues
    (partial uninstall is safe).

    Args:
        manifest_path: Path to the .install-manifest.json file.

    Raises:
        FileNotFoundError: If manifest_path itself does not exist.
    """
    if not manifest_path.exists():
        raise FileNotFoundError(f"Install manifest not found: {manifest_path}")

    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)

    files = data.get("files", [])
    for record in reversed(files):
        dest = Path(record["dest"])
        if dest.exists():
            dest.unlink()
            logger.debug("Removed %s", dest)
        else:
            logger.warning("File already missing during uninstall (skipping): %s", dest)
