from tools.manager import ToolManager


def test_tool_discovery():

    manager = ToolManager()
    manager.discover()

    names = manager.names()

    assert "current_directory" in names
    assert "list_files" in names
    assert "read_file" in names
    assert "create_folder" in names


def test_current_directory_execution():

    manager = ToolManager()
    manager.discover()

    result = manager.execute(
        "current_directory",
        {}
    )

    assert result["success"] is True