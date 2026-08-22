from pathlib import Path

from core.command_center import CommandCenter
from config.settings import WORKSPACE_ROOT


def test_current_directory():
    center = CommandCenter()

    result = center.process(
        "current directory"
    )

    assert result["success"] is True

    assert (
        Path(result["result"]).resolve()
        == WORKSPACE_ROOT.resolve()
    )


def test_list_files_default():
    center = CommandCenter()

    result = center.process(
        "list files"
    )

    assert result["success"] is True

    assert isinstance(
        result["result"],
        list
    )


def test_read_file():
    WORKSPACE_ROOT.mkdir(
        parents=True,
        exist_ok=True
    )

    test_file = (
        WORKSPACE_ROOT /
        ".sentinel_test.txt"
    )

    test_file.write_text(
        "Sentinel test",
        encoding="utf-8"
    )

    try:
        center = CommandCenter()

        result = center.process(
            "read .sentinel_test.txt"
        )

        assert result["success"] is True

        assert (
            result["result"]
            == "Sentinel test"
        )

    finally:
        test_file.unlink(
            missing_ok=True
        )


def test_workspace_escape_blocked():
    center = CommandCenter()

    result = center.tools.execute(
        "read_file",
        {
            "filename": (
                "../README.md"
            )
        }
    )

    assert result["success"] is False

    assert "outside Sentinel workspace" in (
        result["error"]
    )


def test_missing_parameter():
    center = CommandCenter()

    result = center.tools.execute(
        "read_file",
        {}
    )

    assert result["success"] is False

    assert (
        "Missing required parameter: filename"
        in result["details"]
    )