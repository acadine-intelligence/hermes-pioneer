# Pioneer

An inverted search for Hermes. A normal search finds what exists. Pioneer looks for what does not exist yet and should, for your own work.

It reads your project folder, your Hermes memory and your recent chats. Your own model names the frictions and writes candidate gaps. Code then does the parts a model should not grade for itself: it checks every citation, searches for tools that already do the job, and scores the result.

Pioneer is not a tool recommender. When an existing tool already does the job, the verdict says "use that" and the gap is closed. That answer is a result.

## What a round looks like

1. `pioneer_seed` builds a seed from your workspace, memory and chats. Local, read-only, redacted.
2. The agent writes short public queries. `pioneer_scout` runs them and returns a ledger of Signals with ids.
3. The agent writes 4 to 8 gaps that cite Signal ids. `pioneer_submit` drops any gap with no valid citation and scores the rest.
4. `pioneer_absence` searches for existing tools. The agent rules on each one. Code sets originality and the verdict.
5. `pioneer_board` shows the ranked list. On Hermes Desktop it renders as a board with buttons.
6. `pioneer_seed(expand=<gap id>)` opens a child round on one gap. Rounds form a trail.

Say "run pioneer" in a chat. The agent loads the `pioneer:run` skill and does the round.

## Scores

Each measure is 0 to 100.

| Measure | Weight | Where it comes from |
|---|---|---|
| Need | 30 | The model's 1 to 5 rating, cut when fewer than three demand Signals are cited |
| Originality | 25 | The absence check only. The model never rates it |
| Counterfactual | 20 | The 1 to 5 rating, cut to zero when an existing tool does the job |
| Value | 15 | The 1 to 5 rating |
| Durability | 10 | The 1 to 5 rating. A short-lived opening is allowed; the board shows it |

An unmeasured score shows as `-` or `?`. It is never treated as zero.

## Verdicts

| Verdict | Meaning |
|---|---|
| pioneer | Nothing found that does it, and people need it (originality and need at 70 or more, counterfactual at 50 or more) |
| iterate | One measure is weak. The verdict names it |
| beat | An existing tool covers part of it. The gap is the difference |
| use existing | An existing tool does it. Use that tool |
| park | No need was shown |
| unchecked | No absence check yet |

A search that ran fewer than three queries, or that fewer than two sources answered, caps originality at 60. "Nothing found" from a thin search is not originality.

## Tools

| Tool | What it does |
|---|---|
| `pioneer_seed` | Start a round, or expand a gap into a child round |
| `pioneer_scout` | Gather Signals from the sources that are on, plus any the agent supplies from its own tools |
| `pioneer_submit` | Check citations, score and rank the gaps |
| `pioneer_absence` | Search for existing tools, take rulings, set originality and the verdict |
| `pioneer_board` | The ranked list, one gap in full, or the whole trail |
| `pioneer_setup` | Options, what this install already has, and what to turn on next |

Commands: `/pioneer`, `/pioneer trail`, `/pioneer gap <id>`, `/pioneer rounds`, `/pioneer setup`. The same verbs work as `hermes pioneer ...`.

## Options

Run `/pioneer setup` to see every option with its state, what it sends and what it costs, plus recommendations for your install.

| Option | Default | Needs |
|---|---|---|
| Hacker News (`hn`) | on | nothing |
| GitHub repos and refused requests (`github`) | on | nothing. `GITHUB_TOKEN` raises the rate limit |
| OpenAlex papers (`openalex`) | on | nothing |
| This Hermes install and the plugin catalog (`local`) | on | nothing, no network |
| Firecrawl web search (`firecrawl`) | off | `FIRECRAWL_API_KEY` |
| Second judge (`judge`) | off | `llm`: your own model. `jev`: `TYPESAFE_API_KEY` |
| Seed inputs (`workspace`, `memory`, `chats`) | on | nothing |

Only you change a switch: `/pioneer enable firecrawl`, `/pioneer disable chats`, `/pioneer judge jev`. The agent can read the options and recommend. It cannot change them.

The second judge gives an independent probability that each existing tool already does the job. It can raise how much a tool covers, never lower it, so it can only cost a gap originality. Its thresholds (0.70 for "does the job", 0.50 for "covers part") are starting values from one test round. They are not calibrated yet.

Pioneer also works with search tools your agent already has (web search, Reddit, X, papers, other MCP servers). Pioneer never calls them. The agent runs them and passes the results in, where they are cited and scored like any other Signal.

## Desktop

The repo carries an optional Desktop half (`desktop/plugin.js`) and a read-only backend (`dashboard/plugin_api.py`).

- A Pioneer row in the left sidebar opens the Pioneer page: rounds on the left as a tree, the chart, the ranked gaps, and the evidence and absence check for each gap. A Setup tab lists the options and what this install already has. The page keeps Pioneer's own look (ink and cyan glass, a drawn waypoint ring) in any app theme. Rounds and gaps are shown by name. While a round runs, the page shows its stage and the ring turns faster.
- The field "What should exist for" starts a round with an aim. There is no bare run button: a round with no aim returns generic gaps.
- A Pioneer pane sits to the right of the chat and follows a round as it runs. It uses the app's theme.
- The command palette (⌘K) has "Pioneer: open the board".
- Buttons such as Expand and Check it exists send one sentence to a chat, and the agent runs the round. A chat on screen gets it. The Pioneer page has no chat on screen, so there the request starts a new chat. The sentence is copied to the clipboard only when the app can do neither.
- The page never changes a switch. "Change switches" opens Settings → Plugins → Pioneer.

The Desktop half loads on the machine that runs the Desktop app. With a local backend, enable it in Capabilities → Plugins. With a remote backend, install the repo from Git with the Desktop target checked, or copy `desktop/plugin.js` to `~/.hermes/desktop-plugins/pioneer/plugin.js` on the machine that runs Desktop. Without the Desktop half, `pioneer_board` still writes the inline HTML board.

`desktop/plugin.js` is built. Edit `desktop_src/plugin.src.js`, then run `python3 scripts/build_desktop.py`, which inlines the wordmark from `desktop_src/assets/`. The tests fail when the built file is out of date. No picture ships with the plugin. A personal build can carry its own background: `python3 scripts/build_desktop.py --art my.avif -o my-plugin.js`. The Pioneer wordmark is a trademark of Acadine Intelligence and is not covered by the code licence.

The backend has three GET routes under `/api/plugins/pioneer/` (`board`, `gap/{id}`, `setup`) and no route that writes.

## What it reads, sends and writes

- Reads, locally: the project folder of the chat (README, AGENTS.md or CLAUDE.md, package manifests, top-level names), `memories/MEMORY.md` and `memories/USER.md`, `state.db` (title and first message of up to 20 recent chats, read-only), the names and descriptions of installed skills, the names of enabled plugins and MCP servers from `config.yaml`, and the `plugin-catalog/*.yaml` files in the Hermes checkout. It refuses the home folder and the disk root.
- Runs one command: `git log -15 --pretty=%s` in the project folder, with a 5 second limit.
- Redacts keys, tokens, long hex strings and email addresses from the seed. The seed goes to your own model only.
- Sends search queries, and nothing else, to `hn.algolia.com`, `api.github.com` and `api.openalex.org`. With Firecrawl on, also to `api.firecrawl.dev`. Queries that look private (an email, a path, a key, a long number) are refused before they leave.
- With `judge: jev`, sends the gap's title and description and each candidate's name and description to `api.typesafe.ai`. With `judge: llm`, sends the same to your own Hermes model through `ctx.llm`.
- Writes only `plugin-data/pioneer/` under the Hermes home: one JSON file per round and `board.html`.
- No background process. No telemetry. No self-update. In a cron or gateway run every source has a timeout, and a failed source becomes a line on the board.

The weekly automation is registered as a blueprint and stays off until you schedule it.

## Limits

- Need is the weak measure. The model infers it from chatter. Cited asks and workarounds help; they do not prove anyone will pay.
- Hacker News and GitHub miss products that only have a website. Turn on Firecrawl or let the agent web-search each top gap.
- The absence rulings come from the model that wrote the gap. Turn on the second judge for an independent check.
- Word matching is plain English stems. Queries in other languages will match poorly.

## Develop

```
python -m pytest
hermes plugins validate . --install-deps
```

MIT. Built by Acadine Intelligence.
