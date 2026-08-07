#!/usr/bin/env python3
"""Assemble the weekly funding-discovery n8n workflow.

Mirrors Claude+web-search style used by crunchbase_enrichment.upload.workflow.json,
then dedupes/creates Salesforce Accounts and emails a digest via Gmail.

Run:  python3 build_funding_workflow.py
Out:  funding_discovery.workflow.json
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def load_js(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


PREPARE_JS = load_js("funding_prepare.js")
PARSE_JS = load_js("funding_parse.js")
DEDUPE_JS = load_js("funding_dedupe.js")
EMAIL_JS = load_js("funding_email.js")
FINALIZE_EMAIL_JS = load_js("funding_finalize_email.js")

CONTINUE = {"onError": "continueRegularOutput"}


def node(id_, name, type_, ver, x, y, params, extra=None):
    n = {
        "id": id_,
        "name": name,
        "type": type_,
        "typeVersion": ver,
        "position": [x, y],
        "parameters": params,
    }
    if extra:
        n.update(extra)
    return n


nodes = [
    node("fd-sched", "Schedule Trigger", "n8n-nodes-base.scheduleTrigger", 1.2, 0, 300, {
        "rule": {
            "interval": [{
                "field": "cronExpression",
                "expression": "0 21 * * 6",
            }],
        },
    }),

    # Change emailTo here (or in n8n UI) — used by the Gmail node.
    node("fd-config", "Config", "n8n-nodes-base.set", 3.4, 220, 300, {
        "mode": "manual",
        "duplicateItem": False,
        "assignments": {
            "assignments": [
                {
                    "id": "email-to",
                    "name": "emailTo",
                    "value": "heti.shah@assuresoft.com",
                    "type": "string",
                },
            ],
        },
        "options": {},
    }),

    node("fd-sf-get", "Get Salesforce Accounts", "n8n-nodes-base.salesforce", 1, 440, 300, {
        "resource": "account",
        "operation": "getAll",
        "returnAll": True,
        "options": {
            "fields": "Id,Name,Website",
        },
    }, CONTINUE),

    # Collapse N Account items → 1 so discovery runs once per week.
    node("fd-sf-collect", "Collect SF Accounts", "n8n-nodes-base.code", 2, 660, 300, {
        "mode": "runOnceForAllItems",
        "jsCode": (
            "const items = $input.all();\n"
            "return [{ json: { _sfReady: true, _sfAccountCount: items.length } }];\n"
        ),
    }),

    node("fd-prep", "Prepare Funding Discovery", "n8n-nodes-base.code", 2, 880, 300, {
        "mode": "runOnceForAllItems",
        "jsCode": PREPARE_JS,
    }),

    node("fd-claude", "Claude Funding Discovery", "n8n-nodes-base.httpRequest", 4.2, 1100, 300, {
        "method": "POST",
        "url": "https://api.anthropic.com/v1/messages",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendHeaders": True,
        "headerParameters": {
            "parameters": [{"name": "anthropic-version", "value": "2023-06-01"}],
        },
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": "={{ $('Prepare Funding Discovery').item.json._claudeBody }}",
        "options": {
            "timeout": 120000,
        },
    }, CONTINUE),

    node("fd-parse", "Parse Funding Companies", "n8n-nodes-base.code", 2, 1320, 300, {
        "mode": "runOnceForAllItems",
        "jsCode": PARSE_JS,
    }),

    node("fd-dedupe", "Dedupe vs Salesforce", "n8n-nodes-base.code", 2, 1540, 300, {
        "mode": "runOnceForAllItems",
        "jsCode": DEDUPE_JS,
    }),

    node("fd-filter-new", "Only New Accounts", "n8n-nodes-base.filter", 2, 1760, 180, {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
            "conditions": [{
                "id": "cond-new",
                "leftValue": "={{ $json._isNew }}",
                "rightValue": True,
                "operator": {"type": "boolean", "operation": "true", "singleValue": True},
            }],
            "combinator": "and",
        },
        "options": {},
    }),

    node("fd-sf-create", "Create Salesforce Account", "n8n-nodes-base.salesforce", 1, 1980, 180, {
        "resource": "account",
        "operation": "create",
        "name": "={{ $json.Name }}",
        "additionalFields": {
            "website": "={{ $json.Website }}",
            "description": "={{ $json.Description }}",
            "industry": "={{ $json.Industry }}",
            "numberOfEmployees": "={{ $json.NumberOfEmployees }}",
            "billingAddress": {
                "billingCity": "={{ $json.BillingCity }}",
                "billingState": "={{ $json.BillingState }}",
                "billingCountry": "={{ $json.BillingCountry }}",
            },
        },
    }, CONTINUE),

    node("fd-digest", "Build Funding Digest", "n8n-nodes-base.code", 2, 1760, 420, {
        "mode": "runOnceForAllItems",
        "jsCode": EMAIL_JS,
    }),

    node("fd-csv", "Convert Digest to CSV", "n8n-nodes-base.convertToFile", 1.1, 1980, 420, {
        "operation": "csv",
        "options": {
            "fileName": "weekly_funding_digest.csv",
        },
    }),

    node("fd-finalize", "Finalize Email", "n8n-nodes-base.code", 2, 2200, 420, {
        "mode": "runOnceForAllItems",
        "jsCode": FINALIZE_EMAIL_JS,
    }),

    node("fd-gmail", "Send Gmail Digest", "n8n-nodes-base.gmail", 2.1, 2420, 420, {
        "resource": "message",
        "operation": "send",
        "sendTo": "={{ $json.emailTo }}",
        "subject": "={{ $json.subject }}",
        "emailType": "text",
        "message": "={{ $json.body }}",
        "options": {
            "appendAttribution": False,
            "attachmentsUi": {
                "attachmentsBinary": [{"property": "data"}],
            },
        },
    }),
]


def link(src, dst):
    return {src: {"main": [[{"node": dst, "type": "main", "index": 0}]]}}


connections = {}
chain = [
    ("Schedule Trigger", "Config"),
    ("Config", "Get Salesforce Accounts"),
    ("Get Salesforce Accounts", "Collect SF Accounts"),
    ("Collect SF Accounts", "Prepare Funding Discovery"),
    ("Prepare Funding Discovery", "Claude Funding Discovery"),
    ("Claude Funding Discovery", "Parse Funding Companies"),
    ("Parse Funding Companies", "Dedupe vs Salesforce"),
]
for a, b in chain:
    connections.update(link(a, b))

# Fan-out after dedupe: create new accounts + build/email full digest
connections["Dedupe vs Salesforce"] = {
    "main": [[
        {"node": "Only New Accounts", "type": "main", "index": 0},
        {"node": "Build Funding Digest", "type": "main", "index": 0},
    ]],
}
connections.update(link("Only New Accounts", "Create Salesforce Account"))
connections.update(link("Build Funding Digest", "Convert Digest to CSV"))
connections.update(link("Convert Digest to CSV", "Finalize Email"))
connections.update(link("Finalize Email", "Send Gmail Digest"))

workflow = {
    "name": "AssureSoft — Weekly Funding Discovery (Crunchbase → Salesforce → Gmail)",
    "nodes": nodes,
    "connections": connections,
    "active": False,
    "settings": {
        "executionOrder": "v1",
        "timezone": "America/La_Paz",
    },
    "pinData": {},
    "meta": {
        "templateCredsSetupCompleted": False,
        "notes": (
            "After import: attach Anthropic Header Auth to Claude Funding Discovery; "
            "attach your existing Salesforce credential to both Salesforce nodes; "
            "attach Gmail OAuth2 to Send Gmail Digest. "
            "Change recipient in the Config node (emailTo). "
            "NumberOfEmployees maps discovered team size; remap if your org uses a custom Team Size field."
        ),
    },
}

out = os.path.join(HERE, "funding_discovery.workflow.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(workflow, f, indent=2, ensure_ascii=False)

print("Wrote", os.path.basename(out), "| nodes:", len(nodes), "| connections:", len(connections))
