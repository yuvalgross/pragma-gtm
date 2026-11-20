# Lost deal reactivation (synthetic data)

Which lost accounts are worth a second call this week, who calls them and with what reason.

    python3 make_synthetic_lost.py
    python3 reactivate.py data/lost_accounts.csv --out output

Next week, with nobody called twice:

    python3 reactivate.py data/lost_accounts.csv --worked output/top40.csv --out output_week2

Change one rule and see what moves:

    python3 reactivate.py data/lost_accounts.csv --set wait_days_after_loss=60 --out output_60

Standard library only. Every account is invented. The impact rates are assumptions and are set at the top of the script.

What is real: the grouping, the top 40, the duplicate flags and the nine checks run as written.
What is not: the HubSpot write back, the workflows and the German sequence are specified, not running.
