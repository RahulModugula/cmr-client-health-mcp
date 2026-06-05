"""CMR Client Health — an MCP server for spotting renewal risk in learning-engagement data.

WHAT THIS IS
------------
An MCP (Model Context Protocol) server that exposes "client health" tools a Client
Success Manager would use to read an account's learning engagement at a glance and spot
renewal risk before it becomes a churn surprise.

It models the *reporting / analytics* layer that sits DOWNSTREAM of Rustici Content
Controller's automation API. Content Controller distributes SME-vetted training content
to pharma / medical-device clients; for the ~40% of CMR's clients that have no LMS of
their own and consume content through Content Controller "Launcher" links, CMR is the
*only* party with visibility into learner engagement — so proactive monitoring matters
most there.

WHAT THIS IS NOT
----------------
- It does NOT parse SCORM/xAPI packages. Parsing structured course data out of raw
  content packages is a separate, hard problem that Rustici *Generator* solves. This
  layer is strictly post-parse: it consumes already-structured reporting data.
- It does NOT touch any live system. All data is MOCK (see data/mock_data.json).

ACCURACY BOUNDARY (state this proactively — naming it is the credibility win)
----------------------------------------------------------------------------
The endpoint NAMES referenced here (usage/LearnerHistory, usage/RegistrationHistory,
usage/InteractionHistory), the string-ID convention, and the CourseVersion concept are
REAL — taken from Rustici Content Controller v4.1 release notes. The exact FIELD SHAPE of
the mock data is a reasonable APPROXIMATION, not a verified copy of the live response. In
a real integration these fields would be mapped against the actual automation-API output;
swapping mock for live means changing one function body per tool, leaving the tool
contract (the part the LLM sees) identical.
"""

import json
from datetime import date, datetime
from pathlib import Path

from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Business-rule constants — named, not magic numbers, so they are easy to
# defend and adjust. A CSM lead could tune these without touching tool logic.
# ---------------------------------------------------------------------------

# A course below this completion rate is flagged as underperforming. 60% is a
# defensible default for required life-sciences training: most clients expect a
# clear majority of assigned learners to finish. It is a business rule, not a
# law of nature — adjust per account or per therapeutic area as needed.
LOW_COMPLETION_THRESHOLD = 60.0

# Content older than this is flagged as "stale". 365 days approximates the
# "12 months" review cadence common for compliance content (regulations and SOPs
# drift year to year). We use a plain day count rather than pulling in dateutil so
# the only third-party dependency stays fastmcp; the ~leap-day imprecision is
# irrelevant at this granularity.
STALE_AFTER_DAYS = 365

# ---------------------------------------------------------------------------
# Load the mock data ONCE at import time.
#
# We resolve the path relative to THIS file (__file__), not the current working
# directory. Under stdio transport, Claude Desktop launches the server as a
# subprocess with a working directory we do not control — a relative "data/..."
# path would silently fail to load. Anchoring to the module file is the standard
# fix for that common stdio-launch footgun.
# ---------------------------------------------------------------------------
DATA_PATH = Path(__file__).parent / "data" / "mock_data.json"
with DATA_PATH.open(encoding="utf-8") as f:
    _DATA = json.load(f)

ACCOUNTS = _DATA["accounts"]

mcp = FastMCP("CMR Client Health")

# ---------------------------------------------------------------------------
# AUTH STUB (present + explained, not enforced — this is the demo boundary)
#
# In a production integration against Content Controller's automation API, every
# tool call would first validate a Bearer token, because CMR's content and the
# engagement data derived from it are IP-protected and gating matters:
#
#     def _require_auth(token: str) -> None:
#         # Validate `token` against the Content Controller automation-API
#         # credentials (e.g. an OAuth2 client-credentials exchange) and raise
#         # if it is missing, expired, or unauthorized for this tenant.
#         ...
#
# It is omitted here because the demo runs entirely on local mock data with no
# live system to authenticate against. This is the one seam where real-world
# security would attach.
# ---------------------------------------------------------------------------


def _resolve_account(identifier: str) -> dict:
    """Resolve a client by account_id OR by a case-insensitive account_name match.

    The convenience here is deliberate: a CSM (or the LLM relaying their words) will
    naturally say "BioPharma Inc." rather than "acct-001", so we accept either. We match
    on a normalized (lowercased, stripped) name so trailing spaces or casing do not matter.

    Raises a clear ValueError listing valid IDs when nothing matches. FastMCP surfaces a
    raised exception to the model as a tool error rather than crashing the server — which
    also mirrors Content Controller v4.1's real behavior of returning a clean 404 for an
    unknown account rather than a 500.
    """
    needle = identifier.strip().lower()
    for account in ACCOUNTS:
        if account["account_id"].lower() == needle:
            return account
        if account["account_name"].strip().lower() == needle:
            return account

    valid = ", ".join(f'{a["account_id"]} ({a["account_name"]})' for a in ACCOUNTS)
    raise ValueError(
        f"No client account matched '{identifier}'. "
        f"Provide an account_id or exact account name. Valid accounts: {valid}."
    )


def _is_stale(last_content_update: str, today: date) -> bool:
    """Return True if content was last updated more than STALE_AFTER_DAYS ago."""
    updated = datetime.strptime(last_content_update, "%Y-%m-%d").date()
    return (today - updated).days > STALE_AFTER_DAYS


@mcp.tool
def get_client_health(account_id: str) -> dict:
    """Return a full learning-engagement health snapshot for a single client account,
    modeled on Content Controller's usage/LearnerHistory report. Includes per-course
    completion rates, average scores, content freshness (last update date), the client's
    delivery method (Launcher vs. their own LMS), and contract renewal date.

    Use this when someone asks how a specific client is doing, wants a health check before
    a renewal, or needs an overview of a client's engagement.

    Args:
        account_id: The client account ID (e.g. 'acct-001'). Case-insensitive match also
                    accepted on account_name for convenience.
    """
    account = _resolve_account(account_id)
    courses = account["courses"]
    today = date.today()

    # Overall completion rate is weighted by registrations (total completions / total
    # registrations), not a plain average of per-course rates. Weighting prevents a tiny
    # 5-seat course from swinging the headline number as much as a 300-seat rollout.
    total_registrations = sum(c["registrations"] for c in courses)
    total_completions = sum(c["completions"] for c in courses)
    overall_completion_rate = (
        round(total_completions / total_registrations * 100, 1)
        if total_registrations
        else 0.0
    )

    courses_below_threshold = sum(
        1 for c in courses if c["completion_rate"] < LOW_COMPLETION_THRESHOLD
    )
    stale_courses = sum(1 for c in courses if _is_stale(c["last_content_update"], today))

    return {
        "account_id": account["account_id"],
        "account_name": account["account_name"],
        "delivery_method": account["delivery_method"],
        "contract_renewal_date": account["contract_renewal_date"],
        "courses": courses,
        "summary": {
            "course_count": len(courses),
            "overall_completion_rate": overall_completion_rate,
            "courses_below_completion_threshold": courses_below_threshold,
            "stale_courses": stale_courses,
            "low_completion_threshold": LOW_COMPLETION_THRESHOLD,
            "staleness_window_days": STALE_AFTER_DAYS,
        },
    }


@mcp.tool
def get_lowest_performing_courses(account_id: str, limit: int = 3) -> dict:
    """Return the lowest-completion courses for a client, sorted ascending by completion
    rate. Use this to surface renewal risk: low completion means the client isn't getting
    value from the content, which threatens contract renewal.

    Args:
        account_id: The client account ID or name.
        limit: How many of the worst-performing courses to return (default 3).
    """
    account = _resolve_account(account_id)
    today = date.today()

    ranked = sorted(account["courses"], key=lambda c: c["completion_rate"])
    worst = ranked[: max(0, limit)]

    results = []
    for course in worst:
        stale = _is_stale(course["last_content_update"], today)
        low = course["completion_rate"] < LOW_COMPLETION_THRESHOLD

        # A one-line, action-oriented note the CSM (or the LLM) can act on directly.
        # The combined low+stale case is the loudest signal: the content is both
        # under-consumed and out of date, so re-engagement alone won't fix it.
        if low and stale:
            risk_note = "Low completion AND content >12mo old — refresh content, then re-engage learners"
        elif low:
            risk_note = "Low completion — consider re-engagement outreach"
        elif stale:
            risk_note = "Content >12mo old — review for a freshness update"
        else:
            risk_note = "Within healthy range"

        results.append(
            {
                "course_id": course["course_id"],
                "title": course["title"],
                "therapeutic_area": course["therapeutic_area"],
                "completion_rate": course["completion_rate"],
                "avg_score": course["avg_score"],
                "registrations": course["registrations"],
                "completions": course["completions"],
                "last_content_update": course["last_content_update"],
                "is_stale": stale,
                "risk_note": risk_note,
            }
        )

    return {
        "account_id": account["account_id"],
        "account_name": account["account_name"],
        "contract_renewal_date": account["contract_renewal_date"],
        "limit": limit,
        "lowest_performing_courses": results,
    }


@mcp.tool
def get_launcher_clients() -> dict:
    """Return all clients delivered via Content Controller Launcher (i.e. clients with NO
    LMS of their own). For these clients, CMR is the only party with visibility into learner
    engagement — so proactive monitoring matters most here. Use this to identify which
    accounts need CMR-side engagement monitoring.
    """
    launcher_accounts = [a for a in ACCOUNTS if a["delivery_method"] == "launcher"]

    clients = [
        {
            "account_id": a["account_id"],
            "account_name": a["account_name"],
            "contract_renewal_date": a["contract_renewal_date"],
            # Surface the renewal date alongside so the model can spot the highest-priority
            # combination: a Launcher client (no client-side LMS) with a near-term renewal.
            "monitoring_note": (
                "Launcher delivery: no client-side LMS, so CMR is the sole source of "
                "engagement visibility. Prioritize proactive health checks here."
            ),
        }
        for a in launcher_accounts
    ]

    return {
        "delivery_method": "launcher",
        "launcher_client_count": len(clients),
        "why_this_matters": (
            "~40% of CMR clients have no LMS of their own and consume content through "
            "Launcher links. CMR is the only party watching their engagement data, so "
            "these accounts carry the highest monitoring priority — especially near renewal."
        ),
        "clients": clients,
    }


# ===========================================================================
# RESOURCE — app-controlled context (the other half of MCP, beyond tools)
#
# Tools are MODEL-controlled: the LLM decides when to call them. A resource is
# APP-controlled read-only context the host can attach to the conversation up
# front. Exposing the client directory as a resource means a CSM-facing app can
# show "which accounts exist" without spending a tool round-trip — and it gives
# the model the exact, correctly-spelled account names so it never has to guess.
# This is the natural fit for a small, stable reference list like our roster.
# ===========================================================================
@mcp.resource("clients://directory")
def client_directory() -> dict:
    """The full roster of client accounts: id, name, delivery method, renewal date,
    and course count. Read-only reference context for any client-health workflow."""
    return {
        "client_count": len(ACCOUNTS),
        "clients": [
            {
                "account_id": a["account_id"],
                "account_name": a["account_name"],
                "delivery_method": a["delivery_method"],
                "contract_renewal_date": a["contract_renewal_date"],
                "course_count": len(a["courses"]),
            }
            for a in ACCOUNTS
        ],
    }


# ===========================================================================
# PROMPT — the CSM's renewal-review workflow, packaged as a reusable template
#
# The third MCP primitive (after tools + resources) is USER-controlled: prompts
# surface in the client as named, parameterized templates (e.g. a slash command).
# A Client Success Manager runs the SAME multi-step health review before every
# renewal. Encoding that sequence once, here, means anyone on the team triggers
# the whole workflow by name instead of remembering which questions to ask in
# which order — and it composes the three tools above into one repeatable play.
# ===========================================================================
@mcp.prompt
def renewal_health_briefing(account: str) -> str:
    """Generate a complete pre-renewal health briefing for one client account."""
    return (
        f"You are helping a CMR Client Success Manager prepare for the upcoming renewal "
        f"of the client '{account}'. Produce a concise health briefing:\n\n"
        f"1. Call get_client_health('{account}') for the overall snapshot — note the "
        f"overall completion rate, how many courses are below threshold, and how many are "
        f"stale.\n"
        f"2. Call get_lowest_performing_courses('{account}') to surface the specific "
        f"renewal risks, and include each course's risk_note.\n"
        f"3. State whether this is a Launcher client (no client-side LMS) — if so, flag "
        f"that CMR is their only source of engagement visibility.\n"
        f"4. Note how close the contract_renewal_date is.\n"
        f"5. Finish with a short, friendly check-in note the CSM can send.\n\n"
        f"Cite the actual numbers; keep it skimmable."
    )


if __name__ == "__main__":
    mcp.run()  # stdio transport by default
