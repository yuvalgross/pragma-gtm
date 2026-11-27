# HubSpot to Supabase sync (n8n)

`hubspot-to-supabase.json` is an n8n workflow that refreshes the dashboard from a CRM.

**Status: built, not yet run against a HubSpot account.** The workflow file imports into n8n and the node wiring is complete. It has not been executed, so treat it as a tested-on-paper design until the first run is logged here.

## What it does

1. Runs nightly at 02:00.
2. Pulls every deal from HubSpot (name, amount, stage, created, closed, lead source).
3. Maps each deal to the columns of `analytics.demo_deals`, so every query in `queries.sql` works unchanged: `lead_source`, `is_closed`, `is_won`, `amount_eur`, `days_to_close`, `period`.
4. Upserts into `analytics.deals` on `hubspot_id`, so a rerun never duplicates a deal.
5. A failed write posts to Slack.

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

3. Set `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` as n8n environment variables and add the HubSpot credential.
4. Import the JSON, run it once by hand, then check the row count in `analytics.deals` against HubSpot.
5. Point the five queries at `analytics.deals` instead of `analytics.demo_deals`.

`GO_LIVE` in the Code node (default 2025-11-01) splits Before and After signals.
