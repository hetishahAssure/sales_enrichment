// ── Flatten Salesforce Report (hiring) ────────────────────────────────────
// Turns one Analytics API report response into one n8n item per Account row.
// Uses reportMetadata.detailColumns order + factMap["T!T"].rows[].dataCells.
// Reads cell.value (not HTML label). Aliases report keys → Account API names
// so Prepare / Map / Update keep using Id, Name, Website, Is_Hiring_Engineers__c, …
// Code node mode: "Run Once for All Items".

const REPORT_TO_SF = {
  ACCOUNT_ID: "Id",
  "ACCOUNT.NAME": "Name",
  ADDRESS1_STATE: "BillingState",
  URL: "Website",
  "Account.LinkedIn__c": "LinkedIn__c",
  DESCRIPTION: "Description",
  "Account.Is_Hiring_Engineers__c": "Is_Hiring_Engineers__c",
  "Account.Hiring_Score__c": "Hiring_Score__c",
  "Account.Careers_Page__c": "Careers_Page__c",
  "Account.Open_Job_Openings__c": "Open_Job_Openings__c",
  "Account.Open_Job_Openings_Count__c": "Open_Job_Openings_Count__c",
};

function cellValue(cell) {
  if (cell == null || typeof cell !== "object") return cell == null ? null : cell;
  return Object.prototype.hasOwnProperty.call(cell, "value") ? cell.value : null;
}

function firstRecordId(cells) {
  for (const cell of cells) {
    if (cell && cell.recordId) return cell.recordId;
  }
  return "";
}

const root = $input.first().json;
const columns = (root.reportMetadata && root.reportMetadata.detailColumns) || [];
const factMap = root.factMap || {};
const bucket = factMap["T!T"] || factMap["T|T"] || {};
const rows = bucket.rows || [];

if (!columns.length || !rows.length) {
  return [];
}

return rows
  .map((row) => {
    const cells = row.dataCells || [];
    const raw = {};
    columns.forEach((col, i) => {
      raw[col] = cellValue(cells[i]);
    });

    const out = { ...raw };
    for (const [from, to] of Object.entries(REPORT_TO_SF)) {
      if (Object.prototype.hasOwnProperty.call(raw, from)) {
        out[to] = raw[from];
      }
    }

    const id = out.Id || raw.ACCOUNT_ID || firstRecordId(cells) || "";
    if (id) out.Id = id;

    return { json: out };
  })
  .filter((item) => item.json.Id && String(item.json.Name || item.json["ACCOUNT.NAME"] || "").trim());
