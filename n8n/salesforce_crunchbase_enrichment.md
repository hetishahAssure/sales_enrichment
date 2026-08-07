# Salesforce Account Enrichment (Crunchbase funding, weekly) Workflow Documentation

Workflow file: `n8n/salesforce_crunchbase_enrichment.schedule.workflow.json`  
Source modules: `map_salesforce_cb.js`, `cb_build_summary_email.js`, `cb_build_failure_email.js`, `build_salesforce_workflow.py`  
n8n workflow name: **AssureSoft — Salesforce Account Enrichment (Crunchbase funding, weekly)**

## 1. Overview & Purpose

* **Goal**: Enrich existing Salesforce Accounts with funding/investor intelligence on **existing** Account and `crunchbase__*` fields. Complements hiring-signal enrichment; does not discover new companies.
* **Owner**: Marketing/Sales Automations — maintained by Heti Shah (`heti.shah@assuresoft.com`).
* **Environment**: n8n → Salesforce **testing sandbox** PATCH host. Export `"active": false`.

**Skip proxy (no new fields):** Account is treated as already funding-enriched when **any** of these is set:

* `Crunchbase_URL__c`
* `Investors__c`
* `crunchbase__Total_Funding_USD__c`
* `crunchbase__Latest_Round_Funding_Type__c`
* `Latest_Funding_Date__c`

Clear all of those to allow a re-run.

## 2. Trigger Mechanism

* **Type**: Cron Schedule (`Every Sunday 20:00`) plus an `Error Trigger`.
* **Frequency**: Weekly — **Sunday at 20:00**.

```
Every Sunday 20:00
  → Get Accounts (SOQL: all funding proxy fields null, LIMIT 500)
  → Skip Enriched (proxies empty + no legacy "[Funding enriched" in Description)
  → Cap Per Run (25)
  → Prepare Crunchbase → Crunchbase Research → Merge → Map
       ├─ Has Changes → Update Account
       └─ Build Run Summary → Send an Email
Error Trigger → Build Failure Email → Send an Email
```

**Deploy note:** Workflow Settings → **Error Workflow** → this workflow.

## 3. Credentials & Dependencies

| Credential name | Type | Used by |
|-----------------|------|---------|
| `Salesforce account` | Salesforce OAuth2 | Get Accounts, Update Account |
| `Anthropic account` | Anthropic API | Crunchbase Research |
| `SMTP account` | SMTP | Send an Email |

| Field written | Source |
|---------------|--------|
| `crunchbase__Latest_Round_Funding_Type__c` | stage (**skip proxy**) |
| `crunchbase__Latest_Round_Money_Raised_in_USD__c` | last amount |
| `crunchbase__Total_Funding_USD__c` | total (**skip proxy**) |
| `crunchbase__Latest_Round_Date__c` | last date |
| `crunchbase__Number_of_Employees_Crunchbase__c` | employees |
| `crunchbase__Number_of_Investors__c` | investor count |
| `Investors__c` | names (**skip proxy**) |
| `Crunchbase_URL__c` | URL (**skip proxy**) |
| `Latest_Funding_Amount__c` / `Latest_Funding_Date__c` | latest round (**date is skip proxy**) |
| `Is_PE_Backed__c` / `Is_VC_Backed__c` | Yes/No/Unknown |
| `NumberOfEmployees` | parsed count |
| `Description` | **cleanup only** — strips legacy Funding automation blocks |

Company “About” text is **not** written (no dedicated field in this org); it is not stuffed into Description.

## 4. Step-by-Step Data Flow

1. **Get Accounts** with all five funding proxy fields `= null`.
2. **Skip Enriched** mirrors proxies + legacy Description marker.
3. Cap → Claude research → Merge (`_cb_status`) → Map (eligibility gate).
4. PATCH typed fields; strip legacy Description funding block; email digest.

## 5. Error Handling & Edge Cases

* Ineligible research does not write proxy fields → retries next week.
* Employees-only enrichment (no URL/investors/total/stage/date) may **not** set a skip proxy and can retry — rare; watch Skipped/Enriched in digests.
* Manual Sales data on proxy fields excludes the Account from automation.
* PE/VC: `CHECKBOX_PE_VC = false` in `map_salesforce_cb.js`.

## 6. Risks and Gaps of This Automation and Mitigation

| # | Risk / Gap | Impact | Mitigation |
|----|----|----|----|
| 1 | **Proxy skip is coarse** — any proxy field blocks re-run. | Medium | Clear all proxies to retry; document for Sales. |
| 2 | **Partial Sales data** on one proxy field skips full research. | Medium | Acceptable tradeoff vs new Enriched__c fields. |
| 3 | **No Company_Description__c** — About text dropped. | Low | Add field later if Sales needs it. |
| 4 | **Sandbox PATCH host.** | High if wrong org | Update `SF_UPDATE_URL` for production. |
| 5 | **Legacy Description markers** still skip. | Medium | Clear or leave as done. |
| 6 | **Error Workflow unset.** | Medium | Set in n8n. |

## 7. Success Criteria

1. Sunday run succeeds; digest email received.
2. Up to 25 Accounts with all funding proxies blank researched.
3. Eligible Accounts get typed field updates; Description not appended with Funding/About/investors.
4. Legacy funding automation blocks stripped on successful enrich.
5. Accounts with any funding proxy already set are not re-billed.

### Rebuild

```bash
cd n8n && python3 build_salesforce_workflow.py
```
