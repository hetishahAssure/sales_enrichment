# Salesforce Account Enrichment (Hiring signals, weekly) Workflow Documentation

Workflow file: `n8n/salesforce_hiring_enrichment.schedule.workflow.json`  
Source modules: `flatten_report_hiring.js`, `prepare_sf.js`, `merge.js`, `map_salesforce_hiring.js`, `hiring_build_summary_email.js`, `hiring_build_failure_email.js`, `build_salesforce_workflow.py`  
n8n workflow name: **AssureSoft — Salesforce Account Enrichment (Hiring signals, weekly)**

## 1. Overview & Purpose

* **Goal**: Enrich Salesforce Accounts from a **Salesforce Report** cohort with engineering hiring signals (`Is_Hiring_Engineers__c`, `Hiring_Score__c`, `LinkedIn__c`, `Careers_Page__c`, `Open_Job_Openings__c`, `Open_Job_Openings_Count__c`). Complements the Crunchbase funding enrichment workflow.
* **Owner**: Marketing/Sales Automations — maintained by Heti Shah (`heti.shah@assuresoft.com`).
* **Environment**: n8n instance. **Update Account currently PATCHes the Salesforce testing sandbox** (`assuresoft--testing.sandbox.my.salesforce.com`). Export has `"active": false`. Treat as **Staging/sandbox** until production cutover.

**Cohort:** whoever is in the report. There is **no** Skip Enriched / SOQL filter on `Is_Hiring_Engineers__c` — put the right Accounts in the report (and its filters) instead.

## 2. Trigger Mechanism

* **Type**: Cron Schedule (`Every Saturday 20:00`) plus an `Error Trigger`.
* **Frequency**: Weekly — **Saturday at 20:00** (n8n instance timezone).

```
Every Saturday 20:00
  → Get Report (Analytics API GET /analytics/reports/{reportId})
  → Flatten Report (detailColumns + factMap rows → Account API field aliases)
  → Cap Per Run (max 25)
  → Prepare Requests → Claude / JSearch / Theirstack / Apollo
  → Merge & Score → Map to Salesforce
       ├─ Has Changes → Update Account
       └─ Build Run Summary → Send an Email
Error Trigger → Build Failure Email → Send an Email
```

**Deploy note:** Workflow Settings → **Error Workflow** → this workflow.

**Report Id:** set `SF_HIRING_REPORT_ID` when rebuilding, or edit the **Get Report** URL (`…/analytics/reports/00O…`) after import.

## 3. Credentials & Dependencies

| Credential name | Type | Used by |
|-----------------|------|---------|
| `Salesforce account` | Salesforce OAuth2 | Get Report, Update Account |
| `Anthropic account` | Anthropic API | Claude Web Search |
| `Jsearch API Key` | Header Auth | JSearch |
| `Theirstack` | Bearer / Header Auth | Theirstack |
| Apollo Header Auth (as configured) | Header Auth | Apollo |
| `SMTP account` | SMTP | Send an Email |

* **Email**: from `n8n.sales@assuresoft.com.bo` to `sales@assuresoft.com`.

| Field written | Source |
|---------------|--------|
| `Is_Hiring_Engineers__c` | Yes/No/Unknown |
| `Hiring_Score__c` | 0–5 |
| `LinkedIn__c` / `Careers_Page__c` | job URLs |
| `Open_Job_Openings__c` | comma-separated eng role titles (`open_roles`) |
| `Open_Job_Openings_Count__c` | unique eng role count (`open_roles_count`) |
| `Description` | **cleanup only** — strips legacy hiring automation blocks |

Urgency and confidence appear in the **weekly email digest** only (no dedicated SF fields).

### Report columns expected (aliases in `flatten_report_hiring.js`)

| Report column | Account field |
|---------------|---------------|
| `ACCOUNT_ID` | `Id` |
| `ACCOUNT.NAME` | `Name` |
| `URL` | `Website` |
| `ADDRESS1_STATE` | `BillingState` |
| `Account.LinkedIn__c` | `LinkedIn__c` |
| `DESCRIPTION` | `Description` |
| `Account.Is_Hiring_Engineers__c` | `Is_Hiring_Engineers__c` |
| `Account.Hiring_Score__c` | `Hiring_Score__c` |
| `Account.Careers_Page__c` | `Careers_Page__c` |
| `Account.Open_Job_Openings__c` | `Open_Job_Openings__c` |
| `Account.Open_Job_Openings_Count__c` | `Open_Job_Openings_Count__c` |

## 4. Step-by-Step Data Flow

1. **Get Report**: run the configured Analytics report (tabular Account list).
2. **Flatten Report**: one item per row; `dataCells[].value` + aliases above.
3. Cap 25 → research → Merge (`_hiring_status`).
4. **Map**: eligibility gate; write typed fields when research confirms signals; strip legacy Description blobs; do **not** append new Description text.
5. PATCH only when `_hasChanges`; digest email; Error Trigger on hard fail.

## 5. Error Handling & Edge Cases

* Ineligible research (failed APIs / no confirmed signals) does **not** PATCH hiring fields.
* Soft API/PATCH failures continue; digest lists skips and PATCH errors.
* Re-runs enrich whoever is still in the report (including Accounts already enriched) — control that via the report, not workflow filters.
* Cap Per Run (25) still limits API spend per Saturday.

## 6. Risks and Gaps of This Automation and Mitigation

| # | Risk / Gap | Impact | Mitigation |
|----|----|----|----|
| 1 | **Report cohort can re-enrich** already-researched Accounts. | Medium | Narrow report filters / membership; raise Cap carefully. |
| 2 | **No SF field for urgency / confidence.** | Low | Digest email carries those; open roles sync to `Open_Job_Openings__c`. |
| 3 | **Sandbox PATCH / report host.** | High if wrong org | Switch `SF_HOST` / report Id before production. |
| 4 | **Placeholder report Id** (`00OXXXXXXXXXXXXXXX`) if not set. | High | Set `SF_HIRING_REPORT_ID` or edit Get Report URL. |
| 5 | **Silent failures without Error Workflow.** | Medium | Set Error Workflow in n8n. |
| 6 | **LLM / job-board false positives.** | Medium | Spot-check digest. |
| 7 | **Analytics API 2k row limit.** | Medium | Keep report under limit or paginate later. |

## 7. Success Criteria

1. Saturday run succeeds; digest email received.
2. Up to 25 Accounts from the report are researched.
3. Eligible Accounts get field updates; Description is not appended with hiring text.
4. Legacy hiring automation blocks stripped on successful enrich.
5. Cohort membership is controlled by the Salesforce report, not Skip Enriched.

### Rebuild

```bash
cd n8n
SF_HIRING_REPORT_ID=00OyourReportId python3 build_salesforce_workflow.py
```
