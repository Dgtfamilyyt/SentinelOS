from enum import Enum


class PermissionClass(str, Enum):
    """Execution-risk classification for Sentinel tools."""

    READ_ONLY = "READ_ONLY"
    STATE_CHANGE = "STATE_CHANGE"
    RESTRICTED = "RESTRICTED"


class ExecutionPolicy:
    """Decides which tool permission classes may execute."""

    DEFAULT_ALLOWED = frozenset({
        PermissionClass.READ_ONLY,
        PermissionClass.STATE_CHANGE,
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
