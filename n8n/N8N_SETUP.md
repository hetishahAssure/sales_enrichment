# Replicating the hiring-enrichment flow in n8n

This folder contains an importable n8n workflow that mirrors `enrich_hiring.py`,
using **Google Sheets** as the source/sink and all four sources.

```
Start → Get Companies → Skip Enriched → Prepare Requests
   → Claude Web Search → JSearch → Theirstack → Apollo
   → Merge & Score → Write Results
```

Files:
- `hiring_enrichment.workflow.json` — **production** version (Google Sheets in/out)
- `hiring_enrichment.upload.workflow.json` — **test** version: upload a CSV in the
  browser, download the enriched CSV at the end. No Google credentials needed.
- `prepare.js` / `merge.js` — the two Code nodes (already embedded in the JSON; kept here for editing)
- `build_workflow.py` — regenerates both JSON files after you edit the `.js` files

---

## Quick test without Google Sheets (recommended first)

Use `hiring_enrichment.upload.workflow.json`. Flow:

```
On Form Submit (upload CSV) → Extract From File → Skip Enriched → Prepare
   → Claude → JSearch → Theirstack → Apollo → Merge & Score → Convert to File
```

1. Create the **four Header Auth credentials** (Step 2 below). No Google cred needed.
2. Import `hiring_enrichment.upload.workflow.json`.
3. Attach each API credential to its HTTP node.
4. Click **Test workflow** → n8n opens a form → **upload a CSV** (use a small 2–3
   row file first; your `data/YPO_Qualified.csv` works, or trim it).
5. When it finishes, open the execution and download the enriched CSV from the
   **Convert to File** node's output panel.

**Important — verify the upload binary name:** run the form once, click the
**On Form Submit** node output, and check the binary property name of the uploaded
file. If it isn't `file`, open **Extract From File** and set *Input Binary Field*
to match. (n8n sometimes names it after the field label.)

That's the whole loop with zero Google setup. Everything below is the production
Google Sheets version.

---

The four HTTP nodes run one request per company row, each set to **Continue On
Error** so a single failing source never kills the row. The Merge node ports the
Python scoring exactly (0–5 score, Hot/Warm/Cold, High/Medium/Low confidence).

---

## Step 1 — Prepare the Google Sheet

1. Create a Google Sheet and paste your CSV into the first tab (row 1 = headers).
   Keep your existing headers: `Account ID`, `Account Name`, `Website`,
   `LinkedIn`, `Billing State/Province`, `ICP Tier`, etc.
2. Add these **new header columns** to the right (exact spelling — the workflow
   auto-maps by header name):

   ```
   is_hiring_engineers   open_roles           open_roles_count
   hiring_score          hiring_urgency       hiring_source
   careers_page_url      linkedin_jobs_url    indeed_jobs_url
   most_recent_posting   tech_stack_hints     hiring_notes
   data_confidence
   ```

`Account ID` is the match key used to write results back to the correct row, so
make sure every row has a unique value there.

## Step 2 — Create the API credentials (Credentials → New)

All four use **"Header Auth"** (Generic Credential Type). Create one each:

| Credential name | Header **Name** | Header **Value** |
|-----------------|-----------------|------------------|
| Anthropic       | `x-api-key`       | your Anthropic key |
| RapidAPI JSearch| `X-RapidAPI-Key`  | your RapidAPI key  |
| Theirstack      | `Authorization`   | `Bearer <your-theirstack-token>` |
| Apollo          | `X-Api-Key`       | your Apollo key    |

Also create a **Google Sheets OAuth2** credential (Google Sheets node → sign in).

> Your keys are in the project's `.env` file if you need to copy them. Rotate
> them if they were ever exposed.

## Step 3 — Import the workflow

1. n8n → **Workflows → Import from File**.
2. Select `hiring_enrichment.workflow.json`.

## Step 4 — Wire up credentials & sheet (after import)

- **Get Companies**: pick your Google Sheets credential, then select the
  Document and Sheet from the dropdowns.
- **Write Results**: same credential, same Document/Sheet. Confirm operation is
  **Update row**, mapping = **Auto-map**, "Column to match on" = `Account ID`.
- **Claude Web Search** → credential = Anthropic.
- **JSearch** → credential = RapidAPI JSearch.
- **Theirstack** → credential = Theirstack.
- **Apollo** → credential = Apollo.

## Step 5 — Test with one row

1. Temporarily add a **Limit** node (or set "Get Companies → Return only first N
   rows" via a Limit node) after *Get Companies*, or just make a 1-row test sheet.
2. Click **Test workflow**. Watch each node's output:
   - *Prepare Requests* should show `_claudeBody`, `_jsearchQuery`, etc.
   - each HTTP node returns data (or an error item that's tolerated).
   - *Merge & Score* shows `hiring_score`, `open_roles`, ...
   - *Write Results* updates the sheet row.

## Step 6 — Full run

Remove the limit and run. The **Skip Enriched** filter only processes rows where
`is_hiring_engineers` is still empty, so the workflow is **resumable** — re-run
any time and it continues where it left off.

To schedule it, swap the **Start** (Manual Trigger) for a **Schedule Trigger**.

---

## Notes / tuning

- **Rate limiting**: the Claude node has batching (1 req / 1.5 s). Add batching to
  the other HTTP nodes (Settings → Batching) if you hit RapidAPI/Apollo limits.
- **Editing logic**: edit `prepare.js` / `merge.js`, run `python3 build_workflow.py`,
  and re-import (or paste the updated code into the Code nodes).
- **Apollo endpoint**: uses `POST /v1/organizations/search` with the `X-Api-Key`
  header. If your Apollo plan needs the key in the body instead, move the key
  there and drop the credential.
