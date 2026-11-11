"""The visual board: one self-contained HTML file, no external assets, no script.

Hermes Desktop renders it inline in a chat with ``::preview{file="<path>"}``. Colours and font come
from the theme variables the preview frame injects, with fallbacks so the file also reads in a
browser. Buttons use the documented ``data-hermes-send`` attribute: a click sends one plain sentence
to the agent. The board itself never changes state.
"""

from __future__ import annotations

import re
from html import escape
from typing import Any

_SAFE_ID = re.compile(r"r\d{1,6}\.g\d{1,4}")

_CSS = """
:root{--fg:var(--foreground,#e8e8ea);--mut:var(--muted-foreground,#9a9aa3);--acc:var(--accent,#58e6ff);
--line:var(--border,rgba(128,128,128,.28));--surf:var(--card,rgba(128,128,128,.06))}
*{box-sizing:border-box}
.px{display:inline-block;width:620px;min-width:620px;color:var(--fg);font-size:13px;line-height:1.45}
h1{font-size:15px;margin:0 0 2px;font-weight:600;letter-spacing:-.01em}
.sub{color:var(--mut);font-size:12px;margin:0 0 10px}
.top{display:flex;gap:14px;align-items:flex-start;margin-bottom:10px}
svg{flex:none;border:1px solid var(--line);border-radius:10px;background:var(--surf)}
svg text{fill:var(--mut);font-size:9px}
svg .zone{fill:var(--acc);opacity:.13}
svg .dot{fill:var(--acc);animation:pop .5s ease-out both}
svg .dot.dim{fill:var(--mut)}
svg .num{fill:var(--fg);font-size:9px;font-weight:600}
@keyframes pop{from{r:0;opacity:0}}
.key{font-size:12px;color:var(--mut);display:flex;flex-direction:column;gap:5px;padding-top:2px}
.key b{color:var(--fg);font-weight:500}
ol{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:7px}
li{border:1px solid var(--line);border-radius:11px;background:var(--surf);padding:10px 12px;
transition:border-color .15s ease,transform .15s ease}
li:hover{border-color:var(--acc);transform:translateX(2px)}
li.pioneer{border-color:var(--acc)}
.hd{display:flex;align-items:baseline;gap:8px}
.n{color:var(--mut);font-variant-numeric:tabular-nums;flex:none}
.t{flex:1;min-width:0;font-weight:600}
.chip{flex:none;font-size:11px;color:var(--mut);border:1px solid var(--line);border-radius:99px;padding:1px 8px}
.chip.hot{color:#0b0b0f;background:var(--acc);border-color:var(--acc);font-weight:600}
.sc{flex:none;font-weight:600;font-variant-numeric:tabular-nums}
.one{margin:3px 0 0}
.why{color:var(--mut);font-size:12px;margin:3px 0 7px}
.bars{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}
.bar{font-size:11px;color:var(--mut)}
.bar span{float:right;color:var(--fg);font-variant-numeric:tabular-nums}
.bar i{display:block;clear:both;height:4px;border-radius:99px;background:var(--line);overflow:hidden;margin-top:3px}
.bar i b{display:block;height:100%;border-radius:99px;background:var(--acc);animation:grow .8s ease-out}
@keyframes grow{from{width:0}}
.row{display:flex;gap:7px;margin-top:9px;align-items:center}
.row .meta{flex:1;color:var(--mut);font-size:11px}
button{font:inherit;font-size:12px;font-weight:500;border-radius:8px;padding:5px 11px;cursor:pointer;
border:1px solid var(--line);background:transparent;color:var(--fg);
transition:transform .15s ease,border-color .15s ease,box-shadow .15s ease}
button:hover{transform:translateY(-1px);border-color:var(--acc);box-shadow:0 4px 14px -6px var(--acc)}
button:active{transform:translateY(0) scale(.98)}
button.go{background:var(--acc);border-color:var(--acc);color:#0b0b0f}
.foot{color:var(--mut);font-size:11px;margin-top:10px}
"""

_CHIP = {"pioneer": "pioneer", "iterate": "iterate", "beat": "beat it", "unchecked": "not checked",
         "park": "park", "adopt": "use existing"}
_BARS = (("need", "Need"), ("originality", "Original"), ("counterfactual", "Counterfactual"),
         ("value", "Value"), ("durability", "Durable"))


def _bar(label: str, value: Any) -> str:
    shown = "?" if value is None else str(int(value))
    width = 0 if value is None else max(0, min(100, int(value)))
    return f'<div class="bar">{label}<span>{shown}</span><i><b style="width:{width}%"></b></i></div>'


def _chart(gaps: list[dict], win: dict) -> str:
    """Originality across, need up. Unchecked gaps have no originality, so they are not drawn."""
    w, h, pad = 230, 170, 22
    def x(v: float) -> float: return pad + (w - pad - 8) * v / 100
    def y(v: float) -> float: return h - pad - (h - pad - 8) * v / 100
    parts = [f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="Originality against need">',
             f'<rect class="zone" x="{x(win["originality"]):.1f}" y="{y(100):.1f}" '
             f'width="{x(100) - x(win["originality"]):.1f}" height="{y(win["need"]) - y(100):.1f}" rx="4"/>',
             f'<text x="{w / 2:.0f}" y="{h - 6}" text-anchor="middle">originality</text>',
             f'<text x="9" y="{h / 2:.0f}" text-anchor="middle" transform="rotate(-90 9 {h / 2:.0f})">need</text>']
    for i, g in enumerate(gaps, 1):
        if g.get("originality") is None:
            continue
        cx, cy = x(g["originality"]), y(g["need"])
        dim = "" if g["verdict"] in ("pioneer", "iterate", "beat") else " dim"
        parts.append(f'<circle class="dot{dim}" cx="{cx:.1f}" cy="{cy:.1f}" r="8" style="animation-delay:{i * 60}ms"/>'
                     f'<text class="num" x="{cx:.1f}" y="{cy + 3:.1f}" text-anchor="middle">{i}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _buttons(g: dict) -> str:
    gid = g["id"]
    if not _SAFE_ID.fullmatch(gid):
        return ""
    out = []
    if g["verdict"] == "unchecked":
        out.append(f'<button class="go" data-hermes-send="Run the Pioneer absence check on gap {gid}.">Check it exists</button>')
    if g["verdict"] in ("pioneer", "iterate", "beat"):
        out.append(f'<button class="go" data-hermes-send="Expand Pioneer gap {gid} into a new round.">Expand</button>')
    out.append(f'<button data-hermes-send="Show the evidence and the absence check for Pioneer gap {gid}.">Evidence</button>')
    return "".join(out)


def board(b: dict) -> str:
    gaps = b["gaps"]
    where = "whole trail" if b["scope"] == "trail" else f"round {escape(str(b['round']))}"
    counts = ", ".join(f"{n} {_CHIP.get(code, code)}" for code, n in b["counts"].items()) or "no gaps yet"
    unchecked = sum(1 for g in gaps if g.get("originality") is None)
    items = []
    for i, g in enumerate(gaps, 1):
        score = "?" if g["pioneer"] is None else str(g["pioneer"])
        judge = f' · judge {g["judge_exists"]}' if g.get("judge_exists") is not None else ""
        near = g.get("nearest") or {}
        nearest = f' · nearest: {escape(str(near.get("name", ""))[:60])}' if near.get("name") else ""
        thin = " · thin search" if g.get("thin_check") else ""
        hot = " hot" if g["verdict"] == "pioneer" else ""
        items.append(
            f'<li class="{escape(g["verdict"])}"><div class="hd"><span class="n">{i}</span>'
            f'<span class="t">{escape(g["title"])}</span><span class="chip{hot}">{_CHIP.get(g["verdict"], escape(g["verdict"]))}</span>'
            f'<span class="sc">{score}</span></div>'
            f'<p class="one">{escape(g.get("one_line", ""))}</p><p class="why">{escape(g["line"])}</p>'
            f'<div class="bars">{"".join(_bar(label, g.get(key)) for key, label in _BARS)}</div>'
            f'<div class="row"><span class="meta">{g["evidence"]} signals from {len(g["sources"])} sources{judge}{nearest}{thin}</span>'
            f'{_buttons(g)}</div></li>')
    key = ['<div class="key">', "<div><b>Shaded corner</b> = nothing found that does it, and people need it.</div>",
           "<div><b>Original</b> comes from the absence check only.</div>",
           "<div><b>?</b> = not measured yet. Never read it as zero.</div>"]
    if unchecked:
        key.append(f"<div>{unchecked} gaps are not on the chart: no absence check yet.</div>")
    key.append("</div>")
    foot = "Score = need 30, originality 25, counterfactual 20, value 15, durability 10."
    if b["errors"]:
        foot += f" {len(b['errors'])} searches failed, so coverage has holes."
    return (f'<!doctype html><meta charset="utf-8"><style>{_CSS}</style><div class="px">'
            f'<h1>Pioneer board</h1><p class="sub">{where}: {escape(counts)}</p>'
            f'<div class="top">{_chart(gaps, b["win_zone"])}{"".join(key)}</div>'
            f'<ol>{"".join(items)}</ol><p class="foot">{escape(foot)}</p></div>')
