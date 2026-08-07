#!/usr/bin/env python3
"""
Assuresoft — Ultimate Hiring Signal Enrichment Tool
-----------------------------------------------------
The most complete engineering hiring intelligence tool for B2B sales.

Searches FOUR sources per company:
  Source 1 — Claude AI + Web Search (always on, free)
  Source 2 — JSearch API via RapidAPI (Indeed data, ~$10/mo)
  Source 3 — Theirstack.com API (~$99-299/mo)
  Source 4 — Apollo.io People API (existing account)

Each source toggles ON/OFF in the SOURCES config below.
API keys are read from environment variables (see .env / .env.example).

New columns added:
  is_hiring_engineers    Yes | No | Unknown
  open_roles             comma-separated role titles
  open_roles_count       number of relevant roles
  hiring_score           0-5 signal strength
  hiring_urgency         Hot | Warm | Cold | Unknown
  hiring_source          which sources confirmed
  careers_page_url       direct link to careers page
  linkedin_jobs_url      linkedin.com/company/[slug]/jobs/
  indeed_jobs_url        indeed.com search URL
  most_recent_posting    date of most recent posting
  tech_stack_hints       technologies in job descriptions
  hiring_notes           context for sales team
  data_confidence        High | Medium | Low

Usage:
    python3 enrich_hiring.py
    python3 enrich_hiring.py --input   data/YPO_Qualified.csv
    python3 enrich_hiring.py --output  data/YPO_Qualified.csv
    python3 enrich_hiring.py --limit   50
    python3 enrich_hiring.py --tier    1
    python3 enrich_hiring.py --min-delay 2.0 --max-delay 7.0
    python3 enrich_hiring.py --reset-errors
    python3 enrich_hiring.py --sources-report
"""

import anthropic
import csv
import json
import time
import random
import argparse
import re
import os
import sys
import urllib.parse
from datetime import datetime
from collections import defaultdict

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv is optional; env vars can also be exported manually.
    pass

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


# ══════════════════════════════════════════════════════════════════════════════
#
#  ███████╗███████╗████████╗████████╗██╗███╗   ██╗ ██████╗ ███████╗
#  ██╔════╝██╔════╝╚══██╔══╝╚══██╔══╝██║████╗  ██║██╔════╝ ██╔════╝
#  ███████╗█████╗     ██║      ██║   ██║██╔██╗ ██║██║  ███╗███████╗
#  ╚════██║██╔══╝     ██║      ██║   ██║██║╚██╗██║██║   ██║╚════██║
#  ███████║███████╗   ██║      ██║   ██║██║ ╚████║╚██████╔╝███████║
#  ╚══════╝╚══════╝   ╚═╝      ╚═╝   ╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚══════╝
#
#  API keys are loaded from environment variables (.env file).
#  To enable a source: set ENABLED=True and provide its API key in .env
#  Never hardcode keys here — keep them in .env (which is gitignored).
#
# ══════════════════════════════════════════════════════════════════════════════

SOURCES = {

    # ─────────────────────────────────────────────────────────────────────────
    # SOURCE 1 — Claude AI + Web Search
    # Always ON. Uses your Anthropic API key (env: ANTHROPIC_API_KEY).
    # Cost: ~$0.001 per company (included in Anthropic usage)
    # ─────────────────────────────────────────────────────────────────────────
    "claude_web": {
        "ENABLED":    True,                                   # keep True
        "api_key":    os.environ.get("ANTHROPIC_API_KEY", ""),
        "description":"Claude AI + Web Search (LinkedIn, careers page, Indeed, web)",
        "cost":       "~$0.001/company — included in Anthropic API",
        "signup_url": "https://console.anthropic.com/settings/keys",
        "host":       "",
        "base_url":   "",
    },

    # ─────────────────────────────────────────────────────────────────────────
    # SOURCE 2 — JSearch (Indeed data via RapidAPI)
    # Get key: https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
    # Cost: $10/mo Basic (200 req/day) — recommended plan
    # env: JSEARCH_API_KEY
    # ─────────────────────────────────────────────────────────────────────────
    "jsearch": {
        "ENABLED":    True,
        "api_key":    os.environ.get("JSEARCH_API_KEY", ""),
        "description":"JSearch — real-time Indeed job data via RapidAPI",
        "cost":       "$10/mo Basic | $50/mo Pro via RapidAPI",
        "signup_url": "https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch",
        "host":       "jsearch.p.rapidapi.com",
        "base_url":   "",
    },

    # ─────────────────────────────────────────────────────────────────────────
    # SOURCE 3 — Theirstack
    # Get key: https://theirstack.com — request a trial
    # Cost: $99/mo Starter | $299/mo Growth
    # env: THEIRSTACK_API_KEY
    # ─────────────────────────────────────────────────────────────────────────
    "theirstack": {
        "ENABLED":    True,
        "api_key":    os.environ.get("THEIRSTACK_API_KEY", ""),
        "description":"Theirstack — purpose-built engineering hiring intelligence",
        "cost":       "$99/mo Starter | $299/mo Growth",
        "signup_url": "https://theirstack.com",
        "host":       "",
        "base_url":   "https://api.theirstack.com/v1",
    },

    # ─────────────────────────────────────────────────────────────────────────
    # SOURCE 4 — Apollo.io
    # Get key: https://developer.apollo.io (need Professional or Org plan)
    # env: APOLLO_API_KEY
    # ─────────────────────────────────────────────────────────────────────────
    "apollo": {
        "ENABLED":    True,
        "api_key":    os.environ.get("APOLLO_API_KEY", ""),
        "description":"Apollo.io — job signals + technographics",
        "cost":       "Included in Apollo Professional ($99/mo) or Organization ($149/mo)",
        "signup_url": "https://developer.apollo.io",
        "host":       "",
        "base_url":   "https://api.apollo.io/v1",
    },
}

# ══════════════════════════════════════════════════════════════════════════════
#  END OF SETTINGS — do not edit below this line unless you know what you're doing
# ══════════════════════════════════════════════════════════════════════════════

# ── GENERAL CONFIG ────────────────────────────────────────────────────────────
DEFAULT_INPUT  = "data/YPO_Qualified.csv"
DEFAULT_OUTPUT = "data/YPO_Qualified.csv"
MIN_DELAY      = 2.0
MAX_DELAY      = 7.0
MODEL          = "claude-haiku-4-5-20251001"

TARGET_ROLES = [
    "software engineer", "software developer", "backend engineer",
    "frontend engineer", "full stack", "fullstack",
    "devops", "platform engineer", "site reliability", "sre",
    "qa engineer", "quality assurance", "automation engineer",
    "test engineer", "sdet",
    "mobile developer", "ios developer", "android developer",
    "data engineer", "data scientist", "ml engineer", "ai engineer",
    "machine learning", "nlp engineer",
    "bi engineer", "business intelligence", "data analyst",
    "ux designer", "ui designer", "product designer",
    "cloud engineer", "infrastructure engineer",
    "security engineer", "cybersecurity",
    "engineering manager", "director of engineering",
    "vp of engineering", "vp engineering",
    "tech lead", "technical lead", "staff engineer",
]

TECH_KEYWORDS = [
    "Python", "Java", "JavaScript", "TypeScript", "Go", "Rust", "C#", ".NET",
    "React", "Vue", "Angular", "Node.js", "Swift", "Kotlin",
    "AWS", "Azure", "GCP", "Kubernetes", "Docker", "Terraform",
    "Databricks", "Spark", "Kafka", "Airflow",
    "PostgreSQL", "MongoDB", "Redis", "MySQL",
    "GraphQL", "REST", "microservices", "Agile", "Scrum", "CI/CD",
]


# ══════════════════════════════════════════════════════════════════════════════
#  SOURCE 1 — CLAUDE WEB SEARCH
# ══════════════════════════════════════════════════════════════════════════════

def claude_web_search(client, company, website, li_url, state):
    li_jobs_url = ""
    if li_url and "linkedin.com/company/" in li_url:
        slug = li_url.rstrip("/").split("/company/")[-1].split("/")[0]
        li_jobs_url = f"https://www.linkedin.com/company/{slug}/jobs/"

    base = (website or "").rstrip("/")
    careers_hints = f"{base}/careers, {base}/jobs, {base}/join-us" if base else "search for careers page"

    prompt = f"""You are a sales research assistant for AssureSoft, a nearshore software engineering company.

Find CURRENT open engineering/tech job postings at this company.
A company actively hiring engineers is our strongest buying signal.

COMPANY: {company}
WEBSITE: {website or "unknown"}
STATE: {state or "US"}
LINKEDIN JOBS: {li_jobs_url or "search for it"}
CAREERS PAGE: {careers_hints}

Search ALL of these — try every source:
1. LinkedIn Jobs page: {li_jobs_url or f'search linkedin.com for "{company}" jobs'}
2. Company careers page: {careers_hints}
3. Indeed.com: search "{company} software engineer" or "{company} developer"
4. Web: "{company} engineering jobs 2025" or "{company} hiring engineers"

TARGET ROLES — report ANY of these:
Software Engineer/Developer, Backend/Frontend/Full Stack, DevOps/Platform/SRE,
QA/Automation/Test Engineer, SDET, Mobile (iOS/Android), Data/ML/AI Engineer,
BI Engineer, UX/UI Designer, Cloud/Security Engineer, Engineering Manager,
Director/VP Engineering, Tech Lead, Staff Engineer

Return ONLY valid JSON — no markdown, no explanation:
{{
  "is_hiring_engineers": "<Yes | No | Unknown>",
  "open_roles": "<comma-separated role titles actually found>",
  "open_roles_count": <integer — engineering roles only>,
  "hiring_source": "<LinkedIn | Careers Page | Indeed | Web Search | Multiple | None>",
  "careers_page_url": "<direct URL to careers page if found, else empty>",
  "linkedin_jobs_url": "<confirmed linkedin jobs URL, else empty>",
  "indeed_jobs_url": "<indeed URL for company if found, else empty>",
  "most_recent_posting": "<date or 'within last 30 days' or 'unknown'>",
  "tech_stack_hints": "<technologies from job descriptions e.g. 'Python, AWS, React'>",
  "notes": "<one sentence context>"
}}

Rules:
- Only report roles you ACTUALLY found — never guess or fabricate
- Count ONLY engineering/tech roles — ignore sales/marketing/finance
- If LinkedIn blocks, try Indeed and careers page instead"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=800,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )
    text  = " ".join(b.text for b in response.content if hasattr(b, "text"))
    match = re.search(r'\{[\s\S]*?\}', text)
    if not match:
        raise ValueError("No JSON in Claude response")
    data = json.loads(match.group(0))

    return {
        "source":            "claude_web",
        "is_hiring":         str(data.get("is_hiring_engineers", "Unknown")).strip(),
        "roles":             str(data.get("open_roles", "")).strip(),
        "count":             int(data.get("open_roles_count", 0) or 0),
        "hiring_source":     str(data.get("hiring_source", "")).strip(),
        "careers_page_url":  str(data.get("careers_page_url", "")).strip(),
        "linkedin_jobs_url": str(data.get("linkedin_jobs_url", "")).strip(),
        "indeed_jobs_url":   str(data.get("indeed_jobs_url", "")).strip(),
        "recent_posting":    str(data.get("most_recent_posting", "")).strip(),
        "tech_stack":        str(data.get("tech_stack_hints", "")).strip(),
        "notes":             str(data.get("notes", "")).strip(),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  SOURCE 2 — JSEARCH (Indeed via RapidAPI)
# ══════════════════════════════════════════════════════════════════════════════

def jsearch_search(company, state, api_key):
    if not REQUESTS_AVAILABLE:
        raise ImportError("pip install requests")

    query = f'"{company}" (engineer OR developer OR devops OR QA OR "data engineer")'
    resp  = requests.get(
        "https://jsearch.p.rapidapi.com/search",
        headers={"X-RapidAPI-Key": api_key, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"},
        params={"query": query, "page": "1", "num_pages": "1",
                "country": "us", "date_posted": "month"},
        timeout=15
    )
    resp.raise_for_status()
    jobs = resp.json().get("data", [])

    relevant = []
    for job in jobs:
        title = (job.get("job_title") or "").lower()
        emp   = (job.get("employer_name") or "").lower()
        if company.lower()[:6] in emp and any(r in title for r in TARGET_ROLES):
            relevant.append(job.get("job_title", ""))

    roles = list(set(relevant))[:15]
    return {
        "source":            "jsearch",
        "is_hiring":         "Yes" if roles else ("No" if jobs else "Unknown"),
        "roles":             ", ".join(roles),
        "count":             len(roles),
        "hiring_source":     "Indeed (JSearch)",
        "careers_page_url":  "",
        "linkedin_jobs_url": "",
        "indeed_jobs_url":   f"https://www.indeed.com/jobs?q={urllib.parse.quote(company)}",
        "recent_posting":    "within last 30 days",
        "tech_stack":        "",
        "notes":             f"JSearch: {len(jobs)} total postings, {len(roles)} eng roles",
    }


# ══════════════════════════════════════════════════════════════════════════════
#  SOURCE 3 — THEIRSTACK
# ══════════════════════════════════════════════════════════════════════════════

def theirstack_search(company, website, api_key):
    if not REQUESTS_AVAILABLE:
        raise ImportError("pip install requests")

    domain = ""
    if website:
        domain = website.replace("https://","").replace("http://","").split("/")[0]

    resp = requests.post(
        f"{SOURCES['theirstack']['base_url']}/jobs/search",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "page": 0, "limit": 25,
            "order_by": [{"desc": True, "field": "discovered_at"}],
            "job_title_or":    TARGET_ROLES[:10],
            "company_name_or": [company],
            **({"company_domain_or": [domain]} if domain else {}),
        },
        timeout=15
    )
    resp.raise_for_status()
    jobs = resp.json().get("data", [])

    roles = list(set(j.get("job_title","") for j in jobs if j.get("job_title")))

    tech = defaultdict(int)
    for job in jobs:
        desc = (job.get("job_description") or "").lower()
        for kw in TECH_KEYWORDS:
            if kw.lower() in desc:
                tech[kw] += 1
    top_tech = ", ".join(k for k, _ in sorted(tech.items(), key=lambda x: -x[1])[:8])

    return {
        "source":            "theirstack",
        "is_hiring":         "Yes" if roles else "No",
        "roles":             ", ".join(roles[:15]),
        "count":             len(roles),
        "hiring_source":     "Theirstack",
        "careers_page_url":  (jobs[0].get("apply_url","") if jobs else ""),
        "linkedin_jobs_url": "",
        "indeed_jobs_url":   "",
        "recent_posting":    (jobs[0].get("discovered_at","")[:7] if jobs else ""),
        "tech_stack":        top_tech,
        "notes":             f"Theirstack: {len(jobs)} eng roles",
    }


# ══════════════════════════════════════════════════════════════════════════════
#  SOURCE 4 — APOLLO.IO
# ══════════════════════════════════════════════════════════════════════════════

def apollo_search(company, website, api_key):
    if not REQUESTS_AVAILABLE:
        raise ImportError("pip install requests")

    domain = ""
    if website:
        domain = website.replace("https://","").replace("http://","").split("/")[0]

    # Apollo supports api_key in body OR as X-Api-Key header depending on plan
    # We try both approaches to handle different plan types
    base_url = SOURCES["apollo"]["base_url"]

    def try_request(endpoint, use_header_auth):
        payload = {
            "q_organization_name":  company,
            "organization_domains": [domain] if domain else [],
            "page":                 1,
            "per_page":             1,
        }
        if use_header_auth:
            headers = {
                "Content-Type": "application/json",
                "X-Api-Key":    api_key,
            }
        else:
            headers = {"Content-Type": "application/json"}
            payload["api_key"] = api_key

        resp = requests.post(
            f"{base_url}{endpoint}",
            headers=headers,
            json=payload,
            timeout=15
        )
        return resp

    # Try header auth on organizations/search first
    last_error = None
    for endpoint, use_header in [
        ("/organizations/search",  True),
        ("/organizations/search",  False),
        ("/mixed_companies/search", False),
    ]:
        try:
            resp = try_request(endpoint, use_header)
            if resp.status_code in (200, 201):
                break
            last_error = f"HTTP {resp.status_code}"
        except Exception as e:
            last_error = str(e)
    else:
        raise ValueError(f"Apollo API failed: {last_error}")

    data = resp.json()
    orgs = data.get("organizations", data.get("accounts", []))

    if not orgs:
        return {
            "source": "apollo", "is_hiring": "Unknown",
            "roles": "", "count": 0, "hiring_source": "Apollo",
            "careers_page_url": "", "linkedin_jobs_url": "",
            "indeed_jobs_url": "", "recent_posting": "",
            "tech_stack": "", "notes": "Company not found in Apollo",
        }

    org          = orgs[0]
    job_postings = org.get("job_postings") or []
    eng_roles    = [
        j.get("title", "") for j in job_postings
        if any(r in (j.get("title") or "").lower() for r in TARGET_ROLES)
    ]
    tech_names = org.get("technology_names") or []

    return {
        "source":            "apollo",
        "is_hiring":         "Yes" if eng_roles else ("Unknown" if not job_postings else "No"),
        "roles":             ", ".join(set(eng_roles[:15])),
        "count":             len(eng_roles),
        "hiring_source":     "Apollo",
        "careers_page_url":  org.get("organization_job_page_url", ""),
        "linkedin_jobs_url": "",
        "indeed_jobs_url":   "",
        "recent_posting":    (job_postings[0].get("posted_at", "")[:7] if job_postings else ""),
        "tech_stack":        ", ".join(tech_names[:10]),
        "notes":             f"Apollo: {org.get('estimated_num_employees','')} employees, {len(job_postings)} postings",
    }


# ══════════════════════════════════════════════════════════════════════════════
#  RESULT MERGER
# ══════════════════════════════════════════════════════════════════════════════

def merge_results(results):
    if not results:
        return {
            "is_hiring_engineers": "Unknown", "open_roles": "",
            "open_roles_count": 0, "hiring_score": 0,
            "hiring_urgency": "Unknown", "hiring_source": "None",
            "careers_page_url": "", "linkedin_jobs_url": "",
            "indeed_jobs_url": "", "most_recent_posting": "",
            "tech_stack_hints": "", "hiring_notes": "",
            "data_confidence": "Low",
        }

    all_roles   = set()
    sources_hit = []
    any_yes     = False
    any_no      = False
    fields      = {"careers_page_url":"", "linkedin_jobs_url":"",
                   "indeed_jobs_url":"", "recent_posting":""}
    all_tech    = set()
    notes       = []

    for r in results:
        sources_hit.append(r.get("source",""))
        if r.get("is_hiring") == "Yes":
            any_yes = True
        elif r.get("is_hiring") == "No":
            any_no = True

        for role in (r.get("roles") or "").split(","):
            role = role.strip()
            if role:
                all_roles.add(role)

        for field in fields:
            if r.get(field) and not fields[field]:
                fields[field] = r[field]

        for t in (r.get("tech_stack") or "").split(","):
            t = t.strip()
            if t:
                all_tech.add(t)

        if r.get("notes"):
            notes.append(f"[{r['source']}] {r['notes']}")

    is_hiring  = "Yes" if any_yes else ("No" if any_no else "Unknown")
    total      = len(all_roles)
    n_sources  = len(results)
    confidence = "High" if n_sources >= 3 else ("Medium" if n_sources == 2 else "Low")

    score = 0
    if is_hiring == "Yes":
        if total >= 8:    score = 5
        elif total >= 5:  score = 4
        elif total >= 3:  score = 3
        elif total >= 2:  score = 2
        else:             score = 1
        if n_sources >= 2:
            score = min(5, score + 1)

    urgency = "Hot" if score >= 4 else ("Warm" if score >= 2 else ("Cold" if score == 1 else "Unknown"))

    return {
        "is_hiring_engineers": is_hiring,
        "open_roles":          ", ".join(sorted(all_roles)[:20]),
        "open_roles_count":    total,
        "hiring_score":        score,
        "hiring_urgency":      urgency,
        "hiring_source":       " + ".join(sorted(set(sources_hit))),
        "careers_page_url":    fields["careers_page_url"],
        "linkedin_jobs_url":   fields["linkedin_jobs_url"],
        "indeed_jobs_url":     fields["indeed_jobs_url"],
        "most_recent_posting": fields["recent_posting"],
        "tech_stack_hints":    ", ".join(sorted(all_tech)[:12]),
        "hiring_notes":        " | ".join(notes)[:300],
        "data_confidence":     confidence,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  CSV + UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

# Maps real-world CSV header variants to the canonical names the code uses.
# The first entry in each list is the canonical name; the rest are accepted aliases.
COLUMN_ALIASES = {
    "company_name":         ["company_name", "Account Name", "Company Name", "Company"],
    "company_website":      ["company_website", "Website", "Domain", "URL"],
    "company_linkedin_url": ["company_linkedin_url", "LinkedIn", "LinkedIn URL", "Company LinkedIn"],
    "state":                ["state", "Billing State/Province", "State", "State/Province"],
    "icp_tier":             ["icp_tier", "ICP Tier", "Tier"],
}


def normalize_headers(rows):
    """Rename recognized header aliases to canonical names, preserving all other columns."""
    if not rows:
        return rows
    rename = {}
    for col in rows[0].keys():
        for canonical, aliases in COLUMN_ALIASES.items():
            if col != canonical and col in aliases:
                rename[col] = canonical
    if not rename:
        return rows
    return [{rename.get(k, k): v for k, v in row.items()} for row in rows]


def load_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return normalize_headers(rows)


def save_csv(rows, path):
    if not rows:
        return
    keys = list(rows[0].keys())
    for col in ["is_hiring_engineers","open_roles","open_roles_count",
                "hiring_score","hiring_urgency","hiring_source",
                "careers_page_url","linkedin_jobs_url","indeed_jobs_url",
                "most_recent_posting","tech_stack_hints","hiring_notes",
                "data_confidence","_hiring_status","_hiring_error"]:
        if col not in keys:
            keys.append(col)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def is_done(row):
    return row.get("_hiring_status") == "done"


def random_delay(mn, mx):
    d = random.uniform(mn, mx)
    if random.random() < 0.10: d += random.uniform(4.0, 10.0)   # 10% longer pause
    if random.random() < 0.03: d += random.uniform(15.0, 30.0)  # 3% coffee break
    time.sleep(d)
    return d


def print_sources_report():
    print(f"\n  {'─'*62}")
    print(f"  SOURCE STATUS")
    print(f"  {'─'*62}")
    for name, cfg in SOURCES.items():
        on     = cfg["ENABLED"]
        has_key= bool(cfg.get("api_key"))
        status = "✅ ON " if on else "⭕ OFF"
        key_st = "🔑 key set" if has_key else "🔒 no key"
        print(f"  {status}  {name:<14} {cfg['description'][:48]}")
        print(f"         Cost   : {cfg['cost']}")
        if on:
            print(f"         Key    : {key_st}")
        else:
            print(f"         Get it : {cfg.get('signup_url','')}")
    print()


def print_summary(rows):
    done   = [r for r in rows if r.get("_hiring_status") == "done"]
    hiring = [r for r in done if r.get("is_hiring_engineers") == "Yes"]
    if not done:
        return

    by_score  = defaultdict(list)
    all_stacks= defaultdict(int)

    for r in hiring:
        by_score[str(r.get("hiring_score","0"))].append(r)
        for t in (r.get("tech_stack_hints","") or "").split(","):
            t = t.strip()
            if t: all_stacks[t] += 1

    pct = round(len(hiring)/len(done)*100) if done else 0
    print(f"\n  {'─'*62}")
    print(f"  HIRING SUMMARY — {len(done):,} companies checked")
    print(f"  {'─'*62}")
    print(f"  Actively hiring engineers : {len(hiring):,} ({pct}%)")
    print(f"  🔥🔥🔥🔥🔥 Score 5 — 8+ roles, multi-source : {len(by_score['5']):,}")
    print(f"  🔥🔥🔥🔥  Score 4 — 5-7 roles              : {len(by_score['4']):,}")
    print(f"  🔥🔥🔥   Score 3 — 3-4 roles              : {len(by_score['3']):,}")
    print(f"  🔥🔥    Score 2 — 2 roles                 : {len(by_score['2']):,}")
    print(f"  🔥     Score 1 — 1 role                  : {len(by_score['1']):,}")

    top = sorted(hiring, key=lambda r: int(str(r.get("hiring_score",0) or 0)), reverse=True)[:12]
    if top:
        print(f"\n  Hottest hiring prospects:")
        print(f"  {'─'*62}")
        for r in top:
            stars = "🔥" * int(str(r.get("hiring_score",0) or 0))
            print(f"  {stars:<6} {r.get('company_name',''):<30} "
                  f"{r.get('open_roles_count',0):>3} roles  "
                  f"[{r.get('data_confidence','')}]  "
                  f"{r.get('icp_tier','')}")

    if all_stacks:
        print(f"\n  Top tech stacks (messaging intel for sales team):")
        for stack, cnt in sorted(all_stacks.items(), key=lambda x: -x[1])[:12]:
            bar = "█" * min(cnt, 25)
            print(f"    {cnt:>3}x  {stack:<22} {bar}")
    print()


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",          default=DEFAULT_INPUT)
    parser.add_argument("--output",         default=DEFAULT_OUTPUT)
    parser.add_argument("--limit",          type=int, default=0)
    parser.add_argument("--min-delay",      type=float, default=MIN_DELAY)
    parser.add_argument("--max-delay",      type=float, default=MAX_DELAY)
    parser.add_argument("--tier",           type=int, default=0)
    parser.add_argument("--reset-errors",   action="store_true")
    parser.add_argument("--sources-report", action="store_true")
    args = parser.parse_args()

    print(f"\n  Assuresoft — Ultimate Hiring Signal Enrichment")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print_sources_report()

    if args.sources_report:
        return

    active = [n for n, c in SOURCES.items() if c["ENABLED"]]

    # Validate
    api_key = SOURCES["claude_web"]["api_key"]
    if not api_key or api_key == "PASTE_YOUR_ANTHROPIC_KEY_HERE":
        print("  ERROR: Set ANTHROPIC_API_KEY in your .env file (see .env.example).\n")
        sys.exit(1)

    for name in active:
        if name != "claude_web" and (
            not SOURCES[name].get("api_key") or
            SOURCES[name]["api_key"].startswith("PASTE_")
        ):
            print(f"  ⚠️  {name} is enabled but key not set — will be skipped.")

    client = anthropic.Anthropic(api_key=api_key)

    rows = load_csv(args.input)
    for row in rows:
        for col in ["is_hiring_engineers","open_roles","open_roles_count",
                    "hiring_score","hiring_urgency","hiring_source",
                    "careers_page_url","linkedin_jobs_url","indeed_jobs_url",
                    "most_recent_posting","tech_stack_hints","hiring_notes",
                    "data_confidence","_hiring_status","_hiring_error"]:
            row.setdefault(col, "")

    work = [r for r in rows if str(args.tier) in str(r.get("icp_tier",""))] \
           if args.tier else rows

    pending = [r for r in work
               if not is_done(r)
               and (r.get("_hiring_status") != "error" or args.reset_errors)
               and r.get("company_name","").strip()]

    if args.limit:
        pending = pending[:args.limit]

    total     = len(rows)
    done_ct   = sum(1 for r in rows if is_done(r))
    avg_delay = (args.min_delay + args.max_delay) / 2
    est_min   = round(len(pending) * avg_delay / 60, 1)

    print(f"  {'─'*62}")
    print(f"  Input          : {args.input} ({total:,} records)")
    print(f"  Already done   : {done_ct:,}")
    print(f"  To process     : {len(pending):,}  (~{est_min} min)")
    print(f"  Active sources : {', '.join(active)}")
    print(f"  Delay range    : {args.min_delay}s–{args.max_delay}s random + occasional longer pauses")
    print(f"  {'─'*62}\n")

    if not pending:
        print("  Nothing to process. Use --reset-errors to retry.\n")
        print_summary(rows)
        return

    s_hiring = s_not = s_unknown = s_errors = 0
    start    = time.time()

    for i, row in enumerate(pending, 1):
        company = row.get("company_name","")
        website = row.get("company_website","")
        li_url  = row.get("company_linkedin_url","")
        state   = row.get("state","")
        tier    = row.get("icp_tier","")

        print(f"  [{i:>4}/{len(pending)}] {company} [{tier}]")

        results = []
        errors  = []

        for src_name in active:
            cfg = SOURCES[src_name]
            key = cfg.get("api_key","")
            if src_name != "claude_web" and (not key or key.startswith("PASTE_")):
                continue
            try:
                if src_name == "claude_web":
                    r = claude_web_search(client, company, website, li_url, state)
                elif src_name == "jsearch":
                    r = jsearch_search(company, state, cfg["api_key"])
                elif src_name == "theirstack":
                    r = theirstack_search(company, website, cfg["api_key"])
                elif src_name == "apollo":
                    r = apollo_search(company, website, cfg["api_key"])
                else:
                    continue

                results.append(r)
                icon = "✓" if r["is_hiring"]=="Yes" else ("—" if r["is_hiring"]=="No" else "?")
                print(f"          [{src_name}] {icon} {r['count']} roles — {r['notes'][:55]}")

            except Exception as e:
                errors.append(f"{src_name}: {str(e)[:60]}")
                print(f"          [{src_name}] ✗ {str(e)[:60]}")

        merged = merge_results(results)

        for key in ["is_hiring_engineers","open_roles","open_roles_count",
                    "hiring_score","hiring_urgency","hiring_source",
                    "careers_page_url","linkedin_jobs_url","indeed_jobs_url",
                    "most_recent_posting","tech_stack_hints","hiring_notes",
                    "data_confidence"]:
            row[key] = merged[key]

        if errors and not results:
            row["_hiring_status"] = "error"
            row["_hiring_error"]  = " | ".join(errors)
            s_errors += 1
        else:
            row["_hiring_status"] = "done"
            row["_hiring_error"]  = ""

        score  = merged["hiring_score"]
        count  = merged["open_roles_count"]
        conf   = merged["data_confidence"]
        stars  = "🔥" * score

        if merged["is_hiring_engineers"] == "Yes":
            s_hiring += 1
            print(f"          → HIRING {stars} {count} roles [{conf} confidence]")
            if merged["open_roles"]:
                print(f"             {merged['open_roles'][:80]}")
            if merged["tech_stack_hints"]:
                print(f"             Stack: {merged['tech_stack_hints'][:60]}")
        elif merged["is_hiring_engineers"] == "No":
            s_not += 1
            print(f"          → Not hiring")
        else:
            s_unknown += 1
            print(f"          → Unknown")

        save_csv(rows, args.output)

        if i < len(pending):
            actual = random_delay(args.min_delay, args.max_delay)
            if i % 5 == 0:
                print(f"          ⏱  {round(actual,1)}s pause...")

    elapsed = time.time() - start
    print(f"\n  {'─'*62}")
    print(f"  Done    : {s_hiring+s_not+s_unknown:,}")
    print(f"  Hiring  : {s_hiring:,}  |  Not hiring: {s_not:,}  |  Unknown: {s_unknown:,}")
    print(f"  Errors  : {s_errors:,}")
    print(f"  Elapsed : {round(elapsed/60,1)} min")
    print_summary(rows)


if __name__ == "__main__":
    main()
