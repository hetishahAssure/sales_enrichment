// ── Build Funding Digest (CSV rows) ───────────────────────────────────────
// Emits one clean row per discovered company for Convert to File.
// Email subject/body are assembled later in Finalize Email (keeps CSV clean).
// Code node mode: "Run Once for All Items".

const all = $input.all().map((i) => i.json);
const companies = all.filter((c) => !c._empty && c.Name);

if (!companies.length) {
  return [{
    json: {
      company_name: "",
      website: "",
      industry: "",
      employee_count: "",
      billing_city: "",
      billing_state: "",
      billing_country: "",
      funding_stage: "",
      funding_amount: "",
      funding_date: "",
      investors: "",
      crunchbase_url: "",
      company_description: "",
      salesforce_status: "none",
      match_reason: "",
    },
  }];
}

return companies.map((c) => ({
  json: {
    company_name: c.Name,
    website: c.Website,
    industry: c.Industry,
    employee_count: c.employee_count || c.NumberOfEmployees || "",
    billing_city: c.BillingCity,
    billing_state: c.BillingState,
    billing_country: c.BillingCountry,
    funding_stage: c.funding_stage,
    funding_amount: c.funding_amount,
    funding_date: c.funding_date,
    investors: c.investors,
    crunchbase_url: c.crunchbase_url,
    company_description: c.company_description || "",
    salesforce_status: c._isNew ? "new" : "existing",
    match_reason: c._matchReason || "",
  },
}));
