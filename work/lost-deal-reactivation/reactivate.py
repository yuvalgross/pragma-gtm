"""
Lost deal reactivation: which lost accounts are worth a second call this week,
who calls them, and with what reason.

    python3 reactivate.py data/lost_accounts.csv --out output
    python3 reactivate.py data/lost_accounts.csv --set wait_days_after_loss=60 --out output_60
    python3 reactivate.py data/lost_accounts.csv --worked output/top40.csv --out output_week2

Every account gets exactly one group. The top 40 for the week is 5 per seller
and 15 for appointment setting. A seller takes accounts that saw a demo, a
setter takes the ones that never did, never both. Nine checks run at the end
and the run fails loudly if any breaks. Standard library only.
"""
import argparse
import csv
import json
import os
import re
from collections import Counter, defaultdict
from datetime import date

# ---- settings (each is one rule; change it with --set name=value) ------------

S = {
    "today": "2026-10-14",
    "wait_days_after_loss": 90,
    "contract_window_days": 183,        # competitor contract ends within 6 months
    "interest_days": 365,               # interest this year
    "per_seller": 5,
    "setting_cap": 15,
    # impact estimate, assumed rates
    "seller_demo_rate_low": 0.10, "seller_demo_rate_high": 0.20,
    "setting_demo_rate_low": 0.05, "setting_demo_rate_high": 0.10,
    "next_demo_rate": 0.10,
    "win_rate": 0.25,
    "mrr_per_deal": 1550,
}
SELLERS = ["Seller A", "Seller B", "Seller C", "Seller D", "Seller E"]
TARGET_COUNTRIES = {"Germany", "Austria", "Switzerland"}
CLEAR_NO = {"no opportunity", "not icp", "too small", "chain"}
STRONG_INTEREST = {"pricing page", "case study", "webinar", "event stand"}
SOURCE_RANK = {"referral": 0, "inbound demo request": 1, "event": 2, "partner": 3, "outbound": 4}
DECISION_MAKER = {"owner", "managing director"}

GROUPS = [
    "Call first: saw a demo, reason to talk",
    "Call first: no demo, reason to talk",
    "Call next: saw a demo, no reason yet",
    "Email first: no demo, no reason yet",
    "Wait: lost under 90 days ago",
    "Wait: competitor contract runs over 6 months",
    "Ask the seller",
    "Leave out",
]


def days(a, b):
    return (a - b).days


def reasons(r, today):
    """Return (reason list, rank). Rank 0 is contract or timing, 1 is interest."""
    out = []
    if r["competitor_contract_end"]:
        to_go = days(date.fromisoformat(r["competitor_contract_end"]), today)
        if -60 <= to_go <= S["contract_window_days"]:
            out.append(("competitor contract ends " + ("soon" if to_go >= 0 else "recently"), 0))
    if r["lost_reason"] in ("timing", "no answer"):
        out.append((f"lost on {r['lost_reason']}", 0))
    if r["last_engagement"] in STRONG_INTEREST and r["last_engagement_date"]:
        if days(today, date.fromisoformat(r["last_engagement_date"])) <= S["interest_days"]:
            out.append((f"{r['last_engagement']} this year", 1))
    return out


def classify(r, today):
    if r["country"] not in TARGET_COUNTRIES:
        return "Leave out", "not a target market"
    if r["key_account"] == "yes":
        return "Leave out", "key account, own seller"
    if r["is_customer"] == "yes":
        return "Leave out", "customer today"
    if r["lost_reason"] in CLEAR_NO:
        return "Leave out", f"clear no on file: {r['lost_reason']}"
    if r["lifecycle"] == "unqualified":
        return "Ask the seller", "marked unqualified, no reason given"
    if days(today, date.fromisoformat(r["lost_date"])) < S["wait_days_after_loss"]:
        return "Wait: lost under 90 days ago", "lost recently"
    if r["competitor_contract_end"]:
        to_go = days(date.fromisoformat(r["competitor_contract_end"]), today)
        if to_go > S["contract_window_days"] and r["lost_reason"] not in ("timing", "no answer"):
            return "Wait: competitor contract runs over 6 months", "contract ends later"
    why = reasons(r, today)
    demo = r["saw_demo"] == "yes"
    if why:
        return (GROUPS[0] if demo else GROUPS[1]), "; ".join(w for w, _ in why)
    return (GROUPS[2] if demo else GROUPS[3]), "no reason yet"


def sort_key(r):
    why = reasons(r, TODAY)
    best = min((rank for _, rank in why), default=2)
    return (best, r["contact_role"] not in DECISION_MAKER, SOURCE_RANK.get(r["lead_source"], 9), r["account_id"])


def angle(why):
    if "contract" in why:
        return "Their contract is ending: offer a side by side before they renew"
    if "timing" in why:
        return "They said not now: ask what changed since"
    if "no answer" in why:
        return "The thread went quiet: reopen with one new reason"
    return "They looked again this year: ask what they were checking"


def norm(name):
    return re.sub(r"[^a-z]", "", name.lower().replace("gmbh", "").replace("co kg", "").replace("ag", ""))


def main():
    global TODAY
    ap = argparse.ArgumentParser()
    ap.add_argument("export")
    ap.add_argument("--out", default="output")
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--worked", help="last week's top40.csv, so nobody gets the same call twice")
    args = ap.parse_args()
    for kv in args.set:
        k, v = kv.split("=")
        S[k] = type(S[k])(v)
    TODAY = date.fromisoformat(S["today"])

    with open(args.export, newline="") as f:
        rows = list(csv.DictReader(f))
    worked = set()
    if args.worked:
        with open(args.worked, newline="") as f:
            worked = {r["account_id"] for r in csv.DictReader(f)}

    for r in rows:
        r["group"], r["why"] = classify(r, TODAY)
        r["caller"] = ("Seller" if r["saw_demo"] == "yes" else "Appointment setting") if r["group"] in GROUPS[:3] else ""

    # owners no longer on the sales team: their callable accounts go to the seller with the shortest list
    load = Counter(r["owner"] for r in rows if r["group"] in GROUPS[:3] and r["caller"] == "Seller" and r["owner"] in SELLERS)
    reassigned = 0
    for r in sorted(rows, key=lambda x: x["account_id"]):
        if r["caller"] == "Seller" and r["owner"] not in SELLERS:
            to = min(SELLERS, key=lambda s: (load[s], s))
            load[to] += 1
            r["owner"] = to
            r["why"] += "; owner left, shared out"
            reassigned += 1

    # the week's top 40
    pool = [r for r in rows if r["group"] in GROUPS[:2] and r["account_id"] not in worked]
    top = []
    for s in SELLERS:
        mine = sorted([r for r in pool if r["caller"] == "Seller" and r["owner"] == s], key=sort_key)
        top += mine[:S["per_seller"]]
    setting = sorted([r for r in pool if r["caller"] == "Appointment setting"], key=sort_key)
    top += setting[:S["setting_cap"]]
    for r in top:
        r["angle"] = angle(r["why"])

    # probable duplicates: same normalised name, country and size; a person decides
    groups = defaultdict(list)
    for r in rows:
        groups[(norm(r["name"]), r["country"], r["employees"])].append(r["account_id"])
    dups = [ids for ids in groups.values() if len(ids) > 1]

    email = [r for r in rows if r["group"] == GROUPS[3] and r["email_status"] == "ok"]

    # nine checks
    ids = [r["account_id"] for r in top]
    per = Counter(r["owner"] for r in top if r["caller"] == "Seller")
    results = {
        "one group per account": len({r["account_id"] for r in rows}) == len(rows) and all(r["group"] in GROUPS for r in rows),
        "no account on two lists": len(ids) == len(set(ids)),
        "no seller over 5": all(v <= S["per_seller"] for v in per.values()),
        "appointment setting at most 15": sum(1 for r in top if r["caller"] == "Appointment setting") <= S["setting_cap"],
        "no excluded market, key account or customer": all(r["country"] in TARGET_COUNTRIES and r["key_account"] == "no" and r["is_customer"] == "no" for r in top),
        "no clear no": all(r["lost_reason"] not in CLEAR_NO for r in top),
        "sellers saw a demo, setters did not": all((r["caller"] == "Seller") == (r["saw_demo"] == "yes") for r in top),
        "no opted out or invalid contact on the email list": all(r["email_status"] == "ok" for r in email),
        "nobody from last week": not (set(ids) & worked),
    }
    failed = [k for k, ok in results.items() if not ok]
    if failed:
        raise SystemExit("checks failed: " + ", ".join(failed))

    os.makedirs(args.out, exist_ok=True)
    cols = ["account_id", "name", "country", "employees", "owner", "saw_demo", "lost_reason", "lost_date",
            "competitor_contract_end", "last_engagement", "contact_role", "lead_source", "group", "caller", "why"]
    with open(os.path.join(args.out, "all_accounts.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(args.out, "top40.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["account_id", "name", "caller", "owner", "contact_role", "why", "angle"], extrasaction="ignore")
        w.writeheader()
        w.writerows(top)
    with open(os.path.join(args.out, "probable_duplicates.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["account_ids"])
        w.writerows([[" ".join(ids)] for ids in dups])

    counts = Counter(r["group"] for r in rows)
    first_s = counts[GROUPS[0]]
    first_a = counts[GROUPS[1]]
    nxt = counts[GROUPS[2]]

    def impact(n, rate):
        demos = n * rate
        deals = demos * S["win_rate"]
        return round(demos), round(deals), int(round(deals * S["mrr_per_deal"], -2))

    lo = [impact(first_s, S["seller_demo_rate_low"]), impact(first_a, S["setting_demo_rate_low"])]
    hi = [impact(first_s, S["seller_demo_rate_high"]), impact(first_a, S["setting_demo_rate_high"])]
    why_counts = Counter()
    for r in rows:
        if r["group"] in GROUPS[:2]:
            for w_, _ in reasons(r, TODAY):
                why_counts[w_.split(" this year")[0] if "this year" in w_ else w_] += 1
    stale = sum(1 for r in rows if r["group"] in GROUPS[:2] and days(TODAY, date.fromisoformat(r["last_contact_date"])) > 330)
    summary = {
        "accounts": len(rows),
        "groups": {g: counts[g] for g in GROUPS},
        "call_first": first_s + first_a,
        "reasons_in_call_first": dict(why_counts),
        "call_first_no_contact_11_months": stale,
        "owner_left_reassigned": reassigned,
        "top40": {"sellers": dict(per), "appointment_setting": sum(1 for r in top if r["caller"] == "Appointment setting"),
                  "decision_maker_contacts": sum(1 for r in top if r["contact_role"] in DECISION_MAKER)},
        "probable_duplicate_groups": len(dups),
        "email_first_sendable": len(email),
        "empty_lost_reason": sum(1 for r in rows if r["lost_reason"] == ""),
        "impact_quarter_1": {
            "demos": [lo[0][0] + lo[1][0], hi[0][0] + hi[1][0]],
            "deals": [lo[0][1] + lo[1][1], hi[0][1] + hi[1][1]],
            "new_mrr_eur": [lo[0][2] + lo[1][2], hi[0][2] + hi[1][2]],
            "call_next": impact(nxt, S["next_demo_rate"]),
            "assumed": {k: S[k] for k in S if "rate" in k or k == "mrr_per_deal"},
        },
        "checks": results,
        "settings": {k: S[k] for k in ("today", "wait_days_after_loss", "contract_window_days", "interest_days")},
    }
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))


TODAY = date.fromisoformat(S["today"])

if __name__ == "__main__":
    main()
