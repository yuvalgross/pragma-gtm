"""
Signal outreach builder: turns an enriched contact list into a ready to import
three step email sequence, written from each contact's freshest buying signal,
and holds back everyone who should not get it.

    python3 signal_outreach.py data/contacts_synthetic.csv --out output/ --start 2026-11-02

Pipeline
  1. Gate (hard, before any copy is written): opt outs, customers, open deals and
     partners, anyone touched in the last 30 days, invalid emails, personal
     domains, and titles outside the four personas. Log the reason.
  2. Pick the signal: weight by type, half weight after 21 days, drop anything
     older than 45 days. No fresh signal means nurture. Generic copy is never sent.
  3. Write the sequence: opener from the signal, one line for the persona,
     one question as the ask. Follow ups on day 3 and day 8.
  4. Check the copy: word limit, banned phrases, spam words, leftover
     placeholders, link count. Any failure goes to a human, not to the sender.
  5. Schedule: one new contact per company per day, a daily cap per mailbox,
     weekdays only, 08:30 in the contact's own time zone.
  6. Write ready.csv, held.csv, review.csv, preview.md and a summary.

The copy comes from fixed templates so every email can be traced to a rule.
"""
import argparse
import csv
import json
import os
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

# ---- rules set by hand ------------------------------------------------------

SENDER = "Yuval"
COOLDOWN_DAYS = 30          # nobody gets a new sequence within 30 days of a touch
MAX_SIGNAL_AGE = 45         # older signals are ignored
MIN_SIGNAL_SCORE = 2.0      # below this the contact goes to nurture
DAILY_CAP = 30              # new contacts per mailbox per day
PER_COMPANY_PER_DAY = 1     # never start two people at one company on the same day
SEND_AT = time(8, 30)       # local time of the contact
FOLLOW_UP_DAYS = (3, 8)     # business days after step 1
MAX_WORDS_STEP1 = 90

PERSONAL_DOMAINS = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "yahoo.com",
    "icloud.com", "proton.me", "protonmail.com", "gmx.de", "gmx.net", "web.de",
}
BLOCKED_CRM_STATUS = {"customer": "existing customer", "open_deal": "open deal, owned by an AE",
                      "partner": "partner"}

# Title keywords to persona. First match wins, so the more specific terms come first.
PERSONAS = [
    ("revops", ("revenue operations", "revops", "sales ops")),
    ("founder", ("founder", "ceo")),
    ("sales_leader", ("chief revenue", "vp sales", "head of sales", "sales director")),
    ("marketing_leader", ("marketing", "growth")),
]

SIGNAL_WEIGHT = {"hiring": 3, "tech_change": 3, "funding": 2, "event": 2, "content": 2}


def freshness(age):
    if age <= 21:
        return 1.0
    if age <= MAX_SIGNAL_AGE:
        return 0.5
    return 0.0


# ---- copy -------------------------------------------------------------------

SUBJECT = {
    "hiring": "your hiring plan",
    "tech_change": "routing after the switch",
    "funding": "after the round",
    "event": "leads from the event",
    "content": "your post",
}
OPENER = {
    "hiring": "Saw {company} is hiring {detail}.",
    "tech_change": "Noticed {company} {detail}.",
    "funding": "Congrats on the {detail}.",
    "event": "Saw {company} on {detail}.",
    "content": "Read your post on {detail}.",
}
BRIDGE = {
    "hiring": "New hires usually spend their first month working out who owns which lead.",
    "tech_change": "A CRM move is often when routing rules quietly break.",
    "funding": "After a round, inbound tends to grow faster than the rules that route it.",
    "event": "Event weeks bring a spike of leads that often sit in a shared inbox.",
    "content": "That is the exact problem we work on.",
}
PERSONA_LINE = {
    "revops": "We help RevOps teams route every inbound lead to the right rep within a minute, with the rules kept in one place.",
    "sales_leader": "We help sales leaders get every inbound lead in front of the right rep within a minute, so nothing waits overnight.",
    "marketing_leader": "We help marketing teams make sure the leads they paid for reach a rep the same hour.",
    "founder": "We help small teams route inbound leads to the right person within a minute, without hiring for it.",
}
ASK = "Worth a short call next week, or should I send a two minute walkthrough instead?"

STEP2 = ("Hi {first},\n\nA short follow up. Most teams start with a one week audit of where inbound "
         "leads wait and who picks them up. It takes about 30 minutes of your team's time, and I can "
         "send the checklist we use without a call.\n\nWant it?\n\n{sender}")
STEP3 = ("Hi {first},\n\nI'll leave it here. If lead routing becomes a priority at {company}, reply "
         "with \"routing\" and I'll send the checklist.\n\n{sender}")

# Phrases that make an email read as automated or as marketing. Checked on every step.
BANNED_PHRASES = (
    "hope this email finds you", "hope you're well", "i wanted to reach out", "quick question",
    "game changer", "revolutionize", "leverage", "synergy", "circle back", "touch base",
    "cutting edge", "best in class", "in today's", "unlock",
)
SPAM_WORDS = ("free", "guarantee", "risk free", "act now", "limited time", "100%", "no obligation")

# ---- steps ------------------------------------------------------------------


def persona_for(title):
    t = title.lower()
    for persona, keys in PERSONAS:
        if any(k in t for k in keys):
            return persona
    return None


def gate(row):
    domain = row["domain"].lower().strip()
    if row["opted_out"] == "yes":
        return "opted out"
    if row["crm_status"] in BLOCKED_CRM_STATUS:
        return BLOCKED_CRM_STATUS[row["crm_status"]]
    if row["last_contacted_days"] and int(row["last_contacted_days"]) < COOLDOWN_DAYS:
        return f"contacted {row['last_contacted_days']} days ago, cooldown is {COOLDOWN_DAYS}"
    if domain in PERSONAL_DOMAINS:
        return "personal email"
    if row["email_status"] in ("invalid", "unknown", ""):
        return f"email status {row['email_status'] or 'missing'}"
    if not persona_for(row["title"]):
        return f"title '{row['title']}' matches no persona, check by hand"
    return None


def parse_signals(text):
    out = []
    for part in filter(None, text.split(";")):
        kind, age, detail = part.split("|", 2)
        out.append({"type": kind, "age": int(age), "detail": detail.strip()})
    return out


def pick_signal(signals):
    """Strongest fresh signal leads. Each other fresh signal adds one point."""
    scored = []
    for s in signals:
        pts = SIGNAL_WEIGHT.get(s["type"], 1) * freshness(s["age"])
        if pts > 0:
            scored.append((pts, -s["age"], s))
    if not scored:
        return None, 0.0
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    best = scored[0]
    return best[2], best[0] + (len(scored) - 1)


def write_sequence(row, signal, persona):
    v = {"first": row["first_name"], "company": row["company_name"], "detail": signal["detail"],
         "sender": SENDER}
    step1 = "\n\n".join([
        f"Hi {v['first']},",
        OPENER[signal["type"]].format(**v) + " " + BRIDGE[signal["type"]],
        PERSONA_LINE[persona],
        ASK,
        SENDER,
    ])
    return {
        "subject": SUBJECT[signal["type"]].format(**v),
        "step1": step1,
        "step2": STEP2.format(**v),
        "step3": STEP3.format(**v),
    }


def check_copy(seq, row):
    problems = []
    words = len(re.findall(r"\b\w+\b", seq["step1"]))
    if words > MAX_WORDS_STEP1:
        problems.append(f"step 1 is {words} words, limit {MAX_WORDS_STEP1}")
    for key in ("subject", "step1", "step2", "step3"):
        low = seq[key].lower()
        if re.search(r"[{}]", seq[key]):
            problems.append(f"{key}: placeholder left in")
        for p in BANNED_PHRASES:
            if p in low:
                problems.append(f"{key}: banned phrase '{p}'")
        for w in SPAM_WORDS:
            if re.search(rf"\b{re.escape(w)}\b", low):
                problems.append(f"{key}: spam word '{w}'")
        if len(re.findall(r"https?://", low)) > 1:
            problems.append(f"{key}: more than one link")
    if len(seq["subject"].split()) > 6:
        problems.append("subject over six words")
    if row["email_status"] == "risky":
        problems.append("email is risky (catch all), confirm before sending")
    return problems


def business_days(start, n):
    d = start
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def next_weekday(d):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def schedule(ready, start):
    """Highest signal score first. One new contact per company per day, DAILY_CAP per day."""
    ready.sort(key=lambda r: (-r["signal_score"], r["contact_id"]))
    day_load, company_days = {}, {}
    for r in ready:
        d = next_weekday(start)
        while (day_load.get(d, 0) >= DAILY_CAP
               or company_days.get((r["domain"], d), 0) >= PER_COMPANY_PER_DAY):
            d = next_weekday(d + timedelta(days=1))
        day_load[d] = day_load.get(d, 0) + 1
        company_days[(r["domain"], d)] = company_days.get((r["domain"], d), 0) + 1
        local = datetime.combine(d, SEND_AT, tzinfo=ZoneInfo(r["timezone"]))
        r["step1_date"] = d.isoformat()
        r["step1_local"] = f"{d.isoformat()} {SEND_AT.strftime('%H:%M')} {r['timezone']}"
        r["step1_utc"] = local.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M")
        r["step2_date"] = business_days(d, FOLLOW_UP_DAYS[0]).isoformat()
        r["step3_date"] = business_days(d, FOLLOW_UP_DAYS[1]).isoformat()
    return ready


def build(rows, start):
    ready, review, held = [], [], []
    for row in rows:
        reason = gate(row)
        if reason:
            held.append({"contact_id": row["contact_id"], "email": row["email"], "stage": "gate", "reason": reason})
            continue
        signal, score = pick_signal(parse_signals(row["signals"]))
        if not signal or score < MIN_SIGNAL_SCORE:
            why = "no signal in the last 45 days" if not signal else f"signal score {score:g} below {MIN_SIGNAL_SCORE:g}"
            held.append({"contact_id": row["contact_id"], "email": row["email"], "stage": "signal",
                         "reason": f"nurture, {why}"})
            continue
        persona = persona_for(row["title"])
        seq = write_sequence(row, signal, persona)
        problems = check_copy(seq, row)
        rec = {
            "contact_id": row["contact_id"], "email": row["email"], "first_name": row["first_name"],
            "company_name": row["company_name"], "domain": row["domain"], "timezone": row["timezone"],
            "persona": persona, "signal": f"{signal['type']}: {signal['detail']} ({signal['age']} days)",
            "signal_score": score, **seq,
        }
        if problems:
            rec["problems"] = "; ".join(problems)
            review.append(rec)
        else:
            ready.append(rec)
    return schedule(ready, start), review, held


# ---- outputs ----------------------------------------------------------------

READY_COLS = ["email", "first_name", "company_name", "persona", "signal", "signal_score",
              "step1_local", "step1_utc", "step2_date", "step3_date",
              "subject", "step1", "step2", "step3", "contact_id"]


def write_outputs(ready, review, held, out_dir, source, start):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "ready.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=READY_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(ready)
    with open(os.path.join(out_dir, "review.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["contact_id", "email", "signal", "problems", "subject", "step1"],
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(review)
    with open(os.path.join(out_dir, "held.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["contact_id", "email", "stage", "reason"])
        w.writeheader()
        w.writerows(held)

    total = len(ready) + len(review) + len(held)
    lines = [
        f"# Signal outreach, run {date.today().isoformat()}",
        f"Input: {source} ({total} contacts). Ready {len(ready)}. Human review {len(review)}. "
        f"Held {len(held)}. First send day {start.isoformat()}.",
        "",
        "| Contact | Persona | Signal used | Score | Step 1 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in ready:
        lines.append(f"| {r['first_name']}, {r['company_name']} | {r['persona'].replace('_', ' ')} | "
                     f"{r['signal']} | {r['signal_score']:g} | {r['step1_local']} |")
    lines += ["", "## Two emails as they would go out", ""]
    for r in ready[:2]:
        lines += [f"**To {r['email']}, subject: {r['subject']}**", "", "```", r["step1"], "```", ""]
    lines += ["## Sent to a human", ""]
    lines += [f"- {r['email']}: {r['problems']}" for r in review]
    lines += ["", "## Held", ""]
    lines += [f"- {h['email']} ({h['stage']}): {h['reason']}" for h in held]
    with open(os.path.join(out_dir, "preview.md"), "w") as f:
        f.write("\n".join(lines) + "\n")

    summary = {
        "run_date": date.today().isoformat(),
        "input": source,
        "contacts_in": total,
        "ready": len(ready),
        "review": len(review),
        "held_at_gate": sum(1 for h in held if h["stage"] == "gate"),
        "held_no_signal": sum(1 for h in held if h["stage"] == "signal"),
        "first_send_day": start.isoformat(),
        "send_days": sorted({r["step1_date"] for r in ready}),
        "rules": {
            "cooldown_days": COOLDOWN_DAYS, "max_signal_age": MAX_SIGNAL_AGE,
            "min_signal_score": MIN_SIGNAL_SCORE, "daily_cap": DAILY_CAP,
            "per_company_per_day": PER_COMPANY_PER_DAY, "send_at_local": SEND_AT.strftime("%H:%M"),
            "follow_up_business_days": FOLLOW_UP_DAYS, "max_words_step1": MAX_WORDS_STEP1,
            "signal_weights": SIGNAL_WEIGHT,
        },
    }
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print("\n".join(lines[:2 + len(ready) + 3]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", default="output")
    ap.add_argument("--start", help="first send day, YYYY-MM-DD (default: next weekday)")
    a = ap.parse_args()
    start = date.fromisoformat(a.start) if a.start else next_weekday(date.today() + timedelta(days=1))
    with open(a.csv, newline="") as f:
        rows = list(csv.DictReader(f))
    ready, review, held = build(rows, start)
    write_outputs(ready, review, held, a.out, os.path.basename(a.csv), start)


if __name__ == "__main__":
    main()
