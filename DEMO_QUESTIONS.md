# Demo Questions — CMR Client Health MCP

Paste these into Claude Desktop (or any MCP client) once the server is connected.
Ordered from the cleanest "wow" first → progressively deeper. Each note says which
tool(s) fire and what the model should find, so you can narrate while it runs.

> Today's date for staleness math: **2026-06-04**. "Stale" = content not updated in >365 days.

---

## 1. The headline demo (start here)
> **"BioPharma Inc.'s renewal is coming up. Give me a health read — which courses are underperforming, is their content current, and are they on Launcher or their own LMS? Then draft a short check-in note I can send their Client Success Manager."**

- **Fires:** `get_client_health` + `get_lowest_performing_courses`
- **Finds:** Pharmacovigilance Basics at **38.1%** (worst) and Good Clinical Practice (GxP) at **47.5%** — and GxP was last updated **2024-09-15**, so it's both **low completion AND stale** (the loudest risk note). BioPharma is on **Launcher** → CMR is their only visibility. Renews **2026-08-15** (~2 months out).
- **Why it lands:** one natural question → multiple tool calls → a real, actionable draft.

---

## 2. Find the highest-priority accounts to watch
> **"Which of our clients have no LMS of their own? Why do those matter most?"**

- **Fires:** `get_launcher_clients`
- **Finds:** BioPharma Inc., Caldera Devices, Northwind Pharma (all **launcher**). Returns the "~40% of clients, CMR is sole visibility" rationale.
- **Why it lands:** shows the core business insight, not just data.

---

## 3. Pure risk surfacing
> **"Show me the three worst-performing courses at Caldera Devices and what to do about each."**

- **Fires:** `get_lowest_performing_courses` (limit 3)
- **Finds:** Pharmacovigilance **38.7%** (also stale — updated 2024-12-05), HIPAA **41.7%**, Medical Device Regulatory **46.0%**. Each comes back with a one-line risk note.

---

## 4. Compare two accounts (shows the LLM composing tools)
> **"Compare BioPharma Inc. and Apex Biologics — who's healthier heading into renewal?"**

- **Fires:** `get_client_health` twice
- **Finds:** Apex is the healthy contrast — every course **90%+**, all content fresh, renews far out (**2027-02-20**). BioPharma has two failing courses and renews in ~2 months. Clean before/after story.

---

## 5. The "needs everything" account
> **"Northwind Pharma — anything I should worry about before their September renewal?"**

- **Fires:** `get_client_health` + `get_lowest_performing_courses`
- **Finds:** Medical Device Regulatory Compliance at **30.0%** (lowest in the whole dataset) AND stale (updated 2025-07-22 → ~10.5 months, *not quite* stale at 365d — good moment to explain the threshold precisely). Launcher client, renews **2026-09-10**.

---

## 6. Graceful-failure / robustness (only if asked "what if it breaks?")
> **"How is Globex Corp doing?"** (no such account)

- **Fires:** `get_client_health` → raises a clean `ValueError` listing the valid accounts.
- **Why it lands:** shows you handle the unknown-account case the way Content Controller v4.1 does (clean 404, not a 500), and the model recovers gracefully instead of crashing.

---

## Name-matching convenience (mention, don't need to demo)
Every tool accepts **account_id OR account name**, case-insensitive — so "biopharma inc." and "acct-001" both resolve. A CSM talks in names, not IDs.

---

## Quick reference — the seeded accounts

| Account | Delivery | Renewal | Headline |
|---|---|---|---|
| BioPharma Inc. (`acct-001`) | **Launcher** | 2026-08-15 | 2 failing courses, 1 stale — the demo account |
| Meridian Therapeutics (`acct-002`) | LMS dispatch | 2026-11-01 | Healthy, all ~87–90% |
| Caldera Devices (`acct-003`) | **Launcher** | 2026-07-01 | Worst overall — 3 courses under 50% |
| Apex Biologics (`acct-004`) | LMS dispatch | 2027-02-20 | Gold-standard healthy account |
| Northwind Pharma (`acct-005`) | **Launcher** | 2026-09-10 | One course at 30% — single sharp risk |

**Run locally without a client:** `uv run test_local.py` (exercises all three tools).
