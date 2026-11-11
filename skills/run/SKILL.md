---
name: run
description: "Use when the user wants original ideas for their own work. Runs a Pioneer round."
version: 0.1.0
author: Acadine Intelligence
license: MIT
---

# Run a Pioneer round

Pioneer is an inverted search. A normal search finds what exists. Pioneer finds what does not exist yet and should, for this user's own work. The aim is a small original thing the user can build: a micro innovation.

Pioneer is not a tool recommender. When an existing tool already does the job, say so and stop pitching the gap. That honest answer is a result.

You write the queries, the gaps and the rulings. The plugin fetches, checks your citations, scores and decides the verdict. You cannot set a score.

## Steps

1. Call `pioneer_seed`. Pass `steer` when the user named a direction, and a `title` of 3 to 7 plain words that names this round. Refer to rounds and gaps by their titles when you talk to the user; ids are for tool calls. Read the seed: the project, the user's goals, what they keep doing by hand, and what they already have.
2. Name 3 to 6 frictions. Write 6 to 10 search queries a stranger with the same problem would type, 2 to 5 plain words each. Queries leave the machine. Put no name, company, path, amount or private fact in one.
3. Call `pioneer_scout` with the queries. If you have web search, Reddit, X or paper tools, run them on the same frictions and pass the results as `signals`.
4. Read the whole ledger. Write 4 to 8 gaps. Each gap names who it is for, what it does and what is new in how it does it. Cite Signal ids. Rate need, value, counterfactual, durability and fit from 1 to 5. Call `pioneer_submit`.
5. For the top three gaps, call `pioneer_absence` with 3 to 6 queries: the words someone would use to find this product if it existed. Then web-search the same words yourself when you can.
6. Rule on every candidate (solves, partial, unrelated). Add every rival you found or already know under `found`. Call `pioneer_absence` again with the rulings.
7. Call `pioneer_board`. On Hermes Desktop, show the board with the `::preview` line it returns. On other surfaces, print its `text`.
8. Say what each verdict means for the user, in one line per gap. Then offer one next move: expand the strongest gap with `pioneer_seed(expand=<gap id>)`.

## Verdicts

- pioneer: nothing found that does it, and people need it. Worth building.
- iterate: one measure is weak. The verdict names it. Expand the gap or gather evidence for that measure.
- beat: an existing tool covers part of it. The gap is the difference. Narrow the gap to that difference.
- adopt: an existing tool does it. Tell the user to use that tool.
- park: no need was shown. Say so.
- unchecked: no absence check yet. Never present an unchecked gap as original.

## Rules

- Rate honestly. A crowded field is not a gap. An inferred need is a 1 or a 2.
- "Nothing exists" is a claim. Search for the product before you rule. Name every rival you know.
- A score shown as "-" or "?" is unmeasured. Never read it as zero, and never fill it in yourself.
- Need is measured again in every child round. It is not inherited from the parent gap.
- Low durability is allowed. Say how long the opening lasts and what would close it.
- When searches fail, the board says how many. Report that next to the result.
- Building a gap, publishing it or spending money on it is the user's decision.

## Setup

`pioneer_setup` lists the sources, the optional second judge and the seed inputs, with what each one sends and costs, plus recommendations for this install. Only the user changes a switch: `/pioneer enable <id>`, `/pioneer disable <id>`, `/pioneer judge off|llm|jev`.
