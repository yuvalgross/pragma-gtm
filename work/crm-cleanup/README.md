# CRM clean up

Four agents read a HubSpot export. Three clean it (duplicates, fields, owners). The fourth reads the clean customer book and decides who a human calls this week and who an AI looks after. Nothing is written to the CRM: the script writes a change log and the HubSpot API calls, and a person approves them.

## Run it

```
python3 make_synthetic_crm.py                  # writes data/*.csv
python3 crm_cleanup.py data --out output       # as of 2026-11-06 by default
python3 -m unittest test_crm_cleanup           # 8 tests on the rules
```

Standard library only.

## Outputs

- `output/changes.csv` every proposed change with its tier (auto, approve, review, owner_task, enrich) and the reason
- `output/book.csv` every customer with ARR tier, signal, channel (human or AI) and the evidence
- `output/call_list.md` who a human calls next
- `output/hubspot_payloads.json` the CRM v3 calls a person would approve; never sent
- `output/summary.json` counts and money figures

## What is real

The input is synthetic. Every domain ends in `.example`, and names, ARR, usage and dates are invented to exercise the rules. Thresholds and tiers are set by hand at the top of `crm_cleanup.py`. The 25% upsell share is an assumption.

Designed, not running: the Claude step that judges name only duplicates and the one that writes long tail emails (prompts are in the file), enrichment for missing fields and bounced contacts, the Slack approval, and the step that sends the API calls.
