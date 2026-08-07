// ── Prepare Funding Discovery ─────────────────────────────────────────────
// Builds the Anthropic web-search request for software/tech companies that
// received funding in the last 7 days. Code node mode: "Run Once for All Items".

const MODEL = "claude-haiku-4-5-20251001";

const end = new Date();
const start = new Date();
start.setDate(end.getDate() - 7);

const fmt = (d) => d.toISOString().slice(0, 10);
const startDate = fmt(start);
const endDate = fmt(end);

const prompt = `You are a B2B research assistant for AssureSoft, a nearshore software engineering company.

Find software / technology companies that announced or closed a funding round between ${startDate} and ${endDate} (inclusive).

Search Crunchbase, TechCrunch, LinkedIn, and the web for recent funding news.

Filters (ALL required):
1. Funding announced or closed in the last 7 days (${startDate} to ${endDate})
2. Industry is software / tech (SaaS, software products, developer tools, AI/ML platforms, fintech software, cybersecurity, cloud/infra software, data platforms, etc.). Exclude pure biotech hardware, restaurants, retail stores, real estate agencies, and non-software industrials.

Return ONLY a valid JSON array — no markdown, no explanation. Each element:
{
  "company_name": "<legal or common company name>",
  "website": "<https://... or empty string>",
  "company_description": "<one sentence what the company does>",
  "industry": "<e.g. Software | SaaS | Artificial Intelligence | Cybersecurity | FinTech | Developer Tools>",
  "employee_count": "<integer string or empty, e.g. 45>",
  "billing_city": "<city or empty>",
  "billing_state": "<state/province or empty>",
  "billing_country": "<country or empty>",
  "funding_stage": "<Pre-Seed | Seed | Series A | Series B | Series C | Series D+ | Growth Equity | PE Buyout | Debt | Other | Unknown>",
  "funding_amount": "<e.g. $12M | Undisclosed | Unknown>",
  "funding_date": "<YYYY-MM-DD or YYYY-MM if day unknown>",
  "investors": "<comma-separated investor names, or empty>",
  "crunchbase_url": "<https://www.crunchbase.com/organization/[slug] or empty>"
}

Rules:
- Only include companies you can corroborate via search — do NOT fabricate
- Prefer 15–40 high-confidence matches over a long speculative list
- If employee_count is a range, use the midpoint as an integer string
- website should be the company homepage when known
- If nothing qualifies, return []`;

const _claudeBody = {
  model: MODEL,
  max_tokens: 8000,
  tools: [{ type: "web_search_20250305", name: "web_search" }],
  messages: [{ role: "user", content: prompt }],
};

return [{
  json: {
    _startDate: startDate,
    _endDate: endDate,
    _claudeBody,
  },
}];
