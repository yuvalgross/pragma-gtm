"""
Builds the synthetic input for the job search engine sample.

    python3 make_synthetic_jobs.py

Writes:
  data/postings.json       every posting with the day it opened and closed on the company's own list
  data/board_copies.json   what the job boards show: copies of those postings, each first seen on a day
  data/companies.json      each company: ATS, size, funding stage, whether its own list can be read
  data/applications.csv    applications sent before the simulated fortnight, with their outcome

Everything is invented. The shape follows a real search in a European city:
most roles found on boards are not a fit, a third of local roles ask the local
language, boards keep closed roles up for weeks, the same role shows on two or
three boards, and only a role or two a week is worth a tailored CV.
"""
import csv
import json
import os
import random

SEED = 21
DAYS = 14
rnd = random.Random(SEED)

A = ["Lumen", "Quill", "Harbor", "Juniper", "Nimbus", "Orchard", "Pebble", "Saffron", "Tidal", "Vesper",
     "Wren", "Atlas", "Bramble", "Cobalt", "Delta", "Ember", "Fable", "Garnet", "Halcyon", "Indigo",
     "Kestrel", "Linden", "Marlow", "Nettle", "Opal", "Prism", "Quarry", "Rook", "Sable", "Thistle"]
B = ["Labs", "AI", "Cloud", "Works", "HQ", "Data", "Systems", "Health", "Pay", "Logic", "Grid", "Stack"]
ATS = ["ashby"] * 5 + ["greenhouse"] * 3 + ["personio"] * 4 + ["teamtailor"] * 2 + ["join"] * 2 + ["lever", "recruitee", "workable"]
ATS_URL = {
    "ashby": "https://jobs.ashbyhq.example/{slug}/{id}",
    "greenhouse": "https://job-boards.greenhouse.example/{slug}/jobs/{id}",
    "lever": "https://jobs.lever.example/{slug}/{id}",
    "personio": "https://{slug}.jobs.personio.example/job/{id}",
    "teamtailor": "https://{slug}.teamtailor.example/jobs/{id}",
    "join": "https://join.example/companies/{slug}/{id}",
    "recruitee": "https://{slug}.recruitee.example/o/{id}",
    "workable": "https://apply.workable.example/{slug}/j/{id}",
}
# source, tier, chance a posting shows up there, (min, max) days of lag after it opens
SOURCES = [
    ("LinkedIn alert", "A", 0.55, (0, 1)), ("Indeed", "A", 0.25, (0, 12)), ("niche job board", "A", 0.35, (0, 4)),
    ("ATS host search", "A", 0.30, (0, 2)), ("newsletter", "A", 0.15, (2, 7)), ("VC portfolio board", "B", 0.15, (3, 20)),
    ("startup board", "B", 0.12, (5, 25)), ("remote board", "C", 0.08, (5, 30)),
]

LOCATIONS = [  # city, country, weight
    ("Berlin", "Germany", 30), ("Munich", "Germany", 9), ("Hamburg", "Germany", 5), ("Cologne", "Germany", 3),
    ("Remote EU", "EU", 10), ("Remote Germany", "Germany", 7), ("Madrid", "Spain", 3), ("Barcelona", "Spain", 3),
    ("Remote Spain", "Spain", 3), ("Amsterdam", "Netherlands", 7), ("Rotterdam", "Netherlands", 2), ("Remote Netherlands", "Netherlands", 3), ("London", "United Kingdom", 8),
    ("Limassol", "Cyprus", 1), ("Remote US", "United States", 7), ("Stockholm", "Sweden", 3), ("Paris", "France", 4),
]
LOCAL_LANGUAGE = {"Germany": "German C1", "Spain": "Spanish", "Netherlands": "Dutch", "France": "French", "Sweden": "Swedish"}

FAMILIES = {
    "marketing": {
        "titles": ["Marketing Manager"] * 4 + ["Senior Marketing Manager", "Founding Marketer", "Lifecycle Marketing Manager",
                   "Content Marketing Manager", "Growth Marketing Manager", "Head of Marketing", "Marketing Intern",
                   "Working Student Marketing"],
        "build": ["build the lifecycle email program", "launch paid campaigns in new markets",
                  "set up marketing automation", "run product launches end to end",
                  "build the content calendar", "own the website and landing pages"],
        "run": ["report campaign results to leadership", "manage the agency", "run the events calendar",
                "prepare board slides", "manage the budget", "write social posts",
                "maintain the brand guidelines"],
        "tools": ["HubSpot", "Google Ads", "Webflow", "Figma", "GA4", "Canva", "LinkedIn Ads", "Semrush", "Notion", "Zapier", "Salesforce", "Looker", "Mailchimp"],
        "pay": (50, 95),
    },
    "ops": {
        "titles": ["Operations Manager", "Senior Operations Manager", "Business Operations Analyst", "Operations Specialist", "Head of Operations"],
        "build": ["automate internal processes", "build the operations playbook"],
        "run": ["report weekly numbers to leadership", "administer internal tools", "run the planning process",
                "prepare board decks", "manage vendor contracts", "own the office budget"],
        "tools": ["Notion", "Excel", "SQL", "Looker", "Airtable", "Slack", "Jira"],
        "pay": (55, 95),
    },
    "ae": {
        "titles": ["Account Executive", "Senior Account Executive", "Enterprise Account Executive", "Founding AE"],
        "build": [],
        "run": ["run discovery and demos", "own a new business quota", "forecast your pipeline", "prospect into mid market"],
        "tools": ["Salesforce", "HubSpot", "Gong", "Outreach"],
        "pay": (60, 110),
    },
    "cs": {
        "titles": ["Customer Success Manager"] * 4 + ["Senior Customer Success Manager", "Head of Customer Success", "Onboarding Manager", "Customer Success Associate (Junior)", "Working Student Customer Success"],
        "build": ["run onboarding for new customers", "drive adoption and health scores", "own renewals and expansion",
                  "build success playbooks", "lead churn risk reviews", "run business reviews with key accounts"],
        "run": ["answer support tickets", "prospect cold accounts", "handle billing questions", "chase overdue invoices"],
        "tools": ["Gainsight", "HubSpot", "Salesforce", "Intercom", "Zendesk"],
        "pay": (50, 85),
    },
    "data": {
        "titles": ["Data Analyst"] * 3 + ["Senior Data Analyst", "Analytics Engineer", "BI Analyst", "Head of Data", "Data Analyst Intern"],
        "build": ["build dbt models", "build dashboards for sales and marketing", "model the revenue data warehouse",
                  "analyse A/B tests for product teams"],
        "run": ["answer ad hoc data requests", "maintain legacy reports", "handle data access tickets"],
        "tools": ["SQL", "dbt", "Looker", "Python", "BigQuery"],
        "pay": (55, 85),
    },
}
FAMILY_WEIGHTS = [("cs", 30), ("data", 22), ("ae", 18), ("marketing", 14), ("ops", 16)]


def wpick(pairs):
    total = sum(p[-1] for p in pairs)
    r = rnd.uniform(0, total)
    for p in pairs:
        r -= p[-1]
        if r <= 0:
            return p
    return pairs[-1]


def main():
    os.makedirs("data", exist_ok=True)
    companies, names = {}, set()
    while len(companies) < 110:
        n = f"{rnd.choice(A)} {rnd.choice(B)}"
        if n in names:
            continue
        names.add(n)
        size = rnd.choice([15, 30, 45, 70, 110, 160, 240, 380, 600, 1200, 3000])
        stage = "Seed" if size < 40 else "Series A" if size < 120 else "Series B" if size < 300 else "Series C+" if size < 1000 else "Public or late stage"
        r = rnd.random()
        companies[n] = {"slug": n.lower().replace(" ", ""), "ats": rnd.choice(ATS), "employees": size, "stage": stage,
                        "list": "works" if r < 0.86 else ("unreadable" if r < 0.94 else "none")}

    postings, copies = [], []
    pid = 4000
    # postings that opened before the fortnight (older stock still on boards) and during it
    for _ in range(620):
        cname = rnd.choice(list(companies))
        c = companies[cname]
        fam = wpick(FAMILY_WEIGHTS)[0]
        F = FAMILIES[fam]
        city, country, _ = wpick(LOCATIONS)
        if city.startswith("Remote"):
            workplace, office_days = "remote", 0
        else:
            workplace = wpick([("hybrid", 6), ("on site", 3)])[0]
            office_days = 5 if workplace == "on site" else rnd.choice([1, 2, 3, 3, 4])
        if fam in ("cs", "data") and rnd.random() < 0.3:
            duties = rnd.sample(F["build"], k=3) + rnd.sample(F["run"], k=rnd.choice([0, 1]))
        else:
            duties = rnd.sample(F["build"], k=min(len(F["build"]), rnd.choice([0, 1, 1, 2]))) + \
                rnd.sample(F["run"], k=min(len(F["run"]), rnd.choice([1, 2, 3])))
        langs = [LOCAL_LANGUAGE[country]] if country in LOCAL_LANGUAGE and rnd.random() < 0.35 else []
        lo, hi = F["pay"]
        pay = None if rnd.random() < 0.55 else (lambda a: [a, a + rnd.choice([10, 15, 20, 25])])(rnd.randrange(lo, hi - 5, 5))
        opened = rnd.randint(-25, DAYS - 1)
        closed = opened + rnd.randint(6, 45) if rnd.random() < 0.65 else None
        pid += 1
        p = {
            "id": str(pid), "company": cname, "title": rnd.choice(F["titles"]), "family": fam,
            "location": city, "country": country, "workplace": workplace, "office_days": office_days,
            "languages_required": langs, "years_required": wpick([(2, 2), (3, 4), (4, 3), (5, 3), (6, 2), (8, 1)])[0],
            "pay_k_eur": pay, "employees": c["employees"], "duties": duties,
            "tools": rnd.sample(F["tools"], k=min(len(F["tools"]), rnd.choice([3, 4, 5]))),
            "opened_day": opened, "closed_day": closed,
            "url": ATS_URL[c["ats"]].format(slug=c["slug"], id=pid),
        }
        postings.append(p)
        # board copies: each source picks it up with its own chance and lag; boards keep it for weeks
        for src, tier, chance, (lag_lo, lag_hi) in SOURCES:
            if rnd.random() < chance:
                copies.append({"id": p["id"], "source": src, "tier": tier, "seen_day": opened + rnd.randint(lag_lo, lag_hi),
                               "gone_day": (closed or opened + 60) + rnd.randint(10, 30)})
        # a repost: same role under a new id, the old one closes on the company list
        if rnd.random() < 0.06 and opened < DAYS - 3:
            pid += 1
            new = dict(p, id=str(pid), opened_day=opened + rnd.randint(3, 10), url=ATS_URL[c["ats"]].format(slug=c["slug"], id=pid))
            p["closed_day"] = new["opened_day"]
            postings.append(new)
            copies.append({"id": new["id"], "source": "ATS host search", "tier": "A", "seen_day": new["opened_day"], "gone_day": new["opened_day"] + 60})

    with open("data/postings.json", "w") as f:
        json.dump(postings, f, indent=1)
    with open("data/board_copies.json", "w") as f:
        json.dump(copies, f, indent=1)
    with open("data/companies.json", "w") as f:
        json.dump(companies, f, indent=1)

    # applications before the fortnight: shape, size, note, channel and outcome
    rows = []
    for i in range(72):
        shape = wpick([("build", 6), ("run", 3), ("sales", 2)])[0]
        size = wpick([("under 150", 4), ("150 to 500", 3), ("over 500", 3)])[0]
        note = rnd.random() < 0.3
        p_call = {"build": 0.30, "run": 0.10, "sales": 0.15}[shape] * {"under 150": 1.2, "150 to 500": 1.0, "over 500": 0.6}[size]
        p_call *= 1.7 if note else 1.0
        r = rnd.random()
        outcome = "call" if r < p_call else ("rejected at CV" if r < p_call + 0.38 else ("no reply" if r < p_call + 0.7 else "pending"))
        cname = rnd.choice(list(companies))
        rows.append({"application": f"P{i + 1:03d}", "company": cname, "role_shape": shape, "company_size": size,
                     "channel": rnd.choice(["Ashby", "Ashby", "Personio", "Greenhouse", "Teamtailor", "JOIN", "LinkedIn Easy Apply", "Email"]),
                     "cv_score": rnd.choice([8, 8.5, 8.5, 9, 9, 9]), "note_to_named_person": "yes" if note else "no",
                     "days_before_start": rnd.randint(1, 50), "outcome": outcome})
    with open("data/applications.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(postings)} postings, {len(copies)} board copies, {len(companies)} companies, {len(rows)} past applications")


if __name__ == "__main__":
    main()
