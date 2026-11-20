"""
Builds the job hunt board from one scan output and the application history.

    python3 board.py profiles/customer-success.json output/customer-success

Adds what the board tracks around the scan:
  Applications  every application and its stage; a role at 8.5+ is applied to
                the day after it is found, with a CV scored on the rubric
  CVs           score, channel, the headline used, and the outcome
  Salary        live processes ranked by a preference score:
                salary 30%, safety 25%, remote 20%, role fit 15%, product 10%
  Decisions     what the outcomes say, written as a yes or no question
  Scans         the run log, one line per run, skips included
Writes board.html (one self contained page) and board_data.json.
Everything is invented. Standard library only.
"""
import csv
import json
import os
import random
import sys
from collections import Counter, defaultdict

rnd = random.Random(7)
P = json.load(open(sys.argv[1]))
OUT = sys.argv[2]
DATA = "data"
B = json.load(open(os.path.join(OUT, "board.json")))
companies = json.load(open(os.path.join(DATA, "companies.json")))
past = list(csv.DictReader(open(os.path.join(DATA, "applications.csv"))))
LAST = B["days"] - 1

ROLE_BY_SHAPE = {"build": P["target_titles"], "run": P["adjacent_titles"] or P["target_titles"],
                 "sales": P.get("other_titles") or P["target_titles"]}


def title_for(shape):
    return rnd.choice(ROLE_BY_SHAPE[shape])


# ---- applications ---------------------------------------------------------------
apps = []
for a in past:
    day = -int(a["days_before_start"])
    shape = a["role_shape"]
    stage = {"call": "interview", "rejected at CV": "rejected", "no reply": "applied", "pending": "applied"}[a["outcome"]]
    note = {"call": "first call held", "rejected at CV": "rejected at CV stage", "no reply": "no human reply", "pending": "waiting"}[a["outcome"]]
    if a["outcome"] == "call" and day < -25:
        stage, note = rnd.choice([("rejected", "rejected after the hiring manager round"), ("rejected", "rejected after the case study"),
                                  ("closed", "role closed after the first call")])
    apps.append({"id": a["application"], "company": a["company"], "role": title_for(shape),
                 "track": {"build": "Core", "run": "Light", "sales": "Other"}[shape], "stage": stage, "day": day,
                 "note": note, "channel": a["channel"], "cv": float(a["cv_score"]), "shape": shape,
                 "size": a["company_size"], "note_to_person": a["note_to_named_person"], "outcome": a["outcome"]})

for r in B["main"]:
    if r["total"] < P["cv_bar_interviewing"]:
        continue
    day = r["first_seen"] + 1
    if day > LAST:
        continue
    waited = LAST - day
    outcome = "call" if (waited >= 5 and rnd.random() < 0.45) else ("rejected at CV" if waited >= 4 and rnd.random() < 0.3 else "pending")
    stage = {"call": "interview", "rejected at CV": "rejected", "pending": "applied"}[outcome]
    size = "under 150" if r["employees"] < 150 else ("150 to 500" if r["employees"] <= 500 else "over 500")
    apps.append({"id": "N" + r["id"], "company": r["company"], "role": r["title"], "track": "Core", "stage": stage, "day": day,
                 "note": {"call": "first call booked", "rejected at CV": "rejected at CV stage", "pending": "applied with a note to the hiring manager"}[outcome],
                 "channel": r["brief"]["ats"], "cv": rnd.choice([8.5, 9, 9]), "shape": "build", "size": size,
                 "note_to_person": "yes", "outcome": outcome, "fit": r["total"], "headline": r["brief"]["headline"]})
    r["state"] = "Applied" if r.get("state") == "open" else "Closed"
for r in B["main"] + B["reference"]:
    if r.get("state") == "closed":
        r["state"] = "Closed"
    elif r.get("state") == "open":
        r["state"] = "Not applied"

# follow ups: an application with a call whose feedback date passed
for a in apps:
    if a["stage"] == "interview" and a["day"] <= LAST - 6 and rnd.random() < 0.35:
        a["next"] = "feedback date passed: follow up draft ready, sent only after a yes"

# ---- salary and companies: preference score ----------------------------------------
W = {"salary": 0.30, "safety": 0.25, "remote": 0.20, "role": 0.15, "product": 0.10}
SAFETY = {"Seed": 3, "Series A": 5, "Series B": 7, "Series C+": 8, "Public or late stage": 9}
comp = []
for a in [x for x in apps if x["stage"] == "interview"]:
    c = companies[a["company"]]
    band = rnd.choice([(60, 75), (65, 80), (70, 85), (55, 70), (75, 90)])
    stated = rnd.random() < 0.6
    base = (band[0] + band[1]) / 2 if stated else 68
    office = rnd.choice([0, 0, 1, 2, 3, 5])
    parts = {
        "salary": max(0, min(10, (base - 60) / 3)),
        "safety": SAFETY[c["stage"]],
        "remote": {0: 10, 1: 7, 2: 5, 3: 3.5, 5: 2}[office],
        "role": a.get("fit", rnd.choice([7, 7.5, 8, 8.5])),
        "product": rnd.choice([8, 9, 9, 4]),
    }
    adjust = -0.5 if rnd.random() < 0.15 else 0
    score = round(sum(parts[k] * W[k] for k in W) + adjust, 1)
    comp.append({"company": a["company"], "role": a["role"], "stage": c["stage"], "employees": c["employees"],
                 "band": f"€{band[0]}k to €{band[1]}k" if stated else "not stated, estimate €68k",
                 "office": "remote" if office == 0 else f"{office} office days" if office < 5 else "on site",
                 "parts": {k: round(v, 1) for k, v in parts.items()}, "adjust": adjust,
                 "adjust_why": "only an outside recruiter so far" if adjust else "", "score": score})
comp.sort(key=lambda x: -x["score"])

# ---- decisions from the outcomes --------------------------------------------------


def rate(rows, key, val):
    xs = [r for r in rows if r[key] == val and r["outcome"] != "pending"]
    return (sum(1 for r in xs if r["outcome"] == "call"), len(xs))


decided = [a for a in apps if a["outcome"] != "pending"]
b_calls, b_n = rate(decided, "shape", "build")
r_calls, r_n = rate(decided, "shape", "run")
y_calls, y_n = rate(decided, "note_to_person", "yes")
n_calls, n_n = rate(decided, "note_to_person", "no")
big_calls, big_n = rate(decided, "size", "over 500")
sm_calls, sm_n = rate(decided, "size", "under 150")
pct = lambda c, n: f"{round(100 * c / n) if n else 0}%"


def decision(q, why, a, b, change):
    """A yes or no question. Marked applied only when the gap in call rate is 10 points or more."""
    (c1, n1), (c2, n2) = a, b
    gap = (c1 / n1 if n1 else 0) - (c2 / n2 if n2 else 0)
    if gap >= 0.10 and min(n1, n2) >= 10:
        return {"q": q, "why": why, "status": "applied", "answer": "Yes. " + change}
    return {"q": q, "why": why + (" Too small a gap to act on yet." if gap < 0.10 else " Too few outcomes yet."), "status": "open", "answer": ""}


decisions = [
    decision("Rank roles light on the duties you want half a point lower?",
             f"Roles built around your core duties got a call {b_calls} of {b_n} times ({pct(b_calls, b_n)}), roles light on them {r_calls} of {r_n} ({pct(r_calls, r_n)}).",
             (b_calls, b_n), (r_calls, r_n), "Now in the fit line as \"light on wanted duties at a big team minus 0.5\"."),
    decision("Send a note to a named person with every application at 8 or more?",
             f"With a note: {y_calls} calls from {y_n} ({pct(y_calls, y_n)}). Without: {n_calls} from {n_n} ({pct(n_calls, n_n)}).",
             (y_calls, y_n), (n_calls, n_n), "Every CV brief now ends with the note."),
    decision("Apply cold to companies over 500 people only when the role is built around your core duties?",
             f"Under 150 people: {sm_calls} calls from {sm_n} ({pct(sm_calls, sm_n)}). Over 500: {big_calls} from {big_n} ({pct(big_calls, big_n)}).",
             (sm_calls, sm_n), (big_calls, big_n), "Roles light on your core duties at 500+ people are now listed for reference only."),
    {"q": "Treat 21 days of silence as closed and stop follow ups there?",
     "why": f"{sum(1 for a in apps if a['outcome'] == 'no reply')} applications have had no human reply after 21 days.",
     "status": "open", "answer": ""},
]

# ---- run log lines --------------------------------------------------------------------
runs = []
for r in B["run_log"]:
    if "skipped" in r:
        runs.append({"day": r["day"], "head": r["kind"], "text": f"Skipped: {r['skipped']}."})
        continue
    bits = [f"{r['copies_read']} board copies read, {r['in_titles']} new roles in your titles ({r['already_seen']} seen in an earlier run)."]
    if r["new_main"]:
        bits.append("Worth applying: " + "; ".join(r["new_main"]) + ".")
    else:
        bits.append("Nothing at 8 or more.")
    bits.append(f"{r['dropped']} dropped by a gate, {r['seen_not_a_fit']} seen not a fit, {r['reference']} for reference"
                + (f", {r['could_not_verify']} could not verify" if r["could_not_verify"] else "")
                + (f", {r['closed_on_board']} closed on the company list but still on a board" if r["closed_on_board"] else "") + ".")
    if r["tracked_closed"]:
        bits.append("Closed since the last run: " + "; ".join(r["tracked_closed"]) + ".")
    if r["cvs_drafted"]:
        bits.append(f"{r['cvs_drafted']} CV drafted.")
    runs.append({"day": r["day"], "head": r["kind"], "text": " ".join(bits)})

open_roles = [{"company": r["company"], "role": r["title"], "loc": f"{r['location']}, {r['workplace']}", "fit": r["total"],
               "line": r["fit_line"], "state": r["state"], "seen": r["first_seen"], "url": r["url"], "ats": r["brief"]["ats"] if "brief" in r else "",
               "sources": ", ".join(r["sources"])} for r in B["main"] + B["reference"]]
cvs = [{"company": a["company"], "role": a["role"], "day": a["day"], "fit": a.get("fit"), "cv": a["cv"], "channel": a["channel"],
        "note": a["note_to_person"], "outcome": a["outcome"]} for a in apps]
data = {"profile": P["name"], "last": LAST, "apps": apps, "open": open_roles, "cvs": cvs, "comp": comp,
        "decisions": decisions, "runs": runs, "weights": W}
with open(os.path.join(OUT, "board_data.json"), "w") as f:
    json.dump(data, f, indent=1)

TEMPLATE = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "board_template.html")).read()
html = TEMPLATE.replace("__TITLE__", P["name"]).replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
with open(os.path.join(OUT, "board.html"), "w") as f:
    f.write(html)
print({"applications": len(apps), "interviewing": sum(1 for a in apps if a["stage"] == "interview"),
       "open_roles": len(open_roles), "salary_cards": len(comp), "decisions": len(decisions), "runs": len(runs)})
