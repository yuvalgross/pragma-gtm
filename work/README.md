# Work samples

GTM engineering tools I built, each run end to end on synthetic data, with the
rules, the results and the limits written down. Every folder runs with plain
Python (standard library only) and holds the data generator, the tool, its
outputs and a README. The pipeline dashboard is the exception: it lives in Supabase and Hex, and its folder holds the SQL and the aggregates.

| Sample | What it answers | Live page |
|---|---|---|
| [crm-cleanup](crm-cleanup) | Agents clean a HubSpot export, then who in the customer book to call this week | [pragma-gtm.com/work/crm-cleanup](https://pragma-gtm.com/work/crm-cleanup/) |
| [signup-router](signup-router) | Which product signups deserve a person, and which get an automated touch | [pragma-gtm.com/work/signup-router](https://pragma-gtm.com/work/signup-router/) |
| [signal-outreach](signal-outreach) | A three step email sequence written from each contact's freshest buying signal, holding back who should not get it | [pragma-gtm.com/work/signal-outreach](https://pragma-gtm.com/work/signal-outreach/) |
| [account-prioritisation](account-prioritisation) | Which 80 accounts four SDRs call this week, and what happens when the signals run out | [pragma-gtm.com/work/account-prioritisation](https://pragma-gtm.com/work/account-prioritisation/) |
| [lost-deal-reactivation](lost-deal-reactivation) | Which of 760 lost accounts are worth a second call, who makes it and with what reason | [pragma-gtm.com/work/lost-deal-reactivation](https://pragma-gtm.com/work/lost-deal-reactivation/) |
| [pipeline-dashboard](pipeline-dashboard) | What changed in revenue, close rate and MQL rate when outbound started from signals (Supabase + Hex) | [pragma-gtm.com/work/pipeline-dashboard](https://pragma-gtm.com/work/pipeline-dashboard/) |
| [job-search-engine](job-search-engine) | A daily job scan and the board it feeds, for any job title | [pragma-gtm.com/work/job-search-engine](https://pragma-gtm.com/work/job-search-engine/) |

Run any of them:

    cd work/<sample>
    python3 make_synthetic_*.py
    python3 <tool>.py ...   # the exact command is in each README

All data in this folder is invented, except the pipeline dashboard's Clay signal accounts: real companies from public company data, shown as prospects. Nothing here describes a real person.
