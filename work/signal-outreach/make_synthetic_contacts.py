"""
Builds a labelled synthetic contact list for the signal outreach builder.

Every row is invented. Company domains end in .example (reserved, never real)
except the personal email row that exists to test the gate. The columns mimic
what a CRM export (status, last touch, opt out) joined with a Clay enrichment
table (title, email status, signals) would hold. Field names are my assumption,
not a copy of a real schema.

The list is generated from a fixed seed, so every run produces the same rows.
Gate rates are set to roughly what a mixed CRM and enrichment export looks like
in practice; they are inputs to test the rules, not measurements.

Signals are written as type|age_in_days|detail and separated by semicolons.
"""
import csv
import os
import random

SEED = 20261029
N_COMPANIES = 90

COLUMNS = [
    # CRM side
    "contact_id", "first_name", "title", "email", "company_name", "domain",
    "country", "timezone", "headcount", "crm_status", "last_contacted_days", "opted_out",
    # enrichment side (Clay)
    "email_status", "signals",
]

FIRST_NAMES = [
    "Lena", "Tom", "Sara", "Jonas", "Mia", "Paul", "Nora", "Ali", "Eva", "Ben", "Clara", "Max",
    "Ida", "Leo", "Hanna", "Felix", "Marta", "Omar", "Julia", "Noah", "Lisa", "Erik", "Aylin",
    "Tim", "Sofia", "David", "Emma", "Luca", "Maya", "Jan", "Nina", "Oskar", "Rosa", "Finn",
]
GEO = [
    ("DE", "Europe/Berlin"), ("DE", "Europe/Berlin"), ("DE", "Europe/Berlin"), ("NL", "Europe/Amsterdam"),
    ("GB", "Europe/London"), ("GB", "Europe/London"), ("AT", "Europe/Vienna"), ("CH", "Europe/Zurich"),
    ("FR", "Europe/Paris"), ("SE", "Europe/Stockholm"), ("DK", "Europe/Copenhagen"), ("ES", "Europe/Madrid"),
    ("IE", "Europe/Dublin"), ("PL", "Europe/Warsaw"), ("PT", "Europe/Lisbon"), ("BE", "Europe/Brussels"),
]
# (title, weight). A few titles match no persona on purpose.
TITLES = [
    ("Head of Revenue Operations", 6), ("Revenue Operations Manager", 5), ("Sales Ops Lead", 3),
    ("VP Sales", 5), ("Head of Sales", 5), ("Sales Director", 4), ("Chief Revenue Officer", 3),
    ("Founder and CEO", 4), ("Co founder", 3), ("Head of Marketing", 4), ("Marketing Director", 3),
    ("Head of Growth", 3), ("Office Manager", 2), ("Software Engineer", 2), ("Executive Assistant", 1),
]
SIGNAL_DETAILS = {
    "hiring": ["a first RevOps analyst", "three account executives", "a RevOps lead", "two SDRs",
               "a sales ops analyst", "a head of sales", "an inbound SDR", "a marketing ops manager"],
    "tech_change": ["moved from Pipedrive to HubSpot", "moved from Salesforce to HubSpot",
                    "added a scheduling tool to their demo page", "started using Clay",
                    "replaced their chat widget"],
    "funding": ["Series A", "Series B", "seed round", "Series A extension"],
    "event": ["the exhibitor list for a Berlin SaaS conference", "the speaker list for a RevOps meetup",
              "the sponsor list for a fintech summit", "the exhibitor list for a London martech show"],
    "content": ["leads waiting over the weekend", "slow lead response times", "messy territory rules",
                "a free webinar on pipeline hygiene", "handing leads from marketing to sales"],
}
SIGNAL_TYPES = list(SIGNAL_DETAILS)


def pick_weighted(rng, items):
    return rng.choices([i for i, _ in items], weights=[w for _, w in items])[0]


def random_signals(rng):
    """Zero to three signals, ages spread from 1 to 90 days."""
    n = rng.choices([0, 1, 2, 3], weights=[18, 45, 27, 10])[0]
    out = []
    for kind in rng.sample(SIGNAL_TYPES, n):
        age = rng.choice([rng.randint(1, 21), rng.randint(1, 21), rng.randint(22, 45), rng.randint(46, 90)])
        out.append(f"{kind}|{age}|{rng.choice(SIGNAL_DETAILS[kind])}")
    return ";".join(out)


def crm_fields(rng):
    roll = rng.random()
    crm = "customer" if roll < 0.06 else "open_deal" if roll < 0.10 else "partner" if roll < 0.12 else "none"
    touch = str(rng.randint(3, 120)) if rng.random() < 0.22 else ""
    opted = "yes" if rng.random() < 0.04 else "no"
    status = rng.choices(["valid", "risky", "invalid", "unknown"], weights=[78, 11, 7, 4])[0]
    return crm, touch, opted, status


def build_rows(rng):
    rows, used = [], set()
    for c in range(N_COMPANIES):
        letter = f"{chr(65 + c % 26)}{'' if c < 26 else c // 26 + 1}"
        domain = f"company-{letter.lower()}.example"
        country, tz = rng.choice(GEO)
        headcount = rng.choice([8, 15, 30, 45, 80, 140, 220, 400, 900])
        crm, touch, _, _ = crm_fields(rng)
        # one or two contacts per company; customers and open deals apply to the whole account
        for _ in range(rng.choices([1, 2], weights=[70, 30])[0]):
            first = rng.choice([n for n in FIRST_NAMES if (n, domain) not in used])
            used.add((first, domain))
            _, own_touch, own_opt, status = crm_fields(rng)
            rows.append([first, pick_weighted(rng, TITLES), f"{first.lower()}@{domain}",
                         f"Synthetic Company {letter}", domain, country, tz, headcount,
                         crm, touch or own_touch, own_opt,
                         status, random_signals(rng)])
    return rows


# Fixed rows that must each be caught by one specific rule, whatever the seed does.
TEST_ROWS = [
    ["Dan", "Founder", "dan@gmail.com", "", "gmail.com", "DE", "Europe/Berlin", 0, "none", "", "no",
     "valid", "content|4|outbound reply rates"],
    ["Ira", "VP Sales", "ira@company-z9.example", "Synthetic Company Z9", "company-z9.example", "DE",
     "Europe/Berlin", 60, "none", "", "no", "valid", "hiring|five|two SDRs"],
    # these two pass the gate and the signal step, then must stop at the copy check
    ["Rhea", "Head of Marketing", "rhea@company-z8.example", "Synthetic Company Z8", "company-z8.example", "FR",
     "Europe/Paris", 75, "none", "", "no", "valid", "content|10|a free webinar on pipeline hygiene"],
    ["Ugo", "Head of Sales", "ugo@company-z7.example", "Synthetic Company Z7", "company-z7.example", "ES",
     "Europe/Madrid", 45, "none", "", "no", "risky", "hiring|8|two SDRs"],
]


def main(path="data/contacts_synthetic.csv"):
    rng = random.Random(SEED)
    rows = build_rows(rng) + TEST_ROWS
    rows.append(list(rows[0]))          # an exact duplicate, as an export joined twice would produce
    rows[-1][2] = rows[-1][2].upper()   # same address, different case
    out = [[f"con-{i:03d}", *r] for i, r in enumerate(rows, start=1)]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(out)
    print(f"wrote {len(out)} synthetic rows to {path}")


if __name__ == "__main__":
    main()
