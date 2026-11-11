"""Signal sources. Each one turns a short public query into Signals with a source, a kind and a link.

Kinds:
  need        someone asks for it or works around its absence
  talk        people discuss the area (weak need evidence)
  refusal     a maintainer closed the request as not planned
  capability  a published method exists (often with no product)
  supply      something that may already do it
  dead        supply that is archived
  local       something already installed in this Hermes, or in the plugin catalog
  web         an open-web result (kind unknown until read)

No source ever raises. A failure becomes one line in ``errors`` so the report can say what it did not see.
"""

from __future__ import annotations

import concurrent.futures
import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

UA = "hermes-pioneer/0.1 (+https://github.com/acadine-intelligence/hermes-pioneer)"
TIMEOUT = 8.0
DEMAND_KINDS = {"need", "refusal", "talk", "dead"}
SUPPLY_KINDS = {"supply", "dead", "local", "web"}

Fetch = Callable[..., Any]

_STOP = set("a an and are as at be by for from how i in is it my of on or that the this to tool tools with "
            "you your app apps using use via what when which".split())
_PRIVATE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+|/Users/|/home/|sk-[A-Za-z0-9_\-]{12,}|gh[pousr]_[A-Za-z0-9]{12,}"
                      r"|\b[0-9a-fA-F]{24,}\b|\b\d{9,}\b")


def check_query(q: Any) -> str | None:
    """Return the reason a query may not leave the machine, or None when it may."""
    if not isinstance(q, str) or not q.strip():
        return "empty"
    q = q.strip()
    if len(q) < 3:
        return "too short"
    if len(q) > 120:
        return "longer than 120 characters"
    if _PRIVATE.search(q):
        return "looks private (email, path, key or long number)"
    return None


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9][a-z0-9+#.\-]{1,}", (text or "").lower()) if t not in _STOP and len(t) > 2]


def stems(text: str) -> set[str]:
    """Crude word stems for matching: drop a plural s, keep six letters. claims = claim, verifies = verification."""
    return {(t[:-1] if t.endswith("s") and len(t) > 3 else t)[:6] for t in tokens(text)}


def relevant(query: str, text: str) -> bool:
    """True when at least half of the query's words appear in *text*."""
    want = stems(query)
    return not want or len(want & stems(text)) * 2 >= len(want)


def fetch_json(url: str, *, headers: dict | None = None, body: dict | None = None, timeout: float = TIMEOUT) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": UA, "Accept": "application/json",
        **({"Content-Type": "application/json"} if body is not None else {}), **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed https hosts below)
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _strip(text: Any, limit: int = 240) -> str:
    text = re.sub(r"<[^>]+>", " ", html.unescape(str(text or "")))
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " ..."


def _sig(source: str, kind: str, title: Any, url: Any, text: Any = "", date: Any = "", engagement: Any = 0,
         **meta: Any) -> dict:
    try:
        eng = int(engagement or 0)
    except (TypeError, ValueError):
        eng = 0
    return {"source": source, "kind": kind, "title": _strip(title, 140), "url": str(url or ""),
            "text": _strip(text), "date": str(date or "")[:10], "engagement": eng, **({"meta": meta} if meta else {})}


# ---- network sources -----------------------------------------------------------------------------

# Words that mark a comment as someone wanting a thing, or working around its absence.
_WISH = re.compile(r"(?i)\b(i wish|wish (there|it|someone|i)|is there (a|an|any)|looking for (a|an|some)|does anyone know|"
                   r"anyone know of|why is there no|there is no (good |easy )?way|no good way|would pay|i'd pay|"
                   r"ended up (writing|building)|built my own|wrote my own|rolled my own|had to (write|build)|"
                   r"need a (tool|way)|frustrat|pain point|annoying)")


def hn(query: str, *, limit: int = 8, fetch: Fetch = fetch_json, show_only: bool = False, **_: Any) -> list[dict]:
    tags = "show_hn" if show_only else "(story,comment)"
    data = fetch("https://hn.algolia.com/api/v1/search?" + urllib.parse.urlencode(
        {"query": query, "tags": tags, "hitsPerPage": limit}))
    out = []
    want = stems(query)
    for hit in (data or {}).get("hits", []):
        item = f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        title = hit.get("title") or hit.get("story_title") or ""
        # Algolia matches loosely. Keep a hit only when at least half of the query words are in it.
        if not relevant(query, f"{title} {hit.get('comment_text') or ''} {hit.get('story_text') or ''}"):
            continue
        # A long self-post contains most common words. A story must also carry a query word in its title.
        if want and not hit.get("comment_text") and not want & stems(title):
            continue
        if title.strip().lower() in ("", "[dead]", "[flagged]") and not hit.get("comment_text"):
            continue
        if hit.get("comment_text"):
            body = hit.get("comment_text")
            kind = "need" if _WISH.search(_strip(body, 2000)) else "talk"
            out.append(_sig("hn", kind, title, item, body, hit.get("created_at"), hit.get("points")))
            continue
        low = title.lower()
        kind = "supply" if low.startswith("show hn") or low.startswith("launch hn") else \
            "need" if low.startswith(("ask hn", "tell hn")) else "talk"
        out.append(_sig("hn", kind, title, item, hit.get("story_text") or hit.get("url") or "", hit.get("created_at"),
                        (hit.get("points") or 0) + (hit.get("num_comments") or 0)))
    return out


def _gh_headers(token: str | None) -> dict:
    head = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        head["Authorization"] = "Bearer " + token
    return head


def github_repos(query: str, *, limit: int = 8, fetch: Fetch = fetch_json, token: str | None = None, **_: Any) -> list[dict]:
    data = fetch("https://api.github.com/search/repositories?" + urllib.parse.urlencode(
        {"q": f"{query} in:name,description,topics", "per_page": limit, "sort": "stars", "order": "desc"}),
        headers=_gh_headers(token))  # README matches are mostly noise once sorted by stars
    out = []
    for repo in (data or {}).get("items", []):
        # Some repos paste whole documents into the description. Judge the name and its first lines only.
        if not relevant(query, f"{str(repo.get('full_name') or '').replace('/', ' ')} {str(repo.get('description') or '')[:300]}"):
            continue
        archived = bool(repo.get("archived"))
        out.append(_sig("github", "dead" if archived else "supply", repo.get("full_name"), repo.get("html_url"),
                        repo.get("description"), repo.get("pushed_at"), repo.get("stargazers_count"),
                        stars=repo.get("stargazers_count") or 0, archived=archived))
    return out


def github_refusals(query: str, *, limit: int = 6, fetch: Fetch = fetch_json, token: str | None = None, **_: Any) -> list[dict]:
    """Requests a maintainer closed as not planned. Reactions are people who wanted it anyway."""
    data = fetch("https://api.github.com/search/issues?" + urllib.parse.urlencode(
        {"q": f'{query} in:title is:issue state:closed reason:"not planned"', "per_page": limit,
         "sort": "reactions", "order": "desc"}), headers=_gh_headers(token))
    out = []
    for issue in (data or {}).get("items", []):
        reactions = (issue.get("reactions") or {}).get("total_count") or 0
        repo = str(issue.get("repository_url") or "").rsplit("/repos/", 1)[-1]
        out.append(_sig("github", "refusal", f"{repo}: {issue.get('title')}", issue.get("html_url"), issue.get("body"),
                        issue.get("closed_at"), reactions + (issue.get("comments") or 0), reactions=reactions))
    return out


def openalex(query: str, *, limit: int = 5, fetch: Fetch = fetch_json, **_: Any) -> list[dict]:
    data = fetch("https://api.openalex.org/works?" + urllib.parse.urlencode(
        {"search": query, "per-page": limit, "select": "id,display_name,publication_year,cited_by_count,doi"}))
    return [_sig("openalex", "capability", work.get("display_name"), work.get("doi") or work.get("id"),
                 f"{work.get('cited_by_count') or 0} citations", str(work.get("publication_year") or ""),
                 work.get("cited_by_count")) for work in (data or {}).get("results", [])]


def firecrawl(query: str, *, limit: int = 6, fetch: Fetch = fetch_json, key: str | None = None, **_: Any) -> list[dict]:
    if not key:
        raise RuntimeError("FIRECRAWL_API_KEY is not set")
    data = fetch("https://api.firecrawl.dev/v2/search", body={"query": query, "limit": limit},
                 headers={"Authorization": "Bearer " + key}, timeout=20.0)
    rows = (data or {}).get("data") or []
    if isinstance(rows, dict):
        rows = rows.get("web") or []
    return [_sig("firecrawl", "web", row.get("title"), row.get("url"), row.get("description") or row.get("snippet"))
            for row in rows if isinstance(row, dict)]


# ---- local source --------------------------------------------------------------------------------

def local(query: str, *, inventory: dict | None = None, limit: int = 6, **_: Any) -> list[dict]:
    """What this Hermes install already has, plus the plugin catalog. No network."""
    want = stems(query)
    if not want:
        return []
    need = 1 if len(want) == 1 else 2
    inv = inventory or {}
    pools = (
        ("skill", [(s["name"], s.get("what", ""), "") for s in inv.get("skills", [])]),
        ("plugin", [(p, "", "") for p in inv.get("plugins", [])]),
        ("mcp server", [(m, "", "") for m in inv.get("mcp_servers", [])]),
        ("catalog plugin", [(c["name"], c.get("what", ""), c.get("url", "")) for c in inv.get("catalog", [])]),
    )
    scored = []
    for label, items in pools:
        for name, what, url in items:
            have = stems(name.replace("-", " ").replace("_", " ") + " " + what)
            hit = len(want & have)
            if hit >= need and hit / len(want) >= 0.5:
                installed = label != "catalog plugin"
                # engagement carries match strength, so the strongest local match is shown first
                scored.append((hit / len(want), _sig("local", "local", f"{label}: {name}", url, what,
                                                     engagement=round(100 * hit / len(want)),
                                                     installed=installed, where=label)))
    scored.sort(key=lambda pair: -pair[0])
    return [sig for _, sig in scored[:limit]]


# ---- registry ------------------------------------------------------------------------------------

# name -> (function, hosts it calls, what it adds). ``scout`` sources run on every query; ``absence``
# sources look for something that already does the job.
REGISTRY: dict[str, dict[str, Any]] = {
    "hn": {"fn": hn, "roles": ("scout",), "per_call": 6},
    "hn_show": {"fn": lambda q, **kw: hn(q, show_only=True, **kw), "roles": ("absence",), "per_call": 4, "setting": "hn"},
    "github": {"fn": github_repos, "roles": ("scout", "absence"), "per_call": 4},
    "github_refusals": {"fn": github_refusals, "roles": ("scout",), "per_call": 2, "setting": "github"},
    "openalex": {"fn": openalex, "roles": ("scout",), "per_call": 3},
    "local": {"fn": local, "roles": ("scout", "absence"), "per_call": 8, "limit": {"scout": 3, "absence": 6}},
    "firecrawl": {"fn": firecrawl, "roles": ("scout", "absence"), "per_call": 4},
}


def gather(queries: list[str], role: str, enabled: set[str], *, fetch: Fetch = fetch_json,
           inventory: dict | None = None, secrets: dict | None = None) -> tuple[list[dict], list[str], list[str]]:
    """Run every enabled source of *role* over *queries*. Returns (signals, sources that answered, errors)."""
    secrets = secrets or {}
    jobs: list[tuple[str, str, Callable[[], list[dict]]]] = []
    for name, spec in REGISTRY.items():
        if role not in spec["roles"] or spec.get("setting", name) not in enabled:
            continue
        extra = {"limit": spec["limit"][role]} if "limit" in spec else {}
        for q in queries[: spec["per_call"]]:
            jobs.append((name, q, lambda fn=spec["fn"], q=q, extra=extra: fn(
                q, fetch=fetch, inventory=inventory, token=secrets.get("GITHUB_TOKEN"),
                key=secrets.get("FIRECRAWL_API_KEY"), **extra)))
    signals: list[dict] = []
    answered: set[str] = set()
    errors: list[str] = []
    if not jobs:
        return signals, [], errors
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(job): (name, q) for name, q, job in jobs}
        for fut in concurrent.futures.as_completed(futures):
            name, q = futures[fut]
            base = REGISTRY[name].get("setting", name)
            try:
                rows = fut.result()
            except urllib.error.HTTPError as exc:
                errors.append(f"{name}: HTTP {exc.code} on \"{q}\"")
                continue
            except Exception as exc:  # timeouts, DNS, bad JSON: the report names them
                errors.append(f"{name}: {type(exc).__name__} on \"{q}\"")
                continue
            answered.add(base)
            for row in rows:
                row["query"] = q
                signals.append(row)
    return signals, sorted(answered), sorted(errors)
