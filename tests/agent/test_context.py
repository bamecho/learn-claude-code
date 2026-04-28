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

    def test_preview_is_first_2000_chars(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = PersistedOutputManager(output_dir=tmpdir, threshold=10)
            content = "b" * 3000
            result = mgr.maybe_persist("id2", content)
            assert result.preview == "b" * 2000

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
        long_text = "a" * 200
        msgs = [
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "a", "content": long_text}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "b", "content": long_text}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "c", "content": long_text}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "d", "content": long_text}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "e", "content": long_text}
            ]},
        ]
        MicroCompactor.apply(msgs)
        assert msgs[0]["content"][0]["content"] == "(... older tool output omitted)"
        assert msgs[1]["content"][0]["content"] == "(... older tool output omitted)"
        assert msgs[2]["content"][0]["content"] == long_text
        assert msgs[3]["content"][0]["content"] == long_text
        assert msgs[4]["content"][0]["content"] == long_text

    def test_idempotent(self):
        long_text = "a" * 200
        msgs = [
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "a", "content": long_text}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "b", "content": long_text}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "c", "content": long_text}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "d", "content": long_text}
            ]},
        ]
        MicroCompactor.apply(msgs)
        first = msgs[0]["content"][0]["content"]
        assert first == "(... older tool output omitted)"
        MicroCompactor.apply(msgs)
        assert msgs[0]["content"][0]["content"] == first

    def test_mixed_content_blocks(self):
        long_text = "a" * 200
        msgs = [
            {"role": "user", "content": [
                {"type": "text", "text": "hello"},
                {"type": "tool_result", "tool_use_id": "a", "content": long_text}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "b", "content": long_text}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "c", "content": long_text}
            ]},
            {"role": "user", "content": [
                {"type": "text", "text": "world"},
                {"type": "tool_result", "tool_use_id": "d", "content": long_text}
            ]},
        ]
        MicroCompactor.apply(msgs)
        assert msgs[0]["content"][0]["text"] == "hello"
        assert msgs[0]["content"][1]["content"] == "(... older tool output omitted)"
        assert msgs[1]["content"][0]["content"] == long_text
        assert msgs[2]["content"][0]["content"] == long_text
        assert msgs[3]["content"][0]["text"] == "world"
        assert msgs[3]["content"][1]["content"] == long_text

    def test_string_content_skipped(self):
        long_text = "a" * 200
        msgs = [
            {"role": "user", "content": "plain string"},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "a", "content": long_text}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "b", "content": long_text}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "c", "content": long_text}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "d", "content": long_text}
            ]},
        ]
        MicroCompactor.apply(msgs)
        assert msgs[0]["content"] == "plain string"
        assert msgs[1]["content"][0]["content"] == "(... older tool output omitted)"
        assert msgs[2]["content"][0]["content"] == long_text
        assert msgs[3]["content"][0]["content"] == long_text
        assert msgs[4]["content"][0]["content"] == long_text

    def test_short_tool_results_left_untouched(self):
        msgs = [
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "a", "content": "short"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "b", "content": "x"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "c", "content": "also short"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "d", "content": "y"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "e", "content": "still short"}
            ]},
        ]
        MicroCompactor.apply(msgs)
        assert msgs[0]["content"][0]["content"] == "short"
        assert msgs[1]["content"][0]["content"] == "x"
        assert msgs[2]["content"][0]["content"] == "also short"
        assert msgs[3]["content"][0]["content"] == "y"
        assert msgs[4]["content"][0]["content"] == "still short"

    def test_long_tool_results_replaced_short_kept(self):
        long_text = "a" * 200
        msgs = [
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "a", "content": long_text}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "b", "content": "short"}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "c", "content": long_text}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "d", "content": long_text}
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "e", "content": long_text}
            ]},
        ]
        MicroCompactor.apply(msgs)
        assert msgs[0]["content"][0]["content"] == "(... older tool output omitted)"
        assert msgs[1]["content"][0]["content"] == "short"  # <= 120 chars
        assert msgs[2]["content"][0]["content"] == long_text
        assert msgs[3]["content"][0]["content"] == long_text
        assert msgs[4]["content"][0]["content"] == long_text


from unittest.mock import MagicMock
from src.agent.context import HistoryCompactor, track_recent_file, CompactState


class TestTrackRecentFile:
    def test_adds_file_and_caps_at_five(self):
        state = CompactState()
        for i in range(7):
            track_recent_file(state, f"file{i}.py")
        assert state.recent_files == [
            "file2.py", "file3.py", "file4.py", "file5.py", "file6.py"
        ]

    def test_moves_existing_file_to_end(self):
        state = CompactState()
        track_recent_file(state, "a.py")
        track_recent_file(state, "b.py")
        track_recent_file(state, "a.py")
        assert state.recent_files == ["b.py", "a.py"]


class TestHistoryCompactor:
    def test_estimate_context_size(self):
        msgs = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
        size = HistoryCompactor.estimate_context_size(msgs)
        assert size == len(str(msgs))

    def test_write_transcript_creates_jsonl(self, tmp_path):
        import json
        orig_dir = HistoryCompactor.TRANSCRIPT_DIR
        HistoryCompactor.TRANSCRIPT_DIR = tmp_path / ".transcripts"
        try:
            msgs = [{"role": "user", "content": "test"}]
            path = HistoryCompactor.write_transcript(msgs)
            assert path.exists()
            lines = path.read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) == 1
            assert json.loads(lines[0]) == msgs[0]
        finally:
            HistoryCompactor.TRANSCRIPT_DIR = orig_dir

    def test_summarize_history_extracts_text(self):
        provider = MagicMock()
        provider.chat.return_value = MagicMock(
            content=[MagicMock(type="text", text="Summary text.")]
        )
        result = HistoryCompactor.summarize_history(provider, [])
        assert result == "Summary text."
        call_args = provider.chat.call_args
        assert call_args.kwargs["max_tokens"] == 2000

    def test_compact_history_replaces_messages(self):
        provider = MagicMock()
        provider.chat.return_value = MagicMock(
            content=[MagicMock(type="text", text="Compact summary.")]
        )
        state = CompactState()
        state.recent_files = ["main.py", "utils.py"]
        msgs = [
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "old"},
        ]
        new_msgs = HistoryCompactor.compact_history(msgs, state, provider, focus="fix bug")
        assert len(new_msgs) == 1
        assert new_msgs[0]["role"] == "user"
        assert "Compact summary." in new_msgs[0]["content"]
        assert "fix bug" in new_msgs[0]["content"]
        assert "main.py" in new_msgs[0]["content"]
        assert state.has_compacted is True
        assert state.last_summary.startswith("Compact summary.")
