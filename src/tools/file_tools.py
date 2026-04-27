import os
from pathlib import Path

from .base import ToolResult

WORKDIR = Path(os.getcwd()).resolve()


def safe_path(p: str) -> Path:
    """Resolve *p* relative to WORKDIR and enforce workspace boundary."""
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path
