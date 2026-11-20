"""
Builds a labelled synthetic export of one week of product trial signups.

Every row is invented. Work domains end in .example (reserved, never real);
personal email rows use public webmail domains so the gate has something to drop.

The week has three layers:
  - 17 hand built accounts that exercise every scoring rule,
  - a generated long tail: most trial signups never integrate or stop after a
    few test calls, which is the normal shape of a self serve funnel,
  - gate rows: personal email signups (roughly a quarter to a third of signups
    in a self serve product) and users from existing customers and partners. Columns up to integration_path
mimic what a product database and an analytics tool would hold; the columns
after it mimic what a Clay enrichment table would add. Both are assumptions
about field names, not a copy of a real schema.
"""
import csv
import os
import random

random.seed(20261025)

COLUMNS = [
    # product side
    "account_id", "domain", "email_type", "signup_date",
    "volume_w1", "volume_w2", "volume_w3", "volume_w4",
    "products_used", "integration_path",
    # enrichment side (Clay)
    "company_name", "hq_city", "country", "headcount", "category",
    "last_funding_months_ago", "pain_signals", "existing_tool", "hosting",
]

# (company_name, city, country, headcount, category, funding_months, path, products, volume, pain, tool, hosting)
ROWS = [
    ("Synthetic Company A", "Berlin", "DE", 120, "core_segment", 9, "direct_api", "core_a;addon_x", (18000, 24000, 31000, 39000), "job:specialist role;docs:technical need", "incumbent", "self"),
    ("Synthetic Company B", "Amsterdam", "NL", 300, "core_segment", 14, "open_framework", "core_b", (52000, 51000, 53000, 52000), "blog:public problem statement", "none", "cloud"),
    ("Synthetic Company C", "Austin", "US", 60, "core_segment", 22, "self_hosted", "core_b;addon_y", (9000, 12000, 15000, 17000), "blog:public problem statement", "none", "cloud"),
    ("Synthetic Company D", "Munich", "DE", 25, "core_segment", 6, "direct_api", "core_a", (3000, 3200, 3100, 3400), "", "none", "cloud"),
    ("Synthetic Company E", "London", "GB", 15, "other", 40, "partner_marketplace", "core_a", (4000, 6000, 8000, 11000), "", "none", "cloud"),
    ("Synthetic Company F", "Vienna", "AT", 80, "core_segment", 30, "reseller_channel", "core_b", (20000, 22000, 21000, 25000), "job:specialist role", "none", "unknown"),
    ("Synthetic Company G", "Zurich", "CH", 450, "core_segment", 11, "direct_api", "core_b;addon_y;addon_x", (14000, 19000, 26000, 33000), "job:specialist role;job:second hire;blog:public problem statement", "inhouse", "self"),
    ("Synthetic Company H", "Paris", "FR", 700, "other", 5, "direct_api", "core_a", (1000, 900, 1100, 1000), "", "none", "cloud"),
    ("Synthetic Company I", "Lisbon", "PT", 2, "other", 99, "direct_api", "core_a", (200, 150, 300, 100), "", "none", "unknown"),
    ("Synthetic Company J", "Hamburg", "DE", 140, "core_segment", 16, "open_framework", "core_b;addon_y", (7000, 7500, 9000, 12000), "job:specialist role;docs:technical need", "none", "cloud"),
    ("Synthetic Company K", "Chicago", "US", 35, "core_segment", 8, "partner_marketplace", "core_b;addon_y", (15000, 21000, 28000, 36000), "blog:public problem statement", "none", "cloud"),
    ("Synthetic Company L", "Dublin", "IE", 48, "core_segment", 24, "direct_api", "core_a", (2500, 2400, 2600, 2500), "", "incumbent", "cloud"),
    ("Synthetic Company M", "Aachen", "DE", 12, "other", 99, "direct_api", "core_b;addon_y;addon_x", (600, 800, 400, 900), "", "none", "self"),
    ("Synthetic Company N", "Madrid", "ES", 220, "core_segment", 20, "direct_api", "core_b", (30000, 29000, 31000, 30000), "job:specialist role", "incumbent", "cloud"),
    ("Synthetic Company O", "Stuttgart", "DE", 900, "other", 99, "direct_api", "core_a;addon_z", (5000, 5500, 7000, 9000), "job:specialist role", "inhouse", "self"),
    ("Synthetic Company P", "Toronto", "CA", 9, "core_segment", 4, "partner_marketplace", "core_a", (800, 1200, 1900, 2600), "", "none", "cloud"),
    ("Synthetic Company Q", "Barcelona", "ES", 65, "core_segment", 13, "reseller_channel", "core_b;addon_x", (11000, 13000, 12000, 16000), "docs:technical need", "none", "cloud"),
]

GATE_TEST_ROWS = [
    # an existing customer, a partner and a personal email: all three must be dropped before scoring
    ("Customer One", "London", "GB", 300, "core_segment", 12, "direct_api", "core_b", (40000, 42000, 41000, 43000), "", "none", "self", "customer-one.example", "work"),
    ("Partner Two", "San Francisco", "US", 60, "core_segment", 10, "direct_api", "core_b;addon_y", (25000, 26000, 27000, 28000), "", "none", "cloud", "partner-two.example", "work"),
    ("", "", "", 0, "", 0, "direct_api", "core_a", (300, 500, 200, 400), "", "none", "unknown", "gmail.com", "personal"),
]


LONG_TAIL = 210          # work email signups beyond the hand built rows
PERSONAL = 88            # personal email signups
PERSONAL_DOMAINS = ["gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "icloud.com",
                    "proton.me", "gmx.de", "web.de"]
CITIES = [("Berlin", "DE"), ("Munich", "DE"), ("Hamburg", "DE"), ("Amsterdam", "NL"), ("Paris", "FR"),
          ("London", "GB"), ("Madrid", "ES"), ("Warsaw", "PL"), ("Stockholm", "SE"), ("Milan", "IT"),
          ("New York", "US"), ("Austin", "US"), ("Toronto", "CA"), ("Bangalore", "IN"), ("Sao Paulo", "BR")]


def long_tail_row(n):
    """One generated work email signup. Most never integrate; some test a little."""
    city, country = random.choice(CITIES)
    hc = random.choices([random.randint(1, 10), random.randint(11, 50), random.randint(51, 500),
                         random.randint(501, 5000)], weights=[45, 30, 20, 5])[0]
    cat = "core_segment" if random.random() < 0.35 else "other"
    fund = random.randint(3, 40) if random.random() < 0.35 else 99
    stage = random.choices(["never", "tested", "partner"], weights=[55, 33, 12])[0]
    if stage == "never":
        path_, products, vols = "", "core_a", (0, 0, 0, 0)
    else:
        path_ = (random.choice(["partner_marketplace", "reseller_channel"]) if stage == "partner"
                 else random.choices(["direct_api", "open_framework", "self_hosted"], weights=[60, 30, 10])[0])
        products = random.choice(["core_a", "core_b"])
        base = random.randint(20, 1500)
        shape = random.choices(["stop", "flat", "grow"], weights=[50, 35, 15])[0]
        if shape == "stop":
            vols = (base, base // 3, random.randint(0, base // 10), 0)
        elif shape == "flat":
            vols = tuple(max(0, int(base * random.uniform(0.85, 1.15))) for _ in range(4))
        else:
            vols = tuple(int(base * f) for f in (1, 1.3, 1.7, 2.2))
    pain = random.choice(["job:specialist role", "docs:technical need"]) if random.random() < 0.08 else ""
    tool = random.choices(["none", "incumbent", "inhouse"], weights=[85, 10, 5])[0]
    hosting = random.choice(["cloud", "cloud", "self", "unknown"])
    name = f"Synthetic Signup {n:03d}"
    return (name, city, country, hc, cat, fund, path_, products, vols, pain, tool, hosting)


def main(path="data/signups_week_43_synthetic.csv"):
    rows = list(ROWS) + [long_tail_row(n) for n in range(1, LONG_TAIL + 1)]
    out = []
    for i, r in enumerate(rows, start=1):
        name, city, country, hc, cat, fund, path_, products, vols, pain, tool, hosting = r
        slug = name.lower().replace("synthetic ", "").replace(" ", "-")
        out.append([
            f"syn-{i:03d}", f"{slug}.example", "work", f"2026-10-{19 + (i % 6):02d}",
            *vols, products, path_,
            name, city, country, hc, cat, fund, pain, tool, hosting,
        ])
    gate_rows = list(GATE_TEST_ROWS[:2]) + [
        # a second user from the existing customer signs up for a trial: still a customer
        ("Customer One", "London", "GB", 300, "core_segment", 12, "direct_api", "core_a", (500, 800, 600, 900), "", "none", "self", "customer-one.example", "work"),
    ]
    for k in range(PERSONAL):
        vols = (0, 0, 0, 0) if random.random() < 0.7 else tuple(random.randint(0, 600) for _ in range(4))
        gate_rows.append(("", "", "", 0, "", 0, random.choice(["direct_api", ""]), "core_a", vols, "", "none",
                          "unknown", random.choice(PERSONAL_DOMAINS), "personal"))
    for j, r in enumerate(gate_rows, start=len(rows) + 1):
        name, city, country, hc, cat, fund, path_, products, vols, pain, tool, hosting, domain, etype = r
        out.append([
            f"syn-{j:03d}", domain, etype, "2026-10-21",
            *vols, products, path_,
            name, city, country, hc, cat, fund, pain, tool, hosting,
        ])
    random.shuffle(out)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(out)
    print(f"wrote {len(out)} synthetic rows to {path}")


if __name__ == "__main__":
    main()
