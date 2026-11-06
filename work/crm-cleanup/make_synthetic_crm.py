"""
Builds a synthetic HubSpot export: owners, companies, contacts and deals.

Every company, person and domain is invented. Domains end in .example
(reserved, never real). The mess is planted on purpose so each agent in
crm_cleanup.py has something to find:

  * duplicate companies: same domain written two ways, same name with no
    domain, same name on two different domains, ARR split across two records
  * duplicate contacts: one email in two cases
  * country written five different ways
  * lifecycle stage that contradicts the deals
  * open deals whose close date passed months ago, deals with no amount
  * records owned by people who left
  * customers from about EUR 950k a year down to EUR 12 a year, with usage,
    seats, renewal date and the last time a human spoke to them

    python3 make_synthetic_crm.py            # writes data/*.csv
"""
import csv
import os

OWNERS = [
    # owner_id, name, role, territory, active
    ("o1", "Owner One", "AE", "DACH", "true"),
    ("o2", "Owner Two", "AE", "UKI", "true"),
    ("o3", "Owner Three", "AE", "Benelux and France", "true"),
    ("o4", "Owner Four", "AE", "Nordics", "false"),
    ("o5", "Owner Five", "AE", "DACH", "false"),
    ("o6", "Owner Six", "AM", "All", "true"),
    ("o7", "Owner Seven", "AE", "Nordics", "true"),
    ("o8", "Owner Eight", "AM", "All", "false"),
]

# company_id, name, domain, country, industry, lifecycle, owner, created,
# arr_eur, renewal, usage_m1, usage_m2, usage_m3, seats_used, seats_limit, last_human_touch
COMPANIES = [
    # customers, largest to the long tail
    ("c101", "Synthetic Fleet Systems GmbH", "synfleet.example", "Germany", "Logistics", "customer", "o6", "2019-03-04", 950000, "2027-01-15", 41000, 38000, 29000, 820, 1000, "2026-07-02"),
    ("c102", "Synthetic Grid Energy AG", "syngrid.example", "DE", "Energy", "customer", "o8", "2018-11-20", 420000, "2027-06-30", 18000, 21000, 26500, 470, 500, "2026-10-12"),
    ("c103", "Synthetic Rail Data Ltd", "synrail.example", "United Kingdom", "Transport", "customer", "o6", "2020-05-11", 180000, "2026-12-20", 9000, 9100, 8900, 210, 400, "2026-06-01"),
    ("c104", "Synthetic Cold Chain BV", "syncold.example", "NL", "Logistics", "customer", "o6", "2021-02-17", 120000, "2027-09-01", 5000, 6200, 7400, 95, 100, "2026-09-20"),
    ("c105", "Harbor Sensors B.V.", "harborsensors.example", "Netherlands", "Maritime", "customer", "o3", "2020-08-09", 60000, "2027-03-31", 3000, 3100, 3050, 60, 120, "2026-10-01"),
    ("c106", "Harbor Sensors", "http://harborsensors.example", "Holland", "", "customer", "o4", "2023-01-23", 15000, "2027-03-31", 0, 0, 0, 0, 0, ""),
    ("c107", "Synthetic Smart Meter Oy", "synmeter.example", "Finland", "Energy", "customer", "o4", "2021-06-30", 75000, "2026-12-31", 6000, 4800, 3900, 70, 200, "2026-05-14"),
    ("c108", "Synthetic Agri Track SAS", "synagri.example", "France", "Agriculture", "opportunity", "o3", "2022-03-03", 40000, "2027-04-30", 2000, 2600, 3300, 38, 40, "2026-08-08"),
    ("c109", "Synthetic Bike Share GmbH", "synbike.example", "Deutschland", "Mobility", "customer", "", "2022-07-14", 28000, "2027-02-28", 2400, 2300, 2350, 30, 60, "2026-03-03"),
    ("c110", "Synthetic Vending Ltd", "synvend.example", "UK", "Retail", "customer", "o2", "2023-04-01", 15000, "2027-07-31", 900, 1300, 1800, 18, 20, "2026-09-02"),
    ("c111", "Synthetic Parking ApS", "synpark.example", "Denmark", "Mobility", "customer", "o4", "2023-09-19", 9000, "2027-01-31", 800, 600, 450, 9, 25, ""),
    ("c112", "Synthetic Pet Tracker GmbH", "synpet.example", "germany", "Consumer", "customer", "o1", "2024-01-10", 6000, "2027-05-31", 300, 450, 700, 10, 10, "2026-01-20"),
    ("c113", "Synthetic Alarm Box Ltd", "synalarm.example", "Great Britain", "Security", "customer", "o2", "2024-03-15", 3000, "2027-03-15", 200, 210, 190, 4, 10, ""),
    ("c114", "Synthetic Water Sensor SL", "synwater.example", "Spain", "Utilities", "customer", "o3", "2024-06-01", 1200, "2027-06-01", 80, 60, 40, 2, 5, ""),
    ("c115", "Synthetic Garden Pump BV", "synpump.example", "Netherlands", "Consumer", "customer", "o5", "2024-11-11", 600, "2026-12-10", 30, 30, 32, 1, 5, ""),
    ("c116", "Synthetic Beehive Monitor", "synbee.example", "Austria", "Agriculture", "customer", "o5", "2025-02-02", 240, "2027-02-02", 10, 14, 22, 1, 1, ""),
    ("c117", "Synthetic Kiosk Display", "synkiosk.example", "Belgium", "Retail", "customer", "o3", "2025-05-05", 90, "2027-05-05", 5, 5, 4, 1, 2, ""),
    ("c118", "Synthetic Hobby Drone", "syndrone.example", "Ireland", "Consumer", "customer", "", "2025-08-08", 12, "2026-11-30", 1, 1, 0, 1, 1, ""),
    # says customer, but no closed won deal and no ARR
    ("c119", "Synthetic Port Cranes AB", "syncranes.example", "Sweden", "Maritime", "customer", "o7", "2021-10-10", 0, "", 0, 0, 0, 0, 0, "2025-02-11"),
    # prospects and the duplicates that hide among them
    ("c201", "Synthetic Logistics GmbH", "synlogistics.example", "Germany", "Logistics", "opportunity", "o1", "2025-03-01", 0, "", 0, 0, 0, 0, 0, ""),
    ("c202", "Synthetic Logistics", "https://www.synlogistics.example/", "DE", "", "lead", "o5", "2026-02-14", 0, "", 0, 0, 0, 0, 0, ""),
    ("c203", "Nordwind Fleet AB", "nordwind.example", "Sweden", "Logistics", "opportunity", "o7", "2025-09-09", 0, "", 0, 0, 0, 0, 0, ""),
    ("c204", "Nordwind Fleet", "", "Sweden", "", "lead", "o4", "2026-04-04", 0, "", 0, 0, 0, 0, 0, ""),
    ("c205", "Acme Metering Ltd", "acme-metering.example", "UK", "Energy", "lead", "o2", "2025-11-01", 0, "", 0, 0, 0, 0, 0, ""),
    ("c206", "ACME Metering", "acmemetering.example", "United Kingdom", "Energy", "lead", "o2", "2026-06-06", 0, "", 0, 0, 0, 0, 0, ""),
    ("c207", "Synthetic Tank Level GmbH", "syntank.example", "Germany", "Energy", "opportunity", "o1", "2025-12-12", 0, "", 0, 0, 0, 0, 0, ""),
    ("c208", "Synthetic Asset Tag SARL", "synasset.example", "France", "", "opportunity", "o3", "2026-01-15", 0, "", 0, 0, 0, 0, 0, ""),
    ("c209", "Synthetic Fleet Cam Ltd", "synfleetcam.example", "Ireland", "Transport", "lead", "o2", "2026-05-20", 0, "", 0, 0, 0, 0, 0, ""),
    ("c210", "Synthetic Smart Lock AS", "synlock.example", "Norway", "", "lead", "o4", "2026-03-03", 0, "", 0, 0, 0, 0, 0, ""),
    ("c211", "Synthetic EV Charge GmbH", "synev.example", "Germany", "Mobility", "opportunity", "o1", "2025-10-01", 0, "", 0, 0, 0, 0, 0, ""),
    ("c212", "Synthetic Container Track BV", "syncontainer.example", "NL", "Maritime", "opportunity", "o3", "2025-07-07", 0, "", 0, 0, 0, 0, 0, ""),
    ("c213", "Synthetic Med Fridge GmbH", "synfridge.example", "Germany", "Healthcare", "opportunity", "o1", "2026-02-02", 0, "", 0, 0, 0, 0, 0, ""),
    ("c214", "Synthetic Scooter Oy", "synscooter.example", "Finland", "Mobility", "lead", "o4", "2026-08-08", 0, "", 0, 0, 0, 0, 0, ""),
]

# contact_id, company_id, email, first, last, job_title, bounced
CONTACTS = [
    ("p01", "c101", "ops.lead@synfleet.example", "Ada", "Example", "Head of Operations", "false"),
    ("p02", "c101", "it.lead@synfleet.example", "Ben", "Example", "IT Lead", "false"),
    ("p03", "c102", "cto@syngrid.example", "Cara", "Example", "CTO", "false"),
    ("p04", "c103", "head.data@synrail.example", "Dan", "Example", "Head of Data", "false"),
    ("p05", "c104", "coo@syncold.example", "Eli", "Example", "COO", "false"),
    ("p06", "c105", "iot@harborsensors.example", "Fay", "Example", "IoT Manager", "false"),
    ("p07", "c106", "IoT@HarborSensors.example", "Fay", "Example", "", "false"),
    ("p08", "c107", "product@synmeter.example", "Gus", "Example", "Product Lead", "false"),
    ("p09", "c107", "old.champion@synmeter.example", "Hal", "Example", "Engineering Manager", "true"),
    ("p10", "c108", "founder@synagri.example", "Ida", "Example", "Founder", "false"),
    ("p11", "c109", "fleet@synbike.example", "Jon", "Example", "Fleet Manager", "false"),
    ("p12", "c110", "ops@synvend.example", "Kai", "Example", "Operations", "false"),
    ("p13", "c111", "cto@synpark.example", "Lea", "Example", "CTO", "true"),
    ("p14", "c112", "hello@synpet.example", "Max", "Example", "Founder", "false"),
    ("p15", "c113", "admin@synalarm.example", "Nia", "Example", "Admin", "false"),
    ("p16", "c201", "procurement@synlogistics.example", "Oli", "Example", "Procurement", "false"),
    ("p17", "c202", "Procurement@SynLogistics.example", "Oli", "Example", "Procurement Manager", "false"),
    ("p18", "c203", "cto@nordwind.example", "Pia", "Example", "CTO", "false"),
    ("p19", "c205", "energy@acme-metering.example", "Quinn", "Example", "Energy Manager", "false"),
    ("p20", "c207", "ceo@syntank.example", "Ria", "Example", "CEO", "false"),
    ("p21", "c211", "partnerships@synev.example", "Sam", "Example", "Partnerships", "false"),
    ("p22", "c212", "it@syncontainer.example", "Tom", "Example", "IT Manager", "false"),
    ("p23", "c213", "ops@synfridge.example", "Uma", "Example", "Operations", "false"),
    ("p24", "c119", "buyer@syncranes.example", "Vic", "Example", "Buyer", "true"),
]

# deal_id, company_id, name, stage, amount_eur, close_date, owner
DEALS = [
    ("d01", "c101", "Fleet renewal 2026", "closedwon", 950000, "2026-01-15", "o6"),
    ("d02", "c102", "Grid expansion", "closedwon", 420000, "2025-06-30", "o8"),
    ("d03", "c103", "Rail data platform", "closedwon", 180000, "2025-12-20", "o6"),
    ("d04", "c104", "Cold chain rollout", "closedwon", 120000, "2025-09-01", "o6"),
    ("d05", "c105", "Harbor sensors year 1", "closedwon", 60000, "2025-03-31", "o3"),
    ("d06", "c106", "Harbor add on", "closedwon", 15000, "2025-03-31", "o4"),
    ("d07", "c107", "Smart meter pilot to rollout", "closedwon", 75000, "2025-12-31", "o4"),
    ("d08", "c108", "Agri track", "closedwon", 40000, "2025-04-30", "o3"),
    ("d09", "c109", "Bike share", "closedwon", 28000, "2025-02-28", "o5"),
    ("d10", "c110", "Vending", "closedwon", 15000, "2025-07-31", "o2"),
    ("d11", "c201", "Synthetic Logistics pilot", "contractsent", 85000, "2026-07-31", "o1"),
    ("d12", "c202", "Logistics inbound", "appointmentscheduled", 0, "2026-12-15", "o5"),
    ("d13", "c203", "Nordwind fleet", "qualifiedtobuy", 60000, "2026-05-30", "o7"),
    ("d14", "c207", "Tank level", "presentationscheduled", 30000, "2026-12-20", "o1"),
    ("d15", "c208", "Asset tag", "decisionmakerboughtin", 0, "2026-06-15", "o3"),
    ("d16", "c211", "EV charge", "contractsent", 110000, "2026-11-28", "o1"),
    ("d17", "c212", "Container track", "qualifiedtobuy", 45000, "2026-03-31", "o3"),
    ("d18", "c213", "Med fridge", "appointmentscheduled", 22000, "2026-12-31", "o1"),
    ("d19", "c210", "Smart lock", "appointmentscheduled", 0, "2026-02-28", "o4"),
    ("d20", "c102", "Grid phase 2", "qualifiedtobuy", 150000, "2027-02-28", "o8"),
    ("d21", "c112", "Pet tracker", "closedwon", 6000, "2025-05-31", "o1"),
    ("d22", "c113", "Alarm box", "closedwon", 3000, "2025-03-15", "o2"),
]


def write(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main(out="data"):
    os.makedirs(out, exist_ok=True)
    write(os.path.join(out, "owners.csv"), ["owner_id", "name", "role", "territory", "active"], OWNERS)
    write(os.path.join(out, "companies.csv"),
          ["company_id", "name", "domain", "country", "industry", "lifecycle_stage", "owner_id", "created",
           "arr_eur", "renewal_date", "usage_m1", "usage_m2", "usage_m3", "seats_used", "seats_limit",
           "last_human_touch"], COMPANIES)
    write(os.path.join(out, "contacts.csv"),
          ["contact_id", "company_id", "email", "first_name", "last_name", "job_title", "bounced"], CONTACTS)
    write(os.path.join(out, "deals.csv"),
          ["deal_id", "company_id", "deal_name", "stage", "amount_eur", "close_date", "owner_id"], DEALS)
    print(f"wrote {len(OWNERS)} owners, {len(COMPANIES)} companies, {len(CONTACTS)} contacts, {len(DEALS)} deals to {out}/")


if __name__ == "__main__":
    main()
