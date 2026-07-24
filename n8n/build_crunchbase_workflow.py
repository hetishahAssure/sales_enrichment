#!/usr/bin/env python3
"""Assemble the Crunchbase (per-company) n8n workflow — CSV upload -> CSV download.

Reuses the Anthropic Header Auth credential; no Salesforce, no Google Sheets.

Run:  python3 build_crunchbase_workflow.py
Out:  crunchbase_enrichment.upload.workflow.json
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(HERE, "prepare_cb.js"), encoding="utf-8") as f:
    PREPARE_JS = f.read()
with open(os.path.join(HERE, "merge_cb.js"), encoding="utf-8") as f:
    MERGE_JS = f.read()

CONTINUE = {"onError": "continueRegularOutput"}


def node(id_, name, type_, ver, x, y, params, extra=None):
    n = {"id": id_, "name": name, "type": type_, "typeVersion": ver,
         "position": [x, y], "parameters": params}
    if extra:
        n.update(extra)
    return n


nodes = [
    node("cb-form", "On Form Submit", "n8n-nodes-base.formTrigger", 2.2, 0, 300, {
        "formTitle": "Crunchbase Enrichment — upload CSV",
        "formDescription": "Upload your companies CSV to enrich it with funding/investor data.",
        "formFields": {"values": [{
            "fieldLabel": "file",
            "fieldType": "file",
            "requiredField": True,
            "multipleFiles": False,
            "acceptFileTypes": ".csv",
        }]},
        "options": {},
    }, {"webhookId": "crunchbase-enrich-form"}),

    node("cb-extract", "Extract From File", "n8n-nodes-base.extractFromFile", 1, 220, 300, {
        "operation": "csv",
        "binaryPropertyName": "file",
        "options": {},
    }),

    node("cb-skip", "Skip CB Enriched", "n8n-nodes-base.filter", 2, 440, 300, {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
            "conditions": [{
                "id": "cond-empty",
                "leftValue": "={{ $json['last_funding_stage'] }}",
                "rightValue": "",
                "operator": {"type": "string", "operation": "empty", "singleValue": True},
            }],
            "combinator": "and",
        },
        "options": {},
    }),

    node("cb-prep", "Prepare Crunchbase", "n8n-nodes-base.code", 2, 660, 300, {
        "mode": "runOnceForEachItem", "jsCode": PREPARE_JS,
    }),

    node("cb-claude", "Crunchbase Research", "n8n-nodes-base.httpRequest", 4.2, 880, 300, {
        "method": "POST", "url": "https://api.anthropic.com/v1/messages",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "anthropic-version", "value": "2023-06-01"}]},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": "={{ $('Prepare Crunchbase').item.json._cbBody }}",
        "options": {"batching": {"batch": {"batchSize": 1, "batchInterval": 1500}}},
    }, CONTINUE),

    node("cb-merge", "Merge Crunchbase", "n8n-nodes-base.code", 2, 1100, 300, {
        "mode": "runOnceForEachItem", "jsCode": MERGE_JS,
    }),

    node("cb-tofile", "Convert to File", "n8n-nodes-base.convertToFile", 1.1, 1320, 300, {
        "operation": "csv",
        "options": {"fileName": "YPO_crunchbase_enriched.csv"},
    }),
]


def link(a, b):
    return {a: {"main": [[{"node": b, "type": "main", "index": 0}]]}}


chain = ["On Form Submit", "Extract From File", "Skip CB Enriched",
         "Prepare Crunchbase", "Crunchbase Research", "Merge Crunchbase", "Convert to File"]
connections = {}
for a, b in zip(chain, chain[1:]):
    connections.update(link(a, b))

workflow = {
    "name": "AssureSoft — Crunchbase Enrichment (CSV upload test)",
    "nodes": nodes,
    "connections": connections,
    "active": False,
    "settings": {"executionOrder": "v1"},
    "pinData": {},
}

out = os.path.join(HERE, "crunchbase_enrichment.upload.workflow.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(workflow, f, indent=2, ensure_ascii=False)

print("Wrote", os.path.basename(out), "| nodes:", len(nodes), "| connections:", len(connections))
