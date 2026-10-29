# Signal outreach builder

Turns an enriched contact list into a ready to import three step email sequence, written from each contact's freshest buying signal, and holds back everyone who should not get it. Built in October 2026 as a portfolio sample. Every contact, company and signal is invented.

## Run it

```
python3 make_synthetic_contacts.py                                   # writes data/contacts_synthetic.csv
python3 signal_outreach.py data/contacts_synthetic.csv --out output --start 2026-11-02
```

Standard library only (Python 3.9 or later for zoneinfo). Output lands in `output/`: `ready.csv` (one row per contact with subject, three email bodies and send times, in a shape a sequencer can import), `review.csv` (copy that failed a check and needs a person), `held.csv` (who was stopped and why), `preview.md` and `summary.json`.

## What it does

1. Gate first. Opt outs, existing customers, open deals and partners, anyone touched in the last 30 days, invalid or missing email status, personal domains, and titles that match none of the four personas are held with the reason. No copy is written for them.
2. Pick the signal. Hiring and CRM changes weigh 3, funding, events and posts weigh 2. Signals up to 21 days old count in full, 22 to 45 days at half, older ones not at all. Each extra fresh signal adds a point. Below 2 the contact goes to nurture: generic copy is never sent.
3. Write the sequence from fixed templates: an opener built on the signal, one line for the persona, one question as the ask. Follow ups three and eight business days later.
4. Check the copy: step 1 under 90 words, subject under seven words, no leftover placeholders, no banned phrases, no spam words, at most one link. A risky (catch all) email also goes to review. Anything that fails goes to a person, not to the sender.
5. Schedule: strongest signal first, one new contact per company per day, 30 new contacts per mailbox per day, weekdays only, 08:30 in the contact's own time zone.

## What is real and what is not

The input is synthetic. Every domain ends in `.example` except one personal email row that tests the gate. Column names are my assumption of what a CRM export joined with a Clay table would hold; here the enrichment columns are typed in. The offer in the emails (lead routing) is a placeholder product so the copy reads like a real sequence. Pushing `ready.csv` into a sequencer through n8n, and handling replies, are designed and not part of this script.

## What AI did and what I checked

Claude Code wrote both scripts and a first draft of the email lines. The gate rules, weights, freshness window and copy limits are mine. I read every email in `ready.csv` against its input row before publishing.
