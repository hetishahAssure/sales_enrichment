// ── Prepare Requests (Salesforce) ─────────────────────────────────────────
// Runs once per Account row pulled from Salesforce. Builds the request
// bodies/queries for all four hiring sources so the HTTP nodes stay simple.
// Reads standard Account fields (Name, Website, BillingState) with the CSV
// header names as fallbacks so the node also works on uploaded test data.
// Code node mode: "Run Once for Each Item".

const MODEL = "claude-haiku-4-5-20251001";

const TARGET_ROLES = [
  "software engineer", "software developer", "backend engineer", "frontend engineer",
  "full stack", "fullstack", "devops", "platform engineer", "site reliability", "sre",
  "qa engineer", "quality assurance", "automation engineer", "test engineer", "sdet",
  "mobile developer", "ios developer", "android developer", "data engineer", "data scientist",
  "ml engineer", "ai engineer", "machine learning", "nlp engineer", "bi engineer",
  "business intelligence", "data analyst", "ux designer", "ui designer", "product designer",
  "cloud engineer", "infrastructure engineer", "security engineer", "cybersecurity",
  "engineering manager", "director of engineering", "vp of engineering", "vp engineering",
  "tech lead", "technical lead", "staff engineer",
];

const c = $input.item.json;
const company = String(c["Name"] || c["Account Name"] || c["company_name"] || "").trim();
const website = String(c["Website"] || c["company_website"] || "").trim();
const liUrl   = String(c["LinkedIn__c"] || c["LinkedIn"] || c["company_linkedin_url"] || "").trim();
const state   = String(c["BillingState"] || c["Billing State/Province"] || c["state"] || "").trim();

let liJobs = "";
if (liUrl.includes("linkedin.com/company/")) {
  const slug = liUrl.replace(/\/+$/, "").split("/company/")[1].split("/")[0];
  liJobs = `https://www.linkedin.com/company/${slug}/jobs/`;
}

const base = website.replace(/\/+$/, "");
const careersHints = base ? `${base}/careers, ${base}/jobs, ${base}/join-us` : "search for careers page";

let domain = "";
if (website) domain = website.replace("https://", "").replace("http://", "").split("/")[0];

const prompt = `You are a sales research assistant for AssureSoft, a nearshore software engineering company.

Find CURRENT open engineering/tech job postings at this company.
A company actively hiring engineers is our strongest buying signal.

COMPANY: ${company}
WEBSITE: ${website || "unknown"}
STATE: ${state || "US"}
LINKEDIN JOBS: ${liJobs || "search for it"}
CAREERS PAGE: ${careersHints}

Search ALL of these — try every source:
1. LinkedIn Jobs page: ${liJobs || `search linkedin.com for "${company}" jobs`}
2. Company careers page: ${careersHints}
3. Indeed.com: search "${company} software engineer" or "${company} developer"
4. Web: "${company} engineering jobs 2025" or "${company} hiring engineers"

TARGET ROLES — report ANY of these:
Software Engineer/Developer, Backend/Frontend/Full Stack, DevOps/Platform/SRE,
QA/Automation/Test Engineer, SDET, Mobile (iOS/Android), Data/ML/AI Engineer,
BI Engineer, UX/UI Designer, Cloud/Security Engineer, Engineering Manager,
Director/VP Engineering, Tech Lead, Staff Engineer

Return ONLY valid JSON — no markdown, no explanation:
{
  "is_hiring_engineers": "<Yes | No | Unknown>",
  "open_roles": "<comma-separated role titles actually found>",
  "open_roles_count": <integer — engineering roles only>,
  "hiring_source": "<LinkedIn | Careers Page | Indeed | Web Search | Multiple | None>",
  "careers_page_url": "<direct URL to careers page if found, else empty>",
  "linkedin_jobs_url": "<confirmed linkedin jobs URL, else empty>",
  "indeed_jobs_url": "<indeed URL for company if found, else empty>",
  "most_recent_posting": "<date or 'within last 30 days' or 'unknown'>",
  "tech_stack_hints": "<technologies from job descriptions e.g. 'Python, AWS, React'>",
  "notes": "<one sentence context>"
}

Rules:
- Only report roles you ACTUALLY found — never guess or fabricate
- Count ONLY engineering/tech roles — ignore sales/marketing/finance
- If LinkedIn blocks, try Indeed and careers page instead`;

const claudeBody = {
  model: MODEL,
  max_tokens: 800,
  tools: [{ type: "web_search_20250305", name: "web_search" }],
  messages: [{ role: "user", content: prompt }],
};

const jsearchQuery = `"${company}" (engineer OR developer OR devops OR QA OR "data engineer")`;

const theirstackBody = {
  page: 0,
  limit: 25,
  order_by: [{ desc: true, field: "discovered_at" }],
  job_title_or: TARGET_ROLES.slice(0, 10),
  company_name_or: [company],
  ...(domain ? { company_domain_or: [domain] } : {}),
};

const apolloBody = {
  q_organization_name: company,
  organization_domains: domain ? [domain] : [],
  page: 1,
  per_page: 1,
};

return {
  json: {
    ...c,
    _company: company,
    _website: website,
    _state: state,
    _domain: domain,
    _liJobs: liJobs,
    _claudeBody: claudeBody,
    _jsearchQuery: jsearchQuery,
    _theirstackBody: theirstackBody,
    _apolloBody: apolloBody,
  },
};
