#!/usr/bin/env python3
"""Assemble the two scheduled Salesforce enrichment n8n workflows.

The enrichment is split into two independent weekly workflows so each source
can be run, capped, and billed separately:

  hiring     — every Saturday 20:00: hiring signals from a Salesforce Report
               cohort → existing Account fields. No Skip Enriched / SOQL
               “already researched” filter; the report defines who to enrich.
  crunchbase — every Sunday 20:00: funding research → existing Account /
               crunchbase__ fields. Skip proxy: any of Crunchbase_URL__c,
               Investors__c, crunchbase__Total_Funding_USD__c,
               crunchbase__Latest_Round_Funding_Type__c, Latest_Funding_Date__c.

No dedicated *Enriched__c fields. Description is not used as an enrichment
dump; eligible runs only strip legacy automation blocks from Description.

Credentials to attach after import (both workflows):
  - Get Report / Get Accounts / Update Account -> Salesforce OAuth2
  - Crunchbase Research / Claude  -> Anthropic API (`Anthropic account`)
  - JSearch / Theirstack / Apollo -> their Header Auth credentials
  - Send an Email (both)          -> SMTP (`SMTP account`)
  - Also set Workflow Settings → Error Workflow to this workflow so the
    Error Trigger fires on hard failures.

Set SF_HIRING_REPORT_ID (00O…) before rebuild, or edit Get Report URL after
import.

Run:  python3 build_salesforce_workflow.py
Out:  salesforce_hiring_enrichment.schedule.workflow.json
      salesforce_crunchbase_enrichment.schedule.workflow.json
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def read(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


MAP_CB_JS = read("map_salesforce_cb.js")
MAP_HIRING_JS = read("map_salesforce_hiring.js")
MERGE_CB_JS = read("merge_cb.js")
MERGE_JS = read("merge.js")
PREPARE_CB_JS = read("prepare_cb.js")
PREPARE_SF_JS = read("prepare_sf.js")
FLATTEN_REPORT_HIRING_JS = read("flatten_report_hiring.js")
CB_SUMMARY_JS = read("cb_build_summary_email.js")
CB_FAILURE_JS = read("cb_build_failure_email.js")
HIRING_SUMMARY_JS = read("hiring_build_summary_email.js")
HIRING_FAILURE_JS = read("hiring_build_failure_email.js")

CONTINUE = {"onError": "continueRegularOutput"}

# Legacy Description markers — still skipped on the Crunchbase path during
# migration so previously Description-marked Accounts are not re-billed.
CB_LEGACY_MARKERS = ["[Funding enriched"]

# Existing Account fields only (diff + SOQL for Crunchbase). Keep in sync with map_*.js.
CUSTOM_FIELDS = [
    "Careers_Page__c",
    "Crunchbase_URL__c",
    "Hiring_Score__c",
    "Investors__c",
    "Is_Hiring_Engineers__c",
    "Is_PE_Backed__c",
    "Is_VC_Backed__c",
    "Latest_Funding_Amount__c",
    "Latest_Funding_Date__c",
    "LinkedIn__c",
    "Open_Job_Openings__c",
    "Open_Job_Openings_Count__c",
    "crunchbase__Latest_Round_Date__c",
    "crunchbase__Latest_Round_Funding_Type__c",
    "crunchbase__Latest_Round_Money_Raised_in_USD__c",
    "crunchbase__Number_of_Employees_Crunchbase__c",
    "crunchbase__Number_of_Investors__c",
    "crunchbase__Total_Funding_USD__c",
]


def build_soql(where_clause):
    # Proxy skip fields are SOQL-filterable. ORDER BY LastModifiedDate ASC
    # sinks freshly updated accounts to the bottom of the batch.
    return (
        "SELECT Id, Name, Website, BillingState, Description, NumberOfEmployees, "
        + ", ".join(CUSTOM_FIELDS)
        + f" FROM Account WHERE {where_clause} "
        + "ORDER BY LastModifiedDate ASC LIMIT 500"
    )


# Funding: not yet researched if none of the funding proxy fields are set.
CB_SOQL = build_soql(
    "Crunchbase_URL__c = null "
    "AND Investors__c = null "
    "AND crunchbase__Total_Funding_USD__c = null "
    "AND crunchbase__Latest_Round_Funding_Type__c = null "
    "AND Latest_Funding_Date__c = null"
)

# Testing sandbox host (matches current n8n export). Switch to production My
# Domain before go-live.
SF_HOST = "https://assuresoft--testing.sandbox.my.salesforce.com"
SF_API = f"{SF_HOST}/services/data/v59.0"
SF_UPDATE_URL = f"={SF_API}/sobjects/Account/{{{{ $json.Id }}}}"

# Hiring cohort: tabular Accounts report (00O… from the report URL).
# Override with env SF_HIRING_REPORT_ID or edit the Get Report node after import.
SF_HIRING_REPORT_ID = os.environ.get("SF_HIRING_REPORT_ID", "00OXXXXXXXXXXXXXXX")

EMAIL_FROM = "n8n.sales@assuresoft.com.bo"
EMAIL_TO = "sales@assuresoft.com"


def node(id_, name, type_, ver, params, extra=None):
    n = {"id": id_, "name": name, "type": type_, "typeVersion": ver,
         "position": [0, 300], "parameters": params}
    if extra:
        n.update(extra)
    return n


def schedule_node(prefix, name, day):
    return node(f"{prefix}-schedule", name, "n8n-nodes-base.scheduleTrigger", 1.2, {
        "rule": {"interval": [{
            "field": "weeks",
            "weeksInterval": 1,
            "triggerAtDay": [day],
            "triggerAtHour": 20,
            "triggerAtMinute": 0,
        }]},
    })


def get_accounts_node(prefix, soql):
    return node(f"{prefix}-get", "Get Accounts", "n8n-nodes-base.salesforce", 1, {
        "resource": "search",
        "query": soql,
    })


def get_report_node(prefix, report_id):
    return node(f"{prefix}-get-report", "Get Report", "n8n-nodes-base.httpRequest", 4.2, {
        "method": "GET",
        "url": f"={SF_API}/analytics/reports/{report_id}",
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "salesforceOAuth2Api",
        "options": {},
    })


def _empty_field_condition(cond_id, field):
    return {
        "id": cond_id,
        "leftValue": f"={{{{ $json.{field} }}}}",
        "rightValue": "",
        "operator": {
            "type": "string",
            "operation": "empty",
            "singleValue": True,
        },
    }


def skip_enriched_node(prefix, proxy_fields, legacy_markers):
    """Keep Accounts whose skip-proxy fields are empty and lack legacy Description markers."""
    conditions = [
        _empty_field_condition(f"cond-proxy-{i}", field)
        for i, field in enumerate(proxy_fields)
    ]
    for i, marker in enumerate(legacy_markers):
        conditions.append({
            "id": f"cond-legacy-{i}",
            "leftValue": "={{ $json.Description }}",
            "rightValue": marker,
            "operator": {"type": "string", "operation": "notContains"},
        })
    return node(f"{prefix}-skip", "Skip Enriched", "n8n-nodes-base.filter", 2, {
        "conditions": {
            "options": {
                "caseSensitive": True,
                "leftValue": "",
                "typeValidation": "loose",
            },
            "conditions": conditions,
            "combinator": "and",
        },
        "options": {},
    })


def cap_node(prefix):
    return node(f"{prefix}-cap", "Cap Per Run", "n8n-nodes-base.limit", 1, {
        "maxItems": 25,
    })


def code_node(id_, name, js, mode="runOnceForEachItem"):
    return node(id_, name, "n8n-nodes-base.code", 2, {
        "mode": mode, "jsCode": js,
    })


def email_send_node(id_, name):
    return node(id_, name, "n8n-nodes-base.emailSend", 2.1, {
        "fromEmail": EMAIL_FROM,
        "toEmail": EMAIL_TO,
        "subject": "={{ $json.subject }}",
        "emailFormat": "text",
        "text": "={{ $json.body }}",
        "options": {},
    }, {
        "credentials": {
            "smtp": {"id": "yjdTjepkqEgUcibR", "name": "SMTP account"},
        },
    })


def anthropic_node(id_, name, body_expr):
    return node(id_, name, "n8n-nodes-base.httpRequest", 4.2, {
        "method": "POST", "url": "https://api.anthropic.com/v1/messages",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "anthropic-version", "value": "2023-06-01"}]},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": body_expr,
        "options": {"batching": {"batch": {"batchSize": 1, "batchInterval": 1500}}},
    }, CONTINUE)


def has_changes_node(prefix):
    return node(f"{prefix}-haschanges", "Has Changes", "n8n-nodes-base.filter", 2, {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
            "conditions": [{
                "id": "cond-changed",
                "leftValue": "={{ $json._hasChanges }}",
                "rightValue": "",
                "operator": {"type": "boolean", "operation": "true", "singleValue": True},
            }],
            "combinator": "and",
        },
        "options": {},
    })


def update_node(prefix):
    # PATCH via the Salesforce OAuth2 credential: the native Salesforce update
    # operation sends a fixed field set, but "only changed fields" needs a
    # per-item dynamic body — hence one HTTP node on the same credential.
    return node(f"{prefix}-update", "Update Account", "n8n-nodes-base.httpRequest", 4.2, {
        "method": "PATCH",
        "url": SF_UPDATE_URL,
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "salesforceOAuth2Api",
        "sendBody": True, "specifyBody": "json",
        "jsonBody": "={{ $json._changes }}",
        "options": {"batching": {"batch": {"batchSize": 1, "batchInterval": 500}}},
    }, CONTINUE)


hiring_nodes = [
    schedule_node("hi", "Every Saturday 20:00", 6),
    get_report_node("hi", SF_HIRING_REPORT_ID),
    code_node("hi-flatten", "Flatten Report", FLATTEN_REPORT_HIRING_JS,
              mode="runOnceForAllItems"),
    cap_node("hi"),
    code_node("hi-prep", "Prepare Requests", PREPARE_SF_JS),
    anthropic_node("hi-claude", "Claude Web Search",
                   "={{ $('Prepare Requests').item.json._claudeBody }}"),

    node("hi-jsearch", "JSearch", "n8n-nodes-base.httpRequest", 4.2, {
        "method": "GET", "url": "https://jsearch.p.rapidapi.com/search",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendHeaders": True,
        "headerParameters": {"parameters": [
            {"name": "X-RapidAPI-Host", "value": "jsearch.p.rapidapi.com"},
        ]},
        "sendQuery": True,
        "queryParameters": {"parameters": [
            {"name": "query", "value": "={{ $('Prepare Requests').item.json._jsearchQuery }}"},
            {"name": "page", "value": "1"},
            {"name": "num_pages", "value": "1"},
            {"name": "country", "value": "us"},
            {"name": "date_posted", "value": "month"},
        ]},
        "options": {"batching": {"batch": {"batchSize": 1, "batchInterval": 2000}}},
    }, {**CONTINUE, "retryOnFail": True, "maxTries": 3, "waitBetweenTries": 5000}),

    node("hi-theirstack", "Theirstack", "n8n-nodes-base.httpRequest", 4.2, {
        "method": "POST", "url": "https://api.theirstack.com/v1/jobs/search",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendBody": True, "specifyBody": "json",
        "jsonBody": "={{ $('Prepare Requests').item.json._theirstackBody }}",
        "options": {"batching": {"batch": {"batchSize": 1, "batchInterval": 1000}}},
    }, CONTINUE),

    node("hi-apollo", "Apollo", "n8n-nodes-base.httpRequest", 4.2, {
        "method": "POST", "url": "https://api.apollo.io/v1/organizations/search",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendBody": True, "specifyBody": "json",
        "jsonBody": "={{ $('Prepare Requests').item.json._apolloBody }}",
        "options": {"batching": {"batch": {"batchSize": 1, "batchInterval": 1000}}},
    }, CONTINUE),

    code_node("hi-merge", "Merge & Score", MERGE_JS),
    code_node("hi-map", "Map to Salesforce", MAP_HIRING_JS),
    has_changes_node("hi"),
    update_node("hi"),
    code_node("hi-summary", "Build Run Summary", HIRING_SUMMARY_JS,
              mode="runOnceForAllItems"),
    email_send_node("hi-email", "Send an Email"),
    node("hi-error", "Error Trigger", "n8n-nodes-base.errorTrigger", 1, {}),
    code_node("hi-failure", "Build Failure Email", HIRING_FAILURE_JS,
              mode="runOnceForAllItems"),
]

hiring_chain = ["Every Saturday 20:00", "Get Report", "Flatten Report", "Cap Per Run",
                "Prepare Requests", "Claude Web Search", "JSearch", "Theirstack", "Apollo",
                "Merge & Score", "Map to Salesforce", "Has Changes", "Update Account"]

# After Map, Has Changes → Update runs first (connection order), then
# Build Run Summary → Send an Email so the digest can include PATCH errors.
# Error Trigger → Build Failure Email → same Send an Email for hard failures.
hiring_extra = {
    "Map to Salesforce": [
        {"node": "Build Run Summary", "type": "main", "index": 0},
    ],
    "Build Run Summary": [
        {"node": "Send an Email", "type": "main", "index": 0},
    ],
    "Error Trigger": [
        {"node": "Build Failure Email", "type": "main", "index": 0},
    ],
    "Build Failure Email": [
        {"node": "Send an Email", "type": "main", "index": 0},
    ],
}

# The Crunchbase run is scheduled a day after the hiring run so the two
# workflows never hit the Anthropic / Salesforce rate limits at the same time.
cb_nodes = [
    schedule_node("cb", "Every Sunday 20:00", 0),
    get_accounts_node("cb", CB_SOQL),
    skip_enriched_node(
        "cb",
        [
            "Crunchbase_URL__c",
            "Investors__c",
            "crunchbase__Total_Funding_USD__c",
            "crunchbase__Latest_Round_Funding_Type__c",
            "Latest_Funding_Date__c",
        ],
        CB_LEGACY_MARKERS,
    ),
    cap_node("cb"),
    code_node("cb-prep", "Prepare Crunchbase", PREPARE_CB_JS),
    anthropic_node("cb-claude", "Crunchbase Research",
                   "={{ $('Prepare Crunchbase').item.json._cbBody }}"),
    code_node("cb-merge", "Merge Crunchbase", MERGE_CB_JS),
    code_node("cb-map", "Map to Salesforce", MAP_CB_JS),
    has_changes_node("cb"),
    update_node("cb"),
    code_node("cb-summary", "Build Run Summary", CB_SUMMARY_JS,
              mode="runOnceForAllItems"),
    email_send_node("cb-email", "Send an Email"),
    node("cb-error", "Error Trigger", "n8n-nodes-base.errorTrigger", 1, {}),
    code_node("cb-failure", "Build Failure Email", CB_FAILURE_JS,
              mode="runOnceForAllItems"),
]

cb_chain = ["Every Sunday 20:00", "Get Accounts", "Skip Enriched", "Cap Per Run",
            "Prepare Crunchbase", "Crunchbase Research", "Merge Crunchbase",
            "Map to Salesforce", "Has Changes", "Update Account"]


def link(a, b):
    return {a: {"main": [[{"node": b, "type": "main", "index": 0}]]}}


def build(name, nodes, chain, out_name, extra_connections=None, layout_extra=None):
    connections = {}
    for a, b in zip(chain, chain[1:]):
        connections[a] = {"main": [[{"node": b, "type": "main", "index": 0}]]}
    if extra_connections:
        for src, targets in extra_connections.items():
            if src in connections:
                # Append additional targets onto the existing main[0] list
                # (preserves depth-first order: first target runs fully first).
                connections[src]["main"][0].extend(targets)
            else:
                connections[src] = {"main": [targets]}

    # Lay the nodes out left-to-right in chain order.
    order = {n: i for i, n in enumerate(chain)}
    if layout_extra:
        order.update(layout_extra)
    for n in nodes:
        n["position"] = [order.get(n["name"], 0) * 220, 300 if n["name"] not in (
            "Error Trigger", "Build Failure Email"
        ) else 520]
        if n["name"] in ("Error Trigger",):
            n["position"] = [order.get("Map to Salesforce", 7) * 220, 520]
        elif n["name"] in ("Build Failure Email",):
            n["position"] = [order.get("Has Changes", 8) * 220, 520]
        elif n["name"] in ("Build Run Summary",):
            n["position"] = [order.get("Update Account", 9) * 220, 120]
        elif n["name"] in ("Send an Email",):
            n["position"] = [(order.get("Update Account", 9) + 1) * 220, 300]

    # Attach known credentials on Salesforce / Anthropic nodes when present.
    by_name = {n["name"]: n for n in nodes}
    sf_cred = {
        "salesforceOAuth2Api": {
            "id": "bypi7DAgDNwp2IZi",
            "name": "Salesforce account",
        },
    }
    anth_cred = {
        "anthropicApi": {
            "id": "89SoEYPbesTqn7ET",
            "name": "Anthropic account",
        },
    }
    if "Get Accounts" in by_name:
        by_name["Get Accounts"]["credentials"] = sf_cred
    if "Get Report" in by_name:
        by_name["Get Report"]["credentials"] = sf_cred
    if "Update Account" in by_name:
        by_name["Update Account"]["credentials"] = sf_cred
    for anth_node in ("Crunchbase Research", "Claude Web Search"):
        if anth_node not in by_name:
            continue
        by_name[anth_node]["credentials"] = anth_cred
        # Prefer native Anthropic credential (matches live export).
        by_name[anth_node]["parameters"]["authentication"] = (
            "predefinedCredentialType"
        )
        by_name[anth_node]["parameters"]["nodeCredentialType"] = (
            "anthropicApi"
        )
        by_name[anth_node]["parameters"].pop("genericAuthType", None)

    workflow = {
        "name": name,
        "nodes": nodes,
        "connections": connections,
        "active": False,
        "settings": {"executionOrder": "v1"},
        "pinData": {},
    }
    out = os.path.join(HERE, out_name)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(workflow, f, indent=2, ensure_ascii=False)
    print("Wrote", out_name, "| nodes:", len(nodes), "| connections:", len(connections))


build("AssureSoft — Salesforce Account Enrichment (Hiring signals, weekly)",
      hiring_nodes, hiring_chain, "salesforce_hiring_enrichment.schedule.workflow.json",
      extra_connections=hiring_extra)

cb_extra = hiring_extra
build("AssureSoft — Salesforce Account Enrichment (Crunchbase funding, weekly)",
      cb_nodes, cb_chain, "salesforce_crunchbase_enrichment.schedule.workflow.json",
      extra_connections=cb_extra)
