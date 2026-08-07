#!/usr/bin/env python3
"""
Assuresoft — Crunchbase Enrichment Pass
-----------------------------------------
Uses Claude + web search to pull Crunchbase-style data for each company:
  - Funding stage, amount, date, total raised
  - Investor names (PE firms, VCs, Angels)
  - Employee count, founded year, description
  - HQ confirmation

Also builds a separate investor intelligence file:
  - data/YPO_Investors.csv — ranked list of PE/VC firms with all their portfolio
                         companies from your list, for sales targeting

Usage:
    python3 enrich_crunchbase.py

    python3 enrich_crunchbase.py --input  data/YPO_Scored.csv
    python3 enrich_crunchbase.py --output data/YPO_Final.csv
    python3 enrich_crunchbase.py --limit  50
    python3 enrich_crunchbase.py --delay  1.5
    python3 enrich_crunchbase.py --reset-errors
    python3 enrich_crunchbase.py --investors-only   # just rebuild investor file
"""

import anthropic
import csv
import json
import time
import argparse
import re
import os
import sys
from datetime import datetime
from collections import defaultdict

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv is optional; ANTHROPIC_API_KEY can also be exported manually.
    pass

# ── CONFIG ────────────────────────────────────────────────────────────────────
DEFAULT_INPUT    = "data/YPO_Scored.csv"
DEFAULT_OUTPUT   = "data/YPO_Final.csv"
INVESTORS_OUTPUT = "data/YPO_Investors.csv"
DELAY_SECONDS    = 1.5
MODEL            = "claude-haiku-4-5-20251001"

# ── PROMPT ────────────────────────────────────────────────────────────────────
def build_prompt(name: str, company: str, website: str, state: str) -> str:
    return f"""You are a B2B research assistant. Search Crunchbase, LinkedIn, and the web for funding and investor data on this company.

COMPANY: {company}
PERSON:  {name}
WEBSITE: {website or "unknown"}
STATE:   {state or "US"}

Search for:
1. Crunchbase page: crunchbase.com/organization/[company-slug]
2. Recent news about funding rounds
3. LinkedIn company page for employee count
4. Any PE/VC investor mentions

Return ONLY a valid JSON object — no markdown, no explanation:
{{
  "founded_year": "<4-digit year or empty string>",
  "total_funding": "<e.g. $4.2M | $50M | $1.2B | Undisclosed | Unknown>",
  "last_funding_stage": "<Pre-Seed | Seed | Series A | Series B | Series C | Series D+ | PE Buyout | Growth Equity | Bootstrapped | Public | Unknown>",
  "last_funding_amount": "<e.g. $8M | $45M | Undisclosed | Unknown>",
  "last_funding_date": "<e.g. 2023-Q2 | 2024-01 | Unknown>",
  "employee_count": "<e.g. 12 | 85 | 200-500 | 1200 | Unknown>",
  "investors": "<comma-separated list of investor firm names — include PE firms, VC funds, angels. Empty string if none found>",
  "investor_types": "<comma-separated types matching investors list order: PE | VC | Angel | CVC | Family Office | Unknown>",
  "crunchbase_url": "<https://www.crunchbase.com/organization/[slug] or empty string>",
  "company_description": "<one sentence description of what the company does>",
  "is_pe_backed": "<Yes | No | Unknown>",
  "is_vc_backed": "<Yes | No | Unknown>"
}}

Rules:
- Only include investors you confirmed via search — do NOT fabricate names
- If a field cannot be confirmed, use empty string "" or "Unknown"
- For investors, list all you can find — this is important"""


# ── CLAUDE CALL ───────────────────────────────────────────────────────────────
def enrich_crunchbase(client: anthropic.Anthropic, name: str, company: str, website: str, state: str) -> dict:
    response = client.messages.create(
        model=MODEL,
        max_tokens=1200,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": build_prompt(name, company, website, state)}]
    )

    text = " ".join(
        block.text for block in response.content
        if hasattr(block, "text")
    )

    match = re.search(r'\{[\s\S]*?\}', text)
    if not match:
        raise ValueError("No JSON in response")

    data = json.loads(match.group(0))

    def clean(key, default=""):
        return str(data.get(key, default)).strip()

    return {
        "founded_year":        clean("founded_year"),
        "total_funding":       clean("total_funding"),
        "last_funding_stage":  clean("last_funding_stage"),
        "last_funding_amount": clean("last_funding_amount"),
        "last_funding_date":   clean("last_funding_date"),
        "employee_count":      clean("employee_count"),
        "investors":           clean("investors"),
        "investor_types":      clean("investor_types"),
        "crunchbase_url":      clean("crunchbase_url"),
        "company_description": clean("company_description"),
        "is_pe_backed":        clean("is_pe_backed", "Unknown"),
        "is_vc_backed":        clean("is_vc_backed", "Unknown"),
    }


# ── CSV HELPERS ───────────────────────────────────────────────────────────────
def load_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    new_cols = [
        "founded_year", "total_funding", "last_funding_stage",
        "last_funding_amount", "last_funding_date", "employee_count",
        "investors", "investor_types", "crunchbase_url",
        "company_description", "is_pe_backed", "is_vc_backed",
        "_cb_status", "_cb_error"
    ]
    for row in rows:
        for col in new_cols:
            row.setdefault(col, "")
    return rows


def save_csv(rows: list[dict], path: str):
    if not rows:
        return
    keys = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def is_cb_enriched(row: dict) -> bool:
    return row.get("_cb_status") == "done"


# ── INVESTOR INTELLIGENCE FILE ────────────────────────────────────────────────
def build_investor_file(rows: list[dict], output_path: str):
    """
    Builds a separate investor intelligence CSV.
    Each row = one investor firm, with all their portfolio companies from our list,
    sorted by portfolio count so sales can prioritize.
    """
    # investor_name -> list of portfolio companies
    investor_map = defaultdict(list)

    for row in rows:
        investors_raw = row.get("investors", "").strip()
        types_raw     = row.get("investor_types", "").strip()
        if not investors_raw:
            continue

        investors = [i.strip() for i in investors_raw.split(",") if i.strip()]
        types     = [t.strip() for t in types_raw.split(",") if t.strip()]

        for idx, investor in enumerate(investors):
            inv_type = types[idx] if idx < len(types) else "Unknown"
            investor_map[investor].append({
                "investor_type":    inv_type,
                "portfolio_company": row.get("company_name", ""),
                "founder_name":     row.get("full_name", ""),
                "industry":         row.get("industry", ""),
                "state":            row.get("state", ""),
                "funding_stage":    row.get("last_funding_stage", ""),
                "funding_amount":   row.get("last_funding_amount", ""),
                "icp_score":        row.get("icp_score", ""),
                "icp_tier":         row.get("icp_tier", ""),
                "company_website":  row.get("company_website", ""),
                "company_linkedin": row.get("company_linkedin_url", ""),
                "crunchbase_url":   row.get("crunchbase_url", ""),
            })

    if not investor_map:
        print("  No investor data found yet — run enrichment first.")
        return

    # Build flat investor rows — one row per investor with portfolio summary
    investor_rows = []
    for investor_name, portfolio in sorted(investor_map.items(), key=lambda x: -len(x[1])):
        # Get type from first entry
        inv_type = portfolio[0]["investor_type"]

        # Portfolio company names
        companies = [p["portfolio_company"] for p in portfolio]
        industries = list(set(p["industry"] for p in portfolio if p["industry"]))

        # Hot prospects in this portfolio
        hot = [p for p in portfolio if "1" in str(p.get("icp_tier","")) or "Hot" in str(p.get("icp_tier",""))]
        warm = [p for p in portfolio if "2" in str(p.get("icp_tier","")) or "Warm" in str(p.get("icp_tier",""))]

        # Best ICP score in portfolio
        scores = [int(p["icp_score"]) for p in portfolio if str(p["icp_score"]).isdigit()]
        best_score = max(scores) if scores else 0

        investor_rows.append({
            "investor_name":         investor_name,
            "investor_type":         inv_type,
            "portfolio_count":       len(portfolio),
            "hot_prospects":         len(hot),
            "warm_prospects":        len(warm),
            "best_icp_score":        best_score,
            "industries":            " | ".join(industries[:5]),
            "portfolio_companies":   " | ".join(companies[:10]),
            "top_prospect_name":     hot[0]["founder_name"] if hot else (warm[0]["founder_name"] if warm else ""),
            "top_prospect_company":  hot[0]["portfolio_company"] if hot else (warm[0]["portfolio_company"] if warm else ""),
            "top_prospect_website":  hot[0]["company_website"] if hot else (warm[0]["company_website"] if warm else ""),
            "top_prospect_linkedin": hot[0]["company_linkedin"] if hot else (warm[0]["company_linkedin"] if warm else ""),
            "sales_priority":        "HIGH" if (len(hot) >= 2 or best_score >= 80) else "MEDIUM" if (len(hot) >= 1 or len(warm) >= 3) else "LOW",
        })

    # Sort by sales priority then portfolio count
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    investor_rows.sort(key=lambda r: (priority_order.get(r["sales_priority"], 3), -r["portfolio_count"]))

    # Save
    fields = [
        "investor_name", "investor_type", "sales_priority",
        "portfolio_count", "hot_prospects", "warm_prospects", "best_icp_score",
        "industries", "portfolio_companies",
        "top_prospect_name", "top_prospect_company",
        "top_prospect_website", "top_prospect_linkedin"
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(investor_rows)

    # Print investor summary
    high   = [r for r in investor_rows if r["sales_priority"] == "HIGH"]
    medium = [r for r in investor_rows if r["sales_priority"] == "MEDIUM"]
    pe     = [r for r in investor_rows if "PE" in str(r.get("investor_type",""))]
    vc     = [r for r in investor_rows if "VC" in str(r.get("investor_type",""))]

    print(f"\n  {'─'*52}")
    print(f"  INVESTOR INTELLIGENCE FILE: {output_path}")
    print(f"  {'─'*52}")
    print(f"  Total unique investors : {len(investor_rows):,}")
    print(f"  PE firms               : {len(pe):,}")
    print(f"  VC funds               : {len(vc):,}")
    print(f"  HIGH priority targets  : {len(high):,}")
    print(f"  MEDIUM priority        : {len(medium):,}")

    if high:
        print(f"\n  Top HIGH Priority Investors:")
        print(f"  {'─'*52}")
        for r in high[:15]:
            print(f"  {r['investor_name']:<35} {r['investor_type']:<8} {r['portfolio_count']} cos  🔥{r['hot_prospects']} hot")
    print()


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Crunchbase-style enrichment via Claude web search")
    parser.add_argument("--input",          default=DEFAULT_INPUT)
    parser.add_argument("--output",         default=DEFAULT_OUTPUT)
    parser.add_argument("--investors-only", action="store_true", help="Skip enrichment, just rebuild investor file")
    parser.add_argument("--limit",          type=int, default=0)
    parser.add_argument("--delay",          type=float, default=DELAY_SECONDS)
    parser.add_argument("--reset-errors",   action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("\n  ERROR: ANTHROPIC_API_KEY not set.")
        print("  Set it in your .env file (see .env.example) or: export ANTHROPIC_API_KEY=sk-ant-...\n")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    # Load
    source = args.output if os.path.exists(args.output) else args.input
    print(f"  Loading: {source}")
    rows = load_csv(source)

    total          = len(rows)
    already_done   = sum(1 for r in rows if is_cb_enriched(r))

    print(f"\n  Crunchbase Enrichment — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  {'─'*52}")
    print(f"  Total records    : {total:,}")
    print(f"  Already enriched : {already_done:,}")
    print(f"  Model            : {MODEL}")
    print(f"  Delay            : {args.delay}s")
    if args.limit:
        print(f"  Limit            : {args.limit} this run")
    print(f"  Output           : {args.output}")
    print(f"  Investors file   : {INVESTORS_OUTPUT}")
    print(f"  {'─'*52}\n")

    if args.investors_only:
        print("  Rebuilding investor file from existing data...")
        build_investor_file(rows, INVESTORS_OUTPUT)
        return

    # Build pending list
    pending = []
    for row in rows:
        if not row.get("full_name", "").strip():
            continue
        if is_cb_enriched(row):
            continue
        if row.get("_cb_status") == "error" and not args.reset_errors:
            continue
        pending.append(row)

    if args.limit:
        pending = pending[:args.limit]

    if not pending:
        print("  Nothing to enrich. Building investor file from existing data...\n")
        build_investor_file(rows, INVESTORS_OUTPUT)
        return

    print(f"  Records to enrich: {len(pending):,}\n")

    session_done   = 0
    session_errors = 0
    start_time     = time.time()

    for i, row in enumerate(pending, 1):
        name    = row.get("full_name", "")
        company = row.get("company_name", "")
        website = row.get("company_website", "")
        state   = row.get("state", "")

        print(f"  [{i:>4}/{len(pending)}] {name} @ {company}", end="", flush=True)

        try:
            result = enrich_crunchbase(client, name, company, website, state)

            for key, val in result.items():
                row[key] = val
            row["_cb_status"] = "done"
            row["_cb_error"]  = ""
            session_done += 1

            stage     = result["last_funding_stage"] or "?"
            amount    = result["last_funding_amount"] or "?"
            employees = result["employee_count"] or "?"
            investors = result["investors"][:50] if result["investors"] else "no investors found"
            backed    = []
            if result["is_pe_backed"] == "Yes": backed.append("PE")
            if result["is_vc_backed"]  == "Yes": backed.append("VC")
            backed_str = "/".join(backed) or "—"

            print(f"  →  {stage} {amount}  |  {employees} emp  |  [{backed_str}]  {investors}")

        except Exception as e:
            row["_cb_status"] = "error"
            row["_cb_error"]  = str(e)
            session_errors += 1
            print(f"  ✗  ERROR: {e}")

        save_csv(rows, args.output)

        if i < len(pending):
            time.sleep(args.delay)

    # Final investor file rebuild
    elapsed = time.time() - start_time
    print(f"\n  {'─'*52}")
    print(f"  Session done   : {session_done:,}")
    print(f"  Session errors : {session_errors:,}")
    print(f"  Elapsed        : {round(elapsed/60, 1)} min")
    print(f"  Output         : {args.output}")

    # Always rebuild investor file at the end
    build_investor_file(rows, INVESTORS_OUTPUT)


if __name__ == "__main__":
    main()
