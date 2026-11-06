# CRM clean up

Four agents read a HubSpot export. Three clean it (duplicates, fields, owners). The fourth reads the clean customer book and decides who a human calls this week and who an AI looks after. Nothing is written to the CRM: the script writes a change log and the HubSpot API calls, and a person approves them.

## Run it

```
python3 make_synthetic_crm.py                  # writes data/*.csv
python3 crm_cleanup.py data --out output
python3 -m unittest test_crm_cleanup           # 8 tests on the rules
```

Standard library only.

## Outputs

- `output/changes.csv` every proposed change with its tier (auto, approve, review, owner_task, enrich) and the reason
- `output/book.csv` every customer with ARR tier, signal, channel (human or AI) and the evidence
- `output/call_list.md` who a human calls next
- `output/hubspot_payloads.json` the CRM v3 calls a person would approve; never sent
- `output/clay_enrich_queue.csv` the enrich tier, keyed by domain or email for a Clay Audiences import
- `output/summary.json` counts and money figures

## What is real

The input is synthetic. Every domain ends in `.example`, and names, ARR, usage and dates are invented to exercise the rules. Thresholds and tiers are set by hand at the top of `crm_cleanup.py`. The 25% upsell share is an assumption.

Designed, not running: the Claude step that judges name only duplicates and the one that writes long tail emails (prompts are in the file), Clay Audiences segments, signals and CLI enrichment (HubSpot sync into Audiences is import only, so writes stay with the approved API calls), the Slack approval, and the step that sends the API calls.
