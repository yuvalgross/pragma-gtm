"""
Builds a labelled synthetic contact list for the signal outreach builder.

Every row is invented. Company domains end in .example (reserved, never real)
except the personal email row that exists to test the gate. The columns mimic
what a CRM export (status, last touch, opt out) joined with a Clay enrichment
table (title, email status, signals) would hold. Field names are my assumption,
not a copy of a real schema.

Signals are written as type|age_in_days|detail and separated by semicolons.
"""
import csv
import os

COLUMNS = [
    # CRM side
    "contact_id", "first_name", "title", "email", "company_name", "domain",
    "country", "timezone", "headcount", "crm_status", "last_contacted_days", "opted_out",
    # enrichment side (Clay)
    "email_status", "signals",
]

# (first, title, company letter, country, tz, headcount, crm_status, last_touch, opted_out, email_status, signals)
ROWS = [
    ("Lena", "Head of Revenue Operations", "A", "DE", "Europe/Berlin", 140, "none", "", "no", "valid",
     "hiring|9|a first RevOps analyst;tech_change|30|moved from Pipedrive to HubSpot"),
    ("Tom", "VP Sales", "B", "NL", "Europe/Amsterdam", 220, "none", "", "no", "valid",
     "funding|21|Series B in October"),
    ("Sara", "Founder and CEO", "C", "AT", "Europe/Vienna", 18, "none", "", "no", "valid",
     "content|6|leads waiting over the weekend"),
    ("Jonas", "Revenue Operations Manager", "D", "DE", "Europe/Berlin", 90, "none", "", "no", "valid",
     "tech_change|11|moved from Salesforce to HubSpot"),
    ("Mia", "Head of Marketing", "E", "GB", "Europe/London", 60, "none", "", "no", "valid",
     "event|4|the exhibitor list for a Berlin SaaS conference"),
    ("Paul", "Sales Director", "F", "CH", "Europe/Zurich", 310, "none", "", "no", "valid",
     "hiring|13|three account executives"),
    ("Nora", "Chief Revenue Officer", "G", "SE", "Europe/Stockholm", 400, "none", "", "no", "valid",
     "funding|60|Series A last year;event|80|a sponsor slot at a fintech summit"),
    ("Ali", "Marketing Director", "H", "FR", "Europe/Paris", 75, "none", "", "no", "valid",
     "content|10|a free webinar on pipeline hygiene"),
    ("Eva", "VP Revenue Operations", "B", "NL", "Europe/Amsterdam", 220, "none", "", "no", "valid",
     "hiring|17|a RevOps lead"),
    ("Ben", "Co founder", "I", "DE", "Europe/Berlin", 12, "none", "", "no", "valid",
     "funding|35|a pre seed round"),
    ("Clara", "Head of Growth", "J", "ES", "Europe/Madrid", 45, "none", "", "no", "risky",
     "hiring|8|a growth marketer"),
    ("Max", "Office Manager", "K", "DE", "Europe/Berlin", 30, "none", "", "no", "valid",
     "hiring|5|a sales assistant"),
    ("Ida", "Head of Sales", "L", "DK", "Europe/Copenhagen", 150, "none", "", "no", "valid",
     "tech_change|40|added a scheduling tool to their demo page"),
    ("Leo", "Revenue Operations Lead", "M", "IE", "Europe/Dublin", 260, "none", "", "no", "valid",
     "event|12|the speaker list for a RevOps meetup;hiring|20|a sales ops analyst"),
]

GATE_TEST_ROWS = [
    # each of these must be held before any copy is written
    ("Kim", "VP Sales", "customer-one.example", "Customer One", "GB", "Europe/London", 500, "customer", "", "no", "valid", "hiring|3|two SDRs"),
    ("Ron", "Head of RevOps", "open-deal-two.example", "Open Deal Two", "DE", "Europe/Berlin", 80, "open_deal", "", "no", "valid", "funding|10|Series A"),
    ("Ana", "Sales Director", "company-n.example", "Synthetic Company N", "PT", "Europe/Lisbon", 70, "none", "12", "no", "valid", "hiring|6|a sales manager"),
    ("Jan", "VP Marketing", "company-o.example", "Synthetic Company O", "BE", "Europe/Brussels", 120, "none", "", "yes", "valid", "event|7|a sponsor slot at a SaaS summit"),
    ("Eli", "Head of Sales", "company-p.example", "Synthetic Company P", "PL", "Europe/Warsaw", 95, "none", "", "no", "invalid", "hiring|9|an SDR team lead"),
    ("Dan", "Founder", "gmail.com", "", "DE", "Europe/Berlin", 0, "none", "", "no", "valid", "content|4|outbound reply rates"),
]


def main(path="data/contacts_synthetic.csv"):
    out = []
    for i, r in enumerate(ROWS, start=1):
        first, title, letter, country, tz, hc, crm, touch, opt, status, signals = r
        domain = f"company-{letter.lower()}.example"
        out.append([f"con-{i:03d}", first, title, f"{first.lower()}@{domain}",
                    f"Synthetic Company {letter}", domain, country, tz, hc, crm, touch, opt, status, signals])
    for j, r in enumerate(GATE_TEST_ROWS, start=len(ROWS) + 1):
        first, title, domain, company, country, tz, hc, crm, touch, opt, status, signals = r
        out.append([f"con-{j:03d}", first, title, f"{first.lower()}@{domain}",
                    company, domain, country, tz, hc, crm, touch, opt, status, signals])
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(out)
    print(f"wrote {len(out)} synthetic rows to {path}")


if __name__ == "__main__":
    main()
