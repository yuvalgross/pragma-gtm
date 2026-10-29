"""
Signal outreach builder: turns an enriched contact list into a ready to import
three step email sequence, written from each contact's freshest buying signal,
and holds back everyone who should not get it.

    python3 signal_outreach.py data/contacts_synthetic.csv --out output/ --start 2026-11-02

Pipeline
  1. Clean: lowercase emails, drop exact duplicates (an export joined twice),
     reject rows whose signal data cannot be parsed. Nothing is guessed.
  2. Gate (hard, before any copy is written): opt outs, customers, open deals and
     partners, anyone touched in the last 30 days, invalid or unknown emails,
     personal domains, and titles outside the four personas. Log the reason.
  3. Pick the signal: weight by type, half weight after 21 days, drop anything
     older than 45 days. Extra signals add a point only while fresh. Below the
     threshold the contact goes to nurture: generic copy is never sent.
  4. Write the sequence: opener from the signal, one line for the persona, one
     question as the ask. Step 2 is written for the persona, step 3 closes the loop.
  5. Check the copy: word limit, banned phrases, spam words, leftover
     placeholders, link count, risky emails. Any failure goes to a person.
  6. Schedule: strongest and freshest first, one new contact per company per
     day, a daily cap per mailbox, weekdays only, 08:30 in the contact's time zone.
  7. Write ready.csv, review.csv, held.csv, preview.md and summary.json with the
     full funnel and every reason count.

The copy comes from fixed templates so every email can be traced to a rule.
"""
import argparse
import csv
import json
import os
import re
import sys
from collections import Counter
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

# ---- rules set by hand ------------------------------------------------------

SENDER = "Yuval"
COOLDOWN_DAYS = 30          # nobody gets a new sequence within 30 days of a touch
FULL_WEIGHT_DAYS = 21       # signals count in full up to this age
MAX_SIGNAL_AGE = 45         # and at half weight up to this one, then not at all
MIN_SIGNAL_SCORE = 2.0      # below this the contact goes to nurture
DAILY_CAP = 20              # new contacts per mailbox per day, kept low for deliverability
PER_COMPANY_PER_DAY = 1     # never start two people at one company on the same day
SEND_AT = time(8, 30)       # local time of the contact
FOLLOW_UP_DAYS = (3, 8)     # business days after step 1
MAX_WORDS_STEP1 = 90
MAX_SUBJECT_WORDS = 6

REQUIRED_COLUMNS = {
    "contact_id", "first_name", "title", "email", "company_name", "domain", "timezone",
    "crm_status", "last_contacted_days", "opted_out", "email_status", "signals",
}
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
    if age <= FULL_WEIGHT_DAYS:
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
    "tech_change": "A change in the sales stack is often when routing rules quietly break.",
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

# Step 2 offers the same audit checklist, framed for what each persona is measured on.
STEP2_LINE = {
    "revops": "Most RevOps teams start with a one week audit of every routing rule and who owns the leads that fall through them.",
    "sales_leader": "Most sales leaders start with a one week audit of how long inbound leads wait before a rep picks them up.",
    "marketing_leader": "Most marketing teams start with a one week audit of how many paid leads reach a rep the same day.",
    "founder": "Most small teams start with a one week audit of where inbound leads land and who answers them.",
}
STEP2 = ("Hi {first},\n\nA short follow up. {line} It takes about 30 minutes of your team's time, "
         "and I can send the checklist we use without a call.\n\nWant it?\n\n{sender}")
STEP3 = ("Hi {first},\n\nI'll leave it here. If lead routing becomes a priority at {company}, reply "
         "with \"routing\" and I'll send the checklist.\n\n{sender}")

# Phrases that make an email read as automated or as marketing. Checked on every step.
BANNED_PHRASES = (
    "hope this email finds you", "hope you're well", "i wanted to reach out", "quick question",
    "game changer", "revolutionize", "leverage", "synergy", "circle back", "touch base",
    "cutting edge", "best in class", "in today's", "unlock",
)
SPAM_WORDS = ("free", "guarantee", "act now", "limited time", "100%", "no obligation")

# ---- steps ------------------------------------------------------------------


class BadRow(ValueError):
    pass


def persona_for(title):
    t = title.lower()
    for persona, keys in PERSONAS:
        if any(k in t for k in keys):
            return persona
    return None


def parse_signals(text):
    out = []
    for part in filter(None, (p.strip() for p in text.split(";"))):
        bits = part.split("|", 2)
        if len(bits) != 3 or not bits[1].isdigit() or bits[0] not in SIGNAL_WEIGHT:
            raise BadRow(f"cannot read signal '{part}'")
        out.append({"type": bits[0], "age": int(bits[1]), "detail": bits[2].strip()})
    return out


def gate(row):
    if row["opted_out"] == "yes":
        return "opted out"
    if row["crm_status"] in BLOCKED_CRM_STATUS:
        return BLOCKED_CRM_STATUS[row["crm_status"]]
    if row["last_contacted_days"] and int(row["last_contacted_days"]) < COOLDOWN_DAYS:
        return f"contacted in the last {COOLDOWN_DAYS} days"
    if row["domain"].lower().strip() in PERSONAL_DOMAINS:
        return "personal email"
    if row["email_status"] in ("invalid", "unknown", ""):
        return f"email status {row['email_status'] or 'missing'}"
    if not persona_for(row["title"]):
        return "title matches no persona, check by hand"
    return None


def pick_signal(signals):
    """Strongest signal leads; ties go to the fresher one. Each other signal that is
    still inside the full weight window adds one point. Returns (signal, score)."""
    usable = [(SIGNAL_WEIGHT[s["type"]] * freshness(s["age"]), s) for s in signals]
    usable = [(pts, s) for pts, s in usable if pts > 0]
    if not usable:
        return None, 0.0
    usable.sort(key=lambda x: (-x[0], x[1]["age"]))
    best_pts, best = usable[0]
    bonus = sum(1 for _, s in usable[1:] if s["age"] <= FULL_WEIGHT_DAYS)
    return best, best_pts + bonus


def write_sequence(row, signal, persona):
    v = {"first": row["first_name"], "company": row["company_name"], "detail": signal["detail"],
         "sender": SENDER, "line": STEP2_LINE[persona]}
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
    if len(seq["subject"].split()) > MAX_SUBJECT_WORDS:
        problems.append(f"subject over {MAX_SUBJECT_WORDS} words")
    for key in ("subject", "step1", "step2", "step3"):
        low = seq[key].lower()
        if re.search(r"[{}]", seq[key]):
            problems.append(f"{key}: placeholder left in")
        problems += [f"{key}: banned phrase '{p}'" for p in BANNED_PHRASES if p in low]
        problems += [f"{key}: spam word '{w}'" for w in SPAM_WORDS
                     if re.search(rf"(?<!\w){re.escape(w)}(?!\w)", low)]
        if len(re.findall(r"https?://", low)) > 1:
            problems.append(f"{key}: more than one link")
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
    """Highest score first, then the freshest signal. One new contact per company
    per day and DAILY_CAP per day; whoever does not fit moves to the next weekday."""
    ready.sort(key=lambda r: (-r["signal_score"], r["signal_age"], r["contact_id"]))
    day_load, company_days = Counter(), Counter()
    for r in ready:
        d = next_weekday(start)
        while day_load[d] >= DAILY_CAP or company_days[(r["domain"], d)] >= PER_COMPANY_PER_DAY:
            d = next_weekday(d + timedelta(days=1))
        day_load[d] += 1
        company_days[(r["domain"], d)] += 1
        local = datetime.combine(d, SEND_AT, tzinfo=ZoneInfo(r["timezone"]))
        r["step1_date"] = d.isoformat()
        r["step1_local"] = f"{d.isoformat()} {SEND_AT.strftime('%H:%M')} {r['timezone']}"
        r["step1_utc"] = local.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M")
        r["step2_date"] = business_days(d, FOLLOW_UP_DAYS[0]).isoformat()
        r["step3_date"] = business_days(d, FOLLOW_UP_DAYS[1]).isoformat()
    return ready


def build(rows, start):
    ready, review, held = [], [], []
    seen = {}

    def hold(row, stage, reason):
        held.append({"contact_id": row["contact_id"], "email": row["email"], "stage": stage, "reason": reason})

    for row in rows:
        row = {k: (v or "").strip() for k, v in row.items()}
        row["email"] = row["email"].lower()
        if row["email"] in seen:
            hold(row, "clean", f"duplicate of {seen[row['email']]}")
            continue
        seen[row["email"]] = row["contact_id"]
        try:
            signals = parse_signals(row["signals"])
        except BadRow as e:
            hold(row, "clean", f"bad signal data: {e}")
            continue
        reason = gate(row)
        if reason:
            hold(row, "gate", reason)
            continue
        signal, score = pick_signal(signals)
        if not signal:
            hold(row, "signal", f"nurture, no signal in the last {MAX_SIGNAL_AGE} days")
            continue
        if score < MIN_SIGNAL_SCORE:
            hold(row, "signal", f"nurture, signal score below {MIN_SIGNAL_SCORE:g}")
            continue
        persona = persona_for(row["title"])
        seq = write_sequence(row, signal, persona)
        problems = check_copy(seq, row)
        rec = {
            "contact_id": row["contact_id"], "email": row["email"], "first_name": row["first_name"],
            "company_name": row["company_name"], "domain": row["domain"], "timezone": row["timezone"],
            "persona": persona, "signal_type": signal["type"], "signal_age": signal["age"],
            "signal": f"{signal['type']}: {signal['detail']} ({signal['age']} days)",
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


def funnel(ready, review, held):
    stages = Counter(h["stage"] for h in held)
    total = len(ready) + len(review) + len(held)
    return {
        "contacts_in": total,
        "removed_in_cleaning": stages["clean"],
        "held_at_gate": stages["gate"],
        "nurture_no_signal": stages["signal"],
        "sent_to_review": len(review),
        "ready": len(ready),
        "ready_share_of_input": round(len(ready) / total, 3) if total else 0.0,
    }


def reason_key(h):
    if h["stage"] == "clean":
        return "clean: " + ("duplicate" if h["reason"].startswith("duplicate") else "bad signal data")
    return f"{h['stage']}: {h['reason']}"


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

    fun = funnel(ready, review, held)
    reasons = Counter(reason_key(h) for h in held)
    review_reasons = Counter(re.sub(r"^step\d: |^subject: ", "", p)
                             for r in review for p in r["problems"].split("; "))
    per_day = Counter(r["step1_date"] for r in ready)
    summary = {
        "run_date": date.today().isoformat(),
        "input": source,
        "funnel": fun,
        "held_reasons": dict(reasons.most_common()),
        "review_reasons": dict(review_reasons.most_common()),
        "ready_by_signal": dict(Counter(r["signal_type"] for r in ready).most_common()),
        "ready_by_persona": dict(Counter(r["persona"] for r in ready).most_common()),
        "first_sends_per_day": dict(sorted(per_day.items())),
        "rules": {
            "cooldown_days": COOLDOWN_DAYS, "full_weight_days": FULL_WEIGHT_DAYS,
            "max_signal_age": MAX_SIGNAL_AGE, "min_signal_score": MIN_SIGNAL_SCORE,
            "daily_cap": DAILY_CAP, "per_company_per_day": PER_COMPANY_PER_DAY,
            "send_at_local": SEND_AT.strftime("%H:%M"), "follow_up_business_days": FOLLOW_UP_DAYS,
            "max_words_step1": MAX_WORDS_STEP1, "max_subject_words": MAX_SUBJECT_WORDS,
            "signal_weights": SIGNAL_WEIGHT,
        },
    }
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    lines = [
        f"# Signal outreach, run {date.today().isoformat()}",
        f"Input: {source}. {fun['contacts_in']} in, {fun['removed_in_cleaning']} removed in cleaning, "
        f"{fun['held_at_gate']} held at the gate, {fun['nurture_no_signal']} to nurture, "
        f"{fun['sent_to_review']} to review, {fun['ready']} ready. First send day {start.isoformat()}.",
        "",
        "First sends per day: " + ", ".join(f"{d} {n}" for d, n in sorted(per_day.items())),
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
    lines += ["## Why contacts did not make it", ""]
    lines += [f"- {n} × {k}" for k, n in reasons.most_common()]
    lines += [f"- {n} × review: {k}" for k, n in review_reasons.most_common()]
    with open(os.path.join(out_dir, "preview.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines[:4]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", default="output")
    ap.add_argument("--start", help="first send day, YYYY-MM-DD (default: next weekday)")
    a = ap.parse_args()
    start = date.fromisoformat(a.start) if a.start else next_weekday(date.today() + timedelta(days=1))
    with open(a.csv, newline="") as f:
        reader = csv.DictReader(f)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            sys.exit(f"input is missing columns: {', '.join(sorted(missing))}")
        rows = list(reader)
    ready, review, held = build(rows, start)
    write_outputs(ready, review, held, a.out, os.path.basename(a.csv), start)


if __name__ == "__main__":
    main()
