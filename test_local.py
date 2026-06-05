"""Local smoke test AND demo fallback — calls the tool functions directly and prints
clean, screen-shareable output for all three tools plus the error path.

Two jobs:
  1. Regression guard — the asserts below encode the build spec's acceptance criteria, so
     a wrong-but-silent number fails loudly instead of slipping through.
  2. DEMO FALLBACK — if Claude Desktop won't connect live, run this on the shared screen to
     show the exact same tool outputs the model would receive. Each section leads with a
     glanceable HIGHLIGHT (the punchline), then the full pretty-printed JSON as evidence.

This is intentionally SEPARATE from server.py's `mcp.run()` entry point: stdio transport
reserves stdout for protocol traffic, so printing from inside the running server would
corrupt the stream. Run it standalone:

    uv run test_local.py
"""

import json

from server import (
    client_directory,
    get_client_health,
    get_launcher_clients,
    get_lowest_performing_courses,
    renewal_health_briefing,
)

WIDTH = 74


def banner(label):
    """A loud, unmistakable header so each tool's output is obvious on a shared screen."""
    print("\n" + "=" * WIDTH)
    print(f"  {label}")
    print("=" * WIDTH)


def highlight(lines):
    """The punchline — what to actually look at — before the raw JSON evidence."""
    for line in lines:
        print(f"  {line}")
    print("\n  ── full JSON payload (what the model receives) " + "─" * 26)


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 1 — get_client_health, resolved BY NAME (case-insensitive convenience)
# ─────────────────────────────────────────────────────────────────────────────
banner('TOOL 1  ·  get_client_health("BioPharma Inc.")')
health = get_client_health("BioPharma Inc.")
s = health["summary"]
highlight(
    [
        f'Account : {health["account_name"]}  ({health["account_id"]})',
        f'Delivery: {health["delivery_method"]}      Renewal: {health["contract_renewal_date"]}',
        f'SIGNAL  : overall completion {s["overall_completion_rate"]}%   |   '
        f'{s["courses_below_completion_threshold"]} course(s) below {s["low_completion_threshold"]}%   |   '
        f'{s["stale_courses"]} stale (>12mo)',
    ]
)
print(json.dumps(health, indent=2))
assert health["account_id"] == "acct-001"            # resolved by NAME, not id
assert "summary" in health
assert s["courses_below_completion_threshold"] == 2  # 2 seeded problem courses < 60%
assert s["stale_courses"] == 1                        # 1 seeded stale course (GxP, 2024-09-15)

# ─────────────────────────────────────────────────────────────────────────────
# TOOL 2 — get_lowest_performing_courses (renewal-risk surfacing)
# ─────────────────────────────────────────────────────────────────────────────
banner('TOOL 2  ·  get_lowest_performing_courses("acct-001")')
lowest = get_lowest_performing_courses("acct-001")
worst = lowest["lowest_performing_courses"]
highlight(
    [f'Worst {len(worst)} courses by completion (ascending) — the renewal risk:']
    + [
        f'{i + 1}. {c["completion_rate"]:>5}%  {c["title"][:34]:<34}  {c["risk_note"]}'
        for i, c in enumerate(worst)
    ]
)
print(json.dumps(lowest, indent=2))
assert worst[0]["course_id"] == "crs-pharmacovigilance-2026"  # ~38% completion, worst
assert worst[1]["course_id"] == "crs-gxp-compliance"          # low completion AND stale
assert "Low completion AND content" in worst[1]["risk_note"]  # combined-risk note fires

# ─────────────────────────────────────────────────────────────────────────────
# TOOL 3 — get_launcher_clients (CMR is sole engagement visibility)
# ─────────────────────────────────────────────────────────────────────────────
banner("TOOL 3  ·  get_launcher_clients()")
launchers = get_launcher_clients()
highlight(
    [f'Launcher clients (no client-side LMS → CMR is sole visibility): {launchers["launcher_client_count"]}']
    + [
        f'- {c["account_name"]:<22} ({c["account_id"]})   renewal {c["contract_renewal_date"]}'
        for c in launchers["clients"]
    ]
)
print(json.dumps(launchers, indent=2))
ids = sorted(c["account_id"] for c in launchers["clients"])
assert ids == ["acct-001", "acct-003", "acct-005"], ids
assert launchers["launcher_client_count"] == 3

# ─────────────────────────────────────────────────────────────────────────────
# RESOURCE — clients://directory (app-controlled context, not a tool call)
# ─────────────────────────────────────────────────────────────────────────────
banner("RESOURCE  ·  clients://directory")
directory = client_directory()
highlight(
    [f'Client roster ({directory["client_count"]} accounts) — read-only reference context:']
    + [
        f'- {c["account_name"]:<22} {c["delivery_method"]:<13} {c["course_count"]} courses'
        for c in directory["clients"]
    ]
)
print(json.dumps(directory, indent=2))
assert directory["client_count"] == 5
assert {c["account_id"] for c in directory["clients"]} == {
    "acct-001", "acct-002", "acct-003", "acct-004", "acct-005"
}

# ─────────────────────────────────────────────────────────────────────────────
# PROMPT — renewal_health_briefing (the CSM workflow, packaged as a template)
# ─────────────────────────────────────────────────────────────────────────────
banner('PROMPT  ·  renewal_health_briefing("BioPharma Inc.")')
briefing = renewal_health_briefing("BioPharma Inc.")
highlight(
    [
        "Reusable, user-invokable template that orchestrates all three tools into",
        "the CSM's standard pre-renewal review. Rendered prompt text:",
    ]
)
print("\n" + briefing)
assert "BioPharma Inc." in briefing
assert "get_client_health" in briefing
assert "get_lowest_performing_courses" in briefing

# ─────────────────────────────────────────────────────────────────────────────
# ERROR PATH — unknown account returns a clean message, never a stack trace
# ─────────────────────────────────────────────────────────────────────────────
banner('ERROR PATH  ·  get_client_health("acct-999")')
try:
    get_client_health("acct-999")
except ValueError as e:
    print("  ✓ Clean ValueError (FastMCP surfaces this to the model, server stays up):\n")
    print(f"    {e}")
else:
    raise AssertionError("Expected a ValueError for an unknown account id")

print("\n" + "=" * WIDTH)
print("  ALL ACCEPTANCE CHECKS PASSED ✅   (3 tools + resource + prompt + error path)")
print("=" * WIDTH)
