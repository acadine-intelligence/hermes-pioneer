"""Plain-text and Markdown views. Used by tools, /pioneer and the CLI."""

from __future__ import annotations

from typing import Any

BADGE = {"pioneer": "PIONEER", "iterate": "iterate", "beat": "beat", "unchecked": "unchecked",
         "park": "park", "adopt": "use existing"}


def _n(value: Any) -> str:
    return "-" if value is None else str(value)


def _cell(text: Any) -> str:
    return str(text or "").replace("|", "/").replace("\n", " ")


def board(b: dict) -> str:
    """The ranked list as a Markdown table. Unmeasured scores show as "-", never as 0."""
    gaps = b["gaps"]
    if not gaps:
        return f"Pioneer round {b['round']}: no gaps yet. Scout, then submit gaps."
    judged = any(g.get("judge_exists") is not None for g in gaps)
    head = ["#", "Gap", "Verdict", "Score", "Need", "Orig", "Cfact", "Value", "Dur"] + (["Judge"] if judged else [])
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
    for i, g in enumerate(gaps, 1):
        row = [str(i), f"{_cell(g['title'])} ({g['id']})", BADGE.get(g["verdict"], g["verdict"]),
               _n(g["pioneer"]), _n(g["need"]), _n(g["originality"]), _n(g["counterfactual"]),
               _n(g["value"]), _n(g["durability"])]
        if judged:
            row.append(_n(g.get("judge_exists")))
        lines.append("| " + " | ".join(row) + " |")
    notes = []
    for i, g in enumerate(gaps, 1):
        thin = " The absence search was thin, so originality is capped at 60." if g.get("thin_check") else ""
        notes.append(f"{i}. {g['line']}{thin}")
    where = "whole trail" if b["scope"] == "trail" else f"round {b['round']}"
    count = ", ".join(f"{n} {BADGE.get(code, code)}" for code, n in b["counts"].items())
    out = [f"Pioneer board, {where}: {count}", "", *lines, "", *notes, "",
           "Score = need 30, originality 25, counterfactual 20, value 15, durability 10. "
           "Originality comes from the absence check only. \"-\" means not measured yet."]
    if judged:
        out.append(f"Judge ({b['judge']}) = highest probability that an existing tool already does the job.")
    if b["errors"]:
        out.append(f"{len(b['errors'])} searches failed, so coverage has holes: " + "; ".join(b["errors"][:4]))
    return "\n".join(out)


def gap(detail: dict) -> str:
    g = detail["gap"]
    s, v = g["scores"], g["verdict"]
    out = [f"{g['title']} ({g['id']})", g.get("one_line", ""), f"For: {g.get('buyer', '')}",
           f"New part: {g.get('mechanism', '')}", "", f"Verdict: {BADGE.get(v['code'], v['code'])}. {v['line']}",
           f"Score {_n(s['pioneer'])}: need {s['need']}, originality {_n(s['originality'])}, "
           f"counterfactual {_n(s['counterfactual'])}, value {s['value']}, durability {s['durability']}, fit {s['fit']}", ""]
    for dim, r in (g.get("ratings") or {}).items():
        out.append(f"  {dim} {r['n']}/5: {r.get('why', '')}")
    out += ["", "Evidence:"]
    out += [f"  {e['id']} [{e['src']}/{e['kind']}] {e['title']} {e['url']}" for e in detail["evidence"]]
    ab = g.get("absence")
    if ab:
        out += ["", f"Absence check: {len(ab['queries'])} searches, answered by {', '.join(ab['sources_ok']) or 'nothing'}"]
        for c in ab["candidates"]:
            jp = f", judge {c['judge_p']}" if c.get("judge_p") is not None else ""
            out.append(f"  {c['id']} {c.get('ruling') or 'unruled'}{jp}: {c['title']} {c['url']}  {c.get('why', '')}")
    return "\n".join(line for line in out if line is not None)


def setup(report: dict) -> str:
    out = ["Pioneer setup", "", "| Option | Now | Adds | Sends | Cost |", "|---|---|---|---|---|"]
    for o in report["options"]:
        now = str(o["state"]) + ("" if o["ready"] else f" (needs {o['needs']})")
        out.append(f"| {o['title']} (`{o['id']}`) | {now} | {_cell(o['adds'])} | {_cell(o['sends'])} | {_cell(o['cost'])} |")
    out += ["", "Tools your agent can feed Pioneer with:"]
    for c in report["companions"]:
        have = f" You have: {', '.join(c['you_have'])}." if c["you_have"] else ""
        out.append(f"- {c['title']}.{have} {c['use']}")
    if report["recommended"]:
        out += ["", "Recommended for this install:"]
        out += [f"{i}. {r['do']}. {r['why']} How: `{r['how']}`" for i, r in enumerate(report["recommended"], 1)]
    out += ["", "Change a switch: /pioneer enable <id>, /pioneer disable <id>, /pioneer judge off|llm|jev"]
    return "\n".join(out)


def rounds(b: dict) -> str:
    out = ["Pioneer trail"]
    for r in b["rounds"]:
        src = f" from {r['from']}" if r["from"] else ""
        steer = f" steer: {r['steer']}" if r["steer"] else ""
        out.append(f"- {r.get('title') or r['id']} ({r['id']}{src}): {r['gaps']} gaps, {r['signals']} signals, {r['errors']} failed searches.{steer}")
    return "\n".join(out)
