# Signal outreach, run 2026-10-29
Input: contacts_synthetic.csv (20 contacts). Ready 8. Human review 2. Held 10. First send day 2026-11-02.

| Contact | Persona | Signal used | Score | Step 1 |
| --- | --- | --- | --- | --- |
| Lena, Synthetic Company A | revops | hiring: a first RevOps analyst (9 days) | 4 | 2026-11-02 08:30 Europe/Berlin |
| Leo, Synthetic Company M | revops | hiring: a sales ops analyst (20 days) | 4 | 2026-11-02 08:30 Europe/Dublin |
| Jonas, Synthetic Company D | revops | tech_change: moved from Salesforce to HubSpot (11 days) | 3 | 2026-11-02 08:30 Europe/Berlin |
| Paul, Synthetic Company F | sales leader | hiring: three account executives (13 days) | 3 | 2026-11-02 08:30 Europe/Zurich |
| Eva, Synthetic Company B | revops | hiring: a RevOps lead (17 days) | 3 | 2026-11-02 08:30 Europe/Amsterdam |
| Tom, Synthetic Company B | sales leader | funding: Series B in October (21 days) | 2 | 2026-11-03 08:30 Europe/Amsterdam |
| Sara, Synthetic Company C | founder | content: leads waiting over the weekend (6 days) | 2 | 2026-11-02 08:30 Europe/Vienna |
| Mia, Synthetic Company E | marketing leader | event: the exhibitor list for a Berlin SaaS conference (4 days) | 2 | 2026-11-02 08:30 Europe/London |

## Two emails as they would go out

**To lena@company-a.example, subject: your hiring plan**

```
Hi Lena,

Saw Synthetic Company A is hiring a first RevOps analyst. New hires usually spend their first month working out who owns which lead.

We help RevOps teams route every inbound lead to the right rep within a minute, with the rules kept in one place.

Worth a short call next week, or should I send a two minute walkthrough instead?

Yuval
```

**To leo@company-m.example, subject: your hiring plan**

```
Hi Leo,

Saw Synthetic Company M is hiring a sales ops analyst. New hires usually spend their first month working out who owns which lead.

We help RevOps teams route every inbound lead to the right rep within a minute, with the rules kept in one place.

Worth a short call next week, or should I send a two minute walkthrough instead?

Yuval
```

## Sent to a human

- ali@company-h.example: step1: spam word 'free'
- clara@company-j.example: email is risky (catch all), confirm before sending

## Held

- nora@company-g.example (signal): nurture, no signal in the last 45 days
- ben@company-i.example (signal): nurture, signal score 1 below 2
- max@company-k.example (gate): title 'Office Manager' matches no persona, check by hand
- ida@company-l.example (signal): nurture, signal score 1.5 below 2
- kim@customer-one.example (gate): existing customer
- ron@open-deal-two.example (gate): open deal, owned by an AE
- ana@company-n.example (gate): contacted 12 days ago, cooldown is 30
- jan@company-o.example (gate): opted out
- eli@company-p.example (gate): email status invalid
- dan@gmail.com (gate): personal email
