from pathlib import Path

from config.settings import WORKSPACE_ROOT


def ensure_workspace():
    WORKSPACE_ROOT.mkdir(
        parents=True,
        exist_ok=True
    )


def resolve_workspace_path(user_path="."):
    """
    Resolve a user supplied path while ensuring that it
    remains inside Sentinel's configured workspace.
    """

    ensure_workspace()

    root = WORKSPACE_ROOT.resolve()

    supplied = Path(user_path)

    if supplied.is_absolute():
        candidate = supplied.resolve()
    else:
        candidate = (root / supplied).resolve()

    try:
        candidate.relative_to(root)

    except ValueError:
        raise PermissionError(
            f"Path outside Sentinel workspace is not allowed: "
            f"{user_path}"
        )

    return candidate