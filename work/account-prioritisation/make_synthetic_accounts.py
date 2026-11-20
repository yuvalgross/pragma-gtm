"""
Builds the synthetic input for the account prioritisation sample.

    python3 make_synthetic_accounts.py

Writes data/accounts.csv and data/signals.csv. Every company and domain is
invented (domains end in .example). The file also plants the data problems the
prioritisation has to catch: the region code NA, signals filed under the wrong
type, three companies stored twice, and customers with a renewal signal for
the seller's own contract.
"""
import csv
import os
import random
from datetime import date, timedelta

SEED = 7
WEEK1 = date(2026, 10, 5)  # first Monday the run is asked about

rnd = random.Random(SEED)

SYL_A = ["Ash", "Birch", "Cedar", "Elm", "Fern", "Hazel", "Juniper", "Maple", "Oak", "Pine",
         "Rowan", "Willow", "Alder", "Heath", "Moss", "Reed", "Sorrel", "Thistle", "Yarrow", "Clover"]
SYL_B = ["field", "stone", "bridge", "point", "line", "craft", "port", "gate", "mark", "wright"]
SUFFIX = {"EMEA": ["GmbH", "Ltd", "BV", "AB", "SAS"], "NA": ["Inc", "LLC", "Corp"],
          "LATAM": ["SA", "Ltda", "SpA"], "APAC": ["Pte Ltd", "Pty Ltd", "KK"]}

COUNTRIES = {
    "EMEA": ["Germany", "Sweden", "Netherlands", "United Kingdom", "Spain", "France", "Italy", "Poland"],
    "NA": ["United States", "United States", "United States", "Canada"],
    "LATAM": ["Brazil", "Mexico", "Chile", "Colombia", "Argentina"],
    "APAC": ["Singapore", "Australia", "Japan", "India"],
}
REGION_WEIGHTS = [("EMEA", 0.36), ("NA", 0.35), ("LATAM", 0.17), ("APAC", 0.12)]
INDUSTRIES = ["logistics", "fintech", "healthtech", "retail tech", "manufacturing", "energy", "proptech", "mobility"]
CORE = {"logistics", "fintech", "energy", "mobility"}
VENDORS = ["in house build", "several vendors", "single vendor", ""]

# signal detail text -> filed type. A few are filed under the wrong type on purpose.
SIGNALS = [
    ("contract renewal due with current vendor", "competitor_renewal"),
    ("visited pricing page 3 times", "web_intent"),
    ("visited pricing page", "web_intent"),
    ("complained about current vendor in a review", "competitor_pain"),
    ("read API docs", "web_intent"),
    ("hiring a platform engineer", "job_post"),
    ("launched a new product line", "product_launch"),
    ("new head of procurement", "people_move"),
    ("raised a funding round", "funding"),
    ("opened an office in a new market", "expansion"),
    ("new VP Engineering", "people_move"),
    ("attended a webinar", "event"),
    ("downloaded a whitepaper", "content"),
]


def pick_region():
    r = rnd.random()
    acc = 0
    for reg, w in REGION_WEIGHTS:
        acc += w
        if r <= acc:
            return reg
    return "EMEA"


def name(region):
    return f"{rnd.choice(SYL_A)}{rnd.choice(SYL_B)} {rnd.choice(SUFFIX[region])}"


def main():
    os.makedirs("data", exist_ok=True)
    accounts, seen = [], set()
    i = 0
    while len(accounts) < 497:
        region = pick_region()
        nm = name(region)
        if nm.lower() in seen:
            continue
        seen.add(nm.lower())
        i += 1
        country = rnd.choice(COUNTRIES[region])
        r = rnd.random()
        if r < 0.09:
            stage, owner = "customer", "AE"
        elif r < 0.15:
            stage, owner = "open_deal", "AE"
        elif r < 0.21:
            stage, owner = "prospect", "AE"
        elif r < 0.27:
            stage, owner = "closed_lost", ""
        else:
            stage, owner = "prospect", ""
        size = "" if rnd.random() < 0.3 else str(rnd.choice([40, 120, 300, 800, 2000, 5000]))
        accounts.append({
            "account_id": f"A{i:04d}",
            "company": nm,
            "domain": nm.lower().replace(" ", "-") + ".example",
            "country": country,
            "region": region,
            "industry": rnd.choice(INDUSTRIES),
            "employees": size,
            "current_vendor": rnd.choice(VENDORS),
            "stage": stage,
            "owner_type": owner,
            "last_touch": (WEEK1 - timedelta(days=rnd.randint(5, 400))).isoformat() if rnd.random() < 0.25 else "",
            "lost_date": (WEEK1 - timedelta(days=rnd.randint(20, 400))).isoformat() if stage == "closed_lost" else "",
        })

    # three companies stored twice: one copy has sales history, the other looks new
    for src, tag in zip(rnd.sample([a for a in accounts if a["owner_type"] == "" and a["region"] != "APAC"], 3), [".", " (DE)", "  "]):
        src["last_touch"] = (WEEK1 - timedelta(days=12)).isoformat()
        dup = dict(src)
        dup["account_id"] = f"A{len(accounts) + 1:04d}"
        dup["company"] = src["company"] + tag
        dup["last_touch"] = ""
        accounts.append(dup)

    signals = []

    def add(acc, detail, when, filed=None, extra=""):
        typ = filed or dict(SIGNALS)[detail]
        signals.append({"account_id": acc["account_id"], "signal_type": typ, "detail": detail,
                        "signal_date": when.isoformat(), "extra": extra})

    # history before week 1: 45 percent of accounts show something in the last 90 days
    for acc in accounts:
        if rnd.random() < 0.45:
            for _ in range(rnd.choice([1, 1, 2, 2, 3])):
                detail = rnd.choice([d for d, _ in SIGNALS])
                when = WEEK1 - timedelta(days=rnd.randint(1, 85))
                extra = ""
                if detail.startswith("contract renewal"):
                    extra = (when + timedelta(days=rnd.randint(40, 200))).isoformat()
                add(acc, detail, when, extra=extra)
        if rnd.random() < 0.15:  # old signals that should no longer count
            add(acc, rnd.choice([d for d, _ in SIGNALS[5:]]), WEEK1 - timedelta(days=rnd.randint(95, 200)))

    # a single blog visit filed as a pricing visit
    for acc in rnd.sample(accounts, 34):
        add(acc, "read one blog post", WEEK1 - timedelta(days=rnd.randint(2, 60)), filed="web_intent")

    # customers whose "competitor renewal" is the seller's own contract
    for acc in rnd.sample([a for a in accounts if a["stage"] == "customer"], 4):
        acc["current_vendor"] = "us"
        w = WEEK1 - timedelta(days=rnd.randint(3, 30))
        add(acc, "contract renewal due with current vendor", w, extra=(w + timedelta(days=100)).isoformat())

    # the week between the two Mondays: only a trickle of new signals
    for acc in rnd.sample([a for a in accounts if a["owner_type"] == ""], 9):
        detail = rnd.choice(["contract renewal due with current vendor", "hiring a platform engineer", "visited pricing page"])
        when = WEEK1 + timedelta(days=rnd.randint(0, 6))
        extra = (when + timedelta(days=90)).isoformat() if detail.startswith("contract") else ""
        add(acc, detail, when, extra=extra)

    with open("data/accounts.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(accounts[0].keys()))
        w.writeheader()
        w.writerows(accounts)
    with open("data/signals.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["account_id", "signal_type", "detail", "signal_date", "extra"])
        w.writeheader()
        w.writerows(sorted(signals, key=lambda s: (s["signal_date"], s["account_id"])))
    print(f"{len(accounts)} accounts, {len(signals)} signals")


if __name__ == "__main__":
    main()
