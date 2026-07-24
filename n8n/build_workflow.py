#!/usr/bin/env python3
"""Assemble the n8n workflow JSON(s), embedding prepare.js / merge.js safely.

Run:  python3 build_workflow.py
Out:  hiring_enrichment.workflow.json         (Google Sheets source/sink)
      hiring_enrichment.upload.workflow.json  (CSV upload -> CSV download; no Google creds)
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(HERE, "prepare.js"), encoding="utf-8") as f:
    PREPARE_JS = f.read()
with open(os.path.join(HERE, "merge.js"), encoding="utf-8") as f:
    MERGE_JS = f.read()

RL_EMPTY = {"__rl": True, "value": "", "mode": "list", "cachedResultName": ""}
CONTINUE = {"onError": "continueRegularOutput"}


def node(id_, name, type_, ver, x, y, params, extra=None):
    n = {"id": id_, "name": name, "type": type_, "typeVersion": ver,
         "position": [x, y], "parameters": params}
    if extra:
        n.update(extra)
    return n


# ── Shared middle nodes (identical in both variants) ────────────────────────
def middle_nodes(x0):
    return [
        node("m-skip", "Skip Enriched", "n8n-nodes-base.filter", 2, x0, 300, {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                "conditions": [{
                    "id": "cond-empty",
                    "leftValue": "={{ $json['is_hiring_engineers'] }}",
                    "rightValue": "",
                    "operator": {"type": "string", "operation": "empty", "singleValue": True},
                }],
                "combinator": "and",
            },
            "options": {},
        }),
        node("m-prep", "Prepare Requests", "n8n-nodes-base.code", 2, x0 + 220, 300, {
            "mode": "runOnceForEachItem", "jsCode": PREPARE_JS,
        }),
        node("m-claude", "Claude Web Search", "n8n-nodes-base.httpRequest", 4.2, x0 + 440, 300, {
            "method": "POST", "url": "https://api.anthropic.com/v1/messages",
            "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {"parameters": [{"name": "anthropic-version", "value": "2023-06-01"}]},
            "sendBody": True, "specifyBody": "json",
            "jsonBody": "={{ $('Prepare Requests').item.json._claudeBody }}",
            "options": {"batching": {"batch": {"batchSize": 1, "batchInterval": 1500}}},
        }, CONTINUE),
        node("m-jsearch", "JSearch", "n8n-nodes-base.httpRequest", 4.2, x0 + 660, 300, {
            "method": "GET", "url": "https://jsearch.p.rapidapi.com/search",
            "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {"parameters": [{"name": "X-RapidAPI-Host", "value": "jsearch.p.rapidapi.com"}]},
            "sendQuery": True,
            "queryParameters": {"parameters": [
                {"name": "query", "value": "={{ $('Prepare Requests').item.json._jsearchQuery }}"},
                {"name": "page", "value": "1"},
                {"name": "num_pages", "value": "1"},
                {"name": "country", "value": "us"},
                {"name": "date_posted", "value": "month"},
            ]},
            "options": {},
        }, CONTINUE),
        node("m-theirstack", "Theirstack", "n8n-nodes-base.httpRequest", 4.2, x0 + 880, 300, {
            "method": "POST", "url": "https://api.theirstack.com/v1/jobs/search",
            "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
            "sendBody": True, "specifyBody": "json",
            "jsonBody": "={{ $('Prepare Requests').item.json._theirstackBody }}",
            "options": {},
        }, CONTINUE),
        node("m-apollo", "Apollo", "n8n-nodes-base.httpRequest", 4.2, x0 + 1100, 300, {
            "method": "POST", "url": "https://api.apollo.io/v1/organizations/search",
            "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
            "sendBody": True, "specifyBody": "json",
            "jsonBody": "={{ $('Prepare Requests').item.json._apolloBody }}",
            "options": {},
        }, CONTINUE),
        node("m-merge", "Merge & Score", "n8n-nodes-base.code", 2, x0 + 1320, 300, {
            "mode": "runOnceForEachItem", "jsCode": MERGE_JS,
        }),
    ]


MIDDLE_CHAIN = ["Skip Enriched", "Prepare Requests", "Claude Web Search",
                "JSearch", "Theirstack", "Apollo", "Merge & Score"]


def link(a, b):
    return {a: {"main": [[{"node": b, "type": "main", "index": 0}]]}}


def connect(chain):
    conns = {}
    for a, b in zip(chain, chain[1:]):
        conns.update(link(a, b))
    return conns


def write(name, workflow):
    out = os.path.join(HERE, name)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(workflow, f, indent=2, ensure_ascii=False)
    print("Wrote", os.path.basename(out),
          "| nodes:", len(workflow["nodes"]),
          "| connections:", len(workflow["connections"]))


# ══ Variant 1 — Google Sheets ══════════════════════════════════════════════
head = [
    node("s-start", "Start", "n8n-nodes-base.manualTrigger", 1, 0, 300, {}),
    node("s-get", "Get Companies", "n8n-nodes-base.googleSheets", 4.5, 220, 300, {
        "operation": "read", "documentId": RL_EMPTY, "sheetName": RL_EMPTY, "options": {},
    }),
]
tail = [
    node("s-write", "Write Results", "n8n-nodes-base.googleSheets", 4.5, 1980, 300, {
        "operation": "update", "documentId": RL_EMPTY, "sheetName": RL_EMPTY,
        "columns": {"mappingMode": "autoMapInputData", "value": {},
                    "matchingColumns": ["Account ID"], "schema": []},
        "options": {},
    }),
]
sheets_chain = ["Start", "Get Companies"] + MIDDLE_CHAIN + ["Write Results"]
write("hiring_enrichment.workflow.json", {
    "name": "AssureSoft — Hiring Signal Enrichment (Google Sheets)",
    "nodes": head + middle_nodes(440) + tail,
    "connections": connect(sheets_chain),
    "active": False, "settings": {"executionOrder": "v1"}, "pinData": {},
})

# ══ Variant 2 — CSV upload / download (no Google creds) ═════════════════════
head = [
    node("u-form", "On Form Submit", "n8n-nodes-base.formTrigger", 2.2, 0, 300, {
        "formTitle": "Hiring Enrichment — upload CSV",
        "formDescription": "Upload your companies CSV to enrich it.",
        "formFields": {"values": [{
            "fieldLabel": "file",
            "fieldType": "file",
            "requiredField": True,
            "multipleFiles": False,
            "acceptFileTypes": ".csv",
        }]},
        "options": {},
    }, {"webhookId": "hiring-enrich-form"}),
    node("u-extract", "Extract From File", "n8n-nodes-base.extractFromFile", 1, 220, 300, {
        "operation": "csv",
        "binaryPropertyName": "file",
        "options": {},
    }),
]
tail = [
    node("u-tofile", "Convert to File", "n8n-nodes-base.convertToFile", 1.1, 1980, 300, {
        "operation": "csv",
        "options": {"fileName": "YPO_Qualified_enriched.csv"},
    }),
]
upload_chain = ["On Form Submit", "Extract From File"] + MIDDLE_CHAIN + ["Convert to File"]
write("hiring_enrichment.upload.workflow.json", {
    "name": "AssureSoft — Hiring Signal Enrichment (CSV upload test)",
    "nodes": head + middle_nodes(440) + tail,
    "connections": connect(upload_chain),
    "active": False, "settings": {"executionOrder": "v1"}, "pinData": {},
})
