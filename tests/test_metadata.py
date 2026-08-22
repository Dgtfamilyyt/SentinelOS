from tools.manager import ToolManager


def test_tool_metadata():

    manager = ToolManager()
    manager.discover()

    tools = list(manager.all())

    assert len(tools) > 0

    for tool in tools:

        metadata = tool.info()

        assert "name" in metadata
        assert "description" in metadata
        assert "category" in metadata
        assert "parameters" in metadata

        assert metadata["name"]
        assert metadata["description"]
        assert metadata["category"]