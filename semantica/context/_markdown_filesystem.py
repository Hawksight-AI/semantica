"""Filesystem safety helpers for human-editable Markdown persistence."""

import os
import stat
from pathlib import Path
from typing import Optional


def is_filesystem_link(path: Path) -> bool:
    """Return whether *path* is a symlink, junction, or Windows reparse point."""
    if path.is_symlink():
        return True

    isjunction = getattr(os.path, "isjunction", None)
    if isjunction is not None and isjunction(path):
        return True

    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except (FileNotFoundError, NotADirectoryError):
        return False

    reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_point)


def find_filesystem_link(path: Path) -> Optional[Path]:
    """Return the first linked component in *path*, including its ancestors."""
    for candidate in (path, *path.parents):
        if is_filesystem_link(candidate):
            return candidate
    return None
