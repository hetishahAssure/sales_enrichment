// ── Parse Funding Discovery ───────────────────────────────────────────────
// Parses Claude's JSON array into one n8n item per company, shaped for
// Salesforce Account create + email digest.
// Code node mode: "Run Once for All Items".

function nodeJson(name) {
  try { return $(name).first().json; } catch (e) { return null; }
}

function clean(v, def = "") {
  return String(v != null ? v : def).trim();
}

function parseEmployeeCount(raw) {
  const s = clean(raw);
  if (!s || /^unknown$/i.test(s)) return null;
  const range = s.match(/(\d+)\s*[-–]\s*(\d+)/);
  if (range) return Math.round((Number(range[1]) + Number(range[2])) / 2);
  const n = s.replace(/,/g, "").match(/\d+/);
  return n ? Number(n[0]) : null;
}

function buildDescription(d) {
  const lines = [];
  const desc = clean(d.company_description);
  if (desc) lines.push(desc);
  lines.push("");
  lines.push(`Funding: ${clean(d.funding_stage, "Unknown")} | ${clean(d.funding_amount, "Unknown")} | ${clean(d.funding_date, "Unknown")}`);
  const investors = clean(d.investors);
  if (investors) lines.push(`Investors: ${investors}`);
  const cb = clean(d.crunchbase_url);
  if (cb) lines.push(`Crunchbase: ${cb}`);
  const team = clean(d.employee_count);
  if (team) lines.push(`Team size: ${team}`);
  lines.push("Source: Weekly Crunchbase funding discovery (n8n)");
  return lines.join("\n").trim();
}

const meta = nodeJson("Prepare Funding Discovery") || {};
const startDate = meta._startDate || "";
const endDate = meta._endDate || "";

let companies = [];
let parseError = "";

try {
  const resp = nodeJson("Claude Funding Discovery");
  if (!resp) {
    parseError = "No response from Claude Funding Discovery";
  } else if (resp.error) {
    parseError = String(resp.error.message || resp.error).slice(0, 300);
  } else if (Array.isArray(resp.content)) {
    const text = resp.content
      .filter((b) => b && b.type === "text" && b.text)
      .map((b) => b.text)
      .join(" ");
    const m = text.match(/\[[\s\S]*\]/);
    if (!m) throw new Error("No JSON array in Claude response");
    const parsed = JSON.parse(m[0]);
    if (!Array.isArray(parsed)) throw new Error("Parsed JSON is not an array");
    companies = parsed;
  } else {
    parseError = "Unexpected Claude response shape";
  }
} catch (e) {
  parseError = String(e.message || e).slice(0, 300);
}

if (!companies.length) {
  return [{
    json: {
      _empty: true,
      _parseError: parseError,
      _startDate: startDate,
      _endDate: endDate,
      company_name: "",
      Name: "",
      Website: "",
      Description: "",
      Industry: "",
      NumberOfEmployees: null,
      BillingCity: "",
      BillingState: "",
      BillingCountry: "",
      funding_stage: "",
      funding_amount: "",
      funding_date: "",
      investors: "",
      crunchbase_url: "",
      employee_count: "",
    },
  }];
}

return companies.map((d) => {
  const name = clean(d.company_name);
  const website = clean(d.website);
  const employees = parseEmployeeCount(d.employee_count);
  return {
    json: {
      _empty: false,
      _parseError: "",
      _startDate: startDate,
      _endDate: endDate,
      company_name: name,
      Name: name,
      Website: website,
      Description: buildDescription(d),
      Industry: clean(d.industry, "Software"),
      NumberOfEmployees: employees,
      BillingCity: clean(d.billing_city),
      BillingState: clean(d.billing_state),
      BillingCountry: clean(d.billing_country),
      funding_stage: clean(d.funding_stage),
      funding_amount: clean(d.funding_amount),
      funding_date: clean(d.funding_date),
      investors: clean(d.investors),
      crunchbase_url: clean(d.crunchbase_url),
      employee_count: clean(d.employee_count),
      company_description: clean(d.company_description),
    },
  };
});
