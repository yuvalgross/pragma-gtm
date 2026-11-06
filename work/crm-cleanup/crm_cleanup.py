"""
CRM clean up: four agents read a HubSpot export, fix what is safe to fix,
queue what needs a person, and then turn the clean book of customers into a
list of who a human should call next.

    python3 crm_cleanup.py data --out output --as-of 2026-11-06

Agents, in the order they run
  1. Duplicates   companies and contacts that are the same thing twice
  2. Fields       country, lifecycle stage, stale deals, missing data
  3. Owners       records owned by people who left, or by nobody
  4. Book         existing customers: risk, expansion, and who gets a human

Every proposed change gets a tier. Nothing is written to the CRM by this
script; it writes the change log and the API payloads, and a person approves.

  auto        reversible, rule based, old value logged (country format, lifecycle
              stage that contradicts a won deal)
  approve     one batch approval by the RevOps owner per run (merges, which
              cannot be undone, and owner changes, which move people's books)
  review      one by one, a person decides (same name but no shared domain)
  owner_task  goes to the record owner as a task (stale or empty deals)
  enrich      goes to the enrichment queue (missing industry, bounced champion)

Rules are set by hand at the top of this file. Standard library only.
"""
import argparse
import csv
import json
import os
import re
from collections import defaultdict
from datetime import date

# ---- rules set by hand ------------------------------------------------------

LEGAL_SUFFIXES = {"gmbh", "ag", "ltd", "bv", "oy", "sas", "sarl", "ab", "as", "aps", "sl", "inc", "llc", "plc", "se"}

COUNTRIES = {
    "de": "Germany", "deutschland": "Germany", "germany": "Germany",
    "uk": "United Kingdom", "gb": "United Kingdom", "great britain": "United Kingdom",
    "united kingdom": "United Kingdom",
    "nl": "Netherlands", "holland": "Netherlands", "netherlands": "Netherlands",
}

TERRITORY = {
    "Germany": "DACH", "Austria": "DACH", "Switzerland": "DACH",
    "United Kingdom": "UKI", "Ireland": "UKI",
    "Netherlands": "Benelux and France", "Belgium": "Benelux and France", "France": "Benelux and France",
    "Sweden": "Nordics", "Norway": "Nordics", "Denmark": "Nordics", "Finland": "Nordics",
}

LIFECYCLE_RANK = {"customer": 3, "opportunity": 2, "lead": 1}
OPEN_STAGES = {"appointmentscheduled", "qualifiedtobuy", "presentationscheduled",
               "decisionmakerboughtin", "contractsent"}
STALE_AFTER_DAYS = 30          # open deal whose close date passed more than this

# Book of business
TIER_STRATEGIC = 100000        # EUR ARR and up: a named owner, always a human
TIER_CORE = 10000              # EUR ARR and up: a human when there is a signal
RISK_USAGE_DROP = -0.20        # usage month 3 vs month 1
RISK_RENEWAL_DAYS = 90         # renewal this close ...
RISK_NO_TOUCH_DAYS = 60        # ... and nobody spoke to them for this long
EXPANSION_USAGE_RISE = 0.30
EXPANSION_SEAT_UTIL = 0.90
QUIET_DAYS = 180               # core and strategic: no human contact for this long
EXPANSION_SHARE = 0.25         # assumption: an upsell adds a quarter of current ARR

# The LLM steps. Designed, not running in this sample: the rules below stand in
# and anything they cannot decide goes to a person.
DUPLICATE_JUDGE_PROMPT = """You are checking two CRM company records that share a
name but not a domain. Using only the fields given and the public website of each
domain, answer SAME, DIFFERENT or UNSURE, then one sentence of evidence. SAME only
if both domains lead to the same legal entity. Never guess; UNSURE goes to a person."""

LONG_TAIL_CHECKIN_PROMPT = """Write a three sentence email from the account team to a
small customer. Use only these facts: product, usage trend, seats used, renewal date.
Ask one question about what they are trying to do next. No discount, no pricing, no
claims about features. If usage is falling, ask what changed. Plain text."""

# ---- helpers ----------------------------------------------------------------


def norm_domain(d):
    d = (d or "").strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = d.split("/")[0]
    if d.startswith("www."):
        d = d[4:]
    return d


def norm_name(n):
    words = re.sub(r"[^a-z0-9 ]", "", (n or "").lower().replace(".", "")).split()
    return " ".join(w for w in words if w not in LEGAL_SUFFIXES)


def days_between(a, b):
    return (b - a).days


def parse_date(s):
    return date.fromisoformat(s) if s else None


def eur(x):
    return f"EUR {x:,.0f}"


def load(folder):
    def rows(name):
        with open(os.path.join(folder, name), newline="") as f:
            return list(csv.DictReader(f))
    owners = {o["owner_id"]: o for o in rows("owners.csv")}
    companies = rows("companies.csv")
    for c in companies:
        for k in ("arr_eur", "usage_m1", "usage_m2", "usage_m3", "seats_used", "seats_limit"):
            c[k] = int(c[k] or 0)
    contacts = rows("contacts.csv")
    deals = rows("deals.csv")
    for d in deals:
        d["amount_eur"] = int(d["amount_eur"] or 0)
    return owners, companies, contacts, deals


class Log:
    def __init__(self):
        self.rows = []

    def add(self, agent, tier, obj, rid, name, field, old, new, reason):
        self.rows.append({
            "change_id": f"ch{len(self.rows) + 1:03d}", "agent": agent, "tier": tier, "object": obj,
            "record_id": rid, "record_name": name, "field": field, "old": old, "new": new, "reason": reason,
        })

# ---- agent 1: duplicates ----------------------------------------------------


def pick_primary(group, deal_count):
    return sorted(group, key=lambda c: (-deal_count[c["company_id"]],
                                        -LIFECYCLE_RANK.get(c["lifecycle_stage"], 0),
                                        not norm_domain(c["domain"]), c["created"]))[0]


def agent_duplicates(companies, contacts, deals, log):
    deal_count = defaultdict(int)
    for d in deals:
        deal_count[d["company_id"]] += 1
    merged_into = {}            # loser company_id -> primary company_id (approve tier only)
    seen_pairs = set()

    by_domain = defaultdict(list)
    for c in companies:
        if norm_domain(c["domain"]):
            by_domain[norm_domain(c["domain"])].append(c)
    for dom, group in by_domain.items():
        if len(group) < 2:
            continue
        primary = pick_primary(group, deal_count)
        for c in group:
            if c is primary:
                continue
            reason = f"same domain {dom}"
            if c["arr_eur"] and primary["arr_eur"]:
                reason += (f"; ARR on both records ({eur(primary['arr_eur'])} + {eur(c['arr_eur'])}), "
                           "reports show the account at the smaller figure; check the ARR field after the merge")
            log.add("duplicates", "approve", "company", c["company_id"], c["name"], "merge",
                    c["company_id"], primary["company_id"], reason)
            merged_into[c["company_id"]] = primary["company_id"]
            seen_pairs.add(frozenset((c["company_id"], primary["company_id"])))

    by_name = defaultdict(list)
    for c in companies:
        by_name[norm_name(c["name"])].append(c)
    for name, group in by_name.items():
        if len(group) < 2:
            continue
        primary = pick_primary(group, deal_count)
        for c in group:
            if c is primary or frozenset((c["company_id"], primary["company_id"])) in seen_pairs:
                continue
            if not norm_domain(c["domain"]) or not norm_domain(primary["domain"]):
                reason = "same name, one record has no domain"
            else:
                reason = (f"same name on two domains ({norm_domain(primary['domain'])}, "
                          f"{norm_domain(c['domain'])}); could be two legal entities")
            log.add("duplicates", "review", "company", c["company_id"], c["name"], "merge",
                    c["company_id"], primary["company_id"], reason)

    by_email = defaultdict(list)
    for p in contacts:
        by_email[p["email"].strip().lower()].append(p)
    for email, group in by_email.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda p: (not p["job_title"], p["contact_id"]))
        primary = group[0]
        for p in group[1:]:
            log.add("duplicates", "approve", "contact", p["contact_id"], email, "merge",
                    p["contact_id"], primary["contact_id"], "same email in a different case")
    return merged_into

# ---- agent 2: fields --------------------------------------------------------


def agent_fields(companies, contacts, deals, merged_into, as_of, log):
    won = {d["company_id"] for d in deals if d["stage"] == "closedwon"}
    for c in companies:
        if c["company_id"] in merged_into:
            continue
        key = c["country"].strip().lower()
        if key in COUNTRIES and COUNTRIES[key] != c["country"]:
            log.add("fields", "auto", "company", c["company_id"], c["name"], "country",
                    c["country"], COUNTRIES[key], "one spelling per country so territory rules and reports work")
        clean = norm_domain(c["domain"])
        if clean and clean != c["domain"]:
            log.add("fields", "auto", "company", c["company_id"], c["name"], "domain",
                    c["domain"], clean, "bare domain, no protocol or path")
        if c["company_id"] in won and c["lifecycle_stage"] != "customer":
            log.add("fields", "auto", "company", c["company_id"], c["name"], "lifecyclestage",
                    c["lifecycle_stage"], "customer", "has a closed won deal")
        if c["lifecycle_stage"] == "customer" and c["company_id"] not in won and not c["arr_eur"]:
            log.add("fields", "review", "company", c["company_id"], c["name"], "lifecyclestage",
                    "customer", "?", "says customer, no won deal and no ARR: churned, or never won?")
        if not c["industry"]:
            log.add("fields", "enrich", "company", c["company_id"], c["name"], "industry",
                    "", "", "missing industry, needed for segment reports and routing")
    company_name = {c["company_id"]: c["name"] for c in companies}
    for p in contacts:
        if p["bounced"] == "true" and p["company_id"] not in merged_into:
            log.add("fields", "enrich", "contact", p["contact_id"], p["email"], "replacement",
                    p["job_title"], "", f"email bounces at {company_name.get(p['company_id'], '?')}: "
                    "the person likely left; find who replaced them")
    for d in deals:
        if d["stage"] not in OPEN_STAGES:
            continue
        close = parse_date(d["close_date"])
        late = days_between(close, as_of) if close else 0
        if late > STALE_AFTER_DAYS:
            money = f" ({eur(d['amount_eur'])} in the forecast)" if d["amount_eur"] else ""
            log.add("fields", "owner_task", "deal", d["deal_id"], d["deal_name"], "close_date",
                    d["close_date"], "", f"open deal, close date passed {late} days ago{money}: "
                    "update the date or close it lost")
        if not d["amount_eur"]:
            log.add("fields", "owner_task", "deal", d["deal_id"], d["deal_name"], "amount",
                    "0", "", "open deal with no amount, invisible in the forecast")

# ---- agent 3: owners --------------------------------------------------------


def agent_owners(companies, deals, owners, merged_into, log):
    active = {k: o for k, o in owners.items() if o["active"] == "true"}
    am = sorted(k for k, o in active.items() if o["role"] == "AM")[0]
    ae_by_territory = {}
    for k in sorted(active):
        if active[k]["role"] == "AE":
            ae_by_territory.setdefault(active[k]["territory"], k)

    def new_owner(country, is_customer):
        if is_customer:
            return am, "customers go to account management"
        country = COUNTRIES.get(country.strip().lower(), country)
        t = TERRITORY.get(country)
        if t and t in ae_by_territory:
            return ae_by_territory[t], f"territory {t}"
        return None, f"no active owner for {country}"

    company = {c["company_id"]: c for c in companies}
    for c in companies:
        if c["company_id"] in merged_into:
            continue
        cur = c["owner_id"]
        if cur and cur in active:
            continue
        why = "owner has left" if cur else "no owner"
        to, rule = new_owner(c["country"], c["lifecycle_stage"] == "customer" or c["arr_eur"] > 0)
        tier = "approve" if to else "review"
        log.add("owners", tier, "company", c["company_id"], c["name"], "hubspot_owner_id",
                cur, to or "?", f"{why}; {rule}; {eur(c['arr_eur'])} ARR" if c["arr_eur"] else f"{why}; {rule}")
    for d in deals:
        if d["owner_id"] in active:
            continue
        cid = merged_into.get(d["company_id"], d["company_id"])
        c = company[cid]
        to, rule = new_owner(c["country"], c["lifecycle_stage"] == "customer" or c["arr_eur"] > 0)
        log.add("owners", "approve" if to else "review", "deal", d["deal_id"], d["deal_name"],
                "hubspot_owner_id", d["owner_id"], to or "?", f"owner has left; {rule}")

# ---- agent 4: book of business ----------------------------------------------


def agent_book(companies, contacts, merged_into, as_of):
    bounced = defaultdict(list)
    for p in contacts:
        if p["bounced"] == "true":
            bounced[p["company_id"]].append(p["job_title"] or "contact")
    arr = defaultdict(int)
    for c in companies:
        arr[merged_into.get(c["company_id"], c["company_id"])] += c["arr_eur"]
    book = []
    for c in companies:
        cid = c["company_id"]
        if cid in merged_into or not arr[cid]:
            continue
        a = arr[cid]
        tier = "strategic" if a >= TIER_STRATEGIC else "core" if a >= TIER_CORE else "long tail"
        change = (c["usage_m3"] - c["usage_m1"]) / c["usage_m1"] if c["usage_m1"] else 0.0
        util = c["seats_used"] / c["seats_limit"] if c["seats_limit"] else 0.0
        renewal = parse_date(c["renewal_date"])
        to_renewal = days_between(as_of, renewal) if renewal else None
        touch = parse_date(c["last_human_touch"])
        since_touch = days_between(touch, as_of) if touch else None

        risk, expand, why = [], [], []
        if change <= RISK_USAGE_DROP:
            risk.append(f"usage down {abs(change):.0%} in three months")
        if to_renewal is not None and to_renewal <= RISK_RENEWAL_DAYS and (since_touch is None or since_touch > RISK_NO_TOUCH_DAYS):
            risk.append(f"renews in {to_renewal} days, " + ("no human contact on record" if since_touch is None
                                                            else f"last human contact {since_touch} days ago"))
        if bounced[cid]:
            risk.append(f"{', '.join(bounced[cid])} email bounces")
        if change >= EXPANSION_USAGE_RISE:
            expand.append(f"usage up {change:.0%} in three months")
        if util >= EXPANSION_SEAT_UTIL and change > RISK_USAGE_DROP:
            expand.append(f"{c['seats_used']} of {c['seats_limit']} seats used")
        quiet = tier != "long tail" and (since_touch is None or since_touch > QUIET_DAYS)
        if a != c["arr_eur"]:
            why.append(f"ARR {eur(a)} after merging the duplicate record (was {eur(c['arr_eur'])})")

        if risk:
            signal, stake = "risk", a
        elif expand:
            signal, stake = "expansion", round(a * EXPANSION_SHARE)
        elif quiet:
            signal, stake = "quiet", 0
            why.append("no human contact on record" if since_touch is None else f"no human contact for {since_touch} days")
        else:
            signal, stake = "steady", 0

        if tier == "strategic":
            channel = "human"
            action = {"risk": "Owner call this week, then a written save plan",
                      "expansion": "Owner call this week to scope the next tier",
                      "quiet": "Owner call, nobody has spoken to them in months",
                      "steady": "Quarterly review, AI prepares the brief"}[signal]
        elif tier == "core":
            channel = "human" if signal in ("risk", "expansion", "quiet") else "ai, owner approves"
            action = {"risk": "Owner call this week",
                      "expansion": "Owner call to scope the upgrade",
                      "quiet": "Owner check in call",
                      "steady": "AI drafted check in, owner approves before it goes"}[signal]
        else:
            channel = "ai, human on reply" if signal in ("risk", "expansion") else "automated"
            action = {"risk": "AI check in asking what changed, a human picks up any reply",
                      "expansion": "AI upgrade offer, a human picks up any reply",
                      "steady": "Monthly usage summary email, no human"}.get(signal, "Monthly usage summary email, no human")
        book.append({
            "company_id": cid, "name": c["name"], "arr_eur": a, "tier": tier, "signal": signal,
            "eur_at_stake": stake, "channel": channel, "action": action,
            "evidence": "; ".join(risk + expand + why),
        })
    order = {"risk": 0, "expansion": 1, "quiet": 2, "steady": 3}
    book.sort(key=lambda r: (r["channel"] != "human", order[r["signal"]], -r["arr_eur"]))
    return book

# ---- outputs ----------------------------------------------------------------


def payloads(log):
    """The HubSpot CRM v3 calls a person approves. Built, never sent from here."""
    plural = {"company": "companies", "contact": "contacts", "deal": "deals"}
    batches = defaultdict(lambda: defaultdict(dict))
    merges = []
    for r in log.rows:
        if r["field"] == "merge" and r["tier"] == "approve":
            merges.append({"endpoint": f"POST /crm/v3/objects/{plural[r['object']]}/merge",
                           "body": {"primaryObjectId": r["new"], "objectIdToMerge": r["old"]}})
        elif r["tier"] in ("auto", "approve") and r["field"] != "merge":
            batches[(r["tier"], r["object"])][r["record_id"]][r["field"]] = r["new"]
    updates = []
    for (tier, obj), recs in sorted(batches.items()):
        updates.append({"tier": tier, "endpoint": f"POST /crm/v3/objects/{plural[obj]}/batch/update",
                        "body": {"inputs": [{"id": k, "properties": v} for k, v in recs.items()]}})
    return {"note": "Dry run. Nothing here has been sent.", "updates": updates, "merges": merges}


def write_outputs(log, book, deals, companies, owners, out, as_of):
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "changes.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(log.rows[0].keys()))
        w.writeheader()
        w.writerows(log.rows)
    with open(os.path.join(out, "book.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(book[0].keys()))
        w.writeheader()
        w.writerows(book)
    with open(os.path.join(out, "hubspot_payloads.json"), "w") as f:
        json.dump(payloads(log), f, indent=2)
    # The enrich tier, keyed the way a Clay Audiences import matches records:
    # domain for companies, email for people. Only these rows spend credits.
    domain = {c["company_id"]: norm_domain(c["domain"]) for c in companies}
    with open(os.path.join(out, "clay_enrich_queue.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["record_id", "object", "match_key", "need", "reason"])
        for r in log.rows:
            if r["tier"] == "enrich":
                key = domain.get(r["record_id"], "") if r["object"] == "company" else r["record_name"]
                w.writerow([r["record_id"], r["object"], key, r["field"], r["reason"]])

    tiers = defaultdict(int)
    for r in log.rows:
        tiers[r["tier"]] += 1
    active = {k for k, o in owners.items() if o["active"] == "true"}
    stale = [r for r in log.rows if r["object"] == "deal" and r["field"] == "close_date"]
    stale_eur = sum(d["amount_eur"] for d in deals if d["deal_id"] in {r["record_id"] for r in stale})
    hidden = sum(c["arr_eur"] for c in companies
                 if any(r["record_id"] == c["company_id"] and r["field"] == "merge" and r["tier"] == "approve" for r in log.rows))
    unowned = sum(r["arr_eur"] for r in book
                  if next(c for c in companies if c["company_id"] == r["company_id"])["owner_id"] not in active)
    calls = [r for r in book if r["channel"] == "human" and r["signal"] != "steady"]
    summary = {
        "as_of": as_of.isoformat(),
        "records_in": {"companies": len(companies), "deals": len(deals)},
        "changes": len(log.rows),
        "by_tier": dict(sorted(tiers.items())),
        "by_agent": {a: sum(1 for r in log.rows if r["agent"] == a) for a in ("duplicates", "fields", "owners")},
        "customers_in_book": len(book),
        "book_arr_eur": sum(r["arr_eur"] for r in book),
        "arr_on_duplicate_records_eur": hidden,
        "customer_arr_with_no_active_owner_eur": unowned,
        "stale_open_pipeline_eur": stale_eur,
        "human_calls": len(calls),
        "arr_with_risk_signal_eur": sum(r["eur_at_stake"] for r in book if r["signal"] == "risk"),
        "expansion_potential_eur": sum(r["eur_at_stake"] for r in book if r["signal"] == "expansion"),
        "channels": {ch: sum(1 for r in book if r["channel"] == ch) for ch in sorted({r["channel"] for r in book})},
        "assumptions": {"expansion_share_of_arr": EXPANSION_SHARE},
    }
    with open(os.path.join(out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    lines = [f"# Who a human calls next, as of {as_of.isoformat()}", "",
             "| # | Account | ARR | Signal | Evidence | Action |", "| --- | --- | --- | --- | --- | --- |"]
    for i, r in enumerate(calls, start=1):
        lines.append(f"| {i} | {r['name']} | {eur(r['arr_eur'])} | {r['signal']} | {r['evidence']} | {r['action']} |")
    lines += ["", f"{len(log.rows)} changes proposed: " + ", ".join(f"{v} {k}" for k, v in sorted(tiers.items())) + "."]
    with open(os.path.join(out, "call_list.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(json.dumps(summary, indent=2))


def run(folder, as_of):
    owners, companies, contacts, deals = load(folder)
    log = Log()
    merged_into = agent_duplicates(companies, contacts, deals, log)
    agent_fields(companies, contacts, deals, merged_into, as_of, log)
    agent_owners(companies, deals, owners, merged_into, log)
    book = agent_book(companies, contacts, merged_into, as_of)
    return log, book, owners, companies, deals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", help="folder with owners, companies, contacts and deals csv")
    ap.add_argument("--out", default="output")
    ap.add_argument("--as-of", default="2026-11-06")
    a = ap.parse_args()
    as_of = date.fromisoformat(a.as_of)
    log, book, owners, companies, deals = run(a.data, as_of)
    write_outputs(log, book, deals, companies, owners, a.out, as_of)


if __name__ == "__main__":
    main()
