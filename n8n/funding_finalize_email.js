// ── Finalize Email ────────────────────────────────────────────────────────
// Runs after Convert to File. Keeps the CSV binary and adds Gmail fields
// (to / subject / body) from Config + Dedupe results.
// Code node mode: "Run Once for All Items".

function config() {
  try { return $("Config").first().json; } catch (e) { return {}; }
}

const cfg = config();
const emailTo = String(cfg.emailTo || "heti.shah@assuresoft.com").trim();

let deduped = [];
try {
  deduped = $("Dedupe vs Salesforce").all().map((i) => i.json);
} catch (e) {
  deduped = [];
}

const companies = deduped.filter((c) => !c._empty && c.Name);
const startDate = (companies[0] && companies[0]._startDate) || (deduped[0] && deduped[0]._startDate) || "";
const endDate = (companies[0] && companies[0]._endDate) || (deduped[0] && deduped[0]._endDate) || "";
const parseError = (deduped[0] && deduped[0]._parseError) || "";
const newOnes = companies.filter((c) => c._isNew);
const existing = companies.filter((c) => !c._isNew);

const lines = [];
lines.push(`Weekly software/tech funding digest (${startDate} → ${endDate})`);
lines.push("");
lines.push(`Total found: ${companies.length}`);
lines.push(`New (created in Salesforce when not already present): ${newOnes.length}`);
lines.push(`Already in Salesforce: ${existing.length}`);
if (parseError) {
  lines.push("");
  lines.push(`Parser note: ${parseError}`);
}
lines.push("");
lines.push("── All companies ──");
for (const c of companies) {
  const flag = c._isNew ? "NEW" : "EXISTS";
  lines.push(
    `- [${flag}] ${c.Name} | ${c.funding_stage || "?"} ${c.funding_amount || ""} | ${c.Website || "no website"}`
  );
}
lines.push("");
lines.push("CSV attachment includes the full list with funding + Salesforce match status.");

const subject = companies.length
  ? `Weekly funding digest ${startDate}–${endDate} (${companies.length} companies, ${newOnes.length} new)`
  : `Weekly funding digest ${startDate}–${endDate} (no matches)`;

const body = companies.length
  ? lines.join("\n")
  : `No software/tech funding companies found for ${startDate} → ${endDate}.\n${parseError ? `Parser note: ${parseError}` : ""}`.trim();

const input = $input.first();
return [{
  json: {
    emailTo,
    subject,
    body,
    startDate,
    endDate,
    companyCount: companies.length,
    newCount: newOnes.length,
  },
  binary: input.binary || {},
}];
