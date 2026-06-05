# CMR Client Health — MCP Server

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> An MCP server that gives Client Success teams an instant, natural-language health read on
> any client account — modeled on Rustici Content Controller's reporting layer.

Ask a question like *"How is BioPharma Inc. doing ahead of their renewal?"* in any MCP
client (Claude Desktop today, a Slack bot tomorrow) and get back the courses that are
underperforming, whether their content is current, and how they receive content — without
anyone pulling and reading a report by hand.

---

## The problem

CMR Institute produces SME-vetted life-sciences training and distributes it to
pharma / medical-device clients through **Rustici Content Controller**. Roughly **40% of
those clients have no LMS of their own** — they consume content through Content Controller
**Launcher** links. For those accounts, **CMR is the only party** that can see learner
engagement.

That engagement data lives in reports someone has to pull and read manually. Renewal risk —
a course nobody is finishing, compliance content that has gone stale — hides in that data
until it's a renewal conversation. This server surfaces it conversationally instead.

## What it does

Three tools, reachable in natural language from any MCP client:

| Tool | Answers |
|------|---------|
| `get_client_health(account_id)` | "How is this client doing overall?" — per-course completion, scores, content freshness, delivery method, renewal date, plus a computed summary. |
| `get_lowest_performing_courses(account_id, limit=3)` | "Where is the renewal risk?" — worst-completion courses with a one-line risk note each. |
| `get_launcher_clients()` | "Which accounts have no LMS, so we're their only visibility?" — the highest monitoring priority. |

Build the tools once; every MCP client reuses them.

### Beyond tools — the full MCP surface

Most MCP servers stop at tools. This one implements all three MCP primitives, because a
real CSM workflow needs more than model-triggered actions:

| Primitive | Name | What it's for |
|-----------|------|---------------|
| **Resource** (app-controlled context) | `clients://directory` | A read-only roster of every account — id, name, delivery method, renewal date, course count. The host app can attach it up front so the model knows the valid, correctly-spelled account names without spending a tool round-trip. |
| **Prompt** (user-invokable template) | `renewal_health_briefing(account)` | The CSM's standard pre-renewal review, packaged as a reusable, parameterized template (it shows up as a named command in the client). It orchestrates all three tools into one repeatable play, so anyone on the team runs the whole briefing by name instead of remembering the question sequence. |

- **Tools** are *model-controlled* — the LLM decides when to call them.
- **Resources** are *app-controlled* — read-only context the host attaches.
- **Prompts** are *user-controlled* — named templates a person triggers.

## Architecture

```
  ┌─────────────────────┐   stdio    ┌──────────────────┐         ┌────────────────────────────┐
  │  MCP Client          │ <───────>  │  FastMCP server  │ <────>  │  mock data                 │
  │  (Claude Desktop)    │  (JSON-RPC │  (server.py)     │         │  (models Content           │
  │                      │  subprocess)│  3 tools         │         │   Controller               │
  │                      │            │  + 1 resource    │         │   usage/LearnerHistory)    │
  │                      │            │  + 1 prompt      │         │                            │
  └─────────────────────┘            └──────────────────┘         └────────────────────────────┘
```

The mock-data lookup is the **only** thing that's fake. Swapping it for a real Content
Controller integration means changing **one function body per tool** — replace the JSON
lookup with an authenticated automation-API call. The tool contract (names, arguments,
docstrings — the part the LLM sees and reasons about) stays **identical**, so nothing
downstream has to change.

## The post-parse note

This is the **reporting / analytics** layer. It sits *downstream* of SCORM/xAPI parsing.
Pulling structured course data out of raw content packages is a separate, hard problem that
**Rustici Generator** solves; this server consumes the already-structured, post-parse
reporting data. It deliberately makes no claim to parse SCORM itself.

## What's real vs. modeled in the data

The credibility win is in **naming the boundary**, not blurring it:

- **Real** (from Rustici Content Controller v4.1 release notes): the endpoint **names**
  (`usage/LearnerHistory`, `usage/RegistrationHistory`, `usage/InteractionHistory`), the
  convention of **string IDs**, and the **CourseVersion** concept.
- **Modeled / approximate:** the exact **field shape** of `data/mock_data.json`. It's a
  reasonable approximation of the live response, not a verified copy. In production these
  fields would be mapped against the actual automation-API output.

---

## Setup

Requires Python 3.10+ and [`uv`](https://docs.astral.sh/uv/) (falls back to `pip`).

```bash
# from the project directory
uv run server.py        # starts the server over stdio (Ctrl-C to stop)
uv run test_local.py    # runs the local smoke test for all three tools
```

> Don't have `uv`? `pip install "fastmcp>=3.4,<4"` then `python server.py`.

### Install into Claude Desktop

**Primary (recommended) — let FastMCP write the config.** Lowest-risk; try this first.
It auto-detects the Claude Desktop config location and writes the entry (expects Claude
Desktop in its default install location):

```bash
fastmcp install claude-desktop server.py
```

**Fallback — manual config.** Use this if the CLI can't find the config or Claude Desktop
is installed somewhere non-standard. Edit `claude_desktop_config.json` in this repo,
replace the path with your **absolute** project path, and paste it into Claude Desktop's
config file. The `--with fastmcp` flag isolates the dependency so a missing global install
can't break the launch:

```json
{
  "mcpServers": {
    "cmr-client-health": {
      "command": "uv",
      "args": ["run", "--with", "fastmcp", "--directory",
               "/ABSOLUTE/PATH/TO/cmr-client-health-mcp", "fastmcp", "run", "server.py"]
    }
  }
}
```

Claude Desktop's config file lives at:
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Gotchas that silently break it:
- The `--directory` path **must be absolute** — relative paths fail in Claude Desktop.
- **Validate the JSON** — a single trailing comma silently breaks the whole config.
- **Fully quit and reopen** Claude Desktop after editing — closing the window is not
  enough; the config is only read on a cold start.
- Verify the server appears under the **Developer** tab / the tools (🔌) icon before
  relying on it.

## Demo prompt

Paste this into Claude Desktop once the server is connected:

> "BioPharma Inc.'s renewal is coming up. Give me a health read — which courses are
> underperforming, is their content current, and are they on Launcher or their own LMS?
> Then draft a short check-in note I can send their Client Success Manager."

Claude will call `get_client_health` and `get_lowest_performing_courses`, see the two
seeded problem courses (a ~38%-completion Pharmacovigilance course and a stale GxP
Compliance course), note that BioPharma is on **Launcher** (so CMR is their only
visibility), and draft the note.

## Roadmap / "in production"

- **Swap mock for the live automation API** — replace each tool's data lookup with an
  authenticated (Bearer-token) Content Controller call; the tool contract is unchanged.
- **`get_content_freshness`** — a freshness view across *all* clients, not just one.
- **Streamable HTTP transport + auth** — so a shared team Slack bot can hit one server
  instead of every CSM running a local copy.
- **Layer Rustici Generator's parsed JSON** — for content-level Q&A on top of the
  engagement reporting.

## Disclaimer

Built on **mock data** shaped to mirror Content Controller's reporting schema. It is not
affiliated with, nor connected to, any live CMR Institute or Rustici system, and exposes
no real customer data.
