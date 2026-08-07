# Assuresoft — Sales Enrichment

B2B sales intelligence toolkit: enrich company lists with **engineering hiring signals**
and **Crunchbase-style funding/investor data**, plus ready-to-import **n8n** workflows
(Google Sheets / Salesforce / CSV upload).

## Layout

```
.
├── enrich_hiring.py          # Hiring-signal enrichment (CLI)
├── enrich_crunchbase.py      # Funding / investor enrichment (CLI)
├── requirements.txt
├── .env.example              # Copy to .env — never commit real keys
├── data/
│   ├── samples/              # Safe sample CSVs (committed)
│   └── *.csv                 # Working data (gitignored)
└── n8n/                      # Importable workflows + Code-node JS + builders
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # then paste your API keys
```

## Hiring enrichment

Searches up to four sources for open engineering roles and appends hiring-signal
columns (score, urgency, open roles, tech stack, careers links, etc.).

| Source | Env var | Notes |
|--------|---------|-------|
| Claude AI + Web Search | `ANTHROPIC_API_KEY` | Required |
| JSearch (Indeed via RapidAPI) | `JSEARCH_API_KEY` | Optional |
| Theirstack | `THEIRSTACK_API_KEY` | Optional |
| Apollo.io | `APOLLO_API_KEY` | Optional |

```bash
cp data/samples/YPO_Qualified.sample.csv data/YPO_Qualified.csv

python3 enrich_hiring.py --sources-report
python3 enrich_hiring.py --input data/YPO_Qualified.csv --limit 5
python3 enrich_hiring.py --input data/YPO_Qualified.csv --output data/YPO_Qualified.csv
```

Progress is saved after every company (`_hiring_status=done` rows are skipped on resume).

## Crunchbase / funding enrichment

Pulls funding stage, investors, employee count, and related fields, and builds
`data/YPO_Investors.csv` for PE/VC targeting.

```bash
cp data/samples/YPO_Scored.sample.csv data/YPO_Scored.csv

python3 enrich_crunchbase.py --input data/YPO_Scored.csv --output data/YPO_Final.csv
python3 enrich_crunchbase.py --investors-only
```

## n8n workflows

See [`n8n/README.md`](n8n/README.md) for the full index (hiring, Crunchbase,
Salesforce schedules, weekly funding discovery). Start with
[`n8n/N8N_SETUP.md`](n8n/N8N_SETUP.md) for the CSV-upload hiring test flow.

## Security

- **API keys live only in `.env` (gitignored).** Never commit `.env`.
- Working CSVs under `data/` are gitignored (prospect data). Only `data/samples/` is committed.
- If any key was ever committed or shared, rotate it.
