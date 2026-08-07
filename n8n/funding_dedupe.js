// ── Dedupe vs Salesforce ──────────────────────────────────────────────────
// Marks each discovered company as new or existing using Account Name OR
// Website domain (normalized). Code node mode: "Run Once for All Items".

function normalizeName(n) {
  return String(n || "")
    .toLowerCase()
    .replace(/&/g, "and")
    .replace(/[^a-z0-9]/g, "");
}

function normalizeDomain(url) {
  let s = String(url || "").trim().toLowerCase();
  if (!s) return "";
  s = s.replace(/^https?:\/\//, "").replace(/^www\./, "");
  return s.split("/")[0].split("?")[0];
}

function sfAccounts() {
  try {
    return $("Get Salesforce Accounts").all().map((i) => i.json);
  } catch (e) {
    return [];
  }
}

const accounts = sfAccounts();
const items = $input.all();

return items.map((item) => {
  const c = item.json;
  if (c._empty || !c.Name) {
    return {
      json: {
        ...c,
        _isNew: false,
        _skipCreate: true,
        _matchReason: "empty",
      },
    };
  }

  const name = normalizeName(c.Name);
  const domain = normalizeDomain(c.Website);

  let matchReason = "";
  let matchedId = "";

  for (const sf of accounts) {
    const sfName = normalizeName(sf.Name);
    const sfDomain = normalizeDomain(sf.Website);
    const nameMatch = Boolean(name && sfName && name === sfName);
    const domainMatch = Boolean(domain && sfDomain && domain === sfDomain);
    if (nameMatch || domainMatch) {
      matchReason = nameMatch && domainMatch
        ? "name+website"
        : nameMatch
          ? "name"
          : "website";
      matchedId = sf.Id || sf.id || "";
      break;
    }
  }

  const isNew = !matchReason;
  return {
    json: {
      ...c,
      _isNew: isNew,
      _skipCreate: !isNew,
      _matchReason: matchReason || "none",
      _matchedAccountId: matchedId,
      _sfAccountCount: accounts.length,
    },
  };
});
