# pragma-gtm.com

Portfolio site of Yuval Gross, GTM Engineer in Berlin, plus the code for six work samples.

**Live:** [pragma-gtm.com](https://pragma-gtm.com)

## Work samples

Each sample is a small tool with its data, rules, limits and code. All of them run on synthetic data, with plain Python and no outside services.

| Sample | Folder | What it does |
| --- | --- | --- |
| [CRM clean up](https://pragma-gtm.com/work/crm-cleanup/) | [`work/crm-cleanup`](work/crm-cleanup) | Agents fix duplicates, broken fields and orphaned owners in a HubSpot export, then pick which customers get a human this week |
| [Signup router](https://pragma-gtm.com/work/signup-router/) | [`work/signup-router`](work/signup-router) | Gates, scores and routes a week of product trial signups |
| [Signal outreach](https://pragma-gtm.com/work/signal-outreach/) | [`work/signal-outreach`](work/signal-outreach) | Writes a three step sequence from each contact's freshest buying signal and holds back the rest, with the reason |
| [Account prioritisation](https://pragma-gtm.com/work/account-prioritisation/) | [`work/account-prioritisation`](work/account-prioritisation) | Routes 500 accounts across SDRs by territory and capacity |
| [Lost deal reactivation](https://pragma-gtm.com/work/lost-deal-reactivation/) | [`work/lost-deal-reactivation`](work/lost-deal-reactivation) | Sorts lost accounts into groups and builds a Monday call list with the reason to talk |
| [Job search engine](https://pragma-gtm.com/work/job-search-engine/) | [`work/job-search-engine`](work/job-search-engine) | A daily job scan with gates, a readable fit line, a board and a CV check, for any job title |

Every folder has its own README with the commands to run it.

## The site

A single static `index.html` on Vercel, with self hosted fonts and no build step. `vercel.json` holds the headers and redirects.

## Contact

[contact@pragma-gtm.com](mailto:contact@pragma-gtm.com) · [LinkedIn](https://www.linkedin.com/in/yuvalgross)
