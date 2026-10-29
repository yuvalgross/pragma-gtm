"""
Signup router: decides which product trial signups get a human this week
and what that human does first.

    python3 signup_router.py data/signups_week_43_synthetic.csv --out output/

Pipeline
  1. Gate (hard, before any scoring): drop existing customers and partners, and
     personal email domains. Log the reason.
  2. Score 0 to 100: usage 35, company 25, integration 25, pain signals 15.
  3. One next action per account from score and trend.
  4. Write scored.csv, excluded.csv, top5.md and a summary.

Exclusions are a gate, never a weight: no tuning can send a customer a sales
task. Weights and rules are set by hand at the top of this file.
"""
import argparse
import csv
import json
import os
from datetime import date

# ---- rules set by hand ------------------------------------------------------

# In production this list comes from a CRM export of customers, partners and
# open deals. Here it holds the two synthetic domains the test rows use.
EXCLUDED_DOMAINS = {"customer-one.example", "partner-two.example"}
PERSONAL_DOMAINS = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "yahoo.com",
    "icloud.com", "proton.me", "protonmail.com", "gmx.de", "gmx.net", "web.de",
}

WEIGHTS = {"usage": 35, "company": 25, "integration": 25, "pain": 15}

# Direct opportunity by integration path. Accounts that arrive through a
# marketplace or a reseller already have a partner selling to them, so they
# score a quarter of a direct deal and go to the partner owner instead.
INTEGRATION_POINTS = {
    "direct_api": 25, "open_framework": 25, "self_hosted": 25,
    "partner_marketplace": 6, "reseller_channel": 6, "unknown": 10,
}
TARGET_CATEGORIES = {"core_segment"}

THRESHOLD_ENTERPRISE = 70
THRESHOLD_MIDTIER = 45

# ---- scoring ----------------------------------------------------------------


def volume(row):
    return [int(row[f"volume_w{i}"] or 0) for i in range(1, 5)]


def trend(vols):
    """'rising' if three of three week over week steps are up and w4 >= 1.3 x w1."""
    steps = [b > a for a, b in zip(vols, vols[1:])]
    if all(steps) and vols[0] and vols[3] >= 1.3 * vols[0]:
        return "rising"
    if vols[3] < 0.8 * vols[0]:
        return "falling"
    return "flat"


def score_usage(row):
    vols = volume(row)
    t = trend(vols)
    pts, why = 0, []
    if t == "rising":
        pts += 15
        why.append("volume up four weeks running")
    elif t == "flat":
        pts += 6
    level = vols[-1]
    if level >= 25000:
        pts += 10
        why.append(f"{level:,} units last week")
    elif level >= 8000:
        pts += 7
        why.append(f"{level:,} units last week")
    elif level >= 2000:
        pts += 3
    products = set(row["products_used"].split(";")) if row["products_used"] else set()
    if {"addon_x", "addon_y", "addon_z"} & products and {"core_a", "core_b"} & products:
        pts += 10
        why.append("add on used alongside core product")
    return min(pts, WEIGHTS["usage"]), why, t


def score_company(row):
    pts, why = 0, []
    if row["category"] in TARGET_CATEGORIES:
        pts += 10
        why.append(row["category"].replace("_", " "))
    hc = int(row["headcount"] or 0)
    if 20 <= hc <= 500:
        pts += 8
        why.append(f"{hc} staff")
    elif hc > 500:
        pts += 4
    try:
        fund = int(row["last_funding_months_ago"])
    except ValueError:
        fund = 99
    if fund <= 18:
        pts += 7
        why.append(f"funded {fund} months ago")
    return min(pts, WEIGHTS["company"]), why


def score_integration(row):
    path = row["integration_path"] or "unknown"
    pts = INTEGRATION_POINTS.get(path, INTEGRATION_POINTS["unknown"])
    why = [path.replace("_", " ")]
    if path in ("partner_marketplace", "reseller_channel"):
        why.append("scores a quarter, a partner already sells to this account")
    if row["hosting"] == "self":
        why.append("self hosted")
    return pts, why


def score_pain(row):
    signals = [s for s in row["pain_signals"].split(";") if s]
    pts = min(5 * len(signals), 15)
    why = [s.replace(":", ": ") for s in signals]
    if row["existing_tool"] == "incumbent":
        pts = min(pts + 5, 15)
        why.append("incumbent tool already in product (displacement, warm)")
    elif row["existing_tool"] == "inhouse":
        pts = min(pts + 3, 15)
        why.append("in house build")
    return pts, why


def next_action(total, t, path):
    if path == "partner_marketplace":
        return "Nurture, flag to the marketplace partner owner"
    if path == "reseller_channel":
        return "Nurture, flag to the reseller channel owner"
    if total > THRESHOLD_ENTERPRISE and t == "rising":
        return "Custom benchmark, open the enterprise conversation"
    if total >= THRESHOLD_MIDTIER:
        return "Offer the mid tier, open a shared Slack channel"
    return "Nurture"


def gate(row):
    domain = (row["domain"] or "").lower().strip()
    if not domain:
        return "no domain"
    if domain in EXCLUDED_DOMAINS:
        return "existing customer or partner"
    if row["email_type"] == "personal" or domain in PERSONAL_DOMAINS:
        return "personal email"
    return None


def route(rows):
    scored, excluded = [], []
    for row in rows:
        reason = gate(row)
        if reason:
            excluded.append({"account_id": row["account_id"], "domain": row["domain"], "reason": reason})
            continue
        u, u_why, t = score_usage(row)
        c, c_why = score_company(row)
        s, s_why = score_integration(row)
        p, p_why = score_pain(row)
        total = u + c + s + p
        scored.append({
            "account_id": row["account_id"],
            "company_name": row["company_name"],
            "domain": row["domain"],
            "hq_city": row["hq_city"],
            "country": row["country"],
            "headcount": row["headcount"],
            "integration_path": row["integration_path"],
            "trend": t,
            "usage": u, "company": c, "integration": s, "pain": p,
            "score": total,
            "next_action": next_action(total, t, row["integration_path"]),
            "why": "; ".join(u_why + c_why + s_why + p_why),
        })
    scored.sort(key=lambda r: (-r["score"], r["company_name"]))
    for i, r in enumerate(scored, start=1):
        r["rank"] = i
    return scored, excluded


def write_outputs(scored, excluded, out_dir, source):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "scored.csv"), "w", newline="") as f:
        cols = ["rank", "account_id", "company_name", "domain", "hq_city", "country", "headcount",
                "integration_path", "trend", "usage", "company", "integration", "pain", "score", "next_action", "why"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(scored)
    with open(os.path.join(out_dir, "excluded.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["account_id", "domain", "reason"])
        w.writeheader()
        w.writerows(excluded)
    top = scored[:5]
    lines = [
        f"# Signup router, run {date.today().isoformat()}",
        f"Input: {source} ({len(scored) + len(excluded)} rows). Gate dropped {len(excluded)}. Scored {len(scored)}.",
        "",
        "| # | Account | Score | Why | Next action |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in top:
        acct = f"{r['company_name']}, {r['hq_city']}, {r['headcount']} staff, {r['integration_path'].replace('_', ' ')}"
        lines.append(f"| {r['rank']} | {acct} | {r['score']} | {r['why']} | {r['next_action']} |")
    lines.append("")
    lines.append("Dropped before scoring: " + "; ".join(f"{e['domain']} ({e['reason']})" for e in excluded))
    with open(os.path.join(out_dir, "top5.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    summary = {
        "run_date": date.today().isoformat(),
        "input": source,
        "rows_in": len(scored) + len(excluded),
        "excluded": excluded,
        "scored": len(scored),
        "weights": WEIGHTS,
        "thresholds": {"enterprise": THRESHOLD_ENTERPRISE, "mid_tier": THRESHOLD_MIDTIER},
        "actions": {a: sum(1 for r in scored if r["next_action"] == a) for a in sorted({r["next_action"] for r in scored})},
    }
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", default="output")
    a = ap.parse_args()
    with open(a.csv, newline="") as f:
        rows = list(csv.DictReader(f))
    scored, excluded = route(rows)
    write_outputs(scored, excluded, a.out, os.path.basename(a.csv))


if __name__ == "__main__":
    main()
