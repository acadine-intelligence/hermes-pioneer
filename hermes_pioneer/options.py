"""Setup options, what this install already has, and what Pioneer recommends turning on.

Three tables drive everything here. Adding a source, a judge or a companion tool is one new row.
Options are switches the USER owns: the agent can read them and recommend, and only the user's own
``/pioneer enable ...`` or ``hermes pioneer enable ...`` changes one.
"""

from __future__ import annotations

import re
from typing import Any, Callable

# id, setting key, default, what it adds, what it sends where, what it needs, cost
OPTIONS: list[dict[str, Any]] = [
    {"id": "hn", "group": "source", "setting": "source_hn", "default": True, "title": "Hacker News",
     "adds": "People asking for things, complaining and launching. Finds need.",
     "sends": "search queries to hn.algolia.com", "needs": None, "cost": "free, no account"},
    {"id": "github", "group": "source", "setting": "source_github", "default": True, "title": "GitHub",
     "adds": "Existing repos, archived repos people still star, and requests maintainers closed as not planned.",
     "sends": "search queries to api.github.com", "needs": None, "optional_key": "GITHUB_TOKEN",
     "cost": "free; 10 searches a minute without a token, 30 with one"},
    {"id": "openalex", "group": "source", "setting": "source_openalex", "default": True, "title": "OpenAlex papers",
     "adds": "Published methods. Finds capability that has no product yet.",
     "sends": "search queries to api.openalex.org", "needs": None, "cost": "free, no account"},
    {"id": "local", "group": "source", "setting": "source_local", "default": True, "title": "This Hermes install",
     "adds": "Your installed skills, plugins and MCP servers, plus the plugin catalog. Catches \"you already have this\".",
     "sends": "nothing; a local read", "needs": None, "cost": "free"},
    {"id": "firecrawl", "group": "source", "setting": "source_firecrawl", "default": False, "title": "Firecrawl web search",
     "adds": "The open web: product sites and pricing pages GitHub and Hacker News miss. Strongest absence check.",
     "sends": "search queries to api.firecrawl.dev", "needs": "FIRECRAWL_API_KEY", "cost": "about 2 Firecrawl credits a search"},
    {"id": "judge", "group": "judge", "setting": "judge", "default": "off", "choices": ("off", "llm", "jev"),
     "title": "Second judge on the absence check",
     "adds": "An independent probability that each existing tool already does the job. It can only lower originality.",
     "sends": "jev: the gap and candidate descriptions to api.typesafe.ai. llm: the same to your own Hermes model.",
     "needs": None, "cost": "jev: a fraction of a cent a gap, needs TYPESAFE_API_KEY. llm: your own tokens."},
    {"id": "workspace", "group": "seed", "setting": "seed_workspace", "default": True, "title": "Read the project folder",
     "adds": "README, agent rules, manifests, top-level names and the last 15 commit subjects.",
     "sends": "nothing; shown to your own model only", "needs": None, "cost": "free"},
    {"id": "memory", "group": "seed", "setting": "seed_memory", "default": True, "title": "Read Hermes memory",
     "adds": "Your goals and standing context, so gaps sit on your path.",
     "sends": "nothing; shown to your own model only", "needs": None, "cost": "free"},
    {"id": "chats", "group": "seed", "setting": "seed_sessions", "default": True, "title": "Read recent chats",
     "adds": "Title and first ask of the last 20 chats (14 days). Shows what you keep doing by hand.",
     "sends": "nothing; shown to your own model only", "needs": None, "cost": "free"},
]

# Tools the agent may already have. Pioneer never calls them. The agent runs them and hands the
# results to pioneer_scout as signals, or to pioneer_absence as found tools.
COMPANIONS: list[dict[str, Any]] = [
    {"id": "web_search", "always": True, "title": "Web search (built in)",
     "use": "Absence check: search for the product by the words a buyer would use, then read the closest pricing page."},
    {"id": "reddit", "skills": r"reddit", "mcp": r"reddit", "title": "Reddit reading",
     "use": "Where buyers talk. Pass threads to pioneer_scout as need signals."},
    {"id": "x", "skills": r"^x-|twitter", "mcp": r"^x$|twitter", "title": "X search",
     "use": "Live complaints and launch replies. Pass posts to pioneer_scout as need signals."},
    {"id": "papers", "skills": r"arxiv|literature|paper-research|scholar", "mcp": r"science|arxiv|scholar", "title": "Paper search",
     "use": "Citation walks around a method. Pass papers to pioneer_scout as capability signals."},
    {"id": "firecrawl_skill", "skills": r"^firecrawl", "plugins": r"firecrawl", "title": "Firecrawl skills",
     "use": "Scrape a rival's site before ruling on it in pioneer_absence."},
    {"id": "search_mcp", "mcp": r"exa|tavily|brave|perplexity|kagi|serp", "plugins": r"brave|exa|tavily", "title": "Search provider",
     "use": "A second web index for the absence check. Different indexes miss different products."},
    {"id": "pioneer_cloud", "mcp": r"^pioneer$", "title": "Hosted Pioneer",
     "use": "A deeper paid gather on one business URL. Pass its cited signals to pioneer_scout."},
    {"id": "tickets", "mcp": r"linear|jira|github", "title": "Ticket tracker",
     "use": "Turn a gap with a pioneer verdict into a ticket once the user picks it."},
    {"id": "focus", "plugins": r"^focus$", "title": "Focus plugin",
     "use": "Add the chosen gap as a commitment so it becomes the one thing to work on."},
]


def value(get: Callable[[str, Any], Any], option: dict) -> Any:
    raw = get(option["setting"], option["default"])
    if "choices" in option:
        raw = str(raw or option["default"]).lower()
        return raw if raw in option["choices"] else option["default"]
    if isinstance(raw, str):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    return bool(raw)


def resolve(get: Callable[[str, Any], Any]) -> dict[str, Any]:
    vals = {o["id"]: value(get, o) for o in OPTIONS}
    return {"sources": {o["id"] for o in OPTIONS if o["group"] == "source" and vals[o["id"]]},
            "judge": vals["judge"],
            "seed": {k: vals[k] for k in ("workspace", "memory", "chats")}}


def _has(pattern: str | None, names: list[str]) -> list[str]:
    if not pattern:
        return []
    rx = re.compile(pattern, re.I)
    return [n for n in names if rx.search(n)]


def companions(inventory: dict) -> list[dict]:
    skills = [s["name"] for s in inventory.get("skills", [])]
    found = []
    for c in COMPANIONS:
        hits = _has(c.get("skills"), skills)[:3] + _has(c.get("mcp"), inventory.get("mcp_servers", [])) \
            + _has(c.get("plugins"), inventory.get("plugins", []))
        if c.get("always") or hits:
            found.append({"id": c["id"], "title": c["title"], "use": c["use"], "you_have": hits})
    return found


def report(get: Callable[[str, Any], Any], inventory: dict) -> dict[str, Any]:
    """Every option with its current state, plus ordered recommendations for THIS install."""
    keys = inventory.get("keys", {})
    rows = []
    for o in OPTIONS:
        state = value(get, o)
        ready = not o["needs"] or bool(keys.get(o["needs"]))
        rows.append({"id": o["id"], "group": o["group"], "title": o["title"], "state": state if "choices" in o else ("on" if state else "off"),
                     "ready": ready, "adds": o["adds"], "sends": o["sends"], "needs": o["needs"], "cost": o["cost"]})
    state = {r["id"]: r["state"] for r in rows}
    recs: list[dict[str, str]] = []
    if keys.get("FIRECRAWL_API_KEY") and state["firecrawl"] == "off":
        recs.append({"do": "Turn on Firecrawl web search", "why": "You already have a Firecrawl key. GitHub and Hacker News "
                     "miss products that only have a website, so an absence check without the open web is thin.",
                     "how": "/pioneer enable firecrawl"})
    if state["judge"] == "off":
        if keys.get("TYPESAFE_API_KEY"):
            recs.append({"do": "Turn on the Jev judge", "why": "You already have a TypeSafe key. The model that invents a gap "
                         "also rules on its rivals; a calibrated second judge keeps that honest for a fraction of a cent.",
                         "how": "/pioneer judge jev"})
        else:
            recs.append({"do": "Turn on the second judge with your own model", "why": "The model that invents a gap also rules on "
                         "its rivals. A fresh-context second look can only lower originality. It spends your own tokens.",
                         "how": "/pioneer judge llm"})
    if state["github"] == "on" and not keys.get("GITHUB_TOKEN"):
        recs.append({"do": "Add a GitHub token", "why": "Without one GitHub allows 10 searches a minute, and a busy round "
                     "drops queries. A token with no scopes is enough.", "how": "add GITHUB_TOKEN to the Hermes .env file (hermes config env-path prints where it is)"})
    if state["firecrawl"] == "off" and not keys.get("FIRECRAWL_API_KEY"):
        recs.append({"do": "Let the agent's own web search cover the open web", "why": "No Firecrawl key here. Ask the agent to "
                     "web-search each top gap and pass what it finds to pioneer_absence under `found`.",
                     "how": "no setup; the pioneer:run skill already does this"})
    have = companions(inventory)
    feeders = [c["title"] for c in have if c["you_have"] and c["id"] in ("reddit", "x", "papers", "search_mcp", "pioneer_cloud")]
    if feeders:
        recs.append({"do": "Feed Pioneer from tools you already have: " + ", ".join(feeders),
                     "why": "Pioneer never calls them. The agent runs them on the same frictions and passes the results "
                     "to pioneer_scout as signals, so they can be cited and scored.",
                     "how": "no setup; say \"use my other search tools too\" when you start a round"})
    return {"options": rows, "companions": have, "recommended": recs[:5]}
