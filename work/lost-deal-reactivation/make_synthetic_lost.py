"""
Builds the synthetic input for the lost deal reactivation sample.

    python3 make_synthetic_lost.py

Writes data/lost_accounts.csv: 760 invented accounts that did not buy, shaped
like a CRM export. It plants what the play has to handle: owners who are no
longer on the sales team, empty lost reasons, probable duplicates, opted out
contacts, customers and key accounts mixed in.
"""
import csv
import os
import random
from datetime import date, timedelta

SEED = 11
TODAY = date(2026, 10, 14)
rnd = random.Random(SEED)

SELLERS = ["Seller A", "Seller B", "Seller C", "Seller D", "Seller E"]
FORMER = ["Former owner 1", "Former owner 2"]
COUNTRIES = ["Germany"] * 6 + ["Austria"] * 2 + ["Switzerland"] * 2 + ["Italy", "United Kingdom"]
LOST_REASONS = (["timing"] * 7 + ["no answer"] * 4 + ["competitor"] * 8 + ["price"] * 6 + ["no opportunity"] * 4
                + ["not icp"] * 2 + ["too small"] * 2 + ["chain"] * 1 + [""] * 18)
ENGAGEMENT = ["pricing page"] * 3 + ["case study"] * 2 + ["webinar"] * 2 + ["event stand"] + ["newsletter click"] * 4 + [""] * 10
SOURCES = ["referral", "event", "inbound demo request", "outbound", "partner"]
A = ["Alpen", "Berg", "Fluss", "Linden", "Sonnen", "Wald", "Stadt", "Hafen", "Garten", "Rosen", "Eichen", "Kloster"]
B = ["werk", "haus", "hof", "blick", "markt", "studio", "partner", "service", "bau", "plus"]


def d(days_ago):
    return (TODAY - timedelta(days=days_ago)).isoformat()


def main():
    os.makedirs("data", exist_ok=True)
    rows = []
    for i in range(1, 761):
        name = f"{rnd.choice(A)}{rnd.choice(B)} {rnd.choice(['GmbH', 'AG', 'KG', 'GmbH & Co. KG'])}"
        saw_demo = rnd.random() < 0.45
        reason = rnd.choice(LOST_REASONS)
        lost_days = rnd.randint(10, 700)
        contract_end = ""
        if reason == "competitor" and rnd.random() < 0.55:
            contract_end = (TODAY + timedelta(days=rnd.randint(-40, 420))).isoformat()
        eng = rnd.choice(ENGAGEMENT)
        r = rnd.random()
        owner = rnd.choice(SELLERS) if r < 0.8 else rnd.choice(FORMER)
        rows.append({
            "account_id": f"L{i:04d}",
            "name": name,
            "country": rnd.choice(COUNTRIES),
            "employees": rnd.choice([8, 15, 25, 40, 60, 90, 150]),
            "owner": owner,
            "saw_demo": "yes" if saw_demo else "no",
            "lifecycle": "unqualified" if (not saw_demo and rnd.random() < 0.08) else "lost",
            "lost_reason": reason,
            "lost_date": d(lost_days),
            "competitor_contract_end": contract_end,
            "last_engagement": eng,
            "last_engagement_date": d(rnd.randint(5, 300)) if eng else "",
            "last_contact_date": d(rnd.randint(max(lost_days - 30, 1), lost_days + 60)),
            "contact_role": rnd.choice(["owner", "managing director", "owner", "office manager", "marketing"]),
            "email_status": rnd.choice(["ok"] * 12 + ["opted out", "invalid"]),
            "lead_source": rnd.choice(SOURCES),
            "key_account": "yes" if rnd.random() < 0.06 else "no",
            "is_customer": "yes" if rnd.random() < 0.017 else "no",
        })
    # probable duplicates: same company, slightly different spelling, no website to match on
    for src in rnd.sample(rows[:700], 19):
        dup = rows[rnd.randint(700, 759)]
        dup.update({"name": src["name"].replace("GmbH", "Gmbh"), "country": src["country"], "employees": src["employees"]})
    with open("data/lost_accounts.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} accounts")


if __name__ == "__main__":
    main()
