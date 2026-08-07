// ── Build Run Summary Email ───────────────────────────────────────────────
// Connected from Map to Salesforce (after the Has Changes → Update Account
// branch in connection order) so PATCHes finish first under executionOrder v1.
// Lists enriched companies, skips, and failed PATCH bodies.
// Code node mode: "Run Once for All Items".

function safeAll(name) {
  try {
    return $(name).all().map((i) => i.json);
  } catch (e) {
    return [];
  }
}

const mapped = safeAll("Map to Salesforce");
const patched = safeAll("Update Account");

const attempted = mapped.filter((m) => m._eligible && m._hasChanges);
const skipped = mapped.filter((m) => !m._eligible);
const noOp = mapped.filter((m) => m._eligible && !m._hasChanges);

// Has Changes → Update Account preserves item order; pair by index.
const patchFailures = [];
const enrichedList = [];
for (let i = 0; i < attempted.length; i++) {
  const m = attempted[i];
  const p = patched[i];
  if (p && p.error) {
    const msg = String(
      (p.error.message || p.error.description || p.error) || "PATCH failed"
    ).slice(0, 300);
    patchFailures.push({
      name: m.Name || "?",
      id: m.Id || "",
      message: msg,
      body: JSON.stringify(m._changes || {}).slice(0, 400),
    });
  } else {
    enrichedList.push(m);
  }
}

const lines = [];
lines.push("Hi team,");
lines.push("");
lines.push("Weekly Salesforce Account Crunchbase enrichment summary:");
lines.push("");
lines.push(`  • Researched:  ${mapped.length}`);
lines.push(`  • Enriched:    ${enrichedList.length}`);
lines.push(`  • Unchanged:   ${noOp.length} (eligible, Salesforce already matched)`);
lines.push(`  • Skipped:     ${skipped.length} (ineligible — will retry next week)`);
lines.push(`  • PATCH fail:  ${patchFailures.length}`);
lines.push("");

if (enrichedList.length) {
  lines.push("── Companies enriched ──");
  for (const m of enrichedList) {
    const bits = [
      m.last_funding_stage,
      m.total_funding,
      m.investors ? `investors: ${m.investors}` : "",
    ]
      .filter(Boolean)
      .join(" | ");
    lines.push(
      `- ${m.Name || "?"} (${m.Id || "no Id"})${bits ? ` — ${bits}` : ""}` +
        (m.crunchbase_url ? ` — ${m.crunchbase_url}` : "")
    );
    if (m._changedFields) lines.push(`    fields: ${m._changedFields}`);
  }
  lines.push("");
}

if (skipped.length) {
  lines.push("── Skipped (marker NOT written; will retry) ──");
  for (const m of skipped) {
    lines.push(
      `- ${m.Name || "?"} (${m.Id || "no Id"}): ${m._skipReason || m._cb_error || "ineligible"}`
    );
  }
  lines.push("");
}

if (patchFailures.length) {
  lines.push("── PATCH failures ──");
  for (const f of patchFailures) {
    lines.push(`- ${f.name} (${f.id}): ${f.message}`);
    if (f.body) lines.push(`    body: ${f.body}`);
  }
  lines.push("");
}

if (noOp.length) {
  lines.push(`── Eligible but unchanged (${noOp.length}) ──`);
  for (const m of noOp) {
    lines.push(`- ${m.Name || "?"} (${m.Id || "no Id"})`);
  }
  lines.push("");
}

lines.push("— Automations (n8n)");

const hasProblems = skipped.length > 0 || patchFailures.length > 0;
const subject = hasProblems
  ? `⚠️ Crunchbase Account enrichment — ${enrichedList.length} enriched, ${skipped.length} skipped, ${patchFailures.length} PATCH fail`
  : `✅ Crunchbase Account enrichment — ${enrichedList.length} companies enriched`;

return [
  {
    json: {
      subject,
      body: lines.join("\n"),
      hasAttachment: false,
      outcome: hasProblems ? "partial" : "success",
      enrichedCount: enrichedList.length,
      skippedCount: skipped.length,
      patchFailCount: patchFailures.length,
      researchedCount: mapped.length,
    },
  },
];
