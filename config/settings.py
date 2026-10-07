import os
import ipaddress
import json
import re
from pathlib import Path
from dataclasses import dataclass, field
from urllib.parse import urlsplit


class RoutingConfigurationError(ValueError):
    code = "invalid_configuration"


def _valid_model_id(model: str) -> bool:
    return len(model) <= 200 and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]*", model) is not None


def _validate_omniroute_url(value: str) -> None:
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname or ""
        loopback = hostname.lower() == "localhost"
        if not loopback:
            try:
                loopback = ipaddress.ip_address(hostname).is_loopback
            except ValueError:
                loopback = False
        valid = parsed.scheme in {"http", "https"} and bool(hostname) and not parsed.username and not parsed.password
        valid = valid and not parsed.query and not parsed.fragment and (parsed.scheme == "https" or loopback)
    except ValueError:
        valid = False
    if not valid:
        raise RoutingConfigurationError(
            "OmniRoute URL must use HTTPS, or HTTP on localhost, and must not contain credentials or query parameters."
        )


@dataclass(frozen=True)
class RoutingSettings:
    """Environment-backed model-routing settings, alongside existing Sentinel config."""

    policy: str = "local"
    omniroute_enabled: bool = False
    base_url: str = "http://127.0.0.1:20128/v1"
    api_key: str | None = field(default=None, repr=False, compare=False)
    remote_models: dict[str, str] = field(default_factory=dict)
    fallback_to_local: bool = True
    data_policy: str = "redact"

    @classmethod
    def from_env(cls, environ=None):
        env = os.environ if environ is None else environ
        policy = env.get("SENTINEL_AI_BACKEND", "local").strip().lower()
        if policy not in {"local", "omniroute", "auto"}:
            raise RoutingConfigurationError(
                "SENTINEL_AI_BACKEND must be local, omniroute, or auto."
            )

        enabled_value = env.get("SENTINEL_OMNIROUTE_ENABLED", "false").strip().lower()
        if enabled_value not in {"true", "false", "1", "0", "yes", "no"}:
            raise RoutingConfigurationError("SENTINEL_OMNIROUTE_ENABLED must be a boolean value.")
        enabled = enabled_value in {"true", "1", "yes"}

        fallback_value = env.get("SENTINEL_OMNIROUTE_FALLBACK_TO_LOCAL", "true").strip().lower()
        if fallback_value not in {"true", "false", "1", "0", "yes", "no"}:
            raise RoutingConfigurationError("SENTINEL_OMNIROUTE_FALLBACK_TO_LOCAL must be a boolean value.")
        fallback = fallback_value in {"true", "1", "yes"}

        base_url = env.get("SENTINEL_OMNIROUTE_BASE_URL", "http://127.0.0.1:20128/v1").strip().rstrip("/")
        _validate_omniroute_url(base_url)

        raw_models = env.get("SENTINEL_OMNIROUTE_MODELS", "{}").strip()
        try:
            remote_models = json.loads(raw_models)
        except (TypeError, json.JSONDecodeError) as error:
            raise RoutingConfigurationError(
                "SENTINEL_OMNIROUTE_MODELS must be a JSON object of task names to model IDs."
            ) from error
        if not isinstance(remote_models, dict) or any(
            not isinstance(task, str) or not isinstance(model, str)
            or not task.strip() or not _valid_model_id(model)
            for task, model in remote_models.items()
        ):
            raise RoutingConfigurationError("SENTINEL_OMNIROUTE_MODELS contains an invalid task or model ID.")

        data_policy = env.get("SENTINEL_OMNIROUTE_DATA_POLICY", "redact").strip().lower()
        if data_policy not in {"deny", "redact", "allow"}:
            raise RoutingConfigurationError("SENTINEL_OMNIROUTE_DATA_POLICY must be deny, redact, or allow.")

        return cls(
            policy=policy,
            omniroute_enabled=enabled,
            base_url=base_url,
            api_key=env.get("SENTINEL_OMNIROUTE_API_KEY") or None,
            remote_models={task.strip().lower(): model for task, model in remote_models.items()},
            fallback_to_local=fallback,
            data_policy=data_policy,
        )


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
