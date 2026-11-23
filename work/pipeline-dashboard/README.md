# Pipeline dashboard

A revenue dashboard that puts the 12 months before a signal based outbound engine next to the 12 months after.

**Live page:** [pragma-gtm.com/work/pipeline-dashboard](https://pragma-gtm.com/work/pipeline-dashboard/)
**Live dashboard (Hex, view only):** [open in Hex](https://app.hex.tech/01a205b9-5be0-766a-881e-3b8017cffaa9/app/01a205d2-2e2e-75bc-879d-a85607f2d561/latest)

## What it shows

| Number | Value |
| --- | --- |
| Won revenue, 12 months | €295k before, €390k after (+32%) |
| Close rate | 40% signal led, 12% generic outreach |
| MQL rate | 20.0% before, 28.4% after (+42%) |
| Days to win | 36 signal led, 57 generic |

## How it fits together

0. **Clay company search** finds live buying signals on the ICP: hiring for sales, headcount growth, a new sales leader. Saved as `clay_signals` (24 real companies in corporate learning and HR tech, public company data, no people).
1. **Supabase Postgres**, schema `analytics`: `clay_signals`, `demo_deals`, `demo_contacts`, `demo_companies`, `apollo_sequences`.
2. **A dedicated database user for Hex** that sees the `analytics` schema only. The app's own tables, which hold personal data, are out of its reach.
3. **Hex**: five SQL cells, Plotly charts, a public app with the code hidden.
4. **This page**: the same aggregates (`data/dashboard.json`) drawn as inline SVG, so it stays sharp and follows the site's light and dark theme.

## What is real

- `demo_deals`, `demo_contacts`, `demo_companies`: **synthetic**. Calibrated to mirror results published on pragma-gtm.com: exact closed and won counts per period and lead source, won amounts scaled to total exactly €295k and €390k, and an MQL count that gives exactly +42%. Every deal, company and person is invented.
- `clay_signals`: **real** companies from Clay company search, captured 23 Nov 2026. Public company data only (name, domain, location, size), no people or contact data. Shown as prospects, not customers.
- `apollo_sequences`: **real**, aggregate Apollo sequence stats (delivered, opened, replied, demoed). Sequence names are replaced with a description of the audience and the steps. No contacts, no company names.

## Files

| File | What it is |
| --- | --- |
| `queries.sql` | Every query behind the dashboard, and the grants for the Hex database user |
| `data/dashboard.json` | The aggregates the page charts are drawn from (snapshot, November 2026) |
| `index.html` | The work sample page |

All deals, contacts and demo companies in this folder are invented. The only real companies are the Clay signal accounts, shown as prospects from public data. Nothing here describes a real person.
