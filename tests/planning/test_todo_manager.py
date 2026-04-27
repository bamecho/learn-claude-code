import pytest
from src.planning.todo_manager import TodoManager, PLAN_REMINDER_INTERVAL


def test_update_and_render():
    manager = TodoManager()
    manager.update(
        [
            {"content": "Read test", "status": "pending"},
            {"content": "Fix bug", "status": "in_progress", "activeForm": "Fixing the bug"},
        ]
    )
    text = manager.render()
    assert "[ ] Read test" in text
    assert "[>] Fix bug (Fixing the bug)" in text
    assert "(0/2 completed)" in text


def test_update_resets_rounds():
    manager = TodoManager()
    manager.update([{"content": "A", "status": "pending"}])
    for _ in range(PLAN_REMINDER_INTERVAL):
        manager.note_round_without_update()
    assert manager.reminder() is not None
    manager.update([{"content": "B", "status": "pending"}])
    assert manager.reminder() is None


def test_render_completed():
    manager = TodoManager()
    manager.update(
        [
            {"content": "A", "status": "completed"},
            {"content": "B", "status": "completed"},
        ]
    )
    text = manager.render()
    assert "[x] A" in text
    assert "(2/2 completed)" in text


def test_clear_plan():
    manager = TodoManager()
    manager.update([{"content": "A", "status": "pending"}])
    manager.update([])
    text = manager.render()
    assert text == "No session plan yet."


def test_max_items():
    manager = TodoManager()
    items = [{"content": f"item {i}", "status": "pending"} for i in range(13)]
    with pytest.raises(ValueError, match="max 12 items"):
        manager.update(items)


def test_invalid_status():
    manager = TodoManager()
    with pytest.raises(ValueError, match="invalid status"):
        manager.update([{"content": "A", "status": "wrong"}])


def test_status_case_normalization():
    manager = TodoManager()
    manager.update([{"content": "A", "status": "In_Progress"}])
    text = manager.render()
    assert "[>] A" in text
    manager.update([{"content": "B", "status": "COMPLETED"}])
    text = manager.render()
    assert "[x] B" in text


def test_multiple_in_progress():
    manager = TodoManager()
    with pytest.raises(ValueError, match="Only one plan item can be in_progress"):
        manager.update(
            [
                {"content": "A", "status": "in_progress"},
                {"content": "B", "status": "in_progress"},
            ]
        )


def test_empty_content():
    manager = TodoManager()
    with pytest.raises(ValueError, match="content required"):
        manager.update([{"content": "   ", "status": "pending"}])


def test_reminder_at_threshold():
    manager = TodoManager()
    manager.update([{"content": "A", "status": "pending"}])
    for _ in range(PLAN_REMINDER_INTERVAL):
        manager.note_round_without_update()
    reminder = manager.reminder()
    assert reminder is not None
    assert "Refresh your current plan" in reminder


def test_reminder_below_threshold():
    manager = TodoManager()
    manager.update([{"content": "A", "status": "pending"}])
    for _ in range(PLAN_REMINDER_INTERVAL - 1):
        manager.note_round_without_update()
    assert manager.reminder() is None


def test_reminder_no_items():
    manager = TodoManager()
    for _ in range(PLAN_REMINDER_INTERVAL):
        manager.note_round_without_update()
    assert manager.reminder() is None


def test_note_round_increments():
    manager = TodoManager()
    manager.update([{"content": "A", "status": "pending"}])
    for _ in range(PLAN_REMINDER_INTERVAL):
        manager.note_round_without_update()
    assert manager.reminder() is not None
