# Signup router

Decides which product trial signups get a human this week and what that human does first. Adapted from a take home exercise I built in October 2026. Company, product and customer names are removed and every input is synthetic.

## Run it

```
python3 make_synthetic_signups.py                       # writes data/signups_week_43_synthetic.csv
python3 signup_router.py data/signups_week_43_synthetic.csv --out output
```

Standard library only. Output lands in `output/`: `scored.csv` (every account that passed the gate, ranked, with the evidence for each score), `excluded.csv` (what the gate dropped and why), `top5.md` and `summary.json`.

## What it does

1. Gate first. Existing customers, partners and personal email domains are dropped before any scoring and logged with the reason. Exclusions are a gate, never a weight.
2. Score 0 to 100: usage 35 (week over week trend, last week's volume, an add on used alongside the core product), company 25 (core segment, 20 to 500 staff, funded in the last 18 months), integration 25 (direct, open framework and self hosted get full marks; marketplace and reseller paths get a quarter because a partner already sells to them), pain signals 15 (job posts, docs or blog posts that name the problem; an incumbent tool already in the product counts as a warm displacement signal).
3. One next action per account. Above 70 with rising volume: custom benchmark and an enterprise conversation. 45 to 70: mid tier offer and a shared Slack channel. Below 45: nurture. Marketplace and reseller accounts go to the partner owner instead.

## What is real and what is not

The input is synthetic. Every domain ends in `.example` except one personal email row that tests the gate. The column names are my assumption of what a product database and a Clay enrichment table would hold. In production Clay would fill the enrichment columns; here they are typed in. The step that writes one HubSpot task per top row, with the evidence in the body, via n8n, is designed and not part of this script.

## Changes from the original

Fields are renamed and one audio specific configuration check is removed. I ran the original and this version on the same 17 accounts: every usage, company, integration and pain score and every total is identical.

## What AI did and what I checked

Claude Code wrote both scripts from my written description of the gate, weights and thresholds. I set the weights and thresholds, wrote the exclusion rules, read every row of `scored.csv` against the input to check the arithmetic, and capped pain signals at 15 so that no account clears the mid tier line on a keyword match alone.
