from enum import Enum


class PermissionClass(str, Enum):
    """Execution-risk classification for Sentinel tools."""

    READ_ONLY    = "READ_ONLY"
    STATE_CHANGE = "STATE_CHANGE"
    RESTRICTED   = "RESTRICTED"   # Shell, port scan, code exec — needs policy unlock
    ELEVATED     = "ELEVATED"     # Destructive / high-impact — needs explicit authorization


class ExecutionPolicy:
    """Decides which tool permission classes may execute."""

    DEFAULT_ALLOWED = frozenset({
        PermissionClass.READ_ONLY,
        PermissionClass.STATE_CHANGE,
    })

    # Agent mode: unlocks RESTRICTED tools (shell, port scan, run_python)
    AGENT_ALLOWED = frozenset({
        PermissionClass.READ_ONLY,
        PermissionClass.STATE_CHANGE,
        PermissionClass.RESTRICTED,
    })

    # Lab mode: unlocks everything including ELEVATED (offensive tools)
    LAB_ALLOWED = frozenset({
        PermissionClass.READ_ONLY,
        PermissionClass.STATE_CHANGE,
        PermissionClass.RESTRICTED,
        PermissionClass.ELEVATED,
    })

    def __init__(self, allowed_permissions=None):
        if allowed_permissions is None:
            allowed_permissions = self.DEFAULT_ALLOWED

        allowed_permissions = frozenset(
            allowed_permissions
        )

        invalid = [
            permission
            for permission in allowed_permissions
            if not isinstance(
                permission,
                PermissionClass
            )
        ]

        if invalid:
            raise ValueError(
                "ExecutionPolicy permissions must use "
                "PermissionClass values"
            )

        self.allowed_permissions = allowed_permissions

    def allows(self, permission):
        if not isinstance(permission, PermissionClass):
            return False

        return permission in self.allowed_permissions

    @staticmethod
    def permission_name(permission):
        if isinstance(permission, PermissionClass):
            return permission.value

        return "UNKNOWN"
