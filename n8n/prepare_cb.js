// ── Prepare Crunchbase ────────────────────────────────────────────────────
// Runs once per company row. Builds the Anthropic request body for the funding
// / investor research call. Accepts scored-pipeline headers (company_name,
// full_name, company_website, state) or Salesforce-style ones (Account Name,
// Website, BillingState) as a fallback.
// Code node mode: "Run Once for Each Item".

const MODEL = "claude-haiku-4-5-20251001";

const c = $input.item.json;
const company = String(c["company_name"] || c["Account Name"] || c["Name"] || "").trim();
const name    = String(c["full_name"] || c["Full Name"] || "").trim();
const website = String(c["company_website"] || c["Website"] || "").trim();
const state   = String(c["state"] || c["Billing State/Province"] || c["BillingState"] || "").trim();

const prompt = `You are a B2B research assistant. Search Crunchbase, LinkedIn, and the web for funding and investor data on this company.

COMPANY: ${company}
PERSON:  ${name}
WEBSITE: ${website || "unknown"}
STATE:   ${state || "US"}

Search for:
1. Crunchbase page: crunchbase.com/organization/[company-slug]
2. Recent news about funding rounds
3. LinkedIn company page for employee count
4. Any PE/VC investor mentions

Return ONLY a valid JSON object — no markdown, no explanation:
{
  "founded_year": "<4-digit year or empty string>",
  "total_funding": "<e.g. $4.2M | $50M | $1.2B | Undisclosed | Unknown>",
  "last_funding_stage": "<Pre-Seed | Seed | Series A | Series B | Series C | Series D+ | PE Buyout | Growth Equity | Bootstrapped | Public | Unknown>",
  "last_funding_amount": "<e.g. $8M | $45M | Undisclosed | Unknown>",
  "last_funding_date": "<e.g. 2023-Q2 | 2024-01 | Unknown>",
  "employee_count": "<e.g. 12 | 85 | 200-500 | 1200 | Unknown>",
  "investors": "<comma-separated list of investor firm names — include PE firms, VC funds, angels. Empty string if none found>",
  "investor_types": "<comma-separated types matching investors list order: PE | VC | Angel | CVC | Family Office | Unknown>",
  "crunchbase_url": "<https://www.crunchbase.com/organization/[slug] or empty string>",
  "company_description": "<one sentence description of what the company does>",
  "is_pe_backed": "<Yes | No | Unknown>",
  "is_vc_backed": "<Yes | No | Unknown>"
}

Rules:
- Only include investors you confirmed via search — do NOT fabricate names
- If a field cannot be confirmed, use empty string "" or "Unknown"
- For investors, list all you can find — this is important`;

const cbBody = {
  model: MODEL,
  max_tokens: 1200,
  tools: [{ type: "web_search_20250305", name: "web_search" }],
  messages: [{ role: "user", content: prompt }],
};

return {
  json: {
    ...c,
    _company: company,
    _name: name,
    _website: website,
    _state: state,
    _cbBody: cbBody,
  },
};
