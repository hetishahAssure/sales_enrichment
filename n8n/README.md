# n8n workflows

Importable n8n workflows that mirror the Python enrichment scripts, plus the
Code-node JavaScript and Python builders that regenerate the JSON after edits.

Keep related `.js` / builder / `.workflow.json` files in this folder together —
builders load siblings via `HERE = dirname(__file__)`.

## Quick start

1. Create Header Auth credentials (Anthropic, RapidAPI JSearch, Theirstack, Apollo)
   — details in [`N8N_SETUP.md`](N8N_SETUP.md).
2. Import a `*.workflow.json` file in n8n.
3. Attach credentials to the HTTP nodes and run a small test first.

## Index by feature

### Hiring enrichment

| File | Role |
|------|------|
| [`N8N_SETUP.md`](N8N_SETUP.md) | Setup guide (Sheets + CSV upload) |
| `hiring_enrichment.upload.workflow.json` | Test: CSV upload → enriched CSV download |
| `hiring_enrichment.workflow.json` | Production: Google Sheets in/out |
| `prepare.js` / `merge.js` | Code nodes (edit these, then rebuild) |
| `build_workflow.py` | Regenerates both hiring workflow JSONs |
| `hiring_build_summary_email.js` / `hiring_build_failure_email.js` | Email bodies (Salesforce variant) |

### Crunchbase enrichment

| File | Role |
|------|------|
| `crunchbase_enrichment.upload.workflow.json` | CSV upload test flow |
| `prepare_cb.js` / `merge_cb.js` | Code nodes |
| `build_crunchbase_workflow.py` | Regenerates upload workflow JSON |
| `cb_build_summary_email.js` / `cb_build_failure_email.js` | Email bodies (Salesforce variant) |

### Salesforce (scheduled)

| File | Role |
|------|------|
| [`salesforce_hiring_enrichment.md`](salesforce_hiring_enrichment.md) | Hiring schedule docs |
| [`salesforce_crunchbase_enrichment.md`](salesforce_crunchbase_enrichment.md) | Crunchbase schedule docs |
| `salesforce_hiring_enrichment.schedule.workflow.json` | Scheduled hiring enrichment |
| `salesforce_crunchbase_enrichment.schedule.workflow.json` | Scheduled Crunchbase enrichment |
| `prepare_sf.js` / `flatten_report_hiring.js` / `map_salesforce_hiring.js` / `map_salesforce_cb.js` | SF mapping Code nodes |
| `build_salesforce_workflow.py` | Regenerates both Salesforce workflow JSONs |

### Weekly funding discovery

| File | Role |
|------|------|
| [`weekly_funding.md`](weekly_funding.md) | Funding discovery docs |
| `funding_discovery.workflow.json` | Generated funding discovery workflow |
| `funding_prepare.js` / `funding_parse.js` / `funding_dedupe.js` | Code nodes |
| `funding_email.js` / `funding_finalize_email.js` | Email Code nodes |
| `build_funding_workflow.py` | Regenerates `funding_discovery.workflow.json` |
| `weekly_funding.orig.json` / `weekly_funding.updated.json` | Patch input/output |
| `patch_weekly_funding.py` | Patches `weekly_funding.orig.json` → `.updated.json` |

## Rebuild after editing JS

```bash
cd n8n
python3 build_workflow.py
python3 build_crunchbase_workflow.py
python3 build_salesforce_workflow.py
python3 build_funding_workflow.py
# optional:
python3 patch_weekly_funding.py
```
