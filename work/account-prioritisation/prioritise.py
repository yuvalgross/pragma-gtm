"""
Account prioritisation: which accounts each SDR works this week, and why.

    python3 prioritise.py data/accounts.csv data/signals.csv --out output

Runs two Mondays in a row. Week 2 never repeats an account from week 1.

Steps, every Monday
  1. Clean: read the region code NA as North America, merge companies stored
     twice, ignore signals whose text says nothing, log every fix.
  2. Gate: may a rep call it? AE owned, no rep for the region, touched in the
     last 21 days, lost in the last 120 days.
  3. Score: (signal points + fit points) x boost. Signals fade, renewals count
     as they come closer, one signal per type plus a bonus for variety.
  4. Route: territory, then each rep's capacity for new accounts. Free slots
     take the best fitting accounts with no signal, marked fit only.
  5. Output: one list per rep, best first, with why now and a first step.

Every rule is a setting at the top of this file. Standard library only.
"""
import argparse
import csv
import json
import os
import re
from collections import Counter, defaultdict
from datetime import date, timedelta

# ---- settings ---------------------------------------------------------------

MONDAYS = [date(2026, 10, 5), date(2026, 10, 12)]

REPS = [  # name, territory, new accounts per week, months in role
    ("EMEA rep", "EMEA", 25, 14),
    ("US senior rep", "NA", 20, 18),
    ("US junior rep", "NA", 15, 4),
    ("LATAM rep", "LATAM", 20, 12),
]
SENIOR_FIRST_EMPLOYEES = 2000  # in NA, accounts this big go to the senior rep first

# points are set on what a signal says, not on the type it was filed under
SIGNAL_POINTS = {
    "contract renewal due with current vendor": 30,
    "visited pricing page 3 times": 25,
    "complained about current vendor in a review": 24,
    "read API docs": 20,
    "hiring a platform engineer": 22,
    "visited pricing page": 18,
    "launched a new product line": 18,
    "new head of procurement": 15,
    "raised a funding round": 12,
    "opened an office in a new market": 12,
    "new VP Engineering": 10,
    "attended a webinar": 8,
    "downloaded a whitepaper": 8,
    "read one blog post": 0,
}
FIRST_STEP = {
    "contract renewal due with current vendor": ("Head of Procurement", "Open with a cost comparison before they renew"),
    "visited pricing page 3 times": ("Head of Engineering", "Offer a pricing walkthrough for their volume"),
    "visited pricing page": ("Head of Engineering", "Offer a pricing walkthrough for their volume"),
    "complained about current vendor in a review": ("Head of Engineering", "Ask what broke and show how it is handled"),
    "read API docs": ("Lead developer", "Offer a technical session on the integration"),
    "hiring a platform engineer": ("VP Engineering", "Reference the role and the build it is hired for"),
    "launched a new product line": ("Head of Product", "Ask what the launch needs from the stack"),
}
HALF_LIFE_DAYS = 21
MAX_SIGNAL_AGE = 90
VARIETY_BONUS = 6
FUNDING_NEAR_BUILD_DAYS = 60   # funding counts double within this many days of a build signal
COOL_DOWN_DAYS = 21
LOST_WAIT_DAYS = 120
MIN_SCORE = 15
BOOSTS = {}  # e.g. {"logistics": 1.5}

SIZE_POINTS = [(5000, 15), (2000, 12), (800, 9), (300, 6), (0, 3)]
VENDOR_POINTS = {"in house build": 8, "several vendors": 8, "single vendor": 5}
CORE_INDUSTRIES = {"logistics", "fintech", "energy", "mobility"}
MISSING = {"size": 5, "vendor": 3}

# ---- clean ------------------------------------------------------------------


def norm(name):
    n = re.sub(r"\(.*?\)", "", name.lower())
    n = re.sub(r"[^a-z0-9 ]", "", n)
    return re.sub(r"\s+", " ", n).strip()


def clean(accounts, signals, log):
    na = sum(1 for a in accounts if a["region"] == "NA")
    log.append(("region NA read as North America, not as empty", na))
    # merge companies stored twice into the record with sales history
    groups = defaultdict(list)
    for a in accounts:
        groups[(norm(a["company"]), a["country"])].append(a)
    remap, keep = {}, []
    for recs in groups.values():
        recs.sort(key=lambda a: (a["last_touch"] == "", a["account_id"]))
        keep.append(recs[0])
        for dup in recs[1:]:
            remap[dup["account_id"]] = recs[0]["account_id"]
    if remap:
        log.append(("companies stored twice, merged into the record with history", len(remap)))
    for s in signals:
        s["account_id"] = remap.get(s["account_id"], s["account_id"])
    blog = sum(1 for s in signals if s["detail"] == "read one blog post" and s["signal_type"] == "web_intent")
    log.append(("single blog visits filed as pricing interest, scored 0", blog))
    return keep, signals

# ---- score ------------------------------------------------------------------


def days(a, b):
    return (a - b).days


def signal_points(sig, monday):
    base = SIGNAL_POINTS.get(sig["detail"], 0)
    when = date.fromisoformat(sig["signal_date"])
    if when >= monday:
        return 0.0
    if sig["detail"].startswith("contract renewal") and sig["extra"]:
        to_go = days(date.fromisoformat(sig["extra"]), monday)
        if to_go <= 0 or to_go > 180:
            return 0.0
        return base / 2 if to_go <= 30 else float(base)
    age = days(monday, when)
    if age > MAX_SIGNAL_AGE:
        return 0.0
    return base * 0.5 ** (age / HALF_LIFE_DAYS)


def score_signals(sigs, monday):
    best = {}
    for s in sigs:
        p = signal_points(s, monday)
        if p <= 0:
            continue
        key = s["detail"]  # one per kind of signal
        if p > best.get(key, (0, None))[0]:
            best[key] = (p, s)
    if not best:
        return 0.0, None, []
    build_dates = [date.fromisoformat(s["signal_date"]) for p, s in best.values()
                   if s["detail"] in ("hiring a platform engineer", "launched a new product line")]
    total = 0.0
    for key, (p, s) in best.items():
        if key == "raised a funding round" and any(
                abs(days(date.fromisoformat(s["signal_date"]), d)) <= FUNDING_NEAR_BUILD_DAYS for d in build_dates):
            p *= 2
        total += p
    total += VARIETY_BONUS * (len(best) - 1)
    ranked = sorted(best.values(), key=lambda x: -x[0])
    return round(total, 1), ranked[0][1], [s["detail"] for _, s in ranked]


def fit_points(a):
    if a["employees"]:
        n = int(a["employees"])
        size = next(p for floor, p in SIZE_POINTS if n >= floor)
    else:
        size = MISSING["size"]
    vendor = VENDOR_POINTS.get(a["current_vendor"], MISSING["vendor"])
    industry = 6 if a["industry"] in CORE_INDUSTRIES else 4
    return size + vendor + industry

# ---- gate -------------------------------------------------------------------


def gate(a, monday, has_rep):
    if a["owner_type"] == "AE" or a["stage"] in ("customer", "open_deal"):
        return "owned by an AE"
    if a["region"] not in has_rep:
        return "region with no rep"
    if a["last_touch"] and days(monday, date.fromisoformat(a["last_touch"])) < COOL_DOWN_DAYS:
        return "touched in the last 21 days"
    if a["lost_date"] and days(monday, date.fromisoformat(a["lost_date"])) < LOST_WAIT_DAYS:
        return "lost less than 120 days ago"
    return None

# ---- one Monday -------------------------------------------------------------


def run_week(accounts, by_acc, monday, already):
    has_rep = {t for _, t, _, _ in REPS}
    rows, out, alerts = [], Counter(), []
    for a in accounts:
        if a["account_id"] in already:
            continue
        sig, top, kinds = score_signals(by_acc.get(a["account_id"], []), monday)
        reason = gate(a, monday, has_rep)
        if reason == "owned by an AE":
            if sig > 0:
                kind = "retention" if a["current_vendor"] == "us" else ("open deal" if a["stage"] == "open_deal" else "expansion")
                alerts.append({"monday": monday.isoformat(), "account_id": a["account_id"], "company": a["company"],
                               "alert": kind, "signals": "; ".join(kinds)})
            out[reason] += 1
            continue
        if reason:
            out[reason] += 1
            if reason == "region with no rep" and sig > 0:
                out["region with no rep, with a signal"] += 1
            continue
        fit = fit_points(a)
        boost = BOOSTS.get(a["industry"], 1.0)
        score = round((sig + fit) * boost, 1)
        rows.append({"a": a, "signal": sig, "fit": fit, "score": score, "top": top, "kinds": kinds})

    signal_rows = [r for r in rows if r["signal"] > 0]
    out["no buying signal in the last 90 days"] = len(rows) - len(signal_rows)
    weak = [r for r in signal_rows if r["score"] < MIN_SCORE]
    out["signal too weak, score under 15"] = len(weak)
    strong = sorted([r for r in signal_rows if r["score"] >= MIN_SCORE], key=lambda r: -r["score"])
    fit_only = sorted([r for r in rows if r["signal"] == 0], key=lambda r: -r["fit"])

    lists = {name: [] for name, _, _, _ in REPS}
    cap = {name: c for name, _, c, _ in REPS}

    def place(r, label):
        terr = r["a"]["region"]
        reps = [n for n, t, _, _ in REPS if t == terr and len(lists[n]) < cap[n]]
        if not reps:
            return False
        if terr == "NA":
            big = r["a"]["employees"] and int(r["a"]["employees"]) >= SENIOR_FIRST_EMPLOYEES
            if big and "US senior rep" in reps:
                reps = ["US senior rep"]
            else:
                reps.sort(key=lambda n: len(lists[n]) / cap[n])
        lists[reps[0]].append(dict(r, kind=label))
        return True

    waiting = Counter()
    for r in strong:
        if not place(r, "signal"):
            waiting[r["a"]["region"]] += 1
    out["no room left in the rep's territory"] = sum(waiting.values())
    for r in fit_only:
        if all(len(lists[n]) >= cap[n] for n in lists):
            break
        place(r, "fit only")
    return lists, out, alerts, waiting


def tier(r):
    hi_fit, hi_sig = r["fit"] >= 20, r["signal"] >= 30
    return 1 if hi_fit and hi_sig else (2 if hi_fit or hi_sig else 3)


def as_rows(lists, monday):
    rows = []
    months = {n: m for n, _, _, m in REPS}
    for rep, items in lists.items():
        for i, r in enumerate(sorted(items, key=lambda x: (x["kind"] != "signal", -x["score"])), start=1):
            a, top = r["a"], r["top"]
            who, step = FIRST_STEP.get(top["detail"], ("Head of Engineering", "Lead with the signal")) if top else (
                "Head of Engineering", "Fit only: open on their stack and size, no trigger yet")
            note = "Manager joins the first call" if months[rep] < 6 and tier(r) == 1 else ""
            rows.append({
                "monday": monday.isoformat(), "rep": rep, "rank": i, "account_id": a["account_id"],
                "company": a["company"], "country": a["country"], "kind": r["kind"], "tier": tier(r),
                "signal_points": r["signal"], "fit_points": r["fit"], "score": r["score"],
                "why_now": "; ".join(r["kinds"]) if r["kinds"] else "no signal yet",
                "who_to_call": who, "first_step": step, "note": note,
            })
    return rows

# ---- checks -----------------------------------------------------------------


def checks(weeks, accounts_by_id, signals):
    seen = set()
    for monday, rows in weeks:
        per_rep = Counter(r["rep"] for r in rows)
        for name, _, c, _ in REPS:
            assert per_rep[name] <= c, f"{name} over capacity"
        ids = [r["account_id"] for r in rows]
        assert len(ids) == len(set(ids)), "an account is listed twice"
        assert not seen & set(ids), "an account is on both weeks' lists"
        seen |= set(ids)
        for r in rows:
            a = accounts_by_id[r["account_id"]]
            assert a["owner_type"] != "AE" and a["stage"] not in ("customer", "open_deal"), "AE account on a list"
            assert a["region"] != "APAC", "APAC account on a list"
        for s in signals:
            if s["account_id"] in ids and date.fromisoformat(s["signal_date"]) >= monday:
                # allowed in the file, but it must not have scored: verified by signal_points returning 0
                assert signal_points(s, monday) == 0
    return "all checks passed"

# ---- main -------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("accounts")
    ap.add_argument("signals")
    ap.add_argument("--out", default="output")
    ap.add_argument("--capacity", default="", help='change capacity, e.g. "LATAM rep=12,EMEA rep=33"')
    args = ap.parse_args()
    if args.capacity:
        change = dict(x.split("=") for x in args.capacity.split(","))
        REPS[:] = [(n, t, int(change.get(n, c)), m) for n, t, c, m in REPS]

    with open(args.accounts, newline="") as f:
        accounts = list(csv.DictReader(f))  # csv keeps "NA" as text; pandas would not by default
    with open(args.signals, newline="") as f:
        signals = list(csv.DictReader(f))

    log = []
    accounts, signals = clean(accounts, signals, log)
    by_acc = defaultdict(list)
    for s in signals:
        by_acc[s["account_id"]].append(s)

    os.makedirs(args.out, exist_ok=True)
    already, weeks, summary_weeks, all_alerts = set(), [], [], []
    for n, monday in enumerate(MONDAYS, start=1):
        lists, out, alerts, waiting = run_week(accounts, by_acc, monday, already)
        rows = as_rows(lists, monday)
        weeks.append((monday, rows))
        all_alerts += alerts
        already |= {r["account_id"] for r in rows}
        sig_rows = [r for r in rows if r["kind"] == "signal"]
        summary_weeks.append({
            "week": n, "monday": monday.isoformat(), "listed": len(rows),
            "with_signal": len(sig_rows), "fit_only": len(rows) - len(sig_rows),
            "tier_1": sum(1 for r in rows if r["tier"] == 1),
            "avg_signal_points": round(sum(r["signal_points"] for r in sig_rows) / max(len(sig_rows), 1), 1),
            "avg_fit_points": round(sum(r["fit_points"] for r in sig_rows) / max(len(sig_rows), 1), 1),
            "gate": dict(out), "signal_accounts_waiting_by_region": dict(waiting),
            "ae_alerts": len(alerts),
        })
        with open(os.path.join(args.out, f"week{n}_lists.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    result = checks(weeks, {a["account_id"]: a for a in accounts}, signals)

    with open(os.path.join(args.out, "ae_alerts.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["monday", "account_id", "company", "alert", "signals"])
        w.writeheader()
        w.writerows(all_alerts)
    with open(os.path.join(args.out, "data_quality.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["fix", "rows"])
        w.writerows(log)

    lines = ["# Monday lists, week 1", ""]
    for rep in [r[0] for r in REPS]:
        top = [r for r in weeks[0][1] if r["rep"] == rep][:3]
        lines.append(f"## {rep}")
        lines.append("| # | Account | Score | Why now | Who to call | First step |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for r in top:
            lines.append(f"| {r['rank']} | {r['company']}, {r['country']} | {r['score']} | {r['why_now']} | {r['who_to_call']} | {r['first_step']} |")
        lines.append("")
    with open(os.path.join(args.out, "monday.md"), "w") as f:
        f.write("\n".join(lines))

    summary = {"accounts_after_merge": len(accounts), "data_quality": dict(log),
               "weeks": summary_weeks, "checks": result}
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
