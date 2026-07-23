#!/usr/bin/env python3
"""Assemble the n8n workflow JSON, embedding prepare.js / merge.js safely.

Run:  python3 build_workflow.py
Out:  hiring_enrichment.workflow.json  (import into n8n)
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(HERE, "prepare.js"), encoding="utf-8") as f:
    PREPARE_JS = f.read()
with open(os.path.join(HERE, "merge.js"), encoding="utf-8") as f:
    MERGE_JS = f.read()

RL_EMPTY = {"__rl": True, "value": "", "mode": "list", "cachedResultName": ""}


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


CONTINUE = {"onError": "continueRegularOutput"}

nodes = [
    node("n1", "Start", "n8n-nodes-base.manualTrigger", 1, 0, 300, {}),

    node("n2", "Get Companies", "n8n-nodes-base.googleSheets", 4.5, 220, 300, {
        "operation": "read",
        "documentId": RL_EMPTY,
        "sheetName": RL_EMPTY,
        "options": {},
    }),

    node("n3", "Skip Enriched", "n8n-nodes-base.filter", 2, 440, 300, {
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

    node("n4", "Prepare Requests", "n8n-nodes-base.code", 2, 660, 300, {
        "mode": "runOnceForEachItem",
        "jsCode": PREPARE_JS,
    }),

    node("n5", "Claude Web Search", "n8n-nodes-base.httpRequest", 4.2, 880, 300, {
        "method": "POST",
        "url": "https://api.anthropic.com/v1/messages",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "anthropic-version", "value": "2023-06-01"}]},
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": "={{ $('Prepare Requests').item.json._claudeBody }}",
        "options": {"batching": {"batch": {"batchSize": 1, "batchInterval": 1500}}},
    }, CONTINUE),

    node("n6", "JSearch", "n8n-nodes-base.httpRequest", 4.2, 1100, 300, {
        "method": "GET",
        "url": "https://jsearch.p.rapidapi.com/search",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
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

    node("n7", "Theirstack", "n8n-nodes-base.httpRequest", 4.2, 1320, 300, {
        "method": "POST",
        "url": "https://api.theirstack.com/v1/jobs/search",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": "={{ $('Prepare Requests').item.json._theirstackBody }}",
        "options": {},
    }, CONTINUE),

    node("n8", "Apollo", "n8n-nodes-base.httpRequest", 4.2, 1540, 300, {
        "method": "POST",
        "url": "https://api.apollo.io/v1/organizations/search",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": "={{ $('Prepare Requests').item.json._apolloBody }}",
        "options": {},
    }, CONTINUE),

    node("n9", "Merge & Score", "n8n-nodes-base.code", 2, 1760, 300, {
        "mode": "runOnceForEachItem",
        "jsCode": MERGE_JS,
    }),

    node("n10", "Write Results", "n8n-nodes-base.googleSheets", 4.5, 1980, 300, {
        "operation": "update",
        "documentId": RL_EMPTY,
        "sheetName": RL_EMPTY,
        "columns": {
            "mappingMode": "autoMapInputData",
            "value": {},
            "matchingColumns": ["Account ID"],
            "schema": [],
        },
        "options": {},
    }),
]


def link(a, b):
    return {a: {"main": [[{"node": b, "type": "main", "index": 0}]]}}


connections = {}
chain = ["Start", "Get Companies", "Skip Enriched", "Prepare Requests",
         "Claude Web Search", "JSearch", "Theirstack", "Apollo",
         "Merge & Score", "Write Results"]
for a, b in zip(chain, chain[1:]):
    connections.update(link(a, b))

workflow = {
    "name": "AssureSoft — Hiring Signal Enrichment",
    "nodes": nodes,
    "connections": connections,
    "active": False,
    "settings": {"executionOrder": "v1"},
    "pinData": {},
}

out = os.path.join(HERE, "hiring_enrichment.workflow.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(workflow, f, indent=2, ensure_ascii=False)

print("Wrote", out)
print("Nodes:", len(nodes), "| Connections:", len(connections))
