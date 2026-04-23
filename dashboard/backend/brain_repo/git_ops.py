"""Brain Repo — Git operations wrapper via subprocess."""

import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 60  # seconds


def _masked_url(url: str, token: str) -> str:
    """Replace token in URL with *** for safe logging."""
    if not token:
        return url
    return url.replace(token, "***")


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = DEFAULT_TIMEOUT) -> subprocess.CompletedProcess:
    """Run a git subprocess, capturing stdout/stderr, with a timeout."""
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def clone(url: str, token: str, target: Path) -> None:
    """Clone a repository using a token-embedded HTTPS URL.

    The token is injected into the URL as ``https://<token>@github.com/...``.
    The token is never logged.
    """
    # Build authenticated URL — replace 'https://' with 'https://<token>@'
    if token and "://" in url:
        scheme, rest = url.split("://", 1)
        auth_url = f"{scheme}://{token}@{rest}"
    else:
        auth_url = url

    safe_url = _masked_url(auth_url, token)
    log.info("Cloning %s → %s", safe_url, target)

    result = _run(["git", "clone", auth_url, str(target)])
    if result.returncode != 0:
        raise RuntimeError(
            f"git clone failed (exit {result.returncode}): {result.stderr[:500]}"
        )


def commit_all(repo_dir: Path, message: str) -> bool:
    """Stage all changes and commit.

    Returns False if there was nothing to commit (git exits 1 with no staged
    changes), True on success, raises RuntimeError on other failures.
    """
    add_result = _run(["git", "add", "-A"], cwd=repo_dir)
    if add_result.returncode != 0:
        raise RuntimeError(f"git add -A failed: {add_result.stderr[:500]}")

    commit_result = _run(["git", "commit", "-m", message], cwd=repo_dir)
    if commit_result.returncode == 0:
        return True
    # Exit code 1 with "nothing to commit" message → no-op, not an error
    stderr_lower = commit_result.stderr.lower() + commit_result.stdout.lower()
    if "nothing to commit" in stderr_lower or "nothing added to commit" in stderr_lower:
        log.debug("git commit: nothing to commit in %s", repo_dir)
        return False
    raise RuntimeError(f"git commit failed: {commit_result.stderr[:500]}")


def push(repo_dir: Path, token: str) -> bool:
    """Push the current branch to origin.

    Injects the token into the remote URL for authentication.
    Returns False on failure (never raises).
    """
    try:
        # Retrieve current remote URL to build authenticated version
        remote_result = _run(["git", "remote", "get-url", "origin"], cwd=repo_dir)
        if remote_result.returncode != 0:
            log.warning("push: could not get remote URL: %s", remote_result.stderr[:200])
            return False

        remote_url = remote_result.stdout.strip()
        if token and "://" in remote_url:
            scheme, rest = remote_url.split("://", 1)
            # Strip existing credentials if any
            if "@" in rest:
                rest = rest.split("@", 1)[1]
            auth_url = f"{scheme}://{token}@{rest}"
        else:
            auth_url = remote_url

        result = _run(["git", "push", auth_url, "--porcelain"], cwd=repo_dir)
        if result.returncode != 0:
            log.warning("git push failed (exit %d)", result.returncode)
            return False
        return True
    except Exception as exc:
        log.warning("git push raised exception: %s", exc)
        return False


def pull_rebase(repo_dir: Path, token: str) -> bool:
    """Pull with rebase from origin.

    Returns False on failure (never raises).
    """
    try:
        remote_result = _run(["git", "remote", "get-url", "origin"], cwd=repo_dir)
        if remote_result.returncode != 0:
            log.warning("pull_rebase: could not get remote URL")
            return False

        remote_url = remote_result.stdout.strip()
        if token and "://" in remote_url:
            scheme, rest = remote_url.split("://", 1)
            if "@" in rest:
                rest = rest.split("@", 1)[1]
            auth_url = f"{scheme}://{token}@{rest}"
        else:
            auth_url = remote_url

        result = _run(["git", "pull", "--rebase", auth_url], cwd=repo_dir)
        if result.returncode != 0:
            log.warning("git pull --rebase failed (exit %d)", result.returncode)
            return False
        return True
    except Exception as exc:
        log.warning("git pull_rebase raised exception: %s", exc)
        return False


def create_tag(repo_dir: Path, tag: str, message: str) -> bool:
    """Create an annotated tag.

    Returns False on failure (never raises).
    """
    try:
        result = _run(["git", "tag", "-a", tag, "-m", message], cwd=repo_dir)
        if result.returncode != 0:
            log.warning("git tag %s failed: %s", tag, result.stderr[:200])
            return False
        return True
    except Exception as exc:
        log.warning("git create_tag raised exception: %s", exc)
        return False


def checkout_ref(repo_dir: Path, ref: str, target_dir: Path) -> None:
    """Extract a ref to target_dir via git archive | tar.

    Uses ``git archive <ref> | tar -x -C <target_dir>`` semantics.
    target_dir is created if it does not exist.
    """
    target_dir.mkdir(parents=True, exist_ok=True)

    archive_cmd = ["git", "archive", "--format=tar", ref]
    tar_cmd = ["tar", "-x", "-C", str(target_dir)]

    archive_proc = subprocess.Popen(
        archive_cmd,
        cwd=repo_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    tar_proc = subprocess.Popen(
        tar_cmd,
        stdin=archive_proc.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if archive_proc.stdout:
        archive_proc.stdout.close()

    _, tar_err = tar_proc.communicate(timeout=DEFAULT_TIMEOUT)
    archive_proc.wait(timeout=DEFAULT_TIMEOUT)

    if archive_proc.returncode != 0:
        _, arch_err = archive_proc.communicate()
        raise RuntimeError(f"git archive failed: {arch_err.decode()[:500]}")
    if tar_proc.returncode != 0:
        raise RuntimeError(f"tar extraction failed: {tar_err.decode()[:500]}")
