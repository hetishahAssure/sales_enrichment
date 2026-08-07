// ── Merge & Score ─────────────────────────────────────────────────────────
// Ports the Python per-source parsing + merge_results() scoring. Reads the four
// HTTP node outputs (each may have failed → guarded) and the Prepare node, then
// emits the enrichment columns keyed by "Account ID" for the Sheets update.
// Code node mode: "Run Once for Each Item".

const TARGET_ROLES = [
  "software engineer", "software developer", "backend engineer", "frontend engineer",
  "full stack", "fullstack", "devops", "platform engineer", "site reliability", "sre",
  "qa engineer", "quality assurance", "automation engineer", "test engineer", "sdet",
  "mobile developer", "ios developer", "android developer", "data engineer", "data scientist",
  "ml engineer", "ai engineer", "machine learning", "nlp engineer", "bi engineer",
  "business intelligence", "data analyst", "ux designer", "ui designer", "product designer",
  "cloud engineer", "infrastructure engineer", "security engineer", "cybersecurity",
  "engineering manager", "director of engineering", "vp of engineering", "vp engineering",
  "tech lead", "technical lead", "staff engineer",
];

const TECH_KEYWORDS = [
  "Python", "Java", "JavaScript", "TypeScript", "Go", "Rust", "C#", ".NET", "React", "Vue",
  "Angular", "Node.js", "Swift", "Kotlin", "AWS", "Azure", "GCP", "Kubernetes", "Docker",
  "Terraform", "Databricks", "Spark", "Kafka", "Airflow", "PostgreSQL", "MongoDB", "Redis",
  "MySQL", "GraphQL", "REST", "microservices", "Agile", "Scrum", "CI/CD",
];

function nodeJson(name) {
  try { return $(name).item.json; } catch (e) { return null; }
}
function hasRole(title) {
  const t = String(title || "").toLowerCase();
  return TARGET_ROLES.some((r) => t.includes(r));
}

const company = $("Prepare Requests").item.json;
const companyName = String(company["Account Name"] || company._company || "");
const results = [];

// ── SOURCE 1 — Claude web search ──────────────────────────────────────────
try {
  const resp = nodeJson("Claude Web Search");
  if (resp && !resp.error && Array.isArray(resp.content)) {
    const text = resp.content
      .filter((b) => b && b.type === "text" && b.text)
      .map((b) => b.text)
      .join(" ");
    const m = text.match(/\{[\s\S]*?\}/);
    if (m) {
      const d = JSON.parse(m[0]);
      results.push({
        source: "claude_web",
        is_hiring: String(d.is_hiring_engineers || "Unknown").trim(),
        roles: String(d.open_roles || "").trim(),
        count: parseInt(d.open_roles_count || 0) || 0,
        careers_page_url: String(d.careers_page_url || "").trim(),
        linkedin_jobs_url: String(d.linkedin_jobs_url || "").trim(),
        indeed_jobs_url: String(d.indeed_jobs_url || "").trim(),
        recent_posting: String(d.most_recent_posting || "").trim(),
        tech_stack: String(d.tech_stack_hints || "").trim(),
        notes: String(d.notes || "").trim(),
      });
    }
  }
} catch (e) { /* skip source on parse failure */ }

// ── SOURCE 2 — JSearch (Indeed via RapidAPI) ──────────────────────────────
try {
  const resp = nodeJson("JSearch");
  const jobs = resp && Array.isArray(resp.data) ? resp.data : [];
  const nameKey = companyName.toLowerCase().slice(0, 6);
  const relevant = [];
  for (const job of jobs) {
    const title = String(job.job_title || "").toLowerCase();
    const emp = String(job.employer_name || "").toLowerCase();
    if (nameKey && emp.includes(nameKey) && hasRole(title)) relevant.push(job.job_title || "");
  }
  const roles = [...new Set(relevant)].slice(0, 15);
  if (jobs.length || roles.length) {
    results.push({
      source: "jsearch",
      is_hiring: roles.length ? "Yes" : jobs.length ? "No" : "Unknown",
      roles: roles.join(", "),
      count: roles.length,
      careers_page_url: "",
      linkedin_jobs_url: "",
      indeed_jobs_url: "https://www.indeed.com/jobs?q=" + encodeURIComponent(companyName),
      recent_posting: "within last 30 days",
      tech_stack: "",
      notes: `JSearch: ${jobs.length} total postings, ${roles.length} eng roles`,
    });
  }
} catch (e) { /* skip */ }

// ── SOURCE 3 — Theirstack ─────────────────────────────────────────────────
try {
  const resp = nodeJson("Theirstack");
  const jobs = resp && Array.isArray(resp.data) ? resp.data : [];
  const roles = [...new Set(jobs.map((j) => j.job_title).filter(Boolean))];
  const tech = {};
  for (const job of jobs) {
    const desc = String(job.job_description || "").toLowerCase();
    for (const kw of TECH_KEYWORDS) {
      if (desc.includes(kw.toLowerCase())) tech[kw] = (tech[kw] || 0) + 1;
    }
  }
  const topTech = Object.entries(tech).sort((a, b) => b[1] - a[1]).slice(0, 8).map((x) => x[0]).join(", ");
  if (jobs.length) {
    results.push({
      source: "theirstack",
      is_hiring: roles.length ? "Yes" : "No",
      roles: roles.slice(0, 15).join(", "),
      count: roles.length,
      careers_page_url: jobs[0].apply_url || "",
      linkedin_jobs_url: "",
      indeed_jobs_url: "",
      recent_posting: String(jobs[0].discovered_at || "").slice(0, 7),
      tech_stack: topTech,
      notes: `Theirstack: ${jobs.length} eng roles`,
    });
  }
} catch (e) { /* skip */ }

// ── SOURCE 4 — Apollo.io ──────────────────────────────────────────────────
try {
  const resp = nodeJson("Apollo");
  const orgs = resp ? resp.organizations || resp.accounts || [] : [];
  if (orgs && orgs.length) {
    const org = orgs[0];
    const postings = org.job_postings || [];
    const eng = postings.map((j) => j.title || "").filter((t) => hasRole(t));
    const techNames = org.technology_names || [];
    results.push({
      source: "apollo",
      is_hiring: eng.length ? "Yes" : postings.length ? "No" : "Unknown",
      roles: [...new Set(eng.slice(0, 15))].join(", "),
      count: eng.length,
      careers_page_url: org.organization_job_page_url || "",
      linkedin_jobs_url: "",
      indeed_jobs_url: "",
      recent_posting: postings[0] && postings[0].posted_at ? String(postings[0].posted_at).slice(0, 7) : "",
      tech_stack: techNames.slice(0, 10).join(", "),
      notes: `Apollo: ${org.estimated_num_employees || ""} employees, ${postings.length} postings`,
    });
  }
} catch (e) { /* skip */ }

// ── merge_results() ───────────────────────────────────────────────────────
function merge(results) {
  if (!results.length) {
    return {
      is_hiring_engineers: "Unknown", open_roles: "", open_roles_count: 0, hiring_score: 0,
      hiring_urgency: "Unknown", hiring_source: "None", careers_page_url: "", linkedin_jobs_url: "",
      indeed_jobs_url: "", most_recent_posting: "", tech_stack_hints: "", hiring_notes: "", data_confidence: "Low",
      _hiring_status: "error",
      _hiring_error: "no hiring sources returned usable data",
      _sources_ok: 0,
    };
  }
  const allRoles = new Set(), sources = [], allTech = new Set(), notes = [];
  let anyYes = false, anyNo = false;
  const fields = { careers_page_url: "", linkedin_jobs_url: "", indeed_jobs_url: "", recent_posting: "" };
  for (const r of results) {
    sources.push(r.source);
    if (r.is_hiring === "Yes") anyYes = true;
    else if (r.is_hiring === "No") anyNo = true;
    for (let role of String(r.roles || "").split(",")) { role = role.trim(); if (role) allRoles.add(role); }
    for (const f of Object.keys(fields)) { if (r[f] && !fields[f]) fields[f] = r[f]; }
    for (let t of String(r.tech_stack || "").split(",")) { t = t.trim(); if (t) allTech.add(t); }
    if (r.notes) notes.push(`[${r.source}] ${r.notes}`);
  }
  const isHiring = anyYes ? "Yes" : anyNo ? "No" : "Unknown";
  const total = allRoles.size;
  const n = results.length;
  const confidence = n >= 3 ? "High" : n === 2 ? "Medium" : "Low";
  let score = 0;
  if (isHiring === "Yes") {
    if (total >= 8) score = 5;
    else if (total >= 5) score = 4;
    else if (total >= 3) score = 3;
    else if (total >= 2) score = 2;
    else score = 1;
    if (n >= 2) score = Math.min(5, score + 1);
  }
  const urgency = score >= 4 ? "Hot" : score >= 2 ? "Warm" : score === 1 ? "Cold" : "Unknown";
  return {
    is_hiring_engineers: isHiring,
    open_roles: [...allRoles].sort().slice(0, 20).join(", "),
    open_roles_count: total,
    hiring_score: score,
    hiring_urgency: urgency,
    hiring_source: [...new Set(sources)].sort().join(" + "),
    careers_page_url: fields.careers_page_url,
    linkedin_jobs_url: fields.linkedin_jobs_url,
    indeed_jobs_url: fields.indeed_jobs_url,
    most_recent_posting: fields.recent_posting,
    tech_stack_hints: [...allTech].sort().slice(0, 12).join(", "),
    hiring_notes: notes.join(" | ").slice(0, 300),
    data_confidence: confidence,
    _hiring_status: "done",
    _hiring_error: "",
    _sources_ok: n,
  };
}

const merged = merge(results);

// Keep the original row columns (minus internal _-prefixed helpers), then
// overlay the enrichment columns. Works for both the Sheets update (auto-map
// matches on "Account ID") and the CSV download in the test workflow.
const clean = {};
for (const [k, v] of Object.entries(company)) {
  if (!k.startsWith("_")) clean[k] = v;
}

return { json: { ...clean, ...merged } };
