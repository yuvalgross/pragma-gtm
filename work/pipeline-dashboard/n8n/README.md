# HubSpot to Supabase sync (n8n)

`hubspot-to-supabase.json` is an n8n workflow that refreshes the dashboard from a CRM.

**Status: tested locally on sample data, not yet run against a real HubSpot account.**

What was actually run (27 Nov 2026, n8n 2.x on a laptop-class sandbox): the workflow imported cleanly and executed end to end with four HubSpot-shaped sample deals and a mock Supabase endpoint. The upsert sent all four rows with the right headers (`Content-Profile: analytics`, `Prefer: resolution=merge-duplicates`, `apikey`) and the mapped fields matched what I expected (`n8n/test/run.js`). With a wrong key the mock returned 401 and the run took the error output to the alert node. The run also caught two bugs in my first draft (n8n blocks `$env` in nodes by default, and an error item slipped through the success check), both fixed.

What has not been run: the HubSpot node and the Slack node (no account connected from where I tested), and a real Supabase write.

## What it does

1. Runs nightly at 02:00.
2. Pulls every deal from HubSpot (name, amount, stage, created, closed, lead source).
3. Maps each deal to the columns of `analytics.demo_deals`, so every query in `queries.sql` works unchanged: `lead_source`, `is_closed`, `is_won`, `amount_eur`, `days_to_close`, `period`.
4. Upserts into `analytics.deals` on `hubspot_id`, so a rerun never duplicates a deal.
5. A failed write goes to the error output and posts to Slack.

## To run it

1. In HubSpot, use a free developer test account (or sandbox) and add a deal property `lead_source` with the values `REFERRAL`, `SIGNAL`, `INBOUND`, `GENERIC`.
2. Create the table in Supabase:

```sql
create table if not exists analytics.deals (
  hubspot_id text primary key,
  lead_source text not null,
  is_closed boolean not null,
  is_won boolean not null,
  amount_eur numeric not null default 0,
  days_to_close integer,
  period text not null,
  synced_at timestamptz not null default now()
);
```

3. In n8n add a HubSpot credential, a Slack credential, and a Header Auth credential with name `apikey` and your Supabase secret key as the value. Replace `YOUR-PROJECT-REF` in the HTTP node URL.
4. Import the JSON, run it once by hand, then check the row count in `analytics.deals` against HubSpot.
5. Point the five queries at `analytics.deals` instead of `analytics.demo_deals`.

`GO_LIVE` in the Code node (default 2025-11-01) splits Before and After signals.

## Local test

```bash
node test/run.js                 # mapping against test/hubspot-sample.json
python3 test/mock-supabase.py    # mock endpoint on :8899, 201 for key "testkey", 401 otherwise
```
