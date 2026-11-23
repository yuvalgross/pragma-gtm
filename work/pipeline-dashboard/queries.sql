-- Pipeline dashboard: the SQL behind every number on the page and in the Hex app.
-- Postgres (Supabase). Schema: analytics. Read by Hex through its own database user,
-- which can see the analytics schema only; the app's own tables stay locked.
--
-- Data: demo_deals, demo_contacts and demo_companies are SYNTHETIC, calibrated to mirror
-- published results (won revenue 295k -> 390k EUR, 40% vs 12% close rate, +42% MQL rate).
-- apollo_sequences holds real, aggregate Apollo sequence stats with anonymized names.

-- 1. Headline numbers -------------------------------------------------------------------
select
  sum(amount_eur) filter (where is_won and period = 'Before signals') as won_before_eur,
  sum(amount_eur) filter (where is_won and period = 'After signals')  as won_after_eur,
  round(avg(is_won::int) filter (where is_closed and lead_source = 'Signal-led')::numeric * 100, 1)       as signal_close_rate_pct,
  round(avg(is_won::int) filter (where is_closed and lead_source = 'Generic outbound')::numeric * 100, 1) as generic_close_rate_pct,
  (select round(avg(is_mql::int)::numeric * 100, 1) from analytics.demo_contacts where period = 'Before signals') as mql_rate_before_pct,
  (select round(avg(is_mql::int)::numeric * 100, 1) from analytics.demo_contacts where period = 'After signals')  as mql_rate_after_pct,
  round(avg(days_to_close) filter (where is_won and lead_source = 'Signal-led'))       as signal_days_to_win,
  round(avg(days_to_close) filter (where is_won and lead_source = 'Generic outbound')) as generic_days_to_win,
  sum(amount_eur) filter (where not is_closed) as open_pipeline_eur
from analytics.demo_deals;

-- 2. Won revenue by month (completed months only, so a half month never looks like a drop)
select date_trunc('month', close_date)::date as month,
       sum(amount_eur) as won_eur,
       count(*)        as won_deals
from analytics.demo_deals
where is_won
  and close_date < date_trunc('month', current_date)
group by 1
order by 1;

-- 3. Close rate by lead source (closed deals) --------------------------------------------
select lead_source,
       count(*)                                       as closed_deals,
       sum(is_won::int)                               as won_deals,
       round(avg(is_won::int)::numeric * 100, 1)      as win_rate_pct,
       sum(case when is_won then amount_eur else 0 end) as won_eur,
       round(avg(case when is_won then days_to_close end)) as avg_days_to_win
from analytics.demo_deals
where is_closed
group by lead_source
order by win_rate_pct desc;

-- 4. Funnel, last 12 months, closed deals -------------------------------------------------
with d as (select * from analytics.demo_deals where is_closed and period = 'After signals')
select 'Discovery' as stage, 1 as ord, count(*) filter (where reached_discovery) as deals from d
union all select 'Demo',        2, count(*) filter (where reached_demo)        from d
union all select 'Proposal',    3, count(*) filter (where reached_proposal)    from d
union all select 'Negotiation', 4, count(*) filter (where reached_negotiation) from d
union all select 'Closed Won',  5, count(*) filter (where is_won)              from d
order by ord;

-- 5. Outreach sequences, anonymized (at least 50 delivered) ------------------------------
select public_label as name, delivered, opened, replied, demoed,
       round(open_rate  * 100, 1) as open_rate_pct,
       round(reply_rate * 100, 1) as reply_rate_pct,
       round(bounce_rate * 100, 1) as bounce_rate_pct
from analytics.apollo_sequences
where delivered >= 50
order by reply_rate desc;

-- 6. The database user Hex logs in with ---------------------------------------------------
-- Sees the analytics schema only. Writeback is allowed inside analytics so Hex can save
-- results as tables; everything outside it, including the app's own tables, is off limits.
--   create role hex_readonly with login nobypassrls;
--   grant usage, create on schema analytics to hex_readonly;
--   grant select, insert, update, delete on all tables in schema analytics to hex_readonly;
--   alter role hex_readonly set statement_timeout = '120s';
--   (password set by hand in the Supabase SQL editor, never in code)
