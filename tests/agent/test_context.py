import os
import tempfile
import pytest
from src.agent.context import PersistedOutputManager, MicroCompactor


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
            with open(result.file_path, "r", encoding="utf-8") as f:
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
            with patch("src.agent.context.open", side_effect=OSError("disk full")):
                result = mgr.maybe_persist("id3", "x" * 50)
            assert result is None
            captured = capsys.readouterr()
            assert "failed to persist output" in captured.err


class TestMicroCompactor:
    def test_no_tool_results_unchanged(self):
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        MicroCompactor.apply(msgs)
        assert msgs == [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]

    def test_three_or_fewer_tool_results_unchanged(self):
        msgs = [
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "a", "content": "out1"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "b", "content": "out2"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "c", "content": "out3"}
            ]},
        ]
        MicroCompactor.apply(msgs)
        assert msgs[0]["content"][0]["content"] == "out1"
        assert msgs[1]["content"][0]["content"] == "out2"
        assert msgs[2]["content"][0]["content"] == "out3"

    def test_older_tool_results_replaced(self):
        msgs = [
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "a", "content": "out1"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "b", "content": "out2"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "c", "content": "out3"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "d", "content": "out4"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "e", "content": "out5"}
            ]},
        ]
        MicroCompactor.apply(msgs)
        assert msgs[0]["content"][0]["content"] == "(... older tool output omitted)"
        assert msgs[1]["content"][0]["content"] == "(... older tool output omitted)"
        assert msgs[2]["content"][0]["content"] == "out3"
        assert msgs[3]["content"][0]["content"] == "out4"
        assert msgs[4]["content"][0]["content"] == "out5"

    def test_idempotent(self):
        msgs = [
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "a", "content": "out1"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "b", "content": "out2"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "c", "content": "out3"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "d", "content": "out4"}
            ]},
        ]
        MicroCompactor.apply(msgs)
        first = msgs[0]["content"][0]["content"]
        MicroCompactor.apply(msgs)
        assert msgs[0]["content"][0]["content"] == first
