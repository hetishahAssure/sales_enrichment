// ── Build Failure Email ───────────────────────────────────────────────────
// Fires only when the workflow HARD-fails, via the Error Trigger. Produces the
// failure subject/body for the shared Send Email node. No attachment.
// Code node mode: "Run Once for All Items".

const info = ($input.first() && $input.first().json) || {};
const wf =
  (info.workflow && info.workflow.name) ||
  "Salesforce Account Enrichment (Hiring signals, weekly)";
const exec = info.execution || {};
const errMsg =
  (exec.error && (exec.error.message || exec.error)) || "Unknown error";
const lastNode = exec.lastNodeExecuted || "unknown node";
const url = exec.url || "";

const subject = `⚠️ Hiring Account enrichment FAILED — ${wf}`;

const parts = [
  "Hi team,",
  "",
  "The weekly Salesforce hiring-signal enrichment run did NOT complete.",
  "Accounts researched in a partial run (if any) were not summarised by the success email.",
  "",
  `  • Workflow:  ${wf}`,
  `  • Failed at: ${lastNode}`,
  `  • Error:     ${String(errMsg).slice(0, 300)}`,
];
if (url) parts.push(`  • Execution: ${url}`);
parts.push("");
parts.push(
  "Check n8n Executions, Anthropic/JSearch/Theirstack/Apollo quotas, and the Salesforce credential/host."
);
parts.push("Ineligible accounts are not marked enriched and will retry next week.");
parts.push("");
parts.push("— Automations (n8n)");

return [
  {
    json: {
      subject,
      body: parts.join("\n"),
      hasAttachment: false,
      outcome: "failure",
    },
  },
];
