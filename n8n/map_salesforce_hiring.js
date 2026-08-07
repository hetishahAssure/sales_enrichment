// ── Map to Salesforce (hiring) ────────────────────────────────────────────
// Maps the hiring enrichment output onto Account fields and diffs against the
// values read from Salesforce, so the PATCH body contains nothing but the
// fields that actually changed. Empty enrichment values are skipped — they
// never blank out an existing Salesforce value.
//
// Eligibility gate: field PATCHes only run when _hiring_status === "done" AND
// at least one confirmed signal exists (Yes/No hiring answer, open eng roles,
// careers/LinkedIn URL, or hiring_score > 0). Failed/empty research never
// writes Is_Hiring_Engineers__c (the skip proxy).
//
// Custom fields (must exist on Account and be in Get Accounts SOQL):
//
//   Is_Hiring_Engineers__c ← is_hiring_engineers  (Yes/No/Unknown, text)
//                            ALSO the skip proxy — once set, Skip Enriched /
//                            SOQL exclude the Account from future runs.
//   Hiring_Score__c        ← hiring_score         (Number, 0–5)
//   LinkedIn__c            ← linkedin_jobs_url    (URL/text)
//   Careers_Page__c        ← careers_page_url     (URL/text)
//
// Description: enrichment blobs are NOT written. On an eligible run, any legacy
// automation blocks ("Hiring engineers:…[Hiring|Auto-enriched …]") are stripped
// so Description returns to human/company content only.
//
// Note: open role titles / urgency / confidence stay in the weekly email digest
// only — no dedicated Salesforce fields for those in this org.
// Code node mode: "Run Once for Each Item".

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

const hiringStatus = str(j._hiring_status);
const hiringError = str(j._hiring_error);
const hiring = str(j.is_hiring_engineers) || "Unknown";
const rolesCount = parseInt(j.open_roles_count, 10) || 0;
const score = parseInt(j.hiring_score, 10) || 0;
const urgency = str(j.hiring_urgency);
const careersUrl = str(j.careers_page_url);
const linkedinUrl = str(j.linkedin_jobs_url);
const hiringSource = str(j.hiring_source);
const confidence = str(j.data_confidence);

const confirmedBits = [];
if (hiring === "Yes" || hiring === "No") confirmedBits.push("is_hiring_engineers");
if (rolesCount > 0) confirmedBits.push("open_roles_count");
if (score > 0) confirmedBits.push("hiring_score");
if (careersUrl) confirmedBits.push("careers_page_url");
if (linkedinUrl) confirmedBits.push("linkedin_jobs_url");

const researchOk = hiringStatus === "done";
const hasConfirmed = confirmedBits.length > 0;
const eligible = researchOk && hasConfirmed;

let skipReason = "";
if (!researchOk) {
  skipReason = hiringError || `research status=${hiringStatus || "missing"}`;
} else if (!hasConfirmed) {
  skipReason = "no confirmed hiring signals (Yes/No, roles, score, careers/LinkedIn URL)";
}

if (!eligible) {
  return {
    json: {
      Id: j.Id,
      Name: j.Name,
      _changes: {},
      _changedFields: "",
      _hasChanges: false,
      _eligible: false,
      _skipReason: skipReason,
      _hiring_status: hiringStatus || "error",
      _hiring_error: hiringError,
      _confirmedFields: "",
      is_hiring_engineers: hiring,
      hiring_score: score,
      hiring_urgency: urgency,
      open_roles_count: rolesCount,
      hiring_source: hiringSource,
      data_confidence: confidence,
      careers_page_url: careersUrl,
      linkedin_jobs_url: linkedinUrl,
    },
  };
}

// ── Existing hiring-signal fields (Is_Hiring_Engineers__c = skip proxy) ───
setIfChanged("Is_Hiring_Engineers__c", hiring);
setIfChanged("Hiring_Score__c", score);
setIfChanged("LinkedIn__c", linkedinUrl);
setIfChanged("Careers_Page__c", careersUrl);

// ── Description cleanup only (no new enrichment text) ─────────────────────
const current = str(j.Description);
const cleaned = current
  .replace(
    /(^|\n)Hiring engineers:[\s\S]*?\[(?:Hiring|Auto)-enriched \d{4}-\d{2}-\d{2}\]/g,
    "$1"
  )
  .replace(/\n{3,}/g, "\n\n")
  .trim();
if (cleaned !== current) changes.Description = cleaned;

return {
  json: {
    Id: j.Id,
    Name: j.Name,
    _changes: changes,
    _changedFields: Object.keys(changes).sort().join(", "),
    _hasChanges: Object.keys(changes).length > 0,
    _eligible: true,
    _skipReason: "",
    _hiring_status: "done",
    _hiring_error: "",
    _confirmedFields: confirmedBits.join(", "),
    is_hiring_engineers: hiring,
    hiring_score: score,
    hiring_urgency: urgency,
    open_roles_count: rolesCount,
    hiring_source: hiringSource,
    data_confidence: confidence,
    careers_page_url: careersUrl,
    linkedin_jobs_url: linkedinUrl,
  },
};
