"""Runtime configuration overrides — in-memory, reset on server restart.

Agents call get_agent_model() instead of reading config directly.
The test API can set overrides without a server restart.
"""

import config

# Defaults per agent — matches current production assignments
_DEFAULTS = {
    "hydrogen": config.MODEL_BIG,
    "helium":   config.MODEL_SMALL,
    "lithium":  config.MODEL_SMALL,
    "beryllium": config.MODEL_BIG,
    "boron":    config.MODEL_BIG,
    "carbon":   config.MODEL_SMALL,
}

_overrides: dict[str, str] = {}


def get_agent_model(agent: str) -> str:
    """Return the active model for an agent, respecting any runtime override."""
    return _overrides.get(agent, _DEFAULTS[agent])


def set_agent_model(agent: str, model: str):
    if agent not in _DEFAULTS:
        raise ValueError(f"Unknown agent '{agent}'. Valid: {sorted(_DEFAULTS)}")
    _overrides[agent] = model


def reset_agent_model(agent: str):
    _overrides.pop(agent, None)


def reset_all():
    _overrides.clear()


def get_status() -> dict:
    """Return current effective model for every agent, flagging overrides."""
    return {
        agent: {
            "model": get_agent_model(agent),
            "default": _DEFAULTS[agent],
            "overridden": agent in _overrides,
        }
        for agent in _DEFAULTS
    }
