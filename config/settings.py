import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]

WORKSPACE_ROOT = Path(
    os.getenv(
        "SENTINEL_WORKSPACE_ROOT",
        BASE_DIR / "workspace"
    )
).expanduser().resolve()


GENERAL_MODEL = "qwen3:4b"

CODER_MODEL = (
    "WhiteRabbitNeo/"
    "WhiteRabbitNeo-2.5-Qwen-2.5-Coder-7B:latest"
)

CYBER_MODEL = "CyberCrew/notmythos-8b:latest"

DEEP_MODEL = "qwen3.6:latest"