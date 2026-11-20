"""
Builds the synthetic input for the job search engine sample.

    python3 make_synthetic_jobs.py

Writes:
  data/postings.json       what the job boards show (discovery copies)
  data/company_lists.json  each company's own job list (the only proof a role is open)
  data/applications.csv    a past application history with outcomes (for the learning loop)

Every company, person and posting is invented. The feed mixes several job
families (GTM engineering, RevOps, sales, customer success, data) so the same
engine can be pointed at a different profile. It also plants what a real feed
has: the same role on three boards, reposts under a new id, roles that closed
on the company's list but stay up on a board, companies whose list cannot be
read, roles that ask a language, and roles that need a move.
"""
import csv
import json
import os
import random
from datetime import date, timedelta

SEED = 21
TODAY = date(2026, 11, 16)
rnd = random.Random(SEED)

A = ["Lumen", "Quill", "Harbor", "Juniper", "Nimbus", "Orchard", "Pebble", "Saffron", "Tidal", "Vesper",
     "Wren", "Atlas", "Bramble", "Cobalt", "Delta", "Ember", "Fable", "Garnet", "Halcyon", "Indigo"]
B = ["Labs", "AI", "Cloud", "Works", "HQ", "Data", "Systems", "Health", "Pay", "Logic"]
ATS = ["ashby", "greenhouse", "lever", "personio", "teamtailor", "join", "recruitee", "workable"]
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
BOARDS = ["LinkedIn alert", "Indeed", "niche GTM board", "VC portfolio board", "ATS host search", "newsletter"]

LOCATIONS = [  # city, country, weight
    ("Berlin", "Germany", 30), ("Munich", "Germany", 8), ("Hamburg", "Germany", 5),
    ("Remote EU", "EU", 18), ("Remote Germany", "Germany", 8), ("Madrid", "Spain", 4),
    ("Remote Spain", "Spain", 5), ("Amsterdam", "Netherlands", 6), ("London", "United Kingdom", 6),
    ("Limassol", "Cyprus", 2), ("Remote US", "United States", 4), ("Stockholm", "Sweden", 3),
]

FAMILIES = {
    "gtm": {
        "titles": ["GTM Engineer", "Founding GTM Engineer", "Senior GTM Engineer", "GTM Systems Engineer",
                   "RevOps Engineer", "Growth Engineer", "Head of GTM Engineering", "GTM Engineering Intern"],
        "build": ["build enrichment and scoring workflows", "build outbound and signal pipelines",
                  "automate CRM updates with APIs and webhooks", "ship AI agents for research and routing",
                  "build lead routing from scratch", "integrate tools through APIs"],
        "run": ["own pipeline reporting for leadership", "administer the CRM", "run the forecast process",
                "prepare QBR decks", "manage territory and quota planning"],
        "tools": ["Clay", "HubSpot", "Salesforce", "n8n", "Make", "Python", "SQL", "Claude", "Apollo", "Zapier"],
        "pay": (55, 95),
    },
    "revops": {
        "titles": ["Revenue Operations Manager", "Senior RevOps Manager", "Sales Operations Analyst", "RevOps Specialist"],
        "build": ["automate CRM updates with APIs and webhooks", "build lead routing from scratch"],
        "run": ["own pipeline reporting for leadership", "administer the CRM", "run the forecast process",
                "prepare QBR decks", "manage territory and quota planning", "design commission plans"],
        "tools": ["HubSpot", "Salesforce", "SQL", "Looker", "Excel", "Gong"],
        "pay": (55, 90),
    },
    "ae": {
        "titles": ["Account Executive", "Senior Account Executive", "Enterprise Account Executive", "Founding AE"],
        "build": [],
        "run": ["run discovery and demos", "own a new business quota", "forecast your pipeline", "prospect into mid market"],
        "tools": ["Salesforce", "HubSpot", "Gong", "Outreach"],
        "pay": (60, 110),
    },
    "cs": {
        "titles": ["Customer Success Manager", "Senior Customer Success Manager", "Head of Customer Success", "Onboarding Manager"],
        "build": ["run onboarding for new customers", "drive adoption and health scores", "own renewals and expansion",
                  "build success playbooks"],
        "run": ["answer support tickets", "prospect cold accounts", "handle billing questions"],
        "tools": ["Gainsight", "HubSpot", "Salesforce", "Intercom", "Zendesk"],
        "pay": (50, 85),
    },
    "data": {
        "titles": ["Data Analyst", "Analytics Engineer", "BI Analyst"],
        "build": ["build dbt models", "build dashboards for sales and marketing"],
        "run": ["answer ad hoc data requests", "maintain reports"],
        "tools": ["SQL", "dbt", "Looker", "Python", "BigQuery"],
        "pay": (55, 85),
    },
}
FAMILY_WEIGHTS = [("gtm", 40), ("revops", 16), ("ae", 14), ("cs", 22), ("data", 8)]


def wpick(pairs):
    total = sum(w for *_, w in pairs)
    r = rnd.uniform(0, total)
    for item in pairs:
        r -= item[-1]
        if r <= 0:
            return item
    return pairs[-1]


def main():
    os.makedirs("data", exist_ok=True)
    companies, names = [], set()
    while len(companies) < 60:
        n = f"{rnd.choice(A)} {rnd.choice(B)}"
        if n in names:
            continue
        names.add(n)
        size = rnd.choice([12, 25, 40, 80, 120, 180, 260, 450, 900, 2500])
        r = rnd.random()
        list_status = "works" if r < 0.8 else ("unreadable" if r < 0.9 else "none")
        companies.append({"name": n, "slug": n.lower().replace(" ", ""), "ats": rnd.choice(ATS),
                          "employees": size, "list_status": list_status})

    postings, lists = [], {c["name"]: {"ats": c["ats"], "status": c["list_status"], "open_ids": []} for c in companies}
    pid = 1000
    for _ in range(110):
        c = rnd.choice(companies)
        fam = wpick(FAMILY_WEIGHTS)[0]
        F = FAMILIES[fam]
        city, country, _ = wpick(LOCATIONS)
        if city.startswith("Remote"):
            workplace, office_days = "remote", 0
        else:
            workplace = rnd.choice(["hybrid", "hybrid", "on site"])
            office_days = 5 if workplace == "on site" else rnd.choice([1, 2, 3])
        duties = rnd.sample(F["build"], k=min(len(F["build"]), rnd.choice([0, 1, 2, 3]))) + \
            rnd.sample(F["run"], k=min(len(F["run"]), rnd.choice([1, 2, 3])))
        if fam == "gtm" and rnd.random() < 0.45:
            duties = rnd.sample(F["build"], k=3) + rnd.sample(F["run"], k=rnd.choice([0, 1]))
        langs = []
        if rnd.random() < 0.22:
            langs = ["German C1"] if country == "Germany" else (["Spanish"] if country == "Spain" else ["Dutch"] if country == "Netherlands" else [])
        lo, hi = F["pay"]
        pay = None if rnd.random() < 0.45 else (lambda a: [a, a + rnd.choice([10, 15, 20])])(rnd.randrange(lo, hi, 5))
        pid += 1
        posting = {
            "id": str(pid), "company": c["name"], "title": rnd.choice(F["titles"]), "family": fam,
            "location": city, "country": country, "workplace": workplace, "office_days": office_days,
            "languages_required": langs, "years_required": rnd.choice([2, 3, 3, 4, 5, 6]),
            "pay_k_eur": pay, "employees": c["employees"], "duties": duties,
            "tools": rnd.sample(F["tools"], k=min(len(F["tools"]), rnd.choice([2, 3, 4]))),
            "posted": (TODAY - timedelta(days=rnd.randint(0, 25))).isoformat(),
            "url": ATS_URL[c["ats"]].format(slug=c["slug"], id=pid),
        }
        open_now = rnd.random() < 0.82
        if open_now and lists[c["name"]]["status"] == "works":
            lists[c["name"]]["open_ids"].append(posting["id"])
        # discovery copies: the same posting on one to three boards
        for b in rnd.sample(BOARDS, k=rnd.choice([1, 1, 2, 3])):
            postings.append(dict(posting, source=b))
        # some roles get reposted under a new id; only the new id is on the company list
        if open_now and rnd.random() < 0.1 and lists[c["name"]]["status"] == "works":
            pid += 1
            new = dict(posting, id=str(pid), url=ATS_URL[c["ats"]].format(slug=c["slug"], id=pid),
                       posted=TODAY.isoformat(), source="ATS host search")
            lists[c["name"]]["open_ids"].remove(posting["id"])
            lists[c["name"]]["open_ids"].append(new["id"])
            postings.append(new)

    with open("data/postings.json", "w") as f:
        json.dump(postings, f, indent=1)
    with open("data/company_lists.json", "w") as f:
        json.dump(lists, f, indent=1)

    # application history for the learning loop
    rows = []
    for i in range(60):
        shape = rnd.choice(["build", "build", "run"])
        size = rnd.choice(["under 150", "150 to 500", "over 500"])
        note = rnd.random() < 0.35
        p_call = {"build": 0.32, "run": 0.12}[shape] * {"under 150": 1.2, "150 to 500": 1.0, "over 500": 0.6}[size]
        p_call *= 1.6 if note else 1.0
        r = rnd.random()
        outcome = "call" if r < p_call else ("rejected at CV" if r < p_call + 0.4 else "no reply")
        rows.append({"application": f"P{i + 1:03d}", "role_shape": shape, "company_size": size,
                     "note_to_named_person": "yes" if note else "no", "outcome": outcome})
    with open("data/applications.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(postings)} board copies, {len(companies)} companies, {len(rows)} past applications")


if __name__ == "__main__":
    main()
