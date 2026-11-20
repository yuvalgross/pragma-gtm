# Job search engine (synthetic data)

A daily job scan and the board it feeds. It reads every job board, proves each
role on the company's own job list, drops what can never work with the reason,
scores the rest with a fit line anyone can read, and tracks applications, CVs,
live processes and the decisions the outcomes point to. The rules sit in a
profile file, so the same engine runs for any job title.

    python3 make_synthetic_jobs.py
    python3 scan.py profiles/gtm-engineer.json --out output/gtm-engineer
    python3 board.py profiles/gtm-engineer.json output/gtm-engineer
    python3 check_cv.py data/sample_cv_draft.txt output/gtm-engineer/jds/4228.txt

Swap in profiles/customer-success.json to run a different search on the same feed.

The scan replays 14 days: one scheduled run every morning and a manual rerun
that the 20 hour skip rule stops. Open output/gtm-engineer/board.html to see the board.

Standard library only. Every company, posting, candidate and application is invented.

What is real: dedupe, the own list proof, the gates, the fit line, the recheck,
the board, the preference score, the decisions and the CV checks run as written.
What is not: reading live boards, ATS feeds, Gmail and LinkedIn, and writing the
CV and the note to a person. Those run in the live version and are described,
not included.
