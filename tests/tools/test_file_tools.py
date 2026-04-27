import os
from pathlib import Path

import pytest

from src.tools.file_tools import safe_path, WORKDIR


def test_safe_path_relative():
    result = safe_path("src/main.py")
    assert result == WORKDIR / "src" / "main.py"


def test_safe_path_subdirectory():
    result = safe_path("deep/nested/file.txt")
    assert result == WORKDIR / "deep" / "nested" / "file.txt"


def test_safe_path_traversal_attack():
    with pytest.raises(ValueError, match="Path escapes workspace"):
        safe_path("../etc/passwd")


def test_safe_path_absolute_outside():
    with pytest.raises(ValueError, match="Path escapes workspace"):
        safe_path("/etc/passwd")
