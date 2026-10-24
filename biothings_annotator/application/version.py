"""Resolve a source checkout's version for explicitly local deployments."""

import logging
import os
import subprocess
from pathlib import Path


logger = logging.getLogger(__name__)
SOURCE_ROOT = Path(__file__).resolve().parents[2]


def get_local_git_version() -> str:
    """Snapshot this package's checkout, independent of the launch directory."""
    # Do not let a parent shell's Git overrides select a different checkout/index.
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}

    def git(*arguments: str) -> str:
        return subprocess.run(
            ["git", "--no-optional-locks", "-C", str(SOURCE_ROOT), *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
            env=environment,
        ).stdout.strip()

    try:
        if not (SOURCE_ROOT / ".git").exists():
            return "Unknown"
        commit = git("rev-parse", "HEAD")
        if not commit:
            return "Unknown"
        dirty = bool(git("status", "--porcelain", "--untracked-files=all"))
        return f"{commit}-dirty" if dirty else commit
    except (OSError, subprocess.SubprocessError, UnicodeError):
        logger.warning("Unable to determine the local checkout version", exc_info=True)
        return "Unknown"
