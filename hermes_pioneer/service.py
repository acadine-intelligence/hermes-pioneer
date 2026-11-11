"""The Pioneer loop: seed, scout, submit, absence, board. One class, used by tools, /pioneer and the CLI.

The session's own model writes queries, gaps and rulings. This class fetches, checks every citation
against the ledger, scores, decides the verdict and keeps the trail.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Callable

from . import judge as judge_mod
from . import options, score, seed as seed_mod, sources
from .store import Trail

KINDS = ("need", "talk", "refusal", "capability", "supply", "dead", "web")
GAP_KINDS = ("tool", "product", "service", "workflow", "dataset")
MAX_QUERIES = 10
MAX_LEDGER_RETURN = 80
MAX_CANDIDATES_RETURN = 12

SEED_CONTRACT = (
    "This is an inverted search. Find what does not exist yet and should, for this person. Do not recommend "
    "existing tools at this step; the absence check does that later, in code.\n"
    "1. Read the seed. Name 3 to 6 frictions: work this person does by hand, things they glue together, "
    "things their tools refuse to do.\n"
    "2. For each friction write search queries a stranger with the same problem would type. Keep them to "
    "2 to 5 plain words. Queries leave this machine: no names, companies, paths, amounts or private facts.\n"
    "3. Call pioneer_scout with this run id and 6 to 10 queries. If you have other search tools (web, Reddit, "
    "X, papers), run them too and pass what they find as `signals`.")

INVENT_CONTRACT = (
    "Write 4 to 8 gaps and call pioneer_submit. A gap is one specific thing that could exist: who it is for, "
    "what it does, and what is new in how it does it. Small is good: a micro innovation beats a platform.\n"
    "Cite Signal ids from this ledger in `evidence`. A gap with no valid id is dropped. Off-topic ledger "
    "lines carry no weight.\n"
    "Rate each 1 to 5 with one short reason:\n"
    "  need: 5 = many people ask for it and you cite them; 1 = you inferred it.\n"
    "  value: 5 = saves or earns a lot for the person who has it; 1 = a small convenience.\n"
    "  counterfactual: 5 = work that cannot happen today becomes possible; 1 = the same result, slightly sooner.\n"
    "  durability: 5 = no substitute likely within two years; 1 = a platform ships it within months. Low is allowed.\n"
    "  fit: 5 = on this person's path and buildable with what they have; 1 = a stray.\n"
    "Rate honestly. A crowded field is not a gap. Do not rate originality: the absence check measures it.")

ABSENCE_CONTRACT = (
    "Rule on every candidate, then call pioneer_absence again with `rulings`.\n"
    "  solves: a person who wants this gap is served by the candidate as it is. They should use it.\n"
    "  partial: it covers some of the job, or covers it badly.\n"
    "  unrelated: it does a different job.\n"
    "Put what the candidate actually does in `why`. When unsure, say partial. \"Nothing exists\" is a claim: "
    "if you know of, or can find with any other tool (web search), a product that does this, add it under "
    "`found` with its own ruling. Leaving out a rival you know of makes the score a lie.")

NEXT = {
    "adopt": "Tell the user to use the existing tool. Do not pitch this gap.",
    "park": "Say plainly that no need was shown. Offer to look for need elsewhere or drop it.",
    "beat": "The gap is the difference from the nearest tool. Resubmit it with the same id, narrowed to that "
            "difference, or expand it with pioneer_seed(expand=<gap id>).",
    "iterate": "Open a child round on the weakest axis with pioneer_seed(expand=<gap id>), or gather more "
               "evidence with pioneer_scout and resubmit.",
    "pioneer": "Show the board. Offer to expand one level deeper or to turn the gap into a plan.",
    "unchecked": "Run pioneer_absence on it.",
}


def _text(value: Any, limit: int) -> str:
    return seed_mod.clip(str(value or ""), limit)



def _headline(aim: str) -> str:
    """A long aim becomes a short name: its first clause, cut at a word, at most 60 characters."""
    head = re.split(r"[:.?!;\n]| - ", aim.strip(), maxsplit=1)[0].strip() or aim.strip()
    if len(head) > 60:
        head = head[:60].rsplit(" ", 1)[0]
    return head


def _clean_title(text: str) -> str:
    """One plain line, at most 80 characters."""
    return " ".join(str(text or "").split())[:80].rstrip(" .,:;")

class Pioneer:
    def __init__(self, home: Path, data: Path, *, get_config: Callable[[str, Any], Any] | None = None,
                 secret: Callable[[str], str | None] | None = None, llm: Any = None,
                 fetch: sources.Fetch = sources.fetch_json, inventory: Callable[[], dict] | None = None,
                 now: Callable[[], float] = time.time):
        self.home, self.data = Path(home), Path(data)
        self.get = get_config or (lambda key, default=None: default)
        self.secret = secret or (lambda name: None)
        self.llm, self.fetch, self.now = llm, fetch, now
        self._inventory_fn = inventory or (lambda: {})
        self._inventory: dict | None = None
        self.trail = Trail(self.data)

    # ---- shared ----------------------------------------------------------------------------------

    def inventory(self) -> dict:
        if self._inventory is None:
            try:
                self._inventory = self._inventory_fn() or {}
            except Exception:
                self._inventory = {}
        return self._inventory

    def _settings(self) -> dict:
        return options.resolve(self.get)

    def _secrets(self) -> dict:
        return {name: self.secret(name) for name in ("GITHUB_TOKEN", "FIRECRAWL_API_KEY")}

    @staticmethod
    def _queries(raw: Any) -> tuple[list[str], list[str]]:
        good: list[str] = []
        refused: list[str] = []
        for q in raw if isinstance(raw, list) else []:
            why = sources.check_query(q)
            if why:
                refused.append(f"{str(q)[:40]!r}: {why}")
            elif q.strip() not in good:
                good.append(q.strip())
        if len(good) > MAX_QUERIES:
            refused.append(f"{len(good) - MAX_QUERIES} queries over the limit of {MAX_QUERIES}")
        return good[:MAX_QUERIES], refused

    # ---- 1. seed ---------------------------------------------------------------------------------

    def seed(self, cwd: str | None, *, steer: str = "", expand: str | None = None,
             session_id: str | None = None, title: str = "") -> dict:
        parent = None
        if expand:
            prun, pgap = self.trail.find_gap(expand)
            ledger = {s["id"]: s for s in prun["signals"]}
            verdict = pgap.get("verdict") or {}
            parent = {
                "id": pgap["id"], "title": pgap["title"], "one_line": pgap.get("one_line", ""),
                "buyer": pgap.get("buyer", ""), "mechanism": pgap.get("mechanism", ""),
                "verdict": verdict.get("code"), "weakest_axis": verdict.get("binding"),
                "nearest_existing": (verdict.get("nearest") or {}).get("name"),
                "evidence": [{"title": ledger[i]["title"], "url": ledger[i]["url"]}
                             for i in pgap.get("evidence", []) if i in ledger][:8],
            }
        cfg = self._settings()["seed"]
        built = seed_mod.build(self.home, cwd, self.inventory(), use_workspace=cfg["workspace"],
                               use_memory=cfg["memory"], use_sessions=cfg["chats"], steer=steer, parent=parent,
                               exclude_session=session_id, now=self.now())
        run = self.trail.new(created=self.now(), cwd=cwd or "", steer=built["steer"], parent=expand,
                             seed_digest=built["digest"], title=_clean_title(title))
        contract = SEED_CONTRACT
        if parent:
            contract += ("\nThis round expands gap " + parent["id"] + ". Go one level deeper: the sub-problems inside "
                         "it, the people it leaves out, and what must exist first. Measure need again from new "
                         "evidence; it is not inherited from the parent.")
        return {"run": run["id"], "title": self._title(run), "seed": built, "sources_on": sorted(self._settings()["sources"]),
                "next": contract}

    # ---- 2. scout --------------------------------------------------------------------------------

    def scout(self, run_id: str | None, queries: Any, signals: Any = None) -> dict:
        run = self.trail.load(run_id)
        good, refused = self._queries(queries)
        if not good and not signals:
            raise ValueError("no usable queries. " + "; ".join(refused))
        cfg = self._settings()
        found, answered, errors = sources.gather(good, "scout", cfg["sources"], fetch=self.fetch,
                                                 inventory=self.inventory(), secrets=self._secrets())
        for raw in (signals if isinstance(signals, list) else [])[:30]:
            if not isinstance(raw, dict):
                continue
            url = str(raw.get("url") or "")
            if not url.startswith(("https://", "http://")) or not raw.get("title"):
                refused.append("a supplied signal without a title or an http link")
                continue
            kind = str(raw.get("kind")) if raw.get("kind") in KINDS else "talk"
            found.append(sources._sig("agent:" + _text(raw.get("source") or "tool", 24), kind, raw.get("title"), url,
                                      raw.get("text"), raw.get("date"), raw.get("engagement")))
        seen = {(s["source"], s["url"] or s["title"]) for s in run["signals"]}
        fresh: list[dict] = []
        for sig in found:
            key = (sig["source"], sig["url"] or sig["title"])
            if key in seen:
                continue
            seen.add(key)
            sig["id"] = f"S{len(run['signals']) + 1}"
            run["signals"].append(sig)
            fresh.append(sig)
        run["queries"] = list(dict.fromkeys(run["queries"] + good))
        run["errors"] = sorted(set(run["errors"]) | set(errors))
        self.trail.save(run)
        shown = self._quota(fresh, MAX_LEDGER_RETURN)
        by_source: dict[str, int] = {}
        for sig in fresh:
            by_source[sig["source"]] = by_source.get(sig["source"], 0) + 1
        return {
            "run": run["id"], "new_signals": len(fresh), "ledger_total": len(run["signals"]),
            "by_source": by_source, "sources_answered": answered, "errors": errors, "refused": refused,
            "ledger": [self._line(s) for s in shown],
            "not_shown": max(0, len(fresh) - len(shown)),
            "next": INVENT_CONTRACT if fresh else "No new signals. Try different words, or fewer of them.",
        }

    @staticmethod
    def _quota(signals: list[dict], limit: int) -> list[dict]:
        """Rank by engagement inside each source, then interleave, so one loud source cannot fill the ledger."""
        lanes: dict[str, list[dict]] = {}
        for sig in signals:
            lanes.setdefault(sig["source"], []).append(sig)
        for lane in lanes.values():
            lane.sort(key=lambda s: -s.get("engagement", 0))
        out: list[dict] = []
        while len(out) < limit and any(lanes.values()):
            for name in sorted(lanes):
                if lanes[name] and len(out) < limit:
                    out.append(lanes[name].pop(0))
        return out

    @staticmethod
    def _line(sig: dict) -> dict:
        return {"id": sig["id"], "src": sig["source"], "kind": sig["kind"], "title": sig["title"],
                "text": sig["text"][:180], "eng": sig["engagement"], "date": sig["date"], "url": sig["url"]}

    # ---- 3. submit -------------------------------------------------------------------------------

    def submit(self, run_id: str | None, gaps: Any) -> dict:
        run = self.trail.load(run_id)
        if not isinstance(gaps, list) or not gaps:
            raise ValueError("gaps must be a non-empty list")
        ledger = {s["id"]: s for s in run["signals"]}
        existing = {g["id"]: g for g in run["gaps"]}
        accepted: list[str] = []
        dropped: list[dict] = []
        for raw in gaps[:12]:
            if not isinstance(raw, dict) or not str(raw.get("title") or "").strip():
                dropped.append({"title": "?", "why": "no title"})
                continue
            title = _text(raw["title"], 90)
            cited = [str(i) for i in raw.get("evidence") or [] if isinstance(i, (str, int))]
            valid = [i for i in dict.fromkeys(cited) if i in ledger]
            unknown = [i for i in dict.fromkeys(cited) if i not in ledger]
            if not valid:
                dropped.append({"title": title, "why": "no cited Signal id is in the ledger"})
                continue
            ratings: dict[str, dict] = {}
            bad = []
            for dim in score.RATED:
                n = score.rating((raw.get("ratings") or {}).get(dim))
                if n is None:
                    bad.append(dim)
                    continue
                why = (raw["ratings"][dim].get("why") if isinstance(raw["ratings"][dim], dict) else "") or ""
                ratings[dim] = {"n": n, "why": _text(why, 200)}
            if bad:
                dropped.append({"title": title, "why": "missing or invalid 1-5 rating for: " + ", ".join(bad)})
                continue
            gid = str(raw.get("id") or "")
            gap: dict[str, Any] | None = existing.get(gid)
            if gap is None:
                gid = f"{run['id']}.g{len(run['gaps']) + 1}"
                gap = dict(id=gid)
                run["gaps"].append(gap)
                existing[gid] = gap
            gap.update({
                "title": title, "one_line": _text(raw.get("one_line"), 300), "buyer": _text(raw.get("buyer"), 160),
                "mechanism": _text(raw.get("mechanism"), 300),
                "kind": raw.get("kind") if raw.get("kind") in GAP_KINDS else "tool",
                "evidence": valid, "unknown_evidence": unknown, "ratings": ratings,
            })
            score.score_gap(gap, ledger)
            accepted.append(gid)
        run["dropped"] = (run.get("dropped") or []) + dropped
        self.trail.save(run)
        ranked = score.rank(run["gaps"])
        unchecked = [g["id"] for g in ranked if g["verdict"]["code"] == "unchecked"][:3]
        return {
            "run": run["id"], "accepted": accepted, "dropped": dropped,
            "ranking": [self._row(g) for g in ranked],
            "next": ("Originality is unmeasured until the absence check runs. Call pioneer_absence for "
                     + ", ".join(unchecked) + " with 3 to 6 `queries`: the words someone would use to find this "
                     "product if it already existed (product-style names, \"X for Y\", the job itself)."
                     if unchecked else "Every gap is checked. Call pioneer_board."),
        }

    @staticmethod
    def _row(gap: dict) -> dict:
        s, v = gap["scores"], gap["verdict"]
        return {"id": gap["id"], "title": gap["title"], "verdict": v["code"], "line": v["line"],
                "pioneer": s["pioneer"], "provisional": s["provisional"], "need": s["need"],
                "originality": s["originality"], "counterfactual": s["counterfactual"], "value": s["value"],
                "durability": s["durability"], "fit": s["fit"], "judge_exists": s.get("judge_exists"),
                "evidence": len(gap["evidence"]), "sources": s["sources"]}

    # ---- 4. absence ------------------------------------------------------------------------------

    def absence(self, gap_id: str, *, queries: Any = None, rulings: Any = None, found: Any = None) -> dict:
        run, gap = self.trail.find_gap(gap_id)
        ab = gap.setdefault("absence", {"queries": [], "sources_ok": [], "candidates": [], "errors": [], "ruled": False})
        out: dict[str, Any] = {"gap": gap_id}
        if queries:
            good, refused = self._queries(queries)
            if not good:
                raise ValueError("no usable queries. " + "; ".join(refused))
            cfg = self._settings()
            hits, answered, errors = sources.gather(good, "absence", cfg["sources"], fetch=self.fetch,
                                                    inventory=self.inventory(), secrets=self._secrets())
            hits = [h for h in hits if h["kind"] in sources.SUPPLY_KINDS]
            seen = {c["url"] or c["title"] for c in ab["candidates"]}
            fresh = []
            for hit in self._quota(hits, MAX_CANDIDATES_RETURN * 3):
                key = hit["url"] or hit["title"]
                if key in seen or len(fresh) >= MAX_CANDIDATES_RETURN:
                    continue
                seen.add(key)
                hit["id"] = f"C{len(ab['candidates']) + 1}"
                hit["ruling"] = None
                ab["candidates"].append(hit)
                fresh.append(hit)
            ab["queries"] = list(dict.fromkeys(ab["queries"] + good))
            ab["sources_ok"] = sorted(set(ab["sources_ok"]) | set(answered))
            ab["errors"] = sorted(set(ab["errors"]) | set(errors))
            ab["ruled"] = False
            out.update({"searched": good, "sources_answered": answered, "errors": errors, "refused": refused,
                        "candidates": [{"id": c["id"], "src": c["source"], "kind": c["kind"], "name": c["title"],
                                        "what": c["text"][:200], "eng": c["engagement"], "url": c["url"]} for c in fresh],
                        "next": ABSENCE_CONTRACT})
        if isinstance(found, list):
            known = {c["url"] or c["title"] for c in ab["candidates"]} | {c["title"] for c in ab["candidates"]}
            for raw in found[:10]:
                if not isinstance(raw, dict) or not raw.get("name"):
                    continue
                url = str(raw.get("url") or "")
                if url in known or _text(raw["name"], 140) in known:
                    continue  # already a candidate; rule on it by id instead
                known.update({url, _text(raw["name"], 140)})
                cand = sources._sig("agent", "supply", raw["name"], url if url.startswith(("https://", "http://")) else "",
                                    raw.get("what"))
                cand.update({"id": f"C{len(ab['candidates']) + 1}",
                             "ruling": raw.get("ruling") if raw.get("ruling") in score.RULINGS else "partial",
                             "why": _text(raw.get("why") or raw.get("what"), 240)})
                ab["candidates"].append(cand)
            if "agent" not in ab["sources_ok"] and found:
                ab["sources_ok"] = sorted(set(ab["sources_ok"]) | {"agent"})
        if isinstance(rulings, list) or (isinstance(found, list) and not queries):
            by_id = {c["id"]: c for c in ab["candidates"]}
            for raw in rulings or []:
                if not isinstance(raw, dict):
                    continue
                cand = by_id.get(str(raw.get("id")))
                if cand is None or raw.get("ruling") not in score.RULINGS:
                    continue
                cand["ruling"] = raw["ruling"]
                cand["why"] = _text(raw.get("why"), 240)
            missing = [c["id"] for c in ab["candidates"] if c.get("ruling") not in score.RULINGS]
            if missing:
                self.trail.save(run)
                raise ValueError("every candidate needs a ruling (solves, partial or unrelated). Missing: "
                                 + ", ".join(missing))
            if not ab["queries"]:
                self.trail.save(run)
                raise ValueError("run the search first: call pioneer_absence with `queries`")
            ask, status = judge_mod.build(self._settings()["judge"], secret=self.secret, llm=self.llm)
            ab["judge"] = {"backend": status}
            if ask is not None:
                probs, err = judge_mod.judge(ask, gap, ab["candidates"])
                for cid, p in probs.items():
                    by_id[cid]["judge_p"] = p
                if err:
                    ab["judge"]["error"] = err
            ab["ruled"] = True
            ab["checked_at"] = self.now()
        score.score_gap(gap, {s["id"]: s for s in run["signals"]})
        self.trail.save(run)
        if ab["ruled"]:
            code = gap["verdict"]["code"]
            out.update({"result": self._row(gap), "judge": ab.get("judge"),
                        "thin_check": gap["scores"].get("thin_check"),
                        "next": NEXT[code].replace("<gap id>", gap_id)})
        return out

    # ---- 5. board --------------------------------------------------------------------------------

    def board(self, run_id: str | None = None, *, scope: str = "round") -> dict:
        runs = self.trail.all() if scope == "trail" else [self.trail.load(run_id)]
        if not runs:
            raise LookupError("no rounds yet. Start with pioneer_seed.")
        gaps = [g for run in runs for g in run["gaps"]]
        ranked = score.rank(gaps)
        latest = runs[-1]
        rounds = [dict({"id": r["id"], "from": r.get("parent"), "steer": r.get("steer", ""), "signals": len(r["signals"]),
                        "gaps": len(r["gaps"]), "errors": len(r.get("errors") or []), "title": self._title(r),
                        "from_title": self._parent_title(r)}, **self._stage(r)) for r in runs]
        counts: dict[str, int] = {}
        for g in ranked:
            counts[g["verdict"]["code"]] = counts.get(g["verdict"]["code"], 0) + 1
        return {
            "scope": scope, "round": latest["id"], "rounds": rounds, "counts": counts,
            "gaps": [dict(self._row(g), one_line=g.get("one_line", ""), buyer=g.get("buyer", ""),
                          mechanism=g.get("mechanism", ""), kind=g.get("kind", "tool"),
                          nearest=(g["verdict"].get("nearest") or None),
                          thin_check=g["scores"].get("thin_check"), binding=g["verdict"].get("binding"))
                     for g in ranked],
            "errors": sorted({e for r in runs for e in (r.get("errors") or [])}),
            "judge": self._settings()["judge"], "weights": score.WEIGHTS, "win_zone": score.WIN,
        }

    # ---- names and progress -------------------------------------------------------------------

    def _parent_title(self, run: dict) -> str | None:
        if not run.get("parent"):
            return None
        try:
            return self.trail.find_gap(run["parent"])[1].get("title") or None
        except LookupError:
            return None

    def _title(self, run: dict) -> str:
        """A round is shown by a name, never by its id: the name the agent gave it, else the gap it
        expands, else its aim, else the project folder."""
        aim = re.sub(r"^\s*what should exist for\s*", "", run.get("steer") or "", flags=re.I).strip(" ?.")
        folder = Path(run.get("cwd") or "").name
        named = run.get("title") or self._parent_title(run) or _headline(aim) or folder or f"Round {run['id'][1:]}"
        return _clean_title(named[:1].upper() + named[1:])

    def _stage(self, run: dict) -> dict:
        """Where a round is, read from what it holds. It counts as running for 15 minutes after its
        last write; an abandoned round stops showing as busy."""
        if not run["signals"]:
            stage = "reading"
        elif not run["gaps"]:
            stage = "searching"
        elif any(not (g.get("absence") or {}).get("ruled") for g in run["gaps"]):
            stage = "checking"
        else:
            stage = "done"
        updated = run.get("updated") or run.get("created") or 0
        return {"stage": stage, "updated": updated, "running": stage != "done" and self.now() - updated < 900}

    def gap(self, gap_id: str) -> dict:
        run, gap = self.trail.find_gap(gap_id)
        ledger = {s["id"]: s for s in run["signals"]}
        return {"gap": gap, "evidence": [self._line(ledger[i]) for i in gap["evidence"] if i in ledger]}

    # ---- 6. setup --------------------------------------------------------------------------------

    def setup(self) -> dict:
        return options.report(self.get, self.inventory())
