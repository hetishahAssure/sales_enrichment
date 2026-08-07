# Weekly Funding Discovery Workflow Documentation

Workflow file: `n8n/weekly_funding.updated.json`
n8n workflow name: **AssureSoft — Weekly Funding Discovery**

## 1. Overview & Purpose

* **Goal**: Automatically discover software/tech companies that announced or closed a funding round in the last 7 days (recently funded companies are strong prospects for AssureSoft's nearshore engineering services), create Salesforce Accounts for companies not already in CRM, and email the Sales team a weekly digest (CSV) of all findings with their Salesforce match status.
* **Owner**: Marketing/Sales Automations — maintained by Heti Shah (`heti.shah@assuresoft.com`).
* **Environment**: Production n8n instance. **Note:** the workflow is exported with `"active": false` — it must be activated in n8n for the schedule to fire.

## 2. Trigger Mechanism

* **Type**: Cron Schedule (`Schedule Trigger` node) plus an `Error Trigger` node for hard-failure notification.
* **Frequency**: `0 21 * * 6` — every **Saturday at 21:00** in the n8n instance timezone. Verify the instance timezone if the run time matters (weekend run avoids competing with weekday workflows and lands the digest in inboxes before Monday).

## 3. Credentials & Dependencies

* **Required Integrations**:
  * Anthropic Messages API (`POST https://api.anthropic.com/v1/messages`) using model `claude-haiku-4-5-20251001` with the `web_search_20250305` tool
  * Salesforce (Accounts: read all + create)
  * SMTP (outbound email)
* **Credential Names** (exact names in n8n — reuse these, do not create duplicates):

| Credential name | Type | Used by |
|----|----|----|
| `Salesforce account` | Salesforce OAuth2 | Get Salesforce Accounts, Create Salesforce Account |
| `Anthropic account` | Anthropic API | Claude Funding Discovery |
| `SMTP account` | SMTP | Send an Email |

* **Email addresses**: sends from `n8n.sales@assuresoft.com.bo` to `sales@assuresoft.com` (both hardcoded in the `Send an Email` node).

## 4. Step-by-Step Data Flow

1. **Trigger** (`Schedule Trigger`): fires Saturday 21:00; no payload.
2. **Get Salesforce Accounts** (`Salesforce`, get all): fetches **all** Accounts with fields `Id, Name, Website` for later dedupe. `onError: continue` — a failure here does not abort the run (it may emit an error item instead of Account rows).
3. **Collect SF Accounts** (`Code`): collapses input into a single item so the rest of the chain runs once. Counts **only valid Account rows** (`truthy Id`/`id` and no `error` key) into `_sfAccountCount`, so a failed fetch that emits a lone error item is counted as `0`, not `1`.
4. **Prepare Funding Discovery** (`Code`): computes the 7-day window (today minus 7 days → today, ISO dates) and builds the Anthropic request body (`_claudeBody`): a prompt instructing Claude to web-search Crunchbase/TechCrunch/LinkedIn for software/tech companies funded in that window and return a strict JSON array (15–40 high-confidence matches, no fabrication, `[]` if none) with fields such as `company_name`, `website`, `funding_stage`, `funding_amount`, `funding_date`, `investors`, `crunchbase_url`.
5. **Claude Funding Discovery** (`HTTP Request`, Anthropic credential): POSTs the body to the Anthropic API, 120 s timeout, `onError: continue` so API errors flow into the parser as a soft failure.
6. **Parse Funding Companies** (`Code` — data transformation): extracts the first `[...]` JSON array from Claude's text blocks and `JSON.parse`s it into one item per company; normalizes strings, converts `employee_count` ranges to a midpoint integer, and builds a multi-line Salesforce `Description` (funding stage/amount/date, investors, Crunchbase URL, team size, source tag). On any parse/API error it emits a single sentinel item with `_empty: true` and `_parseError` set, so the run still completes and reports the failure.
7. **Dedupe vs Salesforce** (`Code`): loads Salesforce Accounts via the same valid-row filter as Collect (truthy `Id`/`id`, no `error`). Marks each company `_isNew` / `_skipCreate` by comparing normalized Account Name (lowercased, `&`→`and`, alphanumerics only) **or** normalized Website domain (scheme/`www.`/path stripped). Records `_matchReason` (`name`, `website`, `name+website`, or `none`) and `_matchedAccountId`. Every output item — including the empty-result sentinel — carries `_sfAccountCount` so the downstream guard always has the value.
8. **Conditional routing** — the deduped items fan out to two branches:
   * **Branch A — Salesforce upsert**: `Only New Accounts` (`Filter`, AND of two conditions): `_isNew === true` **and** `_sfAccountCount > 0` (empty-fetch guard). If zero valid Accounts were available for dedupe, no item passes the filter and `Create Salesforce Account` never runs. Otherwise `Create Salesforce Account` creates an Account with Name, Website, Industry, NumberOfEmployees, and the rich Description. `onError: continue` — individual create failures don't stop the run.
   * **Branch B — Digest email**: `Build Funding Digest` (`Code`) emits one clean CSV row per company (including `salesforce_status` = `new`/`existing`, or `skipped (SF fetch empty)` when the guard tripped, and `match_reason`) → `Convert Digest to CSV` (`weekly_funding_digest.csv`) → `Finalize Email` (`Code`) picks one of four outcomes (`outcome`: `failure` | `guard_skipped` | `success`):
     * soft failure (`_parseError` set): "⚠️ … FAILED" subject, error details in body;
     * companies found but `_sfAccountCount === 0`: "⚠️ … Salesforce creation SKIPPED" — body explains the Salesforce Account list came back empty, that 0 accounts were created to avoid duplicates, and asks the reader to check the Salesforce connection; CSV still attached; `newCount` forced to `0`;
     * companies found (normal): "✅ Weekly funding digest … N companies (M new)" with a per-company summary list in the body and the CSV attached;
     * no companies: "✅ … no new matches".
9. **Action** (`Send an Email`): sends the digest (attaching the CSV binary when present) from `n8n.sales@assuresoft.com.bo` to `sales@assuresoft.com`.

## 5. Error Handling & Edge Cases

* **Soft failures (run continues, Sales still notified)**:
  * `Claude Funding Discovery` and `Get Salesforce Accounts` use `onError: continueRegularOutput`, so an API error does not abort the run.
  * `Parse Funding Companies` catches all parse/response errors and emits a `_parseError` sentinel; `Finalize Email` turns this into a "⚠️ FAILED" email so the Sales team knows the weekly file is delayed. No retry is attempted.
  * **Empty / failed Salesforce fetch (guard)**: `Collect SF Accounts` and `Dedupe vs Salesforce` both ignore error items and require a truthy Account `Id`. If the valid count is `0`, the `Only New Accounts` filter (`_sfAccountCount > 0`) blocks all Account creation, CSV rows are marked `salesforce_status: skipped (SF fetch empty)`, and the email subject switches to "⚠️ … Salesforce creation SKIPPED". The digest branch is unaffected — the email always goes out. Companies from a skipped week are **not** automatically retried; see Risks.
  * Empty result (`[]` from Claude) produces a "no new matches" success email, not a failure.
* **Hard failures**: the `Error Trigger` → `Build Failure Email` → `Send an Email` path emails a failure notice with the workflow name, last node executed, error message (truncated to 300 chars), and execution URL. **Verify** that this workflow is set as its own Error Workflow in n8n workflow settings — an `Error Trigger` node only fires if the workflow is registered as the error handler.
* **Per-record failures**: `Create Salesforce Account` continues on error, so one bad record (e.g. picklist violation on Industry) doesn't block the others — but these failures are silent (see Risks).
* **Dedupe edge cases**: companies with no name are skipped (`_skipCreate: true, _matchReason: "empty"`); missing websites fall back to name-only matching.

## 6. Risks & Gaps and Mitigation

| # | Risk / Gap | Impact | Mitigation |
|----|----|----|----|
| 1 | **[MITIGATED] Duplicate Accounts if the Salesforce fetch fails / returns empty.** Previously, `onError: continue` + empty dedupe list marked every company `new`. | High — bulk duplicate Accounts in CRM | **Implemented:** `Only New Accounts` requires `_isNew === true` AND `_sfAccountCount > 0`. Zero valid Accounts blocks creation; digest switches to "⚠️ Salesforce creation SKIPPED"; CSV rows marked `skipped (SF fetch empty)`. Residual: #12–#14. |
| 2 | **LLM hallucination / data quality.** Despite prompt guardrails, Claude may fabricate or mis-attribute funding events, amounts, or websites. | Medium — polluted CRM data, wasted outreach | Keep the "corroborate via search" prompt rule; spot-check the weekly CSV; consider requiring a `crunchbase_url` or source link before creating the Account. |
| 3 | **Fragile response parsing.** The parser regex grabs the first `[...]` in Claude's text; markdown wrappers or truncated output (max_tokens 8000) break it. | Medium — soft-failure week, no digest data | Failure is already surfaced via the ⚠️ email. To harden: raise `max_tokens`, or use Anthropic structured outputs / a stricter "JSON only" retry. |
| 4 | **Silent Salesforce create failures.** Creates continue on error, and the normal-success email counts `_isNew` items as "created in Salesforce" regardless of the actual API result. | Medium — email overstates what's in CRM | Capture create results and reconcile counts in `Finalize Email`, or route create errors to a warning section in the email. |
| 5 | **Full-org Account scan.** `returnAll: true` fetches every Account each run; dedupe is an O(companies × accounts) in-memory loop. | Low now, grows with org size (API limits, memory) | Switch to targeted SOQL lookups (query by the ~15–40 discovered names/domains) once Account volume grows. |
| 6 | **[MITIGATED] Unused Config / hardcoded recipients.** The old `Config.emailTo` node was unused while `Send an Email` hardcodes recipients. | Low — maintainer confusion | **Resolved:** the `Config` node was removed from this export. Recipients remain hardcoded (`sales@assuresoft.com` / `n8n.sales@assuresoft.com.bo`); change them in the Send Email node if needed. |
| 7 | **Error Trigger may never fire.** The hard-failure path depends on the workflow being registered as its own Error Workflow in settings; the export does not show this set. | Medium — hard failures go unnoticed | In n8n: Workflow Settings → Error Workflow → select this workflow (or a dedicated error workflow). Test with a forced failure. |
| 8 | **Workflow is inactive in this export** (`"active": false`). | High if unnoticed — nothing runs | Confirm the production instance has it activated; treat activation as part of deployment. |
| 9 | **Dedupe misses fuzzy matches.** Only exact normalized name or apex-domain matches count; subsidiaries, rebrands, or `brand.io` vs `brand.com` slip through. | Low/Medium — occasional duplicates | Acceptable for now; Salesforce duplicate rules and manual review of "NEW" rows in the digest catch stragglers. |
| 10 | **Model and tool version pinning.** `claude-haiku-4-5-20251001` and `web_search_20250305` will eventually be deprecated. | Low — future breakage | Watch Anthropic deprecation notices; the ⚠️ failure email will surface the breakage when it happens. |
| 11 | **[MITIGATED] Guard bypass via error-item count.** A failed Salesforce fetch under `onError: continueRegularOutput` can emit a single error item; counting raw items would make `_sfAccountCount = 1` and let creation through. | High | **Implemented:** both `Collect SF Accounts` and `Dedupe vs Salesforce` count/match only rows with a truthy `Id`/`id` and no `error` key. Still **test by forcing a fetch failure** in a staging copy and confirm the SKIPPED email fires. |
| 12 | **Skipped weeks are never backfilled.** When the guard trips, that week's discovered companies are only in the CSV; the next run covers a new 7-day window, so they are permanently absent from Salesforce unless handled manually. | Medium — lost prospects if nobody acts on the ⚠️ email | The SKIPPED email instructs the reader to check the Salesforce connection. Follow-up runbook: fix the connection, then either manually import the CSV rows or temporarily widen the date window in `Prepare Funding Discovery` and re-run. |
| 13 | **Guard can't distinguish "fetch failed" from "org genuinely has zero Accounts."** In a brand-new/empty Salesforce org the guard would block creation forever. | Low — only matters at bootstrap or after a mass Account purge | Accept for a mature org. If bootstrapping, seed at least one Account or temporarily remove the `_sfAccountCount` condition for the first run. |
| 14 | **Partial fetch is not covered.** The guard only trips at exactly zero *valid* accounts; a truncated fetch (pagination/API limit issue returning, say, 10% of Accounts) passes the guard with an incomplete dedupe list. | Medium — duplicates for companies whose match record was in the missing portion | Track the expected Account count (e.g. compare `_sfAccountCount` against a rolling baseline and skip creation on a large drop); rely on Salesforce duplicate rules as backstop. |
| 15 | **[RESOLVED] Export drift.** The repo previously lagged the live n8n guard changes. | Medium | **Resolved:** `n8n/weekly_funding.updated.json` was replaced with the 2026-08-05 export that includes the guard, valid-row filters, SKIPPED email branch, and Anthropic credential. Keep re-exporting after UI changes. |
| 16 | **Credential type change for Anthropic.** Claude now uses the native `Anthropic account` credential (`anthropicApi`) instead of generic HTTP Header Auth. Restoring an older export, or pointing this node at the old `Header Auth account`, will break discovery. | Medium — silent soft failures until noticed | Ensure `Anthropic account` exists and is selected on `Claude Funding Discovery` after any import. Do not mix the old header-auth credential into this node. |

## 7. Success Criteria

A weekly run is considered successful when **all** of the following hold:

1. The workflow executes automatically Saturday 21:00 (instance timezone) with execution status "Success" in n8n.
2. `sales@assuresoft.com` receives exactly one email per run: the ✅ digest (with `weekly_funding_digest.csv` attached), a ✅ "no new matches" notice, a ⚠️ "Salesforce creation SKIPPED" notice (guard tripped — CSV attached, no Accounts created), or a ⚠️ failure heads-up. **Silence is a failure condition.**
3. The digest lists plausible, corroborable software/tech companies funded within the stated 7-day window (typically 15–40 rows), each with funding stage/amount/date and a `salesforce_status` (`new`, `existing`, or `skipped (SF fetch empty)`).
4. On a normal run, every company marked `new` exists as a Salesforce Account after the run, with Website, Industry, NumberOfEmployees, and the funding summary in Description. On a SKIPPED run, **zero** Accounts are created and the follow-up runbook (risk #12) is executed.
5. No duplicate Accounts are created for companies already in Salesforce (spot-check `EXISTS` rows and Salesforce duplicate reports) — including when the Salesforce fetch fails (the guard must trip, not pass; see risk #11).
6. Anthropic and Salesforce API usage stays within quota (single Claude call and one create per new company per week).
