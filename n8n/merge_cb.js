// ── Merge Crunchbase ──────────────────────────────────────────────────────
// Parses the Claude funding/investor JSON and appends it as separate columns
// onto the original company row. Does NOT touch any hiring columns.
// Code node mode: "Run Once for Each Item".

function nodeJson(name) {
  try { return $(name).item.json; } catch (e) { return null; }
}

const company = $("Prepare Crunchbase").item.json;

// Defaults mirror enrich_crunchbase.py (is_*_backed default to "Unknown").
const funding = {
  founded_year: "",
  total_funding: "",
  last_funding_stage: "",
  last_funding_amount: "",
  last_funding_date: "",
  employee_count: "",
  investors: "",
  investor_types: "",
  crunchbase_url: "",
  company_description: "",
  is_pe_backed: "Unknown",
  is_vc_backed: "Unknown",
  _cb_status: "error",
  _cb_error: "",
};

try {
  const resp = nodeJson("Crunchbase Research");
  if (resp && resp.error) {
    funding._cb_error = String(resp.error.message || resp.error).slice(0, 200);
  } else if (resp && Array.isArray(resp.content)) {
    const text = resp.content
      .filter((b) => b && b.type === "text" && b.text)
      .map((b) => b.text)
      .join(" ");
    const m = text.match(/\{[\s\S]*?\}/);
    if (!m) throw new Error("No JSON in response");
    const d = JSON.parse(m[0]);
    const clean = (k, def = "") => String(d[k] != null ? d[k] : def).trim();

    funding.founded_year = clean("founded_year");
    funding.total_funding = clean("total_funding");
    funding.last_funding_stage = clean("last_funding_stage");
    funding.last_funding_amount = clean("last_funding_amount");
    funding.last_funding_date = clean("last_funding_date");
    funding.employee_count = clean("employee_count");
    funding.investors = clean("investors");
    funding.investor_types = clean("investor_types");
    funding.crunchbase_url = clean("crunchbase_url");
    funding.company_description = clean("company_description");
    funding.is_pe_backed = clean("is_pe_backed", "Unknown");
    funding.is_vc_backed = clean("is_vc_backed", "Unknown");
    funding._cb_status = "done";
    funding._cb_error = "";
  } else {
    funding._cb_error = "No response from Claude node";
  }
} catch (e) {
  funding._cb_error = String(e.message || e).slice(0, 200);
}

// Keep original row columns (minus internal _-prefixed helpers), then append funding.
const base = {};
for (const [k, v] of Object.entries(company)) {
  if (!k.startsWith("_")) base[k] = v;
}

return { json: { ...base, ...funding } };
