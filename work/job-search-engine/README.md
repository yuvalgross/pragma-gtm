# Job search engine (synthetic data)

Finds roles across job boards, proves each one is open on the company's own list,
scores it with a fit line you can read, and keeps a board. The rules sit in a
profile file, so the same engine runs for any job title.

    python3 make_synthetic_jobs.py
    python3 scan.py profiles/gtm-engineer.json --out output/gtm-engineer
    python3 scan.py profiles/customer-success.json --out output/customer-success
    python3 check_cv.py data/sample_cv_draft.txt output/gtm-engineer/jds/1074.txt

A new job title is a new profile: target and adjacent titles, the duties you want
and want to avoid, tools on record, languages, home city, regions you work in,
location points, pay floor, years on record, companies rejected before.

Standard library only. Every company, posting and application is invented.

What is real: dedupe, the own list proof, the gates, the fit line, the board, the
learning loop report and the CV checks run as written.
What is not: reading live boards, ATS feeds, Gmail and LinkedIn; writing the CV
and the note to a person. Those run in the live version and are described, not
included.
