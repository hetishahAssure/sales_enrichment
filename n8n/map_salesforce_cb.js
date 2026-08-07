// ── Map to Salesforce (Crunchbase) ────────────────────────────────────────
// Maps the funding enrichment output onto Account fields and diffs against
// the values read from Salesforce, so the PATCH body contains nothing but the
// fields that actually changed. Empty/unparseable enrichment values are
// skipped — they never blank out an existing Salesforce value.
//
// Eligibility gate: field PATCHes only run when _cb_status === "done" AND at
// least one confirmed field is present (crunchbase_url, parseable money/date,
// investors, usable stage, or employee count). Failed/empty research never
// writes the skip-proxy fields (Crunchbase_URL__c / Investors__c /
// crunchbase__Total_Funding_USD__c / stage / Latest_Funding_Date__c).
//
// Crunchbase managed-package fields (typed, so values are converted):
//
//   crunchbase__Latest_Round_Funding_Type__c        ← last_funding_stage
//   crunchbase__Latest_Round_Money_Raised_in_USD__c ← last_funding_amount
//   crunchbase__Total_Funding_USD__c                ← total_funding
//   crunchbase__Latest_Round_Date__c                ← last_funding_date
//   crunchbase__Number_of_Employees_Crunchbase__c   ← employee_count
//   crunchbase__Number_of_Investors__c              ← investors (count)
//
// Org custom fields:
//
//   Investors__c             ← investors
//   Crunchbase_URL__c        ← crunchbase_url
//   Latest_Funding_Amount__c ← last_funding_amount (parsed number)
//   Latest_Funding_Date__c   ← last_funding_date (YYYY-MM-DD)
//   Is_PE_Backed__c / Is_VC_Backed__c ← Yes/No/Unknown (or Checkbox)
//
// Skip proxy (SOQL / Skip Enriched): Account is treated as already enriched
// when ANY of Crunchbase_URL__c, Investors__c, crunchbase__Total_Funding_USD__c,
// crunchbase__Latest_Round_Funding_Type__c, Latest_Funding_Date__c is set.
//
// Description: enrichment blobs are NOT written. On an eligible run, any legacy
// automation block ("Funding:…[Funding enriched …]") is stripped.
// Company "About" is omitted (no Company_Description__c in this org).
// Code node mode: "Run Once for Each Item".

// Set true if Is_PE_Backed__c / Is_VC_Backed__c are Checkbox fields:
// Yes → true, No → false, Unknown → skipped.
const CHECKBOX_PE_VC = false;

const j = $input.item.json;
const changes = {};
const str = (v) => String(v == null ? "" : v).trim();

function setIfChanged(field, value) {
  if (value == null || value === "") return;
  const current = j[field];
  if (typeof value === "number") {
    const cur = current == null || current === "" ? null : Number(current);
    if (cur !== value) changes[field] = value;
  } else if (typeof value === "boolean") {
    if (Boolean(current) !== value) changes[field] = value;
  } else if (str(current) !== str(value)) {
    changes[field] = str(value);
  }
}

function yesNoToBool(v) {
  const s = str(v).toLowerCase();
  return s === "yes" ? true : s === "no" ? false : null;
}

function parseMoney(v) {
  const m = str(v).replace(/,/g, "").match(/^\$?\s*(\d+(?:\.\d+)?)\s*([KMB])?$/i);
  if (!m) return null;
  const mult = { K: 1e3, M: 1e6, B: 1e9 }[(m[2] || "").toUpperCase()] || 1;
  return Math.round(parseFloat(m[1]) * mult);
}

function parseDate(v) {
  const s = str(v);
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
  if (/^\d{4}-\d{2}$/.test(s)) return `${s}-01`;
  const q = s.match(/^(\d{4})-Q([1-4])$/i);
  if (q) return `${q[1]}-${String((parseInt(q[2], 10) - 1) * 3 + 1).padStart(2, "0")}-01`;
  if (/^\d{4}$/.test(s)) return `${s}-01-01`;
  return null;
}

function parseEmployees(v) {
  const ec = str(v).replace(/,/g, "");
  if (/^\d+$/.test(ec)) return parseInt(ec, 10);
  const range = ec.match(/^(\d+)\s*[-–]\s*(\d+)$/);
  if (range) return Math.round((parseInt(range[1], 10) + parseInt(range[2], 10)) / 2);
  return null;
}

const cbStatus = str(j._cb_status);
const cbError = str(j._cb_error);
const stage = str(j.last_funding_stage);
const investors = str(j.investors);
const crunchbaseUrl = str(j.crunchbase_url);
const totalMoney = parseMoney(j.total_funding);
const lastMoney = parseMoney(j.last_funding_amount);
const lastDate = parseDate(j.last_funding_date);
const employees = parseEmployees(j.employee_count);
const usableStage = Boolean(stage && stage !== "Unknown");
const total = str(j.total_funding);

const confirmedBits = [];
if (crunchbaseUrl) confirmedBits.push("crunchbase_url");
if (totalMoney != null) confirmedBits.push("total_funding");
if (lastMoney != null) confirmedBits.push("last_funding_amount");
if (lastDate) confirmedBits.push("last_funding_date");
if (investors) confirmedBits.push("investors");
if (usableStage) confirmedBits.push("last_funding_stage");
if (employees !== null) confirmedBits.push("employee_count");

const researchOk = cbStatus === "done";
const hasConfirmed = confirmedBits.length > 0;
const eligible = researchOk && hasConfirmed;

let skipReason = "";
if (!researchOk) {
  skipReason = cbError || `research status=${cbStatus || "missing"}`;
} else if (!hasConfirmed) {
  skipReason = "no confirmed funding fields (url/money/date/investors/stage/employees)";
}

if (!eligible) {
  return {
    json: {
      Id: j.Id,
      Name: j.Name,
      Website: j.Website,
      _changes: {},
      _changedFields: "",
      _hasChanges: false,
      _eligible: false,
      _skipReason: skipReason,
      _cb_status: cbStatus || "error",
      _cb_error: cbError,
      _confirmedFields: "",
      total_funding: total,
      last_funding_stage: stage,
      last_funding_amount: str(j.last_funding_amount),
      investors,
      crunchbase_url: crunchbaseUrl,
    },
  };
}

// ── Crunchbase managed-package fields ─────────────────────────────────────
if (usableStage) setIfChanged("crunchbase__Latest_Round_Funding_Type__c", stage);
setIfChanged("crunchbase__Latest_Round_Money_Raised_in_USD__c", lastMoney);
setIfChanged("crunchbase__Total_Funding_USD__c", totalMoney);
setIfChanged("crunchbase__Latest_Round_Date__c", lastDate);

const investorCount = investors ? investors.split(",").filter((s) => s.trim()).length : null;
if (investorCount) setIfChanged("crunchbase__Number_of_Investors__c", investorCount);

// ── Org custom fields (skip proxies among these) ──────────────────────────
setIfChanged("Investors__c", investors);
setIfChanged("Crunchbase_URL__c", crunchbaseUrl);
setIfChanged("Latest_Funding_Amount__c", lastMoney);
setIfChanged("Latest_Funding_Date__c", lastDate);
if (CHECKBOX_PE_VC) {
  setIfChanged("Is_PE_Backed__c", yesNoToBool(j.is_pe_backed));
  setIfChanged("Is_VC_Backed__c", yesNoToBool(j.is_vc_backed));
} else {
  setIfChanged("Is_PE_Backed__c", str(j.is_pe_backed));
  setIfChanged("Is_VC_Backed__c", str(j.is_vc_backed));
}

if (employees !== null) {
  setIfChanged("NumberOfEmployees", employees);
  setIfChanged("crunchbase__Number_of_Employees_Crunchbase__c", employees);
}

// ── Description cleanup only (no new enrichment text) ─────────────────────
const current = str(j.Description);
const cleaned = current
  .replace(/(^|\n)Funding:[\s\S]*?\[Funding enriched \d{4}-\d{2}-\d{2}\]/g, "$1")
  .replace(/\n{3,}/g, "\n\n")
  .trim();
if (cleaned !== current) changes.Description = cleaned;

return {
  json: {
    Id: j.Id,
    Name: j.Name,
    Website: j.Website,
    _changes: changes,
    _changedFields: Object.keys(changes).sort().join(", "),
    _hasChanges: Object.keys(changes).length > 0,
    _eligible: true,
    _skipReason: "",
    _cb_status: "done",
    _cb_error: "",
    _confirmedFields: confirmedBits.join(", "),
    total_funding: total,
    last_funding_stage: stage,
    last_funding_amount: str(j.last_funding_amount),
    investors,
    crunchbase_url: crunchbaseUrl,
  },
};
