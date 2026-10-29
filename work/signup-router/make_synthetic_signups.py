"""
Builds a labelled synthetic export of one week of product trial signups.

Every row is invented. Domains end in .example (reserved, never real) except the
personal email row that exists to test the gate. Columns up to integration_path
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


def main(path="data/signups_week_43_synthetic.csv"):
    out = []
    for i, r in enumerate(ROWS, start=1):
        name, city, country, hc, cat, fund, path_, products, vols, pain, tool, hosting = r
        slug = name.lower().replace("synthetic ", "").replace(" ", "-")
        out.append([
            f"syn-{i:03d}", f"{slug}.example", "work", f"2026-10-{19 + (i % 6):02d}",
            *vols, products, path_,
            name, city, country, hc, cat, fund, pain, tool, hosting,
        ])
    for j, r in enumerate(GATE_TEST_ROWS, start=len(ROWS) + 1):
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
