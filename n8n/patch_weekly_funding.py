#!/usr/bin/env python3
"""Patch the Weekly Funding Discovery workflow to send success/failure email.

- Wires Finalize Email -> Send an Email (was disconnected).
- Sets Send an Email subject/body/attachment from the incoming item.
- Rewrites Finalize Email to choose success / no-match / soft-failure copy.
- Adds Error Trigger -> Build Failure Email -> Send an Email (hard-failure path).

Run:  python3 patch_weekly_funding.py
In:   weekly_funding.orig.json
Out:  weekly_funding.updated.json
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(HERE, "weekly_funding.orig.json"), encoding="utf-8") as f:
    wf = json.load(f)

FINALIZE_JS = r"""// ── Finalize Email ────────────────────────────────────────────────────────
// Runs after Convert to File. Keeps the CSV binary and sets the email
// subject/body based on the run outcome:
//   - soft failure (Claude/parse errored but flow continued) -> ⚠️ notice
//   - companies found -> ✅ digest (CSV attached)
//   - no companies    -> ✅ "no matches"
// Code node mode: "Run Once for All Items".

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

let subject;
let body;

if (parseError) {
  subject = `⚠️ Weekly funding discovery FAILED — ${startDate}–${endDate}`;
  body = [
    "Hi Sales team,",
    "",
    "The weekly funding discovery run hit an error and could not produce results.",
    "",
    `  • Window: ${startDate} → ${endDate}`,
    `  • Error:  ${parseError}`,
    "",
    "No action needed — this is a heads-up that this week's file may be delayed.",
    "",
    "— Automations (n8n)",
  ].join("\n");
} else if (companies.length) {
  subject = `✅ Weekly funding digest ${startDate}–${endDate} · ${companies.length} companies (${newOnes.length} new)`;
  const lines = [];
  lines.push("Hi Sales team,");
  lines.push("");
  lines.push(`Weekly software/tech funding digest (${startDate} → ${endDate}).`);
  lines.push("");
  lines.push(`  • Total found: ${companies.length}`);
  lines.push(`  • New (created in Salesforce): ${newOnes.length}`);
  lines.push(`  • Already in Salesforce: ${existing.length}`);
  lines.push("");
  lines.push("── All companies ──");
  for (const c of companies) {
    const flag = c._isNew ? "NEW" : "EXISTS";
    lines.push(`- [${flag}] ${c.Name} | ${c.funding_stage || "?"} ${c.funding_amount || ""} | ${c.Website || "no website"}`);
  }
  lines.push("");
  lines.push("Full list with funding + Salesforce match status is attached as CSV.");
  lines.push("");
  lines.push("— Automations (n8n)");
  body = lines.join("\n");
} else {
  subject = `✅ Weekly funding digest ${startDate}–${endDate} · no new matches`;
  body = [
    "Hi Sales team,",
    "",
    `No software/tech funding companies were found for ${startDate} → ${endDate}.`,
    "",
    "— Automations (n8n)",
  ].join("\n");
}

const input = $input.first();
const hasAttachment = Boolean(input.binary && input.binary.data);

return [{
  json: {
    subject,
    body,
    hasAttachment,
    outcome: parseError ? "failure" : "success",
    startDate,
    endDate,
    companyCount: companies.length,
    newCount: newOnes.length,
  },
  binary: input.binary || {},
}];
"""

FAILURE_JS = r"""// ── Build Failure Email ───────────────────────────────────────────────────
// Fires only when the workflow HARD-fails, via the Error Trigger. Produces the
// failure subject/body for the shared Send Email node. No attachment.
// Code node mode: "Run Once for All Items".

const info = ($input.first() && $input.first().json) || {};
const wf = (info.workflow && info.workflow.name) || "Weekly Funding Discovery";
const exec = info.execution || {};
const errMsg = (exec.error && (exec.error.message || exec.error)) || "Unknown error";
const lastNode = exec.lastNodeExecuted || "unknown node";
const url = exec.url || "";

const subject = `⚠️ Weekly funding discovery FAILED — ${wf}`;

const parts = [
  "Hi Sales team,",
  "",
  "The weekly funding discovery run did NOT complete. No results were produced this run.",
  "",
  `  • Workflow:  ${wf}`,
  `  • Failed at: ${lastNode}`,
  `  • Error:     ${String(errMsg).slice(0, 300)}`,
];
if (url) parts.push(`  • Execution: ${url}`);
parts.push("");
parts.push("No action needed from Sales — this is a heads-up that this week's file may be delayed.");
parts.push("");
parts.push("— Automations (n8n)");

return [{ json: { subject, body: parts.join("\n"), hasAttachment: false, outcome: "failure" } }];
"""

# ── apply node edits ────────────────────────────────────────────────────────
by_name = {n["name"]: n for n in wf["nodes"]}

by_name["Finalize Email"]["parameters"]["jsCode"] = FINALIZE_JS

send = by_name["Send an Email"]
send["parameters"] = {
    "fromEmail": "n8n.sales@assuresoft.com.bo",
    "toEmail": "sales@assuresoft.com",
    "subject": "={{ $json.subject }}",
    "emailFormat": "text",
    "text": "={{ $json.body }}",
    "options": {
        "attachments": "={{ $json.hasAttachment ? 'data' : '' }}",
    },
}

# ── add error-path nodes ────────────────────────────────────────────────────
wf["nodes"].append({
    "parameters": {},
    "id": "err-trigger-0001",
    "name": "Error Trigger",
    "type": "n8n-nodes-base.errorTrigger",
    "typeVersion": 1,
    "position": [224, 480],
})
wf["nodes"].append({
    "parameters": {"jsCode": FAILURE_JS},
    "id": "build-failure-email-0001",
    "name": "Build Failure Email",
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": [448, 480],
})


def to(node):
    return {"main": [[{"node": node, "type": "main", "index": 0}]]}


# ── fix / add connections ───────────────────────────────────────────────────
wf["connections"]["Finalize Email"] = to("Send an Email")   # was empty
wf["connections"]["Error Trigger"] = to("Build Failure Email")
wf["connections"]["Build Failure Email"] = to("Send an Email")

wf["name"] = "AssureSoft — Weekly Funding Discovery (with success/failure email)"

out = os.path.join(HERE, "weekly_funding.updated.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(wf, f, indent=2, ensure_ascii=False)

print("Wrote", os.path.basename(out))
print("Nodes:", len(wf["nodes"]))
print("Send an Email inputs:",
      sum(1 for src, c in wf["connections"].items()
          for grp in c.get("main", []) for l in grp if l["node"] == "Send an Email"))
