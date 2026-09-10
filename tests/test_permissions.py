import pytest

from tools.base import Tool
from tools.manager import ToolManager
from tools.policy import (
    ExecutionPolicy,
    PermissionClass,
)


class CountingTool(Tool):

    name = "counting_tool"
    description = "Records whether execution occurred."
    category = "test"
    parameters = {}

    def __init__(self, permission=None):
        if permission is not None:
            self.permission = permission

        self.calls = 0

    def execute(self):
        self.calls += 1
        return self.calls


def test_default_policy_preserves_existing_permissions():
    policy = ExecutionPolicy()

    assert policy.allows(
        PermissionClass.READ_ONLY
    )
    assert policy.allows(
        PermissionClass.STATE_CHANGE
    )
    assert not policy.allows(
        PermissionClass.RESTRICTED
    )


def test_filesystem_tools_have_explicit_permissions():
    manager = ToolManager()
    manager.discover()

    permissions = {
        name: manager.get(name).permission
        for name in manager.names()
    }

    assert permissions["current_directory"] == (
        PermissionClass.READ_ONLY
    )
    assert permissions["list_files"] == (
        PermissionClass.READ_ONLY
    )
    assert permissions["read_file"] == (
        PermissionClass.READ_ONLY
    )
    assert permissions["create_folder"] == (
        PermissionClass.STATE_CHANGE
    )


def test_permission_is_exposed_as_metadata():
    tool = CountingTool(
        PermissionClass.READ_ONLY
    )

    assert tool.info()["permission"] == "READ_ONLY"


def test_read_only_policy_blocks_state_change():
    policy = ExecutionPolicy({
        PermissionClass.READ_ONLY
    })
    manager = ToolManager(policy=policy)
    tool = CountingTool(
        PermissionClass.STATE_CHANGE
    )
    manager.registry.register(tool)

    result = manager.execute(tool.name, {})

    assert result == {
        "success": False,
        "tool": "counting_tool",
        "error": "Tool execution denied by policy",
        "permission": "STATE_CHANGE",
    }
    assert tool.calls == 0


def test_unclassified_tool_is_restricted_by_default():
    manager = ToolManager()
    tool = CountingTool()
    manager.registry.register(tool)

    result = manager.execute(tool.name, {})

    assert result["success"] is False
    assert result["permission"] == "RESTRICTED"
    assert tool.calls == 0


def test_default_policy_allows_state_change():
    manager = ToolManager()
    tool = CountingTool(
        PermissionClass.STATE_CHANGE
    )
    manager.registry.register(tool)

    result = manager.execute(tool.name, {})

    assert result["success"] is True
    assert result["result"] == 1
    assert tool.calls == 1


def test_policy_rejects_unknown_permission_values():
    with pytest.raises(ValueError):
        ExecutionPolicy({"READ_ONLY"})
