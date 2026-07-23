# Assuresoft — Hiring Signal Enrichment

Engineering-hiring intelligence tool for B2B sales. For each company in a CSV, it
searches up to four sources for open engineering roles and appends hiring-signal
columns (score, urgency, open roles, tech stack, careers links, etc.).

## Sources

| Source | Env var | Cost | Notes |
|--------|---------|------|-------|
| Claude AI + Web Search | `ANTHROPIC_API_KEY` | ~$0.001/company | Required, always on |
| JSearch (Indeed via RapidAPI) | `JSEARCH_API_KEY` | ~$10/mo | Optional |
| Theirstack | `THEIRSTACK_API_KEY` | ~$99–299/mo | Optional |
| Apollo.io | `APOLLO_API_KEY` | Included in plan | Optional |

Optional sources are skipped automatically if their key is blank.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # then edit .env and paste your keys
```

## Input CSV

The tool reads these columns (see `YPO_Qualified.sample.csv`):

- `company_name` (required)
- `company_website`
- `company_linkedin_url`
- `state`
- `icp_tier`

Copy the sample to get started:

```bash
cp YPO_Qualified.sample.csv YPO_Qualified.csv
```

## Run

```bash
# Check which sources are enabled / have keys
python3 enrich_hiring.py --sources-report

# Process a small batch first
python3 enrich_hiring.py --input YPO_Qualified.csv --limit 5

# Full run
python3 enrich_hiring.py --input YPO_Qualified.csv --output YPO_Qualified.csv
```

Other flags: `--tier N`, `--min-delay`, `--max-delay`, `--reset-errors`.

Progress is saved to the output CSV after every company, so the run is resumable —
already-processed rows (`_hiring_status=done`) are skipped on the next run.

## Security

- **API keys live only in `.env`, which is gitignored.** Never commit `.env`.
- The output data CSV is also gitignored (it contains prospect data).
- If any key was ever committed or shared, rotate it.
