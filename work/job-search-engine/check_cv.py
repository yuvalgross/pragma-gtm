"""
CV check: runs the tailoring rules on a plain text CV against one job post.

    python3 check_cv.py data/sample_cv_draft.txt output/customer-success/jds/4577.txt

What it checks
  ATS       headline mirrors the JD title; JD keywords covered (x of y); each
            keyword in the skills section and inside a bullet
  Proof     each of the JD's top 3 needs has a bullet with a number
  Wording   at most one 4+ word phrase lifted from the JD (mirror the skill
            terms, never the ad's voice)
  Writing   no pronouns, no hedges before numbers ("about", "~"), no dashes as
            punctuation, no filler, no repeated opening verb in a role, one
            line per bullet, a number or a scope in every bullet
  Focus     needs a person: does the top third answer the JD's main need?

Scores each part 0 to 2 like the rubric (focus is left to a person) and lists
every line to fix. Standard library only.
"""
import re
import sys

PRONOUNS = r"\b(I|me|my|we|our|us)\b"
HEDGES = r"(\babout\s+\d|~\s*\d|\bapproximately\b|\baround\s+\d|\broughly\b)"
DASHES = r"(\s[-–—]\s|–|—)"
FILLER = ["passionate", "dynamic", "results driven", "proven track record", "responsible for",
          "helped with", "worked on", "duties included", "synergy"]
MAX_BULLET = 120


def read(path):
    return [l.rstrip("\n") for l in open(path, encoding="utf-8")]


def jd_parts(jd):
    title = jd[0].strip()
    duties = [l[2:].strip() for l in jd if l.startswith("- ")]
    tools = []
    for l in jd:
        if l.lower().startswith("tools:"):
            tools = [t.strip() for t in l.split(":", 1)[1].split(",") if t.strip()]
    # the object of each duty is the keyword: "build lead routing from scratch" -> "lead routing"
    objects = []
    for d in duties:
        words = d.split()[1:]
        obj = " ".join(w for w in words if w not in ("from", "scratch", "through", "and", "for", "with", "the", "new", "tools"))
        objects.append(obj)
    return title, duties, tools, objects


def sections(cv):
    out, cur = {"top": []}, "top"
    for l in cv:
        if l.strip().isupper() and len(l.strip()) > 3:
            cur = l.strip()
            out[cur] = []
        else:
            out[cur].append(l)
    return out


def main():
    cv, jd = read(sys.argv[1]), read(sys.argv[2])
    title, duties, tools, objects = jd_parts(jd)
    S = sections(cv)
    top = [l for l in S["top"] if l.strip()]
    headline = top[2] if len(top) > 2 else ""
    text = "\n".join(cv)
    bullets = [l.strip()[2:] for l in cv if l.strip().startswith("- ")]
    skills = " ".join(S.get("SKILLS", []))
    fixes = []

    # ATS
    head_ok = headline.lower().startswith(title.lower())
    if not head_ok:
        fixes.append(f"Headline should start with the JD title \"{title}\" (now: \"{headline}\")")
    keys = tools + objects
    def found(k):
        parts = [p for p in re.split(r"\s+", k.lower()) if len(p) > 3]
        return all(p.rstrip("s") in text.lower() for p in parts) if parts else k.lower() in text.lower()
    covered = [k for k in keys if found(k)]
    missing = [k for k in keys if k not in covered]
    for k in tools:
        in_sk, in_b = k.lower() in skills.lower(), any(k.lower() in b.lower() for b in bullets)
        if k in covered and not (in_sk and in_b):
            fixes.append(f"Put \"{k}\" in both SKILLS and a bullet (skills {in_sk}, bullet {in_b})")
    cov = len(covered) / max(len(keys), 1)
    ats = 2 if head_ok and cov >= 0.8 else (1 if head_ok or cov >= 0.6 else 0)

    # Proof
    proof_hits = 0
    for obj in objects[:3]:
        parts = [p.rstrip("s") for p in obj.lower().split() if len(p) > 3]
        hit = [b for b in bullets if all(p in b.lower() for p in parts) and re.search(r"\d", b)]
        if hit:
            proof_hits += 1
        else:
            fixes.append(f"No bullet with a number proves \"{obj}\"")
    proof = 2 if proof_hits == 3 else (1 if proof_hits == 2 else 0)

    # Wording: lifted phrases
    def grams(s, n=4):
        w = re.findall(r"[a-z0-9]+", s.lower())
        return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}
    lifted = sorted(grams(" ".join(duties)) & grams(text))
    if len(lifted) > 1:
        fixes.append(f"{len(lifted)} phrases lifted from the JD, keep at most one: {lifted}")
    wording = 2 if len(lifted) <= 1 else (1 if len(lifted) <= 3 else 0)

    # Writing
    writing_issues = []
    for i, l in enumerate(cv, 1):
        body = l.strip()[2:] if l.strip().startswith("- ") else l
        if re.search(PRONOUNS, body):
            writing_issues.append(f"line {i}: pronoun")
        if re.search(HEDGES, body, re.I):
            writing_issues.append(f"line {i}: hedge before a number")
        if re.search(DASHES, body):
            writing_issues.append(f"line {i}: dash used as punctuation")
        for f in FILLER:
            if f in body.lower():
                writing_issues.append(f"line {i}: filler \"{f}\"")
    role_verbs = {}
    current = None
    for i, l in enumerate(cv, 1):
        s = l.strip()
        if s and not s.startswith("- ") and "|" in s:
            current = s.split("|")[0].strip()
            role_verbs[current] = []
        if s.startswith("- "):
            b = s[2:]
            after = b.split(":", 1)[1].strip() if ":" in b else b
            verb = after.split()[0].lower() if after else ""
            if current is not None:
                if verb in role_verbs[current]:
                    writing_issues.append(f"line {i}: opening verb \"{verb}\" repeated in {current}")
                role_verbs[current].append(verb)
            if len(b) > MAX_BULLET:
                writing_issues.append(f"line {i}: bullet over one line ({len(b)} characters)")
            if not re.search(r"\d", b):
                writing_issues.append(f"line {i}: no number or scope")
    fixes += writing_issues
    writing = 2 if not writing_issues else (1 if len(writing_issues) <= 2 else 0)

    auto = ats + proof + wording + writing
    print(f"CV check against: {title}")
    print(f"Keywords: {len(covered)} of {len(keys)} covered" + (f"; missing: {', '.join(missing)}" if missing else ""))
    print(f"Rubric: ATS {ats}, proof {proof}, wording {wording}, writing {writing}, focus (set by a person)")
    print(f"Automatic part: {auto} of 8. Bar: 9 of 10 overall, never deliver under 8.")
    print("Fix list:" if fixes else "Fix list: none, writing check passed")
    for f in fixes:
        print(f"  - {f}")


if __name__ == "__main__":
    main()
