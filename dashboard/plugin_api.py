"""Pioneer backend routes for the Desktop page and pane: /api/plugins/pioneer/...

GET /board          every round and every gap, ranked (the whole trail)
GET /gap/{gap_id}   one gap: ratings, evidence, absence check
GET /setup          options, what this install already has, recommendations

Read-only. Rounds are run by the agent through the pioneer tools, and switches are changed by the
user in Settings, so nothing here writes.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter

_LIB = Path(__file__).resolve().parent.parent / "hermes_pioneer"


def _load_lib():
    """Load the plugin's own engine package by path. The dashboard imports this file on its own,
    outside the agent's plugin package, so a relative import has no parent to resolve against."""
    name = "hermes_pioneer_dashboard_lib"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _LIB / "__init__.py",
                                                  submodule_search_locations=[str(_LIB)])
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load pioneer engine from {_LIB}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_load_lib()
from hermes_pioneer_dashboard_lib import host  # noqa: E402

router = APIRouter()


def _svc():
    # Built per request: host paths and settings follow the active profile.
    return host.build_service()


def _wrap(fn) -> dict[str, Any]:
    try:
        return {"ok": True, **fn()}
    except (ValueError, LookupError) as exc:
        return {"ok": False, "error": str(exc)}


@router.get("/board")
async def board() -> dict:
    svc = _svc()
    if not svc.trail.ids():
        return {"ok": True, "empty": True}
    return _wrap(lambda: {"empty": False, "board": svc.board(scope="trail")})


@router.get("/gap/{gap_id}")
async def gap(gap_id: str) -> dict:
    return _wrap(lambda: _svc().gap(gap_id))


@router.get("/setup")
async def setup() -> dict:
    return _wrap(lambda: {"setup": _svc().setup()})
