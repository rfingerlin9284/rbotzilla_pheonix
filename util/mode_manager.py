"""Runtime mode manager for headless trading operations.

Supported modes:
- PAPER: practice/sandbox APIs with real market data
- LIVE: real-money APIs with real market data (PIN required)
- BACKTEST: historical execution mode only

Only OANDA and Coinbase are managed here.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PIN_REQUIRED = 841921
VALID_MODES = {"PAPER", "LIVE", "BACKTEST"}
VALID_BROKERS = {"oanda", "coinbase"}

_ROOT_DIR = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _ROOT_DIR / "configs" / "runtime_mode.json"
_UPGRADE_TOGGLE = _ROOT_DIR / ".upgrade_toggle"


def _default_state() -> Dict[str, Any]:
    return {
        "mode": "PAPER",
        "headless": True,
        "dashboard_enabled": False,
        "brokers": {
            "oanda": {"enabled": True},
            "coinbase": {"enabled": False},
        },
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "history": [],
    }


def _persist(state: Dict[str, Any]) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    _UPGRADE_TOGGLE.write_text("ON\n" if state["mode"] == "LIVE" else "OFF\n", encoding="utf-8")


def _load_state() -> Dict[str, Any]:
    if not _CONFIG_PATH.exists():
        state = _default_state()
        _persist(state)
        return state

    try:
        state = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        state = _default_state()
        _persist(state)
        return state

    if state.get("mode") not in VALID_MODES:
        state["mode"] = "PAPER"
    if "brokers" not in state:
        state["brokers"] = _default_state()["brokers"]
    for broker in VALID_BROKERS:
        state["brokers"].setdefault(broker, {"enabled": broker == "oanda"})
    state.setdefault("headless", True)
    state.setdefault("dashboard_enabled", False)
    state.setdefault("history", [])
    return state


def get_mode_info() -> Dict[str, Any]:
    state = _load_state()
    mode = state["mode"]
    return {
        "mode": mode,
        "api": mode in {"PAPER", "LIVE"},
        "description": "Three-mode headless runtime (PAPER/LIVE/BACKTEST)",
        "headless": bool(state.get("headless", True)),
        "dashboard_enabled": bool(state.get("dashboard_enabled", False)),
        "brokers": state.get("brokers", {}),
    }


def switch_mode(mode: str, pin: Optional[int] = None, brokers: Optional[List[str]] = None) -> Dict[str, Any]:
    normalized = (mode or "").strip().upper()
    if normalized not in VALID_MODES:
        raise ValueError(f"Invalid mode '{mode}'. Valid modes: {sorted(VALID_MODES)}")
    if normalized == "LIVE" and pin != PIN_REQUIRED:
        raise PermissionError("LIVE mode requires valid PIN")

    state = _load_state()
    previous = state.get("mode")
    state["mode"] = normalized
    state["headless"] = True
    state["dashboard_enabled"] = False

    if brokers:
        requested = {b.strip().lower() for b in brokers}
        invalid = requested - VALID_BROKERS
        if invalid:
            raise ValueError(f"Invalid brokers: {sorted(invalid)}")
        for broker in VALID_BROKERS:
            state["brokers"][broker]["enabled"] = broker in requested

    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    state["history"].append(
        {
            "from": previous,
            "to": normalized,
            "ts": state["last_updated"],
            "brokers": {k: v.get("enabled", False) for k, v in state["brokers"].items()},
        }
    )
    state["history"] = state["history"][-100:]
    _persist(state)
    return {"ok": True, "mode": normalized, "brokers": state["brokers"]}


def set_broker_enabled(broker: str, enabled: bool) -> Dict[str, Any]:
    normalized = broker.strip().lower()
    if normalized not in VALID_BROKERS:
        raise ValueError(f"Unsupported broker '{broker}'")
    state = _load_state()
    state["brokers"][normalized]["enabled"] = bool(enabled)
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    _persist(state)
    return {"ok": True, "broker": normalized, "enabled": bool(enabled)}


def get_connector_environment(connector: str) -> str:
    normalized = connector.strip().lower()
    if normalized not in VALID_BROKERS:
        raise ValueError(f"Unsupported connector '{connector}'")

    mode = _load_state()["mode"]
    if mode == "LIVE":
        return "live"
    if mode == "BACKTEST":
        raise RuntimeError(f"Connector '{connector}' unavailable in BACKTEST mode")
    return "practice" if normalized == "oanda" else "sandbox"


def read_upgrade_toggle() -> bool:
    if not _UPGRADE_TOGGLE.exists():
        return False
    return _UPGRADE_TOGGLE.read_text(encoding="utf-8").strip().upper() == "ON"
