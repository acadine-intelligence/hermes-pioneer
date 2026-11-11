"""Engine and adapter tests. No network: every source call goes through a fake fetch."""

from __future__ import annotations

import json
import sqlite3
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hermes_pioneer import judge, options, render, render_html, score, seed, sources  # noqa: E402
from hermes_pioneer.service import Pioneer  # noqa: E402

INVENTORY = {
    "skills": [{"name": "invoice-chaser", "what": "Chase unpaid invoices by email"},
               {"name": "reddit-reading", "what": "Read Reddit threads"}],
    "plugins": ["focus"], "mcp_servers": ["science", "linear"],
    "catalog": [{"name": "git-review", "what": "Review a git diff before commit", "url": "https://example.test/git-review"}],
    "keys": {"FIRECRAWL_API_KEY": True, "TYPESAFE_API_KEY": False, "GITHUB_TOKEN": False},
}


def fake_fetch(url, *, headers=None, body=None, timeout=8.0):
    if "hn.algolia.com" in url:
        if "show_hn" in url:
            return {"hits": [{"objectID": "9", "title": "Show HN: Ledgerly, changelog diffs for cron jobs", "points": 40,
                              "num_comments": 12, "created_at": "2026-05-01T00:00:00Z"}]}
        return {"hits": [
            {"objectID": "1", "title": "Ask HN: How do you know which cron job broke?", "points": 120, "num_comments": 80,
             "created_at": "2026-03-01T00:00:00Z"},
            {"objectID": "2", "story_title": "Cron monitoring", "comment_text": "I <b>wish</b> something told me why the cron job failed",
             "points": 3, "created_at": "2026-03-02T00:00:00Z"},
            {"objectID": "3", "title": "Cron job scheduling is fine actually", "points": 10, "num_comments": 2, "created_at": "2026-01-01T00:00:00Z"}]}
    if "search/repositories" in url:
        return {"items": [
            {"full_name": "acme/cronwatch", "html_url": "https://github.com/acme/cronwatch", "description": "Watch cron jobs and explain each failure",
             "stargazers_count": 900, "pushed_at": "2026-06-01T00:00:00Z", "archived": False},
            {"full_name": "old/cronlog", "html_url": "https://github.com/old/cronlog", "description": "Explain cron failures",
             "stargazers_count": 400, "pushed_at": "2022-01-01T00:00:00Z", "archived": True}]}
    if "search/issues" in url:
        return {"items": [{"title": "Explain why a job failed", "html_url": "https://github.com/acme/cronwatch/issues/7",
                           "repository_url": "https://api.github.com/repos/acme/cronwatch", "body": "Out of scope",
                           "closed_at": "2026-02-01T00:00:00Z", "comments": 9, "reactions": {"total_count": 31}}]}
    if "openalex" in url:
        return {"results": [{"display_name": "Root cause analysis of scheduled job failures", "doi": "https://doi.org/10.1/x",
                             "cited_by_count": 55, "publication_year": 2024}]}
    if "firecrawl" in url:
        raise urllib.error.HTTPError(url, 402, "Payment Required", None, None)  # type: ignore[arg-type]
    raise AssertionError(f"unexpected url {url}")


@pytest.fixture()
def home(tmp_path):
    (tmp_path / "memories").mkdir()
    (tmp_path / "memories" / "MEMORY.md").write_text(
        "Runs 40 cron jobs. API_KEY=sk-abcdefghijklmnopqrstuvwxyz012345 mail me at owner@example.com\n")
    (tmp_path / "memories" / "USER.md").write_text("Wants small original tools.\n")
    db = sqlite3.connect(tmp_path / "state.db")
    db.execute("CREATE TABLE sessions (id TEXT, source TEXT, title TEXT, cwd TEXT, parent_session_id TEXT, "
               "started_at REAL, last_activity_at REAL)")
    db.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT)")
    db.execute("INSERT INTO sessions VALUES ('a','desktop','Fix the nightly job','/w/app',NULL,1000,1000)")
    db.execute("INSERT INTO sessions VALUES ('b','cron','cron run','/w/app',NULL,1000,1000)")
    db.execute("INSERT INTO messages (session_id, role, content) VALUES ('a','user','why did the nightly job fail again')")
    db.commit()
    db.close()
    return tmp_path


@pytest.fixture()
def project(tmp_path_factory):
    root = tmp_path_factory.mktemp("proj")
    (root / "README.md").write_text("# Nightly\nKeeps scheduled jobs honest. token: ghp_abcdefghijklmnopqrstuvwxyz0123\n")
    (root / "package.json").write_text(json.dumps({"name": "nightly", "description": "job runner", "dependencies": {"croner": "1"}}))
    return root


def make(home, data, *, cfg=None, llm=None, secret=None, inv=None, fetch=fake_fetch):
    cfg = cfg or {}
    return Pioneer(home, data, get_config=lambda k, d=None: cfg.get(k, d), secret=secret or (lambda n: None), llm=llm,
                   fetch=fetch, inventory=lambda: inv if inv is not None else INVENTORY, now=lambda: 2000.0)


def gap(evidence, **over):
    base = {"title": "Why-it-failed notes for cron jobs", "one_line": "Explains each failed run in one line.",
            "buyer": "people who run many scheduled jobs", "mechanism": "diffs the failing run against the last good one",
            "kind": "tool", "evidence": evidence,
            "ratings": {d: {"n": 4, "why": "cited"} for d in score.RATED}}
    base.update(over)
    return base


def checked(svc, run_id, rulings, *, queries=("cron failure explainer", "why did cron job fail", "cron run diff"), found=None):
    svc.absence(f"{run_id}.g1", queries=list(queries))
    _, g = svc.trail.find_gap(f"{run_id}.g1")
    full = [{"id": c["id"], "ruling": rulings.get(c["title"], "unrelated"), "why": "read it"} for c in g["absence"]["candidates"]]
    return svc.absence(f"{run_id}.g1", rulings=full, found=found)


def round_one(svc, project):
    run = svc.seed(str(project))["run"]
    led = svc.scout(run, ["cron job failure", "scheduled job monitoring"])
    need_ids = [s["id"] for s in led["ledger"] if s["kind"] in ("need", "refusal", "talk")][:3]
    svc.submit(run, [gap(need_ids)])
    return run, led


# ---- seed ----------------------------------------------------------------------------------------

def test_seed_reads_workspace_memory_chats_and_redacts(home, project, tmp_path):
    out = make(home, tmp_path / "d").seed(str(project), steer="cron")
    s = out["seed"]
    blob = json.dumps(s)
    assert s["workspace"]["name"] == project.name and s["workspace"]["manifests"][0]["deps"] == ["croner"]
    assert "sk-abcdefghij" not in blob and "ghp_abcdefghij" not in blob and "owner@example.com" not in blob
    assert "[secret]" in s["memory"]["notes"] and "[email]" in s["memory"]["notes"]
    assert [c["title"] for c in s["recent_chats"]] == ["Fix the nightly job"]  # the cron run is skipped
    assert s["already_have"]["mcp_servers"] == ["science", "linear"]
    assert "inverted search" in out["next"]


def test_seed_refuses_home_folder_and_respects_switches(home, tmp_path):
    svc = make(home, tmp_path / "d", cfg={"seed_memory": False, "seed_sessions": "false"})
    s = svc.seed(str(Path.home()))["seed"]
    assert "workspace" not in s and "memory" not in s and "recent_chats" not in s
    assert any("home folder" in o for o in s["omitted"])


# ---- sources -------------------------------------------------------------------------------------

@pytest.mark.parametrize("q,ok", [("cron job failure", True), ("x", False), ("mail owner@example.com", False),
                                  ("/Users/me/secret plan", False), ("a" * 121, False), (None, False),
                                  ("invoice 1234567890", False)])
def test_query_guard(q, ok):
    assert (sources.check_query(q) is None) is ok


def test_scout_builds_ledger_and_names_failures(home, project, tmp_path):
    svc = make(home, tmp_path / "d", cfg={"source_firecrawl": True}, secret=lambda n: "k")
    run = svc.seed(str(project))["run"]
    out = svc.scout(run, ["cron job failure", "owner@example.com leak"],
                    signals=[{"title": "Thread: cron pain", "url": "https://reddit.example/t/1", "kind": "need", "source": "reddit"},
                             {"title": "no link"}])
    kinds = {s["kind"] for s in out["ledger"]}
    assert {"need", "talk", "supply", "dead", "refusal", "capability"} <= kinds
    assert any(e.startswith("firecrawl: HTTP 402") for e in out["errors"])
    assert any("looks private" in r for r in out["refused"]) and any("supplied signal" in r for r in out["refused"])
    assert any(s["src"] == "agent:reddit" for s in out["ledger"])
    assert "hn" in out["sources_answered"] and "firecrawl" not in out["sources_answered"]
    again = svc.scout(run, ["cron job failure"])
    assert again["new_signals"] == 0  # same links are not added twice


def test_sources_off_are_not_called(home, project, tmp_path):
    calls = []
    def fetch(url, **kw):
        calls.append(url)
        return fake_fetch(url, **kw)
    svc = make(home, tmp_path / "d", cfg={"source_hn": False, "source_openalex": False}, fetch=fetch)
    svc.scout(svc.seed(str(project))["run"], ["cron job failure"])
    assert calls and all("github" in u for u in calls)


def test_hn_comment_is_need_only_when_it_asks_for_something():
    def fetch(url, **kw):
        return {"hits": [{"objectID": "1", "story_title": "t", "comment_text": "I ended up writing my own script for this"},
                         {"objectID": "2", "story_title": "t", "comment_text": "Rust is nice"},
                         {"objectID": "3", "title": "[dead]"}]}
    assert [s["kind"] for s in sources.hn("x y", fetch=fetch)] == ["need", "talk"]
    assert [s["kind"] for s in sources.hn("rust script", fetch=fetch)] == ["need", "talk"]
    assert sources.hn("kubernetes operator billing", fetch=fetch) == []   # loose matches are dropped


def test_hn_story_needs_a_query_word_in_its_title():
    def fetch(url, **kw):
        return {"hits": [{"objectID": "1", "title": "Show HN: A C++ runtime", "story_text": "a proof that every agent can stop on a hook"},
                         {"objectID": "2", "title": "Show HN: Proof gate for agents", "story_text": "stop hook"}]}
    assert [s["title"] for s in sources.hn("stop hook proof agent", fetch=fetch)] == ["Show HN: Proof gate for agents"]


def test_github_search_stays_out_of_readmes_and_local_ranks_by_match():
    seen = []
    def fetch(url, **kw):
        seen.append(url)
        return {"items": []}
    sources.github_repos("cron explainer", fetch=fetch)
    assert "in%3Aname%2Cdescription%2Ctopics" in seen[0]
    inv = {"skills": [{"name": "proof-of-concept", "what": "agent demo"}, {"name": "proofgate", "what": "No proof, no done for an agent"}]}
    assert [h["title"] for h in sources.local("agent done without proof", inventory=inv)] == ["skill: proofgate", "skill: proof-of-concept"]
    assert sources.local("agent done without proof", inventory=inv)[0]["engagement"] == 75
    inv = {"catalog": [{"name": "proofgate", "what": "Verifies an agent's completion claims"}]}
    assert sources.local("completion claim verification agent", inventory=inv)[0]["engagement"] == 100  # stems match
    def bee(url, **kw):
        return {"items": [{"full_name": "x/sem2", "html_url": "u", "description": "According to all known laws of aviation " + "bee " * 200 + "agent skill usage"},
                          {"full_name": "a/skills-cleaner", "html_url": "v", "description": "Track skill usage by AI agents"}]}
    assert [r["title"] for r in sources.github_repos("skill usage analytics agent", fetch=bee)] == ["a/skills-cleaner"]


def test_refused_requests_are_matched_on_the_title():
    seen = []
    def fetch(url, **kw):
        seen.append(url)
        return {"items": []}
    sources.github_refusals("explain job failure", fetch=fetch)
    assert "in%3Atitle" in seen[0] and "not+planned" in seen[0]


def test_local_source_finds_installed_and_catalog():
    hits = sources.local("chase unpaid invoices", inventory=INVENTORY)
    assert hits and hits[0]["title"] == "skill: invoice-chaser" and hits[0]["meta"]["installed"] is True
    cat = sources.local("review git diff", inventory=INVENTORY)
    assert cat and cat[0]["meta"]["installed"] is False


# ---- submit and scoring --------------------------------------------------------------------------

def test_uncited_gap_is_dropped_and_unknown_ids_are_kept_apart(home, project, tmp_path):
    svc = make(home, tmp_path / "d")
    run = svc.seed(str(project))["run"]
    led = svc.scout(run, ["cron job failure"])
    first = led["ledger"][0]["id"]
    out = svc.submit(run, [gap(["S999"]), gap([first, "S999"], title="Second"),
                           gap([first], title="Bad rating", ratings={"need": 9})])
    assert out["accepted"] == [f"{run}.g1"]
    assert [d["why"] for d in out["dropped"]][0] == "no cited Signal id is in the ledger"
    assert "missing or invalid" in out["dropped"][1]["why"]
    _, g = svc.trail.find_gap(f"{run}.g1")
    assert g["unknown_evidence"] == ["S999"]


def test_originality_is_unmeasured_until_the_absence_check(home, project, tmp_path):
    svc = make(home, tmp_path / "d")
    run, _ = round_one(svc, project)
    row = svc.board(run)["gaps"][0]
    assert row["verdict"] == "unchecked" and row["originality"] is None and row["pioneer"] is None
    text = render.board(svc.board(run))
    assert "| - |" in text and "unchecked" in text


def test_need_is_cut_when_demand_evidence_is_thin(home, project, tmp_path):
    svc = make(home, tmp_path / "d")
    run = svc.seed(str(project))["run"]
    led = svc.scout(run, ["cron job failure"])
    supply = next(s["id"] for s in led["ledger"] if s["kind"] == "supply")
    need = [s["id"] for s in led["ledger"] if s["kind"] in ("need", "refusal", "talk")]
    svc.submit(run, [gap([supply]), gap(need[:1], title="one"), gap(need[:3], title="three")])
    by_title = {g["title"]: g["scores"]["need"] for g in svc.trail.load(run)["gaps"]}
    assert by_title["Why-it-failed notes for cron jobs"] == 30  # 75 x 0.4: no demand signal at all
    assert by_title["one"] == 45 and by_title["three"] == 75


def test_verdict_pioneer_when_nothing_covers_it(home, project, tmp_path):
    svc = make(home, tmp_path / "d")
    run, _ = round_one(svc, project)
    out = checked(svc, run, {})
    r = out["result"]
    assert r["verdict"] == "pioneer" and r["originality"] == 100 and r["counterfactual"] == 75
    assert r["pioneer"] == round((75 * 30 + 100 * 25 + 75 * 20 + 75 * 15 + 75 * 10) / 100)


def test_verdict_adopt_when_an_existing_tool_solves_it(home, project, tmp_path):
    svc = make(home, tmp_path / "d")
    run, _ = round_one(svc, project)
    r = checked(svc, run, {"acme/cronwatch": "solves"})["result"]
    assert r["verdict"] == "adopt" and r["originality"] == 10 and r["counterfactual"] == 0
    assert "Use acme/cronwatch" in r["line"]


def test_verdict_beat_on_partial_cover_and_archived_repo_cannot_solve(home, project, tmp_path):
    svc = make(home, tmp_path / "d")
    run, _ = round_one(svc, project)
    r = checked(svc, run, {"old/cronlog": "solves"})["result"]  # archived: capped at partial
    assert r["verdict"] == "beat" and r["originality"] == 55 and "old/cronlog" in r["line"]


def test_verdict_park_when_need_is_low(home, project, tmp_path):
    svc = make(home, tmp_path / "d")
    run = svc.seed(str(project))["run"]
    led = svc.scout(run, ["cron job failure"])
    need = [s["id"] for s in led["ledger"] if s["kind"] == "need"][:3]
    ratings = {d: {"n": 4} for d in score.RATED}
    ratings["need"] = {"n": 2}
    svc.submit(run, [gap(need, ratings=ratings)])
    assert checked(svc, run, {})["result"]["verdict"] == "park"


def test_thin_absence_search_caps_originality(home, project, tmp_path):
    svc = make(home, tmp_path / "d")
    run, _ = round_one(svc, project)
    out = checked(svc, run, {}, queries=("cron failure explainer",))
    assert out["thin_check"] is True and out["result"]["originality"] == 60 and out["result"]["verdict"] == "iterate"


def test_every_candidate_needs_a_ruling_and_found_rivals_count(home, project, tmp_path):
    svc = make(home, tmp_path / "d")
    run, _ = round_one(svc, project)
    svc.absence(f"{run}.g1", queries=["cron failure explainer", "why did cron job fail", "cron run diff"])
    with pytest.raises(ValueError, match="every candidate needs a ruling"):
        svc.absence(f"{run}.g1", rulings=[{"id": "C1", "ruling": "unrelated"}])
    r = checked(svc, run, {}, found=[{"name": "Cronitor", "url": "https://cronitor.io", "what": "explains failures",
                                      "ruling": "solves", "why": "has failure reasons"}])["result"]
    assert r["verdict"] == "adopt" and "Cronitor" in r["line"]
    _, g = svc.trail.find_gap(f"{run}.g1")
    before = len(g["absence"]["candidates"])
    svc.absence(f"{run}.g1", rulings=[], found=[{"name": "Cronitor", "url": "https://cronitor.io", "ruling": "solves"}])
    assert len(svc.trail.find_gap(f"{run}.g1")[1]["absence"]["candidates"]) == before   # the same rival is not added twice


def test_rulings_without_a_search_are_refused(home, project, tmp_path):
    svc = make(home, tmp_path / "d")
    run, _ = round_one(svc, project)
    with pytest.raises(ValueError, match="run the search first"):
        svc.absence(f"{run}.g1", rulings=[])


@pytest.mark.parametrize("bad", [None, True, "0.9", float("nan"), float("inf"), 1.2, -0.1, [], {}])
def test_poisoned_judge_values_never_move_a_score(bad):
    assert score.coverage({"ruling": "unrelated", "judge_p": bad}) == 0.0


@pytest.mark.parametrize("p,cover", [(0.95, 1.0), (0.70, 1.0), (0.69, 0.5), (0.50, 0.5), (0.49, 0.0), (0.05, 0.0)])
def test_judge_bands(p, cover):
    assert score.coverage({"ruling": "unrelated", "judge_p": p}) == cover


def test_judge_can_lower_originality_but_never_raise_it(home, project, tmp_path):
    class Llm:
        def __init__(self, p): self.p = p
        def complete_structured(self, **kw):
            state = json.loads(kw["input"][0]["text"])
            return type("R", (), {"parsed": {c["_row_id"]: self.p for c in state["candidates"]}})()
    svc = make(home, tmp_path / "hi", cfg={"judge": "llm"}, llm=Llm(0.9))
    run, _ = round_one(svc, project)
    hi = checked(svc, run, {})["result"]                      # model said unrelated, judge says it exists
    assert hi["verdict"] == "adopt" and hi["judge_exists"] == 0.9
    svc = make(home, tmp_path / "lo", cfg={"judge": "llm"}, llm=Llm(0.01))
    run, _ = round_one(svc, project)
    lo = checked(svc, run, {"acme/cronwatch": "solves"})["result"]  # model said solves, judge disagrees
    assert lo["verdict"] == "adopt" and lo["originality"] == 10


def test_judge_failure_leaves_rulings_in_charge(home, project, tmp_path):
    class Boom:
        def complete_structured(self, **kw): raise TimeoutError("slow")
    svc = make(home, tmp_path / "d", cfg={"judge": "llm"}, llm=Boom())
    run, _ = round_one(svc, project)
    out = checked(svc, run, {})
    assert out["result"]["verdict"] == "pioneer" and "TimeoutError" in out["judge"]["error"]
    ask, status = judge.build("jev", secret=lambda n: None)
    assert ask is None and "not set" in status


def test_nearest_tool_prefers_judge_then_installed_and_judge_never_skips_close_rivals():
    cands = [{"id": "C1", "title": "big repo", "ruling": "solves", "engagement": 900, "source": "github"},
             {"id": "C2", "title": "skill: mine", "ruling": "solves", "engagement": 50, "source": "local", "meta": {"installed": True}},
             {"id": "C3", "title": "catalog plugin: theirs", "ruling": "solves", "engagement": 50, "source": "local", "meta": {"installed": False}}]
    ab = {"ruled": True, "queries": ["a", "b", "c"], "sources_ok": ["github", "local"], "candidates": cands}
    assert score.absence_result(ab)["nearest"]["name"] == "skill: mine"
    cands[0]["judge_p"] = 0.9
    assert score.absence_result(ab)["nearest"]["name"] == "big repo"
    many = [{"id": f"C{i}", "title": "x", "text": "", "ruling": "unrelated", "engagement": 500} for i in range(30)]
    many.append({"id": "C99", "title": "found rival", "text": "", "ruling": "partial", "engagement": 0})
    asked = []
    judge.judge(lambda state, qs: asked.extend(qs) or {}, {"title": "t"}, many)
    assert "C99" in asked and len(asked) == judge.MAX_CANDIDATES


def test_judge_questions_address_rows_by_id():
    cands = [{"id": "C1", "title": "a", "text": "x"}, {"id": "C2", "title": "b", "text": "y"}]
    qs = judge.questions_for(cands)
    assert '"C2"' in qs["C2"]["instructions"] and "index" not in qs["C2"]["instructions"]
    assert [c["_row_id"] for c in judge.state_for({"title": "t"}, cands)["candidates"]] == ["C1", "C2"]


# ---- trail ---------------------------------------------------------------------------------------

def test_expand_opens_a_child_round_that_carries_the_parent(home, project, tmp_path):
    svc = make(home, tmp_path / "d")
    run, _ = round_one(svc, project)
    checked(svc, run, {"old/cronlog": "partial"})
    child = svc.seed(str(project), expand=f"{run}.g1")
    assert child["run"] == "r2" and child["seed"]["parent_gap"]["nearest_existing"] == "old/cronlog"
    assert "not inherited" in child["next"]
    trail = svc.board(scope="trail")
    assert [r["from"] for r in trail["rounds"]] == [None, "r1.g1"]
    with pytest.raises(LookupError):
        svc.seed(str(project), expand="r9.g9")


# ---- render --------------------------------------------------------------------------------------

def test_html_board_escapes_model_text_and_marks_unmeasured(home, project, tmp_path):
    svc = make(home, tmp_path / "d")
    run = svc.seed(str(project))["run"]
    led = svc.scout(run, ["cron job failure"])
    ids = [s["id"] for s in led["ledger"]][:3]
    svc.submit(run, [gap(ids, title="<script>alert(1)</script>", one_line='"><img src=x onerror=1>')])
    page = render_html.board(svc.board(run))
    assert "<script>alert" not in page and "<img src=x" not in page and "&lt;script&gt;" in page
    assert "<script" not in page and ">?<" in page
    assert 'data-hermes-send="Run the Pioneer absence check on gap r1.g1."' in page


def test_setup_report_recommends_from_what_is_installed():
    rep = options.report(lambda k, d=None: d, INVENTORY)
    dos = [r["do"] for r in rep["recommended"]]
    assert dos[0] == "Turn on Firecrawl web search"            # the key is already there
    assert any("your own model" in d for d in dos)              # no TypeSafe key, so the llm judge
    assert any("Add a GitHub token" in d for d in dos)
    assert dos[-1] == "Feed Pioneer from tools you already have: Reddit reading, Paper search"
    states = {o["id"]: o["state"] for o in rep["options"]}
    assert states["firecrawl"] == "off" and states["hn"] == "on" and states["judge"] == "off"
    assert "| Firecrawl web search (`firecrawl`) | off |" in render.setup(rep)
    with_jev = options.report(lambda k, d=None: d, {**INVENTORY, "keys": {"TYPESAFE_API_KEY": True}})
    assert any("Jev" in r["do"] for r in with_jev["recommended"])


# ---- adapter -------------------------------------------------------------------------------------

class FakeCtx:
    def __init__(self, cwd):
        self.tools, self.commands, self.cli, self.skills, self.blueprints, self.cfg, self.cwd = {}, {}, {}, {}, {}, {}, cwd
        self.llm = None
    def register_tool(self, name, toolset, schema, handler, **kw): self.tools[name] = (toolset, schema, handler)
    def register_command(self, name, handler, **kw): self.commands[name] = handler
    def register_cli_command(self, name, help, setup_fn, handler_fn=None, **kw): self.cli[name] = handler_fn
    def register_skill(self, name, path, description="", **kw): self.skills[name] = Path(path)
    def register_automation_blueprint(self, key, **kw): self.blueprints[key] = kw
    def get_config(self, key, default=None): return self.cfg.get(key, default)
    def set_config(self, key, value): self.cfg[key] = value
    def session_cwd(self): return self.cwd


def test_plugin_registers_what_the_manifest_declares(home, project, tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("pioneer_plugin", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pioneer_plugin"] = mod
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod.host, "hermes_home", lambda: home)
    monkeypatch.setattr(mod.host, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(mod.host, "inventory", lambda: INVENTORY)
    monkeypatch.setattr(mod.host, "secret", lambda name: None)
    (tmp_path / "data").mkdir()
    ctx = FakeCtx(str(project))
    mod.register(ctx)
    declared = [line.strip()[2:] for line in (ROOT / "plugin.yaml").read_text().split("provides_tools:")[1]
                .split("config_schema:")[0].splitlines() if line.strip().startswith("- ")]
    assert sorted(ctx.tools) == sorted(declared) and len(declared) == 6
    assert ctx.skills["run"].is_file() and "weekly" in ctx.blueprints and "pioneer" in ctx.commands
    for name, (_, schema, _) in ctx.tools.items():
        assert schema["name"] == name and schema["parameters"]["type"] == "object"

    seeded = json.loads(ctx.tools["pioneer_seed"][2]({"steer": "cron"}, session_id="zz"))
    assert seeded["success"] and seeded["run"] == "r1" and seeded["seed"]["workspace"]["name"] == project.name
    assert json.loads(ctx.tools["pioneer_board"][2]({"gap": "nope"}))["success"] is False   # errors come back as JSON
    setup = json.loads(ctx.tools["pioneer_setup"][2]({}))
    assert setup["success"] and "Recommended for this install" in setup["text"]

    assert "Firecrawl web search: on" in ctx.commands["pioneer"]("enable firecrawl")
    assert ctx.cfg == {"source_firecrawl": True}
    assert "needs FIRECRAWL_API_KEY" in ctx.commands["pioneer"]("enable firecrawl")
    assert "takes: off, llm, jev" in ctx.commands["pioneer"]("judge maybe") and "judge" not in ctx.cfg
    assert "No switch named" in ctx.commands["pioneer"]("enable judge")
    assert "no gaps yet" in ctx.commands["pioneer"]("")
    import argparse
    assert ctx.cli["pioneer"](argparse.Namespace(args=["trail"], html=True, json=False)) == 0
    assert "whole trail" in (tmp_path / "data" / "board.html").read_text()


# ---- desktop half and its backend ----------------------------------------------------------------

def _load_api(monkeypatch, home, data, inv=INVENTORY):
    import importlib.util
    sys.modules.pop("hermes_pioneer_dashboard_lib", None)
    spec = importlib.util.spec_from_file_location("pioneer_dashboard_api", ROOT / "dashboard" / "plugin_api.py")
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    monkeypatch.setattr(api.host, "hermes_home", lambda: home)
    monkeypatch.setattr(api.host, "data_dir", lambda: data)
    monkeypatch.setattr(api.host, "inventory", lambda: inv)
    monkeypatch.setattr(api.host, "secret", lambda name: None)
    monkeypatch.setattr(api.host, "settings", lambda: {})
    return api


def _client(api):
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    app = fastapi.FastAPI()
    app.include_router(api.router, prefix="/api/plugins/pioneer")
    return TestClient(app)


def _two_rounds(home, project, data):
    """A parent round with one checked gap and a child round with one unchecked gap."""
    svc = make(home, data)
    run, _ = round_one(svc, project)
    checked(svc, run, {"old/cronlog": "partial"})
    child = svc.seed(str(project), expand=f"{run}.g1", title="Cron failure notes, deeper")["run"]
    led = svc.scout(child, ["scheduled job monitoring"])
    svc.submit(child, [gap([led["ledger"][0]["id"]], title="<script>alert(1)</script>")])
    return svc


def test_dashboard_routes_are_read_only_and_survive_bad_input(home, project, tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    api = _load_api(monkeypatch, home, data)
    http = _client(api)
    assert http.get("/api/plugins/pioneer/board").json() == {"ok": True, "empty": True}
    _two_rounds(home, project, data)
    body = http.get("/api/plugins/pioneer/board").json()
    assert body["ok"] and body["empty"] is False
    assert [r["from"] for r in body["board"]["rounds"]] == [None, "r1.g1"] and len(body["board"]["gaps"]) == 2
    child = body["board"]["rounds"][1]
    assert child["title"] == "Cron failure notes, deeper" and child["from_title"] == "Why-it-failed notes for cron jobs"
    assert child["stage"] == "checking" and child["running"] is True          # its gap has no absence check yet
    one = http.get("/api/plugins/pioneer/gap/r1.g1").json()
    assert one["ok"] and one["gap"]["absence"]["ruled"] is True and one["evidence"]
    for bad in ("r9.g9", "nope", "r1.g1x"):
        assert http.get(f"/api/plugins/pioneer/gap/{bad}").json()["ok"] is False
    assert http.get("/api/plugins/pioneer/gap/..%2F..%2Fetc").status_code == 404   # a path never reaches the store
    setup = http.get("/api/plugins/pioneer/setup").json()
    assert setup["ok"] and len(setup["setup"]["options"]) == 9
    assert {r.methods.pop() for r in api.router.routes} == {"GET"}       # no route writes
    before = sorted(p.name for p in (data / "runs").iterdir())
    http.post("/api/plugins/pioneer/board")
    assert sorted(p.name for p in (data / "runs").iterdir()) == before


def test_empty_trail_board_is_a_clear_error_not_a_crash(home, tmp_path):
    with pytest.raises(LookupError, match="no rounds yet"):
        make(home, tmp_path / "d").board(scope="trail")


def _desktop_modules():
    import shutil
    node = shutil.which("node")
    try:
        import hermes_constants
        modules = Path(hermes_constants.__file__).resolve().parent / "apps" / "desktop" / "node_modules"
    except Exception:
        modules = Path("/nonexistent")
    if not node or not (modules / "react-dom").is_dir():
        pytest.skip("needs node and the Hermes Desktop node_modules (react, react-dom)")
    return node, modules


def _stage_desktop(tmp_path, modules):
    """A folder where node can import the built plugin against the stub SDK."""
    import shutil
    stage = tmp_path / "stage"
    (stage / "node_modules" / "@hermes" / "plugin-sdk").mkdir(parents=True)
    for name in ("react", "react-dom", "scheduler"):
        if (modules / name).exists():
            (stage / "node_modules" / name).symlink_to(modules / name)
    sdk = stage / "node_modules" / "@hermes" / "plugin-sdk"
    shutil.copy(ROOT / "tests" / "desktop_stub" / "index.mjs", sdk / "index.mjs")
    (sdk / "package.json").write_text(json.dumps({"name": "@hermes/plugin-sdk", "type": "module", "exports": "./index.mjs"}))
    (stage / "package.json").write_text(json.dumps({"type": "module"}))
    shutil.copy(ROOT / "desktop" / "plugin.js", stage / "plugin.js")
    return stage


def test_a_button_on_the_page_starts_a_chat_instead_of_copying(tmp_path):
    """The Pioneer page has no chat on screen. A request from it must still reach a chat."""
    import shutil, subprocess
    node, modules = _desktop_modules()
    stage = _stage_desktop(tmp_path, modules)
    shutil.copy(ROOT / "tests" / "desktop_ask.mjs", stage / "ask.mjs")
    proc = subprocess.run([node, "ask.mjs"], cwd=stage, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr[-2000:]
    out = json.loads(proc.stdout)
    expand = "Expand Pioneer gap r1.g3 into a new round."
    assert out["chatOnScreen"] == [["submit", "active", expand], ["notify", "success", "Sent to the chat"]]
    assert out["pageNoChat"] == [["newChat"], ["submit", "new", expand], ["notify", "success", "Started a new chat with it"]]
    for stuck in ("newChatNeverMounts", "olderAppNoNewChat"):
        assert out[stuck][-1][:2] == ["notify", "info"] and "clipboard" in out[stuck][-1][2]
        assert expand not in out[stuck][-1][2]                       # the notice never quotes the request back
        assert not [e for e in out[stuck] if e[0] == "submit"]
    assert [e[0] for e in out["doubleClick"]].count("submit") == 1 and [e[0] for e in out["doubleClick"]].count("newChat") == 1
    assert out["aims"] == ["Hermes Agent plugins", "a solo founder running client agents", "Hermes Agent plugins",
                           "Hermes Agent plugins", "guest houses", "", ""]


def test_desktop_half_renders_every_state(home, project, tmp_path, monkeypatch):
    import shutil, subprocess
    node, modules = _desktop_modules()
    data = tmp_path / "data"
    data.mkdir()
    api = _load_api(monkeypatch, home, data)
    http = _client(api)
    _two_rounds(home, project, data)
    stage = _stage_desktop(tmp_path, modules)
    shutil.copy(ROOT / "tests" / "desktop_render.mjs", stage / "render.mjs")
    (stage / "fixtures.json").write_text(json.dumps({
        "pioneer/board": {"data": http.get("/api/plugins/pioneer/board").json()},
        "pioneer/setup": {"data": http.get("/api/plugins/pioneer/setup").json()["setup"]},
    }))
    proc = subprocess.run([node, "render.mjs"], cwd=stage, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr[-2000:]
    out = json.loads(proc.stdout)
    assert out["id"] == "pioneer"
    regs = {r["id"]: r for r in out["regs"]}
    assert regs["page"]["data"]["path"] == "/pioneer" and regs["nav"]["data"] == {
        "path": "/pioneer", "label": "Pioneer", "codicon": "compass"}
    assert regs["pane"]["area"] == "panes" and regs["pane"]["data"]["placement"] == "right" and "open" in regs
    assert out["events"] == [["onEvent", "plugin.pioneer.trail.updated"]]
    assert "pnr-skel" in out["loading"] and "Reading the trail" not in out["loading"]
    assert "backend unavailable" in out["down"] and "HTTP 404" in out["down"] and "Retry" in out["down"]
    assert "No rounds yet" in out["empty"] and "What should exist for" in out["empty"] and "Run a round" not in out["empty"]
    page = out["page"]
    assert "All rounds" in page and "Cron failure notes, deeper" in page and "Why-it-failed notes for cron jobs" in page
    assert "Round 2, from" not in page and "r1.g1 ·" not in page            # names, not ids
    assert "beat it" in page and "not checked" in page and "Check it exists" in page and "Expand" in page
    assert "<script>alert" not in page and "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert page.count("<title>") == 1                       # one dot on the chart: the unchecked gap is not drawn
    assert "not on the chart" not in page and "The shaded corner" not in page   # no prose around the chart
    assert "Cron failure notes, deeper" in out["pane"] and "Why-it-failed notes" not in out["pane"]   # the pane opens on the latest round
    # The page carries Pioneer's own look and art. The pane beside the chat stays in the app's theme.
    assert "pnr-glass pnr-busy" in page and 'alt="Pioneer"' in page and 'class="pnr-way"' in page
    assert "Checking what already exists" in page and "pnr-run" in page   # a round in progress shows as running
    assert "data:image/avif" not in page and "data:image/png" not in page  # no picture ships with the plugin
    assert "What should exist for" in page and "pnr-card" in page and "pnr-art" in page
    assert "pnr-glass" not in out["pane"] and "data:image/avif" not in out["pane"] and "--ui-accent" in out["pane"]


def test_desktop_file_is_built_from_its_source_and_ships_no_picture(tmp_path):
    import subprocess
    script = str(ROOT / "scripts" / "build_desktop.py")
    done = subprocess.run([sys.executable, script, "--check"], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout
    built = (ROOT / "desktop" / "plugin.js").read_text()
    assert "__PIONEER_" not in built and len(built) < 60_000
    assert "data:image/avif" not in built and "const ART = ''" in built
    assert not [p for p in (ROOT / "desktop_src" / "assets").iterdir() if p.suffix in (".avif", ".png", ".jpg", ".webp")]
    assert "Run pioneer on this workspace. What should exist for" in built        # every round carries an aim
    assert "ask('Run pioneer on this workspace.')" not in built
    # A personal build inlines its own image into another file and leaves the repo copy alone.
    art, out = tmp_path / "mine.png", tmp_path / "mine.js"
    art.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    assert subprocess.run([sys.executable, script, "--art", str(art)], capture_output=True, text=True).returncode != 0
    assert subprocess.run([sys.executable, script, "--art", str(art), "-o", str(out)], capture_output=True, text=True).returncode == 0
    assert "const ART = 'data:image/png;base64," in out.read_text() and (ROOT / "desktop" / "plugin.js").read_text() == built


def test_rounds_are_named_not_numbered(home, project, tmp_path):
    svc = make(home, tmp_path / "d")
    first = svc.seed(str(project), steer="What should exist for guest houses with no night staff?")
    assert first["title"] == "Guest houses with no night staff"
    assert svc.seed(str(project))["title"] == project.name[:1].upper() + project.name[1:]     # no aim: the project folder
    assert svc.seed(str(project), title="  Night desk\n automation.  ")["title"] == "Night desk automation"
    long_aim = "Hermes Agent plugins: what plugins should exist for people running Hermes as their daily driver"
    assert svc.seed(str(project), steer=long_aim)["title"] == "Hermes Agent plugins"
    wordy = "people who run a great many scheduled agent jobs and never read what those jobs deliver"
    assert svc.seed(str(project), steer=wordy)["title"] == "People who run a great many scheduled agent jobs and never"
    run, _ = round_one(svc, project)
    assert svc.seed(str(project), expand=f"{run}.g1")["title"] == "Why-it-failed notes for cron jobs"   # the gap it expands
    rows = svc.board(scope="trail")["rounds"]
    assert all(r["title"] and not r["title"].startswith("r") or r["title"][1:2].isalpha() for r in rows)
    assert rows[0]["stage"] == "reading" and rows[0]["running"] is True
