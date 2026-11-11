"""Scores and verdicts. The model rates; this file scores, ranks and decides what a rating may do.

Five measures, each 0 to 100:

  need            do people want it? The model's 1-5 rating, cut when fewer than three demand Signals are cited.
  originality     is it absent? Comes ONLY from the absence check. Never from the model's opinion.
  counterfactual  is the world better with it? The 1-5 rating, cut to zero when something already does the job.
  value           is it worth having? The 1-5 rating.
  durability      how long before a substitute appears? The 1-5 rating. A short life is allowed; it is shown.

``fit`` (does it sit on your path) is a filter: it orders ties and flags strays. It is not in the score.
"""

from __future__ import annotations

from typing import Any

from .sources import DEMAND_KINDS

VERSION = "pioneer-score@1"
WEIGHTS = {"need": 30, "originality": 25, "counterfactual": 20, "value": 15, "durability": 10}
RATED = ("need", "value", "counterfactual", "durability", "fit")
RULINGS = {"solves": 1.0, "partial": 0.5, "unrelated": 0.0}
WIN = {"originality": 70, "need": 70, "counterfactual": 50}
PARK_BELOW_NEED = 40
THIN_CAP = 60          # originality ceiling when the absence check searched too little
JUDGE_SOLVES = 0.70    # a second judge at or above this probability counts as "solves"
JUDGE_PARTIAL = 0.50   # below this the judge is undecided or says no, and changes nothing


def rating(value: Any) -> int | None:
    """A 1-5 rating, or None. Accepts 4 or {"n": 4, "why": "..."}."""
    if isinstance(value, dict):
        value = value.get("n")
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
        return None
    return value


def pct(n: int) -> int:
    return (n - 1) * 25


def prob(x: Any) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return float(x) if x == x and 0.0 <= x <= 1.0 else None


def coverage(candidate: dict) -> float:
    """How much of the gap one existing thing covers. A second judge can raise this, never lower it."""
    ruled = RULINGS.get(str(candidate.get("ruling")), 0.0)
    p = prob(candidate.get("judge_p"))
    judged = 1.0 if p is not None and p >= JUDGE_SOLVES else 0.5 if p is not None and p >= JUDGE_PARTIAL else 0.0
    cover = max(ruled, judged)
    # An archived project cannot fully serve anyone. Dead supply with users is an opening, not an answer.
    return min(cover, 0.5) if candidate.get("kind") == "dead" else cover


def absence_result(absence: dict | None) -> dict | None:
    """Originality from the absence check, plus the nearest existing thing."""
    if not absence or not absence.get("ruled"):
        return None
    cands = absence.get("candidates") or []
    def closeness(c: dict) -> tuple:
        # Among equally covering tools, name the one the judge rates closest, then one already
        # installed, then one in the plugin catalog, then the most used.
        meta = c.get("meta") or {}
        local = 2 if meta.get("installed") else 1 if c.get("source") == "local" else 0
        return (prob(c.get("judge_p")) or 0.0, local, c.get("engagement") or 0)
    covered = sorted(((coverage(c), closeness(c), c) for c in cands), key=lambda t: (t[0], t[1]), reverse=True)
    best = covered[0][0] if covered else 0.0
    partials = sum(1 for cov, _, _ in covered if cov == 0.5)
    if best >= 1.0:
        originality = 10
    elif best >= 0.5:
        originality = max(30, 55 - 5 * (partials - 1))
    else:
        originality = 100
    thin = len(absence.get("queries") or []) < 3 or len(absence.get("sources_ok") or []) < 2
    if thin:
        originality = min(originality, THIN_CAP)
    nearest = covered[0][2] if covered and best > 0 else None
    return {"originality": originality, "coverage": best, "thin": thin, "partials": partials,
            "nearest": {"name": nearest.get("title", ""), "url": nearest.get("url", ""),
                        "why": nearest.get("why", ""), "installed": bool((nearest.get("meta") or {}).get("installed"))}
            if nearest else None}


def score_gap(gap: dict, ledger: dict[str, dict]) -> dict:
    """Recompute ``gap['scores']`` and ``gap['verdict']`` in place and return the gap."""
    r = {dim: rating((gap.get("ratings") or {}).get(dim)) or 1 for dim in RATED}
    cited = [ledger[i] for i in gap.get("evidence", []) if i in ledger]
    demand = [s for s in cited if s.get("kind") in DEMAND_KINDS]
    fetched = [s for s in demand if not str(s.get("source", "")).startswith("agent")]
    damp = (0.4, 0.6, 0.8)[len(demand)] if len(demand) < 3 else 1.0
    if demand and not fetched:
        damp *= 0.85  # every demand Signal was supplied by the agent; the plugin fetched none of it
    scores: dict[str, Any] = {
        "need": round(pct(r["need"]) * damp), "value": pct(r["value"]), "durability": pct(r["durability"]),
        "fit": pct(r["fit"]), "originality": None, "counterfactual": None, "pioneer": None,
        "demand_signals": len(demand), "sources": sorted({s.get("source", "") for s in cited}),
    }
    provisional = (scores["need"] * WEIGHTS["need"] + scores["value"] * WEIGHTS["value"]
                   + scores["durability"] * WEIGHTS["durability"])
    scores["provisional"] = round(provisional / (WEIGHTS["need"] + WEIGHTS["value"] + WEIGHTS["durability"]))
    found = absence_result(gap.get("absence"))
    if found:
        scores["originality"] = found["originality"]
        scores["counterfactual"] = round(pct(r["counterfactual"]) * (1 - found["coverage"]))
        scores["pioneer"] = round(sum(scores[k] * w for k, w in WEIGHTS.items()) / 100)
        scores["thin_check"] = found["thin"]
        judged = [prob(c.get("judge_p")) for c in gap["absence"].get("candidates", [])]
        judged = [p for p in judged if p is not None]
        scores["judge_exists"] = round(max(judged), 2) if judged else None
    gap["scores"] = scores
    gap["verdict"] = verdict(scores, found)
    return gap


def verdict(scores: dict, found: dict | None) -> dict:
    if not found:
        return {"code": "unchecked", "line": "Not checked for existing tools yet."}
    near = found.get("nearest") or {}
    name = near.get("name") or "an existing tool"
    if found["coverage"] >= 1.0:
        lead = "You already have" if near.get("installed") else "Use"
        return {"code": "adopt", "line": f"{lead} {name}. It does this. Not a gap.", "nearest": near}
    if scores["need"] < PARK_BELOW_NEED:
        return {"code": "park", "line": "Nothing shows people need it. Park it.", "nearest": near or None}
    if found["coverage"] >= 0.5:
        return {"code": "beat", "line": f"{name} covers part of it. The gap is the difference.", "nearest": near}
    if all(scores[k] >= floor for k, floor in WIN.items()) and not found["thin"]:
        return {"code": "pioneer", "line": "Nothing found that does this, and people need it."}
    axes = {k: scores[k] - floor for k, floor in WIN.items()}
    weakest = min(axes, key=lambda k: axes[k])
    hint = "search wider before trusting the absence" if found["thin"] and axes[weakest] >= 0 else \
        {"need": "find people asking for it", "originality": "run more absence searches",
         "counterfactual": "say what gets better and for whom"}[weakest]
    return {"code": "iterate", "line": f"Weakest: {weakest}. Next: {hint}.", "binding": weakest}


ORDER = {"pioneer": 0, "iterate": 1, "beat": 2, "unchecked": 3, "park": 4, "adopt": 5}


def rank(gaps: list[dict]) -> list[dict]:
    def key(gap: dict) -> tuple:
        s = gap.get("scores") or {}
        main = s.get("pioneer")
        if main is None:
            main = s.get("provisional") or 0
        return (ORDER.get((gap.get("verdict") or {}).get("code", "unchecked"), 9), -main, -s.get("fit", 0), gap.get("id", ""))
    return sorted(gaps, key=key)
