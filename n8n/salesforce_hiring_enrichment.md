# Salesforce Account Enrichment (Hiring signals, weekly) Workflow Documentation

Workflow file: `n8n/salesforce_hiring_enrichment.schedule.workflow.json`  
Source modules: `prepare_sf.js`, `merge.js`, `map_salesforce_hiring.js`, `hiring_build_summary_email.js`, `hiring_build_failure_email.js`, `build_salesforce_workflow.py`  
n8n workflow name: **AssureSoft — Salesforce Account Enrichment (Hiring signals, weekly)**

## 1. Overview & Purpose

* **Goal**: Enrich existing Salesforce Accounts with engineering hiring signals on **existing** Account fields (`Is_Hiring_Engineers__c`, `Hiring_Score__c`, `LinkedIn__c`, `Careers_Page__c`) so Sales can prioritize companies actively hiring engineers. Complements the Crunchbase funding enrichment workflow.
* **Owner**: Marketing/Sales Automations — maintained by Heti Shah (`heti.shah@assuresoft.com`).
* **Environment**: n8n instance. **Update Account currently PATCHes the Salesforce testing sandbox** (`assuresoft--testing.sandbox.my.salesforce.com`). Export has `"active": false`. Treat as **Staging/sandbox** until production cutover.

**Skip proxy (no new fields):** an Account is treated as already hiring-enriched when `Is_Hiring_Engineers__c` is populated. Clear that field to allow a re-run.

## 2. Trigger Mechanism

* **Type**: Cron Schedule (`Every Saturday 20:00`) plus an `Error Trigger`.
* **Frequency**: Weekly — **Saturday at 20:00** (n8n instance timezone).

```
Every Saturday 20:00
  → Get Accounts (SOQL WHERE Is_Hiring_Engineers__c = null, LIMIT 500)
  → Skip Enriched (Is_Hiring_Engineers__c empty + no legacy Description markers)
  → Cap Per Run (max 25)
  → Prepare Requests → Claude / JSearch / Theirstack / Apollo
  → Merge & Score → Map to Salesforce
       ├─ Has Changes → Update Account
       └─ Build Run Summary → Send an Email
Error Trigger → Build Failure Email → Send an Email
```

**Deploy note:** Workflow Settings → **Error Workflow** → this workflow.

## 3. Credentials & Dependencies

| Credential name | Type | Used by |
|-----------------|------|---------|
| `Salesforce account` | Salesforce OAuth2 | Get Accounts, Update Account |
| `Anthropic account` | Anthropic API | Claude Web Search |
| `Jsearch API Key` | Header Auth | JSearch |
| `Theirstack` | Bearer / Header Auth | Theirstack |
| Apollo Header Auth (as configured) | Header Auth | Apollo |
| `SMTP account` | SMTP | Send an Email |

* **Email**: from `n8n.sales@assuresoft.com.bo` to `sales@assuresoft.com`.

| Field written | Source |
|---------------|--------|
| `Is_Hiring_Engineers__c` | Yes/No/Unknown (**also skip proxy**) |
| `Hiring_Score__c` | 0–5 |
| `LinkedIn__c` / `Careers_Page__c` | job URLs |
| `Description` | **cleanup only** — strips legacy hiring automation blocks |

Open role titles, urgency, and confidence appear in the **weekly email digest** only (no dedicated SF fields).

## 4. Step-by-Step Data Flow

1. **Get Accounts**: `WHERE Is_Hiring_Engineers__c = null`.
2. **Skip Enriched**: proxy empty + Description does not contain `[Hiring enriched` / `[Auto-enriched`.
3. Cap 25 → research → Merge (`_hiring_status`).
4. **Map**: eligibility gate; write typed fields; strip legacy Description blobs; do **not** append new Description text.
5. PATCH + digest email; Error Trigger on hard fail.

## 5. Error Handling & Edge Cases

* Ineligible research does **not** set `Is_Hiring_Engineers__c` → Account retries next week.
* Soft API/PATCH failures continue; digest lists skips and PATCH errors.
* To **re-enrich** an Account: clear `Is_Hiring_Engineers__c` (and remove legacy Description markers if present).
* Sales-filled `Is_Hiring_Engineers__c` will also exclude the Account from automation.

## 6. Risks and Gaps of This Automation and Mitigation

| # | Risk / Gap | Impact | Mitigation |
|----|----|----|----|
| 1 | **Proxy skip is coarse** — any value on `Is_Hiring_Engineers__c` blocks re-run. | Medium | Clear field to retry; document for Sales. |
| 2 | **No field for open roles / urgency.** | Medium | Digest email carries detail; add SF fields later if needed. |
| 3 | **Sandbox PATCH host.** | High if wrong org | Switch `SF_UPDATE_URL` before production. |
| 4 | **Legacy Description markers** still skip Accounts. | Medium | Clear markers or leave skipped (already “done”). |
| 5 | **Silent failures without Error Workflow.** | Medium | Set Error Workflow in n8n. |
| 6 | **LLM / job-board false positives.** | Medium | Spot-check digest. |

## 7. Success Criteria

1. Saturday run succeeds; digest email received.
2. Up to 25 Accounts with blank `Is_Hiring_Engineers__c` researched.
3. Eligible Accounts get field updates; Description is not appended with hiring text.
4. Legacy hiring automation blocks stripped on successful enrich.
5. Already-populated `Is_Hiring_Engineers__c` Accounts are not re-billed.

### Rebuild

```bash
cd n8n && python3 build_salesforce_workflow.py
```
