from pathlib import Path

import pytest

from src.tools.file_tools import safe_path, WORKDIR, ReadFileTool, WriteFileTool, EditFileTool
import src.tools.file_tools as ft


@pytest.fixture(autouse=True)
def patch_workdir(monkeypatch, tmp_path):
    monkeypatch.setattr(ft, "WORKDIR", tmp_path)


def test_safe_path_relative(tmp_path):
    result = safe_path("src/main.py")
    assert result == tmp_path / "src" / "main.py"


def test_safe_path_subdirectory(tmp_path):
    result = safe_path("deep/nested/file.txt")
    assert result == tmp_path / "deep" / "nested" / "file.txt"


def test_safe_path_traversal_attack():
    with pytest.raises(ValueError, match="Path escapes workspace"):
        safe_path("../etc/passwd")


def test_safe_path_absolute_outside():
    with pytest.raises(ValueError, match="Path escapes workspace"):
        safe_path("/etc/passwd")


class TestReadFileTool:
    def test_read_full(self, tmp_path):
        (tmp_path / "hello.txt").write_text("line1\nline2\nline3\n")
        tool = ReadFileTool()
        result = tool.execute("tu_1", {"filePath": "hello.txt"})
        assert result.is_error is False
        assert result.content == "line1\nline2\nline3\n"

    def test_read_range(self, tmp_path):
        (tmp_path / "hello.txt").write_text("a\nb\nc\nd\n")
        tool = ReadFileTool()
        result = tool.execute("tu_1", {"filePath": "hello.txt", "startLine": 2, "endLine": 3})
        assert result.is_error is False
        assert result.content == "b\nc\n"

    def test_read_start_only(self, tmp_path):
        (tmp_path / "hello.txt").write_text("a\nb\nc\n")
        tool = ReadFileTool()
        result = tool.execute("tu_1", {"filePath": "hello.txt", "startLine": 2})
        assert result.is_error is False
        assert result.content == "b\nc\n"

    def test_read_end_only(self, tmp_path):
        (tmp_path / "hello.txt").write_text("a\nb\nc\n")
        tool = ReadFileTool()
        result = tool.execute("tu_1", {"filePath": "hello.txt", "endLine": 2})
        assert result.is_error is False
        assert result.content == "a\nb\n"

    def test_read_not_found(self, tmp_path):
        tool = ReadFileTool()
        result = tool.execute("tu_1", {"filePath": "missing.txt"})
        assert result.is_error is True
        assert "not found" in result.content

    def test_read_out_of_range(self, tmp_path):
        (tmp_path / "hello.txt").write_text("a\n")
        tool = ReadFileTool()
        result = tool.execute("tu_1", {"filePath": "hello.txt", "startLine": 5})
        assert result.is_error is False
        assert result.content == ""

    def test_read_path_escape(self, tmp_path):
        tool = ReadFileTool()
        result = tool.execute("tu_1", {"filePath": "../secret.txt"})
        assert result.is_error is True
        assert "escapes workspace" in result.content

    def test_read_unicode_error(self, tmp_path):
        (tmp_path / "binary.bin").write_bytes(b"\xff\xfe")
        tool = ReadFileTool()
        result = tool.execute("tu_1", {"filePath": "binary.bin"})
        assert result.is_error is True


class TestWriteFileTool:
    def test_write_new_file(self, tmp_path):
        tool = WriteFileTool()
        result = tool.execute("tu_1", {"filePath": "new.txt", "content": "hello"})
        assert result.is_error is False
        assert "Wrote 5 bytes" in result.content
        assert (tmp_path / "new.txt").read_text() == "hello"

    def test_write_overwrite(self, tmp_path):
        (tmp_path / "existing.txt").write_text("old")
        tool = WriteFileTool()
        result = tool.execute("tu_1", {"filePath": "existing.txt", "content": "new"})
        assert result.is_error is False
        assert (tmp_path / "existing.txt").read_text() == "new"

    def test_write_create_nested_dirs(self, tmp_path):
        tool = WriteFileTool()
        result = tool.execute("tu_1", {"filePath": "deep/dir/file.txt", "content": "nested"})
        assert result.is_error is False
        assert (tmp_path / "deep" / "dir" / "file.txt").read_text() == "nested"

    def test_write_path_escape(self, tmp_path):
        tool = WriteFileTool()
        result = tool.execute("tu_1", {"filePath": "../evil.txt", "content": "x"})
        assert result.is_error is True
        assert "escapes workspace" in result.content


class TestEditFileTool:
    def test_edit_success(self, tmp_path):
        (tmp_path / "foo.txt").write_text("hello world")
        tool = EditFileTool()
        result = tool.execute("tu_1", {"filePath": "foo.txt", "oldText": "world", "newText": "python"})
        assert result.is_error is False
        assert "Replaced 1 occurrence" in result.content
        assert (tmp_path / "foo.txt").read_text() == "hello python"

    def test_edit_not_found(self, tmp_path):
        (tmp_path / "foo.txt").write_text("hello world")
        tool = EditFileTool()
        result = tool.execute("tu_1", {"filePath": "foo.txt", "oldText": "missing", "newText": "x"})
        assert result.is_error is True
        assert "not found" in result.content

    def test_edit_multiple_matches(self, tmp_path):
        (tmp_path / "foo.txt").write_text("aaa aaa aaa")
        tool = EditFileTool()
        result = tool.execute("tu_1", {"filePath": "foo.txt", "oldText": "aaa", "newText": "bbb"})
        assert result.is_error is True
        assert "found 3 times" in result.content

    def test_edit_path_escape(self, tmp_path):
        tool = EditFileTool()
        result = tool.execute("tu_1", {"filePath": "../secret.txt", "oldText": "a", "newText": "b"})
        assert result.is_error is True
        assert "escapes workspace" in result.content

    def test_edit_unicode_error(self, tmp_path):
        (tmp_path / "binary.bin").write_bytes(b"\xff\xfe")
        tool = EditFileTool()
        result = tool.execute("tu_1", {"filePath": "binary.bin", "oldText": "a", "newText": "b"})
        assert result.is_error is True
