"""Where Pioneer finds Hermes state and keeps its own.

The only module that imports Hermes. Every import is optional, so the engine runs and tests without
Hermes installed.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

PLUGIN_NAME = "pioneer"


def hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home  # follows the active profile
        return Path(get_hermes_home())
    except Exception:
        return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def data_dir() -> Path:
    try:
        from plugins.plugin_storage import plugin_data_dir
        return Path(plugin_data_dir(PLUGIN_NAME))
    except Exception:
        path = hermes_home() / "plugin-data" / PLUGIN_NAME
        path.mkdir(parents=True, exist_ok=True)
        return path


def secret(name: str) -> str | None:
    """Credentials come through Hermes's secret scope only."""
    try:
        from agent.secret_scope import get_secret
        return get_secret(name) or None
    except Exception:
        return None


def _config() -> dict:
    try:
        try:
            from hermes_cli.config import load_config_readonly as load
        except ImportError:
            from hermes_cli.config import load_config as load
        cfg = load() or {}
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def settings() -> dict:
    entry = (_config().get("plugins") or {}).get("entries", {}).get(PLUGIN_NAME) or {}
    found = entry.get("settings") or entry.get("config") or {}
    return found if isinstance(found, dict) else {}


_FRONT = re.compile(r"^(name|description):\s*(.+)$", re.M)


def _skills(home: Path, cap: int = 1500) -> list[dict]:
    """Name and description of each installed skill. Reads the first 800 bytes of each SKILL.md."""
    out: list[dict] = []
    root = home / "skills"
    if not root.is_dir():
        return out
    for path in sorted(root.rglob("SKILL.md")):
        if len(out) >= cap:
            break
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                head = fh.read(800)
        except OSError:
            continue
        fields = {k: v.strip().strip("\"'") for k, v in _FRONT.findall(head)}
        name = fields.get("name") or path.parent.name
        out.append({"name": name, "what": fields.get("description", "")[:200]})
    return out


_CAT_FIELD = re.compile(r"^(name|repo|description):[ \t]*(.*)$", re.M)


def _catalog(cap: int = 4000) -> list[dict]:
    """The plugin catalog files that ship with this Hermes checkout (public data, read as plain text).
    Empty when the folder is not there."""
    try:
        import hermes_constants
        root = Path(hermes_constants.__file__).resolve().parent / "plugin-catalog"
    except Exception:
        return []
    out: list[dict] = []
    if not root.is_dir():
        return out
    for path in sorted(root.glob("*.yaml"))[:cap]:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                text = fh.read(4000)
        except OSError:
            continue
        fields = dict(_CAT_FIELD.findall(text))
        what = fields.get("description", "").strip()
        if what[:1] in (">", "|"):  # folded block: take the indented lines that follow
            block = text.split("description:", 1)[1].split("\n", 1)[-1]
            lines = []
            for line in block.splitlines():
                if line.strip() and not line.startswith((" ", "\t")):
                    break
                lines.append(line.strip())
            what = " ".join(x for x in lines if x)
        out.append({"name": (fields.get("name") or path.stem).strip("\"' "), "what": what.strip("\"' ")[:300],
                    "url": fields.get("repo", "").strip("\"' ")})
    return out


def inventory() -> dict[str, Any]:
    """What this Hermes install already has. Names only, never values."""
    cfg = _config()
    home = hermes_home()
    mcp = cfg.get("mcp_servers") or {}
    plugins = (cfg.get("plugins") or {}).get("enabled") or []
    return {
        "skills": _skills(home),
        "plugins": [str(p) for p in plugins] if isinstance(plugins, list) else [],
        "mcp_servers": sorted(str(k) for k in mcp) if isinstance(mcp, dict) else [],
        "catalog": _catalog(),
        "keys": {name: bool(secret(name)) for name in ("FIRECRAWL_API_KEY", "TYPESAFE_API_KEY", "GITHUB_TOKEN")},
        "clis": {name: bool(shutil.which(name)) for name in ("git", "gh")},
    }


def build_service(get_config=None, llm=None):
    """One factory for the agent half and the dashboard route, so both read the same settings."""
    from .service import Pioneer

    if get_config is None:
        cfg = settings()
        get_config = lambda key, default=None: cfg.get(key, default)  # noqa: E731
    return Pioneer(hermes_home(), data_dir(), get_config=get_config, secret=secret, llm=llm, inventory=inventory)
