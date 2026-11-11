"""Pioneer: an inverted search. It looks for what does not exist yet and should, for your own work.

Hermes adapter. All logic lives in ``hermes_pioneer`` (stdlib only) so it tests without a running
agent. This module wires it to six tools, the /pioneer command, ``hermes pioneer``, the
``pioneer:run`` skill and one optional weekly automation.
"""

from __future__ import annotations

import json
import logging
import os
import shlex
from pathlib import Path
from typing import Any

try:
    from .hermes_pioneer import host, options, render, render_html
    from .hermes_pioneer.service import Pioneer  # noqa: F401
except ImportError:  # imported as a top-level module (pytest collecting the repo root)
    from hermes_pioneer import host, options, render, render_html  # type: ignore[no-redef]
    from hermes_pioneer.service import Pioneer  # type: ignore[no-redef]  # noqa: F401

logger = logging.getLogger(__name__)

TOOLSET = "pioneer"
_ctx: Any = None
_service: Pioneer | None = None


def service() -> Pioneer:
    global _service
    if _service is None:
        get, llm = None, None
        if _ctx is not None:
            get = lambda key, default=None: _ctx.get_config(key, default)  # noqa: E731
            try:
                llm = _ctx.llm
            except Exception:
                llm = None
        _service = host.build_service(get, llm)
    return _service


def _changed(what: str) -> None:
    """Tell an open Desktop board that the trail moved. A no-op when no Desktop is connected."""
    try:
        from hermes_cli.plugin_events import broadcast_plugin_event
        broadcast_plugin_event(host.PLUGIN_NAME, "trail.updated", {"what": what})
    except Exception:
        logger.debug("pioneer: no desktop event sent", exc_info=True)


def _cwd() -> str | None:
    try:
        if _ctx is not None:
            found = _ctx.session_cwd()
            if found:
                return str(found)
    except Exception:
        logger.debug("pioneer: session cwd unavailable", exc_info=True)
    return os.getcwd()


def _visual(board: dict) -> dict:
    """Write the HTML board and say how to show it. Text surfaces ignore this and print `text`."""
    try:
        path = service().data / "board.html"
        path.write_text(render_html.board(board), encoding="utf-8")
    except OSError:
        return {}
    return {"visual": {"html": str(path), "show": (
        f"On Hermes Desktop, put ::preview{{file=\"{path}\"}} alone on its own line to render the board inline "
        "(buttons included). On every other surface, print `text` as it is.")}}


def _ok(**payload: Any) -> str:
    return json.dumps({"success": True, **payload}, default=str, ensure_ascii=False)


def _err(exc: Exception) -> str:
    return json.dumps({"success": False, "error": str(exc)})


# ---- tools -------------------------------------------------------------------------------------

_RATING = {"type": "object", "properties": {
    "n": {"type": "integer", "minimum": 1, "maximum": 5}, "why": {"type": "string"}}, "required": ["n"]}

SCHEMAS = {
    "pioneer_seed": {
        "name": "pioneer_seed",
        "description": (
            "Start a Pioneer round. Pioneer is an inverted search: it finds what does NOT exist yet and should, "
            "for this user's own work. It is not a tool recommender. This call reads the project folder, Hermes "
            "memory and recent chat titles (local, read-only, redacted) and returns a seed plus the next step. "
            "Use `expand` with a gap id to go one level deeper on an earlier gap. Call it when the user wants "
            "original ideas, asks what to build, asks what is missing, or says pioneer."),
        "parameters": {"type": "object", "properties": {
            "steer": {"type": "string", "description": "What the user wants this round aimed at, in their words"},
            "title": {"type": "string", "description": "A specific name for this round, 3 to 7 plain words. Shown instead of the round id"},
            "expand": {"type": "string", "description": "Gap id from an earlier round, like r1.g2"},
            "path": {"type": "string", "description": "Project folder to read; default is this chat's folder"},
        }, "additionalProperties": False},
    },
    "pioneer_scout": {
        "name": "pioneer_scout",
        "description": (
            "Gather Signals for a round and add them to its ledger. Runs each query on the sources the user "
            "turned on (Hacker News, GitHub repos and refused requests, OpenAlex papers, this Hermes install; "
            "Firecrawl when on). Queries leave this machine: 2 to 5 plain public words each, never names, "
            "companies, paths or private facts. Pass results from your other tools (web search, Reddit, X, "
            "papers) as `signals` so they can be cited. Returns ledger lines with ids."),
        "parameters": {"type": "object", "properties": {
            "run": {"type": "string", "description": "Round id like r1; default is the latest round"},
            "queries": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
            "signals": {"type": "array", "maxItems": 30, "items": {"type": "object", "properties": {
                "title": {"type": "string"}, "url": {"type": "string"}, "text": {"type": "string"},
                "kind": {"type": "string", "enum": ["need", "talk", "refusal", "capability", "supply", "dead", "web"]},
                "source": {"type": "string", "description": "Tool it came from, like web_search"},
                "engagement": {"type": "integer"}, "date": {"type": "string"},
            }, "required": ["title", "url"]}},
        }, "additionalProperties": False},
    },
    "pioneer_submit": {
        "name": "pioneer_submit",
        "description": (
            "Submit the gaps you wrote from the ledger. Code checks every cited Signal id, drops gaps with no "
            "valid evidence, scores and ranks. You rate need, value, counterfactual, durability and fit from "
            "1 to 5. You do not rate originality: only the absence check measures it. Pass an existing gap `id` "
            "to revise that gap."),
        "parameters": {"type": "object", "properties": {
            "run": {"type": "string", "description": "Round id; default is the latest round"},
            "gaps": {"type": "array", "minItems": 1, "maxItems": 12, "items": {"type": "object", "properties": {
                "id": {"type": "string", "description": "Only when revising a gap"},
                "title": {"type": "string"},
                "one_line": {"type": "string", "description": "What it does, in one sentence"},
                "buyer": {"type": "string", "description": "Who it is for"},
                "mechanism": {"type": "string", "description": "What is new in how it does it"},
                "kind": {"type": "string", "enum": ["tool", "product", "service", "workflow", "dataset"]},
                "evidence": {"type": "array", "items": {"type": "string"}, "description": "Signal ids like S12"},
                "ratings": {"type": "object", "properties": {
                    "need": _RATING, "value": _RATING, "counterfactual": _RATING, "durability": _RATING, "fit": _RATING,
                }, "required": ["need", "value", "counterfactual", "durability", "fit"]},
            }, "required": ["title", "one_line", "buyer", "mechanism", "evidence", "ratings"]}},
        }, "required": ["gaps"], "additionalProperties": False},
    },
    "pioneer_absence": {
        "name": "pioneer_absence",
        "description": (
            "The absence check: does this gap already exist? Two calls per gap. First pass `queries` (3 to 6, "
            "the words someone would use to find the product if it existed) to get candidates. Then pass "
            "`rulings` for every candidate (solves, partial or unrelated, with what it actually does) and any "
            "rival you found with other tools under `found`. Code then sets originality and the verdict: "
            "pioneer, iterate, beat, park, or adopt (an existing tool does it and the user should use that)."),
        "parameters": {"type": "object", "properties": {
            "gap": {"type": "string", "description": "Gap id like r1.g2"},
            "queries": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
            "rulings": {"type": "array", "items": {"type": "object", "properties": {
                "id": {"type": "string", "description": "Candidate id like C3"},
                "ruling": {"type": "string", "enum": ["solves", "partial", "unrelated"]},
                "why": {"type": "string"},
            }, "required": ["id", "ruling"]}},
            "found": {"type": "array", "maxItems": 10, "items": {"type": "object", "properties": {
                "name": {"type": "string"}, "url": {"type": "string"}, "what": {"type": "string"},
                "ruling": {"type": "string", "enum": ["solves", "partial", "unrelated"]}, "why": {"type": "string"},
            }, "required": ["name", "ruling"]}},
        }, "required": ["gap"], "additionalProperties": False},
    },
    "pioneer_board": {
        "name": "pioneer_board",
        "description": (
            "The ranked Pioneer list with every score, the verdict for each gap and the nearest existing tool. "
            "Read-only. Returns Markdown plus an HTML board for Hermes Desktop. Pass `gap` for one gap's full "
            "evidence and absence check. Use scope trail for every round."),
        "parameters": {"type": "object", "properties": {
            "run": {"type": "string", "description": "Round id; default is the latest round"},
            "scope": {"type": "string", "enum": ["round", "trail"]},
            "gap": {"type": "string", "description": "Gap id for the detail view"},
        }, "additionalProperties": False},
    },
    "pioneer_setup": {
        "name": "pioneer_setup",
        "description": (
            "Show Pioneer's options (signal sources, the second judge, what the seed reads), their state in this "
            "install, the tools the agent already has that can feed Pioneer, and what to turn on next. "
            "Read-only: only the user changes a switch, with /pioneer enable, /pioneer disable or /pioneer judge."),
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
}


def pioneer_seed(args: dict, **kw: Any) -> str:
    try:
        out = _ok(**service().seed(args.get("path") or _cwd(), steer=str(args.get("steer") or ""),
                                    title=str(args.get("title") or ""),
                                    expand=args.get("expand") or None, session_id=kw.get("session_id")))
        _changed("seed")
        return out
    except Exception as exc:
        logger.debug("pioneer_seed failed", exc_info=True)
        return _err(exc)


def pioneer_scout(args: dict, **kw: Any) -> str:
    try:
        out = _ok(**service().scout(args.get("run"), args.get("queries") or [], args.get("signals")))
        _changed("scout")
        return out
    except Exception as exc:
        logger.debug("pioneer_scout failed", exc_info=True)
        return _err(exc)


def pioneer_submit(args: dict, **kw: Any) -> str:
    try:
        out = _ok(**service().submit(args.get("run"), args.get("gaps")))
        _changed("submit")
        return out
    except Exception as exc:
        logger.debug("pioneer_submit failed", exc_info=True)
        return _err(exc)


def pioneer_absence(args: dict, **kw: Any) -> str:
    try:
        out = _ok(**service().absence(str(args.get("gap") or ""), queries=args.get("queries"),
                                       rulings=args.get("rulings"), found=args.get("found")))
        _changed("absence")
        return out
    except Exception as exc:
        logger.debug("pioneer_absence failed", exc_info=True)
        return _err(exc)


def pioneer_board(args: dict, **kw: Any) -> str:
    try:
        if args.get("gap"):
            detail = service().gap(str(args["gap"]))
            return _ok(gap=detail, text=render.gap(detail))
        b = service().board(args.get("run"), scope=args.get("scope") or "round")
        return _ok(board=b, text=render.board(b), **_visual(b))
    except Exception as exc:
        logger.debug("pioneer_board failed", exc_info=True)
        return _err(exc)


def pioneer_setup(args: dict, **kw: Any) -> str:
    try:
        report = service().setup()
        return _ok(setup=report, text=render.setup(report))
    except Exception as exc:
        logger.debug("pioneer_setup failed", exc_info=True)
        return _err(exc)


HANDLERS = {"pioneer_seed": pioneer_seed, "pioneer_scout": pioneer_scout, "pioneer_submit": pioneer_submit,
            "pioneer_absence": pioneer_absence, "pioneer_board": pioneer_board, "pioneer_setup": pioneer_setup}


# ---- /pioneer ----------------------------------------------------------------------------------

USAGE = """/pioneer                    the ranked board for the latest round
/pioneer trail              every round, ranked together
/pioneer gap <id>           one gap: ratings, evidence, absence check
/pioneer rounds             the rounds and what each one expanded
/pioneer setup              options, what you already have, what to turn on
/pioneer enable <id>        turn a source or seed input on (hn, github, openalex, local, firecrawl, workspace, memory, chats)
/pioneer disable <id>       turn it off
/pioneer judge off|llm|jev  second judge on the absence check
To run a round, ask the agent: "run pioneer" (it loads the pioneer:run skill)."""


def _switch(option_id: str, state: Any) -> str:
    option = next((o for o in options.OPTIONS if o["id"] == option_id), None)
    if option is None or ("choices" in option) != isinstance(state, str):
        return f"No switch named {option_id!r}.\n\n{USAGE}"
    if isinstance(state, str) and state not in option["choices"]:
        return f"{option['title']} takes: {', '.join(option['choices'])}"
    if _ctx is None:
        return "Settings can only be changed inside Hermes."
    _ctx.set_config(option["setting"], state)
    note = ""
    if state and option.get("needs") and not host.secret(option["needs"]):
        note = f" It needs {option['needs']}; until that is set this source reports an error and the round continues."
    if state == "jev" and not host.secret("TYPESAFE_API_KEY"):
        note = " It needs TYPESAFE_API_KEY; until that is set the judge stays off."
    shown = state if isinstance(state, str) else ("on" if state else "off")
    return f"{option['title']}: {shown}.{note}\nSends: {option['sends']}. Cost: {option['cost']}."


def run_command(raw: str) -> str:
    try:
        parts = shlex.split(raw or "")
    except ValueError:
        parts = (raw or "").split()
    verb = parts[0].lower() if parts else "board"
    rest = parts[1:]
    try:
        svc = service()
        if verb in ("board", "list", "show"):
            return render.board(svc.board(rest[0] if rest else None))
        if verb == "trail":
            return render.board(svc.board(scope="trail"))
        if verb == "rounds":
            return render.rounds(svc.board(scope="trail"))
        if verb == "gap" and rest:
            return render.gap(svc.gap(rest[0]))
        if verb in ("setup", "options"):
            return render.setup(svc.setup())
        if verb in ("enable", "disable") and rest:
            return _switch(rest[0].lower(), verb == "enable")
        if verb == "judge" and rest:
            return _switch("judge", rest[0].lower())
        return USAGE
    except (ValueError, LookupError) as exc:
        return f"{exc}\n\n{USAGE}"


def _slash(raw_args: str) -> str:
    return run_command(raw_args)


# ---- CLI ---------------------------------------------------------------------------------------

def _cli_setup(parser) -> None:
    parser.add_argument("args", nargs="*", help="board | trail | gap <id> | rounds | setup | enable <id> | disable <id> | judge <mode>")
    parser.add_argument("--html", action="store_true", help="write the visual board and print its path")
    parser.add_argument("--json", action="store_true", help="print the board as JSON")


def _cli_handler(args) -> int:
    try:
        scope = "trail" if "trail" in (args.args or []) else "round"
        if getattr(args, "html", False):
            print(_visual(service().board(scope=scope)).get("visual", {}).get("html") or "could not write the board")
        elif getattr(args, "json", False):
            print(json.dumps(service().board(scope=scope), indent=2, default=str))
        else:
            print(run_command(" ".join(shlex.quote(a) for a in args.args)))
    except LookupError as exc:
        print(exc)
        return 1
    return 0


# ---- registration ------------------------------------------------------------------------------

def register(ctx) -> None:
    global _ctx, _service
    _ctx, _service = ctx, None
    for name, handler in HANDLERS.items():
        ctx.register_tool(name=name, toolset=TOOLSET, schema=SCHEMAS[name], handler=handler, emoji="🧭")
    ctx.register_command("pioneer", _slash, description="Find what does not exist yet and should",
                         args_hint="[trail|gap <id>|rounds|setup|enable <id>|disable <id>|judge <mode>]")
    ctx.register_cli_command("pioneer", "Find what does not exist yet and should", _cli_setup, _cli_handler,
                             description="Show the Pioneer board, one gap, the trail, or the setup options.")
    ctx.register_skill("run", Path(__file__).parent / "skills" / "run" / "SKILL.md",
                       description="Use when the user wants original ideas for their own work. Runs a Pioneer round.")
    ctx.register_automation_blueprint(
        "weekly", title="Pioneer weekly round",
        description="Once a week, look for what does not exist yet and should, from your project folder and memory.",
        schedule_template="0 9 * * 1",
        prompt_template=("Load the pioneer:run skill and run one Pioneer round on this workspace. Check the top three "
                         "gaps for existing tools. Report the board and say plainly which gaps turned out to exist already."),
        category="weekly", skills=["pioneer:run"], tags=["ideas", "research"])
