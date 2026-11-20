"""
Job search engine: a daily scan that finds roles, proves they are open, scores
them honestly and keeps a board. The rules live in a profile file, so the same
engine runs for any job title.

    python3 scan.py profiles/customer-success.json --out output/customer-success
    python3 scan.py profiles/data-analyst.json --out output/data-analyst

It replays 14 days of the scheduled scan (every morning, plus one manual
evening rerun). Every run:
  0. Skip rule: if the last run started under 20 hours ago, do nothing.
  1. Discover: read the board copies first seen since the last run. Tier A
     sources every run, tier B weekly, tier C monthly.
  2. Dedupe: one row per company and title (a role posted in two cities or
     reposted under a new id collapses into one), and a role an earlier run
     already handled is not scored again when a later board picks it up.
  3. Prove: only the company's own job list decides. Gone from the list means
     closed, whatever the boards still show. A list that cannot be read is
     "could not verify", never closed on a guess. No list of its own: "board only".
  4. Gate (dropped with a reason, never scored): junior or student role, a
     language the profile does not have, a region it does not work in, a move
     inside the home country with no remote option, a company that rejected
     it before, none of the wanted duties.
  5. Role fit 0 to 10: title, share of wanted duties, tools on record against
     tools asked, years asked above the record, a title above the record.
  6. Fit line: role fit plus location points, then pay, office, startup and
     "light on wanted duties" factors, each written out.
  7. Show: role fit under 6.5 is "seen, not a fit". Total 8+ is "worth
     applying" (9+ "strong fit") and gets a CV brief and a note to a named
     person; while interviewing, a CV is drafted only from 8.5.
  8. Recheck: every tracked role is read again on its company's list.
After the fortnight: board.json, summary.json and the run log.
board.py turns them into the board. Standard library only.
"""
import argparse
import json
import os
import re
from collections import Counter, defaultdict

DAYS = 14
TIER_EVERY = {"A": 1, "B": 7, "C": 30}
SCHEDULE = [(d, 7.75, "scheduled") for d in range(DAYS)] + [(5, 20.5, "manual rerun")]
ATS_PATTERNS = [
    ("ashbyhq", "Ashby", "AI assisted screening checks each requirement: mirror the JD's skill and tool terms in skills and in bullets."),
    ("greenhouse", "Greenhouse", "Parsed into fields and searched by keyword: exact terms and standard headings."),
    ("lever", "Lever", "No stemming, one profile per company: exact terms, identical facts across applications."),
    ("personio", "Personio", "Plain text conversion: simple layout, extractable text, the ad's language."),
    ("teamtailor", "Teamtailor", "An AI summary is written against the JD: name every required skill near the top."),
    ("join.", "JOIN", "Small companies, fast human read: the top third has to answer the JD."),
    ("recruitee", "Recruitee", "Reliable parser plus screening questions: answer knockout questions carefully."),
    ("workable", "Workable", "Parsed profile and screening questions: standard headings, exact terms."),
]


def half(x):
    return round(x * 2) / 2


def norm_title(t):
    t = re.sub(r"\b(senior|sr|founding|junior)\b", "", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def ats_of(url):
    for key, name, advice in ATS_PATTERNS:
        if key in url:
            return name, advice
    return "Unknown", "Check how the application is received before building the CV."

# ---- rules -------------------------------------------------------------------


def title_scope(title, P):
    t = title.lower()
    if any(x.lower() in t for x in P["target_titles"]):
        scope = "target"
    elif any(x.lower() in t for x in P["adjacent_titles"]):
        scope = "adjacent"
    else:
        return "out"
    if any(re.search(rf"\b{re.escape(w.lower())}\b", t) for w in P["drop_titles"]):
        return "drop"
    return scope


def duty_share(duties, P):
    core = sum(1 for d in duties if any(w.lower() in d.lower() for w in P["core_duties"]))
    avoid = sum(1 for d in duties if any(w.lower() in d.lower() for w in P["avoid_duties"]))
    return core, avoid


def gate(r, P, scope):
    if scope == "drop":
        return "junior, intern or student role"
    missing = [l for l in r["languages_required"] if l not in P["languages"]]
    if missing:
        return f"{', '.join(missing)} required"
    if r["country"] not in P["work_regions"]:
        return "outside the regions you work in"
    if r["company"] in P["rejected_before"]:
        return "rejected there before, done story"
    if (P["no_moves_inside_home_country"] and r["country"] == P["home_country"]
            and r["workplace"] != "remote" and r["location"] != P["home_city"]):
        return "needs a move inside the home country, no remote"
    if P["drop_when_no_core_duties"] and duty_share(r["duties"], P)[0] == 0:
        return "none of the duties you want to do"
    return None


def role_fit(r, P, scope):
    base = 4.0 if scope == "target" else 2.5
    core, avoid = duty_share(r["duties"], P)
    share = core / max(core + avoid, 1)
    have = set(r["tools"]) & set(P["tools"])
    missing = len(r["tools"]) - len(have)
    fit = base + 3 * share + 2 * len(have) / max(len(r["tools"]), 1) - min(0.75 * missing, 1.5)
    if r["years_required"] >= P["years_on_record"] + 2:
        fit -= 0.5
    above = any(r["title"].startswith(s) for s in P["senior_titles_above_record"])
    if above:
        fit -= 1
    return max(0, min(half(fit), 10)), share, above


def location_points(r, P):
    L = P["location_points"]
    if r["location"] == P["home_city"]:
        return L.get("home city", 0), "home city"
    if r["location"] == f"Remote {P['home_country']}":
        return L.get("remote home country", 0), "remote in home country"
    if r["location"] == "Remote EU":
        return L.get("remote EU", 0), "EU remote"
    if r["location"] in L:
        return L[r["location"]], r["location"]
    return 0, f"{r['location']} needs a move"


def fit_line(r, P, rf, share):
    parts = [f"role {rf:g}"]
    pts, label = location_points(r, P)
    total = rf + pts
    parts.append(f"{label} +{pts:g}")
    if r["pay_k_eur"]:
        lo, hi = r["pay_k_eur"]
        if hi < P["pay_floor_k_eur"]:
            total -= 1.5
            parts.append("pay below floor minus 1.5")
        elif lo >= P["pay_floor_k_eur"]:
            total += 0.5
            parts.append("pay above floor +0.5")
        else:
            parts.append("floor inside the band")
    else:
        parts.append("pay not stated (ask)")
    if r["workplace"] == "on site":
        total -= 0.5
        parts.append("on site only minus 0.5")
    if r["employees"] < 150:
        total -= 0.5
        parts.append("startup minus 0.5")
    if share < 0.5 and r["employees"] >= 300:
        total -= 0.5
        parts.append("light on wanted duties at a big team minus 0.5")
    total = max(0, min(half(total), 10))
    return total, f"fit {total:g} ({', '.join(parts)})"


def brief(r, P):
    have = [k for k in P["cv_keywords_on_record"] if any(k.lower() in t.lower() for t in r["tools"] + r["duties"])]
    gaps = [t for t in r["tools"] if t not in P["cv_keywords_on_record"]]
    if r["years_required"] >= P["years_on_record"] + 2:
        gaps.append(f"{r['years_required']} years asked")
    ats, advice = ats_of(r["url"])
    loc = f"{P['home_city']}, {P['home_country']}" + ("" if r["location"] == P["home_city"] else
                                                      " (open to remote)" if r["workplace"] == "remote" else " (open to relocation)")
    return {"headline": r["title"], "top_requirements": r["duties"][:3], "keywords_on_record": have,
            "gaps_to_name_not_cover": gaps, "location_line": loc, "ats": ats, "ats_advice": advice}


def is_open(p, day):
    return p["opened_day"] <= day and (p["closed_day"] is None or day < p["closed_day"])

# ---- one run -------------------------------------------------------------------


def run(day, last_day, P, posts, copies, companies, tracked, seen_keys):
    read = [c for c in copies if last_day < c["seen_day"] <= day < c["gone_day"]
            and (c["tier"] == "A" or day % TIER_EVERY[c["tier"]] == 0)]
    by_role = defaultdict(list)
    for c in read:
        p = posts[c["id"]]
        by_role[(p["company"], norm_title(p["title"]))].append(c)
    out = {k: [] for k in ("main", "reference", "seen", "dropped", "unverified", "closed")}
    in_titles = already = 0
    for key, cs in by_role.items():
        p = dict(posts[max(cs, key=lambda c: int(c["id"]))["id"]])
        p["sources"] = sorted({c["source"] for c in cs})
        scope = title_scope(p["title"], P)
        if scope == "out":
            continue
        if key in seen_keys:  # a later copy of a role an earlier run already handled
            already += 1
            continue
        seen_keys.add(key)
        in_titles += 1
        own = companies[p["company"]]["list"]
        if own == "works" and not is_open(p, day):
            out["closed"].append(dict(p, why="closed on the company's list, still on a board"))
            continue
        reason = gate(p, P, scope)
        if reason:
            out["dropped"].append(dict(p, why=reason))
            continue
        rf, share, above = role_fit(p, P, scope)
        total, line = fit_line(p, P, rf, share)
        if above:
            line += "; title above the record, name the leadership gap"
        p.update(role_fit=rf, total=total, fit_line=line, first_seen=day, key=list(key), state="open")
        if rf < P["show_bar_role"]:
            out["seen"].append(dict(p, why=f"role {rf:g}, {'light on the duties you want' if share < 0.5 else 'tools and years'}"))
        elif own != "works":
            out["unverified"].append(dict(p, why="board only" if own == "none" else "company list unreadable"))
        elif total >= P["cv_bar_total"]:
            p["verdict"] = "Strong fit" if total >= 9 else "Worth applying"
            p["brief"] = brief(p, P)
            out["main"].append(p)
            tracked[p["id"]] = p
        else:
            p["verdict"] = "Below the 8 bar, listed for reference"
            out["reference"].append(p)
            tracked[p["id"]] = p
    closed_now = []
    for pid, t in tracked.items():
        if t["state"] == "open" and not is_open(posts[pid], day):
            t["state"], t["closed_seen"] = "closed", day
            closed_now.append(t)
    log = {
        "day": day, "copies_read": len(read), "unique_roles": len(by_role), "in_titles": in_titles, "already_seen": already,
        "new_main": [f"{r['company']}, {r['title']} (fit {r['total']:g})" for r in out["main"]],
        "reference": len(out["reference"]), "seen_not_a_fit": len(out["seen"]), "dropped": len(out["dropped"]),
        "could_not_verify": len(out["unverified"]), "closed_on_board": len(out["closed"]),
        "tracked_closed": [f"{t['company']}, {t['title']}" for t in closed_now],
        "cvs_drafted": sum(1 for r in out["main"] if r["total"] >= P["cv_bar_interviewing"]),
    }
    return out, log

# ---- the fortnight ----------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="output")
    args = ap.parse_args()
    P = json.load(open(args.profile))
    posts = {p["id"]: p for p in json.load(open(os.path.join(args.data, "postings.json")))}
    copies = json.load(open(os.path.join(args.data, "board_copies.json")))
    companies = json.load(open(os.path.join(args.data, "companies.json")))

    tracked, run_log, all_out, seen_keys = {}, [], defaultdict(list), set()
    last_day, last_start = -2, None  # the scan ran before the fortnight; day 0 reads the last 2 days
    for day, hour, kind in sorted(SCHEDULE):
        start = day * 24 + hour
        if last_start is not None and start - last_start < 20:
            run_log.append({"day": day, "kind": kind, "skipped": f"last run started {start - last_start:.0f}h ago, under 20h"})
            continue
        out, log = run(day, last_day, P, posts, copies, companies, tracked, seen_keys)
        log["kind"] = kind
        run_log.append(log)
        for k, v in out.items():
            all_out[k] += v
        last_day, last_start = day, start

    shown = all_out["main"] + all_out["reference"]
    assert all(companies[r["company"]]["list"] == "works" for r in shown), "an unverified role was shown"
    assert all(r["role_fit"] >= P["show_bar_role"] for r in shown), "a weak role was shown"
    assert all(r["total"] >= P["cv_bar_total"] for r in all_out["main"]), "a role under the bar got a brief"
    assert not any(r["company"] in P["rejected_before"] for r in shown), "a done story came back"
    ids = [r["id"] for r in shown]
    assert len(ids) == len(set(ids)), "a role was reported twice"

    os.makedirs(os.path.join(args.out, "jds"), exist_ok=True)
    keep = ["id", "company", "title", "location", "workplace", "url", "sources", "role_fit", "total", "fit_line",
            "verdict", "brief", "why", "first_seen", "state", "closed_seen", "employees", "pay_k_eur", "duties",
            "tools", "years_required", "languages_required"]
    slim = lambda rs: [{k: r[k] for k in keep if k in r} for r in rs]
    board = {"profile": P["name"], "days": DAYS, "run_log": run_log,
             "main": slim(all_out["main"]), "reference": slim(all_out["reference"]), "seen": slim(all_out["seen"]),
             "dropped": slim(all_out["dropped"]), "could_not_verify": slim(all_out["unverified"]),
             "closed_on_board": slim(all_out["closed"])}
    with open(os.path.join(args.out, "board.json"), "w") as f:
        json.dump(board, f, indent=1)
    runs = [r for r in run_log if "skipped" not in r]
    summary = {
        "profile": P["name"], "runs": len(runs), "skipped": len(run_log) - len(runs),
        "copies_read": sum(r["copies_read"] for r in runs), "unique_roles": sum(r["unique_roles"] for r in runs),
        "in_titles": sum(r["in_titles"] for r in runs), "already_seen": sum(r["already_seen"] for r in runs), "main_8_plus": len(all_out["main"]),
        "reference": len(all_out["reference"]), "seen_not_a_fit": len(all_out["seen"]), "dropped": len(all_out["dropped"]),
        "could_not_verify": len(all_out["unverified"]), "closed_on_board": len(all_out["closed"]),
        "tracked_closed_later": sum(len(r["tracked_closed"]) for r in runs), "cvs_drafted": sum(r["cvs_drafted"] for r in runs),
        "drop_reasons": dict(Counter(r["why"] for r in all_out["dropped"]).most_common()),
        "main": [f"{r['company']}, {r['title']}: {r['fit_line']}" for r in all_out["main"]],
    }
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    for r in all_out["main"]:
        jd = [r["title"], f"{r['company']}, {r['location']} ({r['workplace']})", "", "What you will do:"]
        jd += [f"- {d}" for d in r["duties"]] + ["", "Tools: " + ", ".join(r["tools"]), f"Experience: {r['years_required']}+ years"]
        with open(os.path.join(args.out, "jds", f"{r['id']}.txt"), "w") as f:
            f.write("\n".join(jd) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
