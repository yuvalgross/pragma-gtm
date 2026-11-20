# Account prioritisation (synthetic data)

Which accounts each of four SDRs works this week, and why. Runs two Mondays in a row.

    python3 make_synthetic_accounts.py
    python3 prioritise.py data/accounts.csv data/signals.csv --out output

Try a leadership decision without touching the logic:

    python3 prioritise.py data/accounts.csv data/signals.csv --capacity "LATAM rep=12,EMEA rep=33" --out output_move

Standard library only. Every company, domain and signal is invented; domains end in .example.

What is real: the gate, the scoring, the routing and the checks run as written.
What is not: the Clay enrichment, the n8n writes into Salesforce and the Slack list are designed, not running.
