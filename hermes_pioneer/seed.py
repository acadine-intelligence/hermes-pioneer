"""Build the Seed: what you are working on, read from the workspace, Hermes memory and recent chats.

Everything here is a local read. The Seed goes to the session's own model and nowhere else. Text is
redacted before it is returned, because the model writes public search queries from it.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # Python 3.10
    tomllib = None  # type: ignore[assignment]

_SECRET = re.compile(
    r"sk-[A-Za-z0-9_\-]{16,}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|xox[baprs]-[A-Za-z0-9\-]{10,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}"
    r"|-----BEGIN[^-]+-----[\s\S]*?-----END[^-]+-----"
    r"|\b[0-9a-fA-F]{32,}\b"
)
_ASSIGN = re.compile(r"(?i)\b([A-Z0-9_]*(?:api[_-]?key|token|secret|password|passwd)[A-Z0-9_]*)(\s*[=:]\s*)[\"']?[^\s\"']{8,}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_SKIP_DIRS = {"node_modules", "__pycache__", "dist", "build", "target", "venv", ".venv"}
_UNATTENDED = ("cron", "kanban", "subagent", "batch")


def redact(text: str) -> str:
    text = _SECRET.sub("[secret]", text or "")
    text = _ASSIGN.sub(lambda m: f"{m.group(1)}{m.group(2)}[secret]", text)
    return _EMAIL.sub("[email]", text)


def clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " ..."


def _read(path: Path, limit: int) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return clip(redact(fh.read(limit * 2)), limit)
    except OSError:
        return ""


def _manifests(root: Path) -> list[dict]:
    out: list[dict] = []
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
            deps = list((data.get("dependencies") or {}).keys()) + list((data.get("devDependencies") or {}).keys())
            out.append({"file": "package.json", "name": str(data.get("name", "")),
                        "what": clip(str(data.get("description", "")), 200), "deps": deps[:30]})
        except (OSError, ValueError, AttributeError):
            pass
    for name, table in (("pyproject.toml", "project"), ("Cargo.toml", "package")):
        path = root / name
        if not path.is_file() or tomllib is None:
            continue
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        meta = data.get(table) or {}
        raw = meta.get("dependencies") if table == "project" else data.get("dependencies")
        deps = [re.split(r"[<>=!~\[; ]", str(d), maxsplit=1)[0] for d in (raw or [])]
        out.append({"file": name, "name": str(meta.get("name", "")),
                    "what": clip(str(meta.get("description", "")), 200), "deps": deps[:30]})
    plugin = root / "plugin.yaml"
    if plugin.is_file():
        head = _read(plugin, 1200)
        fields = dict(re.findall(r"^(name|description):\s*(.+)$", head, re.M))
        out.append({"file": "plugin.yaml", "name": fields.get("name", "").strip("\"' "),
                    "what": clip(fields.get("description", "").strip("\"' "), 200), "deps": []})
    return out


def _commits(root: Path) -> list[str]:
    try:
        proc = subprocess.run(["git", "-C", str(root), "log", "-15", "--pretty=%s"],
                              capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    return [clip(redact(line), 110) for line in proc.stdout.splitlines() if line.strip()]


def workspace(cwd: str | None) -> tuple[dict | None, str | None]:
    """Read the project folder. Refuses the home folder and the filesystem root."""
    if not cwd:
        return None, "no workspace folder for this session"
    root = Path(cwd).expanduser()
    try:
        root = root.resolve()
    except OSError:
        return None, "workspace folder cannot be resolved"
    if not root.is_dir():
        return None, "workspace folder does not exist"
    if root == Path.home().resolve() or root.parent == root:
        return None, "workspace is the home folder or the disk root; open a project folder"
    readme = next((p for p in (root / n for n in ("README.md", "README.rst", "README.txt", "README")) if p.is_file()), None)
    rules = next((p for p in (root / n for n in ("AGENTS.md", "CLAUDE.md", ".cursorrules")) if p.is_file()), None)
    try:
        names = sorted(p.name + ("/" if p.is_dir() else "") for p in root.iterdir()
                       if not p.name.startswith(".") and p.name not in _SKIP_DIRS)
    except OSError:
        names = []
    return {
        "name": root.name,
        "path": str(root),
        "readme": _read(readme, 2500) if readme else "",
        "rules": _read(rules, 1200) if rules else "",
        "manifests": _manifests(root),
        "tree": names[:40],
        "recent_commits": _commits(root),
    }, None


def memory(home: Path) -> dict:
    base = home / "memories"
    return {"notes": _read(base / "MEMORY.md", 3500), "user": _read(base / "USER.md", 2500)}


def sessions(home: Path, *, days: float = 14, limit: int = 20, now: float | None = None,
             exclude: str | None = None) -> tuple[list[dict], str | None]:
    """Title and first ask of recent chats. Read-only; skips cron, Kanban and subagent runs."""
    db = home / "state.db"
    if not db.is_file():
        return [], "no chat history found"
    now = now or time.time()
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2.0)
    except sqlite3.Error as exc:
        return [], f"chat history unreadable: {exc}"
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
        act = "COALESCE(last_activity_at, started_at)" if "last_activity_at" in cols else "started_at"
        title = "title" if "title" in cols else "NULL"
        cwd = "cwd" if "cwd" in cols else "NULL"
        where = [f"{act} > ?", "source NOT IN (%s)" % ",".join("?" * len(_UNATTENDED))]
        if "parent_session_id" in cols:
            where.append("parent_session_id IS NULL")
        rows = conn.execute(
            f"SELECT id, {title}, {cwd} FROM sessions WHERE {' AND '.join(where)} ORDER BY {act} DESC LIMIT ?",
            (now - days * 86400, *_UNATTENDED, limit + 1)).fetchall()
        out: list[dict] = []
        for sid, ttl, scwd in rows:
            if sid == exclude or len(out) >= limit:
                continue
            first = conn.execute("SELECT content FROM messages WHERE session_id = ? AND role = 'user' "
                                 "ORDER BY id LIMIT 1", (sid,)).fetchone()
            ask = clip(redact(str(first[0] or "")), 220) if first else ""
            if not ttl:  # untitled rows are mostly automated runs; a chat the user had gets a title
                continue
            out.append({"title": clip(redact(str(ttl or "")), 90), "ask": ask,
                        "folder": Path(str(scwd)).name if scwd else ""})
        return out, None
    except sqlite3.Error as exc:
        return [], f"chat history unreadable: {exc}"
    finally:
        conn.close()


def build(home: Path, cwd: str | None, inventory: dict, *, use_workspace: bool = True, use_memory: bool = True,
          use_sessions: bool = True, steer: str = "", parent: dict | None = None,
          exclude_session: str | None = None, now: float | None = None) -> dict[str, Any]:
    seed: dict[str, Any] = {"steer": clip(redact(steer), 400), "omitted": []}
    if parent:
        seed["parent_gap"] = parent
    if use_workspace:
        ws, why = workspace(cwd)
        if ws:
            seed["workspace"] = ws
        else:
            seed["omitted"].append(f"workspace: {why}")
    else:
        seed["omitted"].append("workspace: turned off in settings")
    if use_memory:
        mem = memory(home)
        if mem["notes"] or mem["user"]:
            seed["memory"] = mem
        else:
            seed["omitted"].append("memory: empty")
    else:
        seed["omitted"].append("memory: turned off in settings")
    if use_sessions:
        chats, why = sessions(home, exclude=exclude_session, now=now)
        if chats:
            seed["recent_chats"] = chats
        else:
            seed["omitted"].append(f"recent chats: {why or 'none in the last 14 days'}")
    else:
        seed["omitted"].append("recent chats: turned off in settings")
    skills = [s["name"] for s in inventory.get("skills", [])]
    seed["already_have"] = {
        "skills": skills[:150], "skills_total": len(skills),
        "plugins": inventory.get("plugins", []), "mcp_servers": inventory.get("mcp_servers", []),
    }
    blob = json.dumps(seed, sort_keys=True, ensure_ascii=False)
    seed["digest"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
    return seed
