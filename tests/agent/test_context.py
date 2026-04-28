import os
import tempfile
import pytest
from src.agent.context import PersistedOutputManager


class TestPersistedOutputManager:
    def test_small_content_returns_none(self):
        mgr = PersistedOutputManager()
        result = mgr.maybe_persist("id1", "x" * 100)
        assert result is None

    def test_large_content_persists_and_returns_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = PersistedOutputManager(output_dir=tmpdir, threshold=10)
            content = "a" * 50
            result = mgr.maybe_persist("id1", content)
            assert result is not None
            assert result.tool_use_id == "id1"
            assert result.original_length == 50
            assert os.path.exists(result.file_path)
            with open(result.file_path, "r") as f:
                assert f.read() == content

    def test_preview_is_first_500_chars(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = PersistedOutputManager(output_dir=tmpdir, threshold=10)
            content = "b" * 1000
            result = mgr.maybe_persist("id2", content)
            assert result.preview == "b" * 500

    def test_write_failure_prints_warning(self, capsys):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = PersistedOutputManager(output_dir=tmpdir, threshold=10)
            from unittest.mock import patch
            with patch("builtins.open", side_effect=OSError("disk full")):
                result = mgr.maybe_persist("id3", "x" * 50)
            assert result is None
            captured = capsys.readouterr()
            assert "Warning" in captured.err or "persist" in captured.err
