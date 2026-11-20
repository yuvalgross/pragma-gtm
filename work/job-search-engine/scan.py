"""
Job search engine: find roles, prove they are open, score them honestly,
and keep a board. The rules live in a profile file, so the same engine runs
for any job title.

    python3 scan.py profiles/gtm-engineer.json --out output/gtm-engineer
    python3 scan.py profiles/customer-success.json --out output/customer-success

Steps
  1. Discover: read every board copy (LinkedIn alerts, Indeed, niche boards...).
  2. Dedupe: one row per company and title; reposts collapse into the newest id.
  3. Verify: only the company's own job list proves a role is open. A board copy
     of a role the company took down is closed. A list that cannot be read is
     "could not verify", never closed on a guess. A company with no list of its
     own keeps the role as "board only".
  4. Gates (dropped with a reason, never scored): title out of scope, junior or
     intern, a required language the profile does not have, a move inside the
     home country with no remote option, a role the profile was rejected from,
     a role with none of the duties the profile wants to do.
  5. Role fit (0 to 10): title, share of the duties the profile wants, tools
     on record against tools asked, years asked above the record.
  6. Total: role fit plus location points, then factors shown in the fit line:
     pay against the floor, on site only, startup, run shape at a big team.
  7. Show: only role fit 6.5+ reaches the main list. Total 8+ gets a tailoring
     brief and a note to a named person; everything else is listed for
     reference or as "seen, not a fit".
  8. Channel: the ATS is read from the URL and decides how the CV is written.
  9. Board: board.json and a static board.html, plus the learning loop on past
     applications.

Standard library only.
"""
import argparse
import csv
import html
import json
import os
import re
from collections import Counter, defaultdict
from datetime import date

TODAY = date(2026, 11, 16)

ATS_PATTERNS = [  # how to tell the ATS from the URL, and what that means for the CV
    ("ashbyhq", "Ashby", "AI assisted screening checks each requirement: mirror the JD's skill and tool terms in skills and in bullets."),
    ("greenhouse", "Greenhouse", "Parsed into fields and searched by keyword: exact terms and standard headings."),
    ("lever", "Lever", "No stemming, one profile per company: exact terms, keep facts identical across applications."),
    ("personio", "Personio", "Plain text conversion: simple layout, extractable text, match the ad's language."),
    ("teamtailor", "Teamtailor", "An AI summary is written against the JD: name every required skill near the top."),
    ("join.", "JOIN", "Small companies, fast human read: the top third has to answer the JD."),
    ("recruitee", "Recruitee", "Reliable parser plus screening questions: answer knockout questions carefully."),
    ("workable", "Workable", "Parsed profile and screening questions: standard headings, exact terms."),
]
OPS_CAP = -1.0


def norm_title(t):
    t = t.lower()
    t = re.sub(r"\b(senior|sr|founding|lead|head of|junior|\(.*?\))\b", "", t)
    return re.sub(r"\s+", " ", t).strip()


def ats_of(url):
    for key, name, advice in ATS_PATTERNS:
        if key in url:
            return name, advice
    return "Unknown", "Check how the application is received before building the CV."


def half(x):
    return round(x * 2) / 2


# ---- steps 1 to 3 -----------------------------------------------------------

def dedupe(postings):
    groups = defaultdict(list)
    for p in postings:
        groups[(p["company"], norm_title(p["title"]), p["location"])].append(p)
    rows = []
    for (_, _, _), copies in groups.items():
        ids = sorted({c["id"] for c in copies}, key=int)
        newest = max(copies, key=lambda c: int(c["id"]))
        row = dict(newest)
        row["sources"] = sorted({c["source"] for c in copies})
        row["all_ids"] = ids
        row["repost"] = len(ids) > 1
        rows.append(row)
    return rows, sum(len(c) for c in groups.values()) - len(groups)


def verify(row, lists):
    own = lists.get(row["company"], {"status": "none", "open_ids": []})
    if own["status"] == "none":
        return "board only"
    if own["status"] == "unreadable":
        return "could not verify"
    live = [i for i in row["all_ids"] if i in own["open_ids"]]
    if live:
        row["id"] = live[-1]
        return "verified"
    return "closed on own list"

# ---- steps 4 to 6 -----------------------------------------------------------


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


def gate(row, P):
    scope = title_scope(row["title"], P)
    if scope == "out":
        return "title out of scope", scope
    if scope == "drop":
        return "junior, intern or student role", scope
    missing = [l for l in row["languages_required"] if l not in P["languages"]]
    if missing:
        return f"{', '.join(missing)} required", scope
    if row["country"] not in P["work_regions"]:
        return f"{row['location']} is outside the regions you work in", scope
    if row["company"] in P["rejected_before"]:
        return "rejected there before, done story", scope
    if row["company"] in P["excluded_companies"]:
        return "excluded company", scope
    if (P["no_moves_inside_home_country"] and row["country"] == P["home_country"]
            and row["workplace"] != "remote" and row["location"] != P["home_city"]):
        return "needs a move inside the home country, no remote", scope
    core, _ = duty_share(row["duties"], P)
    if P["drop_when_no_core_duties"] and core == 0:
        return "none of the duties you want to do", scope
    return None, scope


def role_fit(row, P, scope):
    base = 4.0 if scope == "target" else 2.5
    core, avoid = duty_share(row["duties"], P)
    share = core / max(core + avoid, 1)
    have = set(row["tools"]) & set(P["tools"])
    missing = len(row["tools"]) - len(have)
    fit = base + 3 * share + 2 * len(have) / max(len(row["tools"]), 1) - min(0.75 * missing, 1.5)
    if row["years_required"] >= P["years_on_record"] + 2:
        fit -= 0.5
    above = any(row["title"].startswith(s) or f" {s} " in f" {row['title']} " for s in P["senior_titles_above_record"])
    if above:
        fit -= 1
    return min(half(fit), 10), share, above


def location_points(row, P):
    L = P["location_points"]
    if row["location"] == P["home_city"]:
        return L.get("home city", 0), "home city"
    if row["location"] == f"Remote {P['home_country']}":
        return L.get("remote home country", 0), "remote in home country"
    if row["location"] == "Remote EU":
        return L.get("remote EU", 0), "EU remote"
    if row["location"] in L:
        return L[row["location"]], row["location"]
    return L.get("other", 0), f"{row['location']} needs a move"


def total_fit(row, P, rf, share):
    parts = [f"role {rf:g}"]
    pts, label = location_points(row, P)
    total = rf + pts
    parts.append(f"{label} {pts:+g}".replace("+-", "minus ").replace("+0", "+0"))
    if row["pay_k_eur"]:
        lo, hi = row["pay_k_eur"]
        floor = P["pay_floor_k_eur"]
        if hi < floor:
            total -= 1.5
            parts.append("pay below floor minus 1.5")
        elif lo >= floor:
            total += 0.5
            parts.append("pay above floor +0.5")
        else:
            parts.append("floor inside the band")
    else:
        parts.append("pay not stated (ask)")
    if row["workplace"] == "on site":
        total -= 0.5
        parts.append("on site only minus 0.5")
    if row["employees"] < 150:
        total -= 0.5
        parts.append("startup minus 0.5")
    ops = 0.0
    if share < 0.5 and row["employees"] >= 300:
        ops -= 0.5
        parts.append("run shape at a big team minus 0.5")
    total += max(ops, OPS_CAP)
    total = min(half(total), 10)
    return total, f"fit {total:g} ({', '.join(parts)})"

# ---- step 7: what a CV for this role needs -----------------------------------


def brief(row, P):
    jd_terms = set(row["tools"]) | {d for d in row["duties"]}
    have = [k for k in P["cv_keywords_on_record"]
            if any(k.lower() in t.lower() for t in jd_terms)]
    missing = [t for t in row["tools"] if t not in P["cv_keywords_on_record"]]
    ats, advice = ats_of(row["url"])
    if row["location"] == P["home_city"]:
        loc_line = f"{P['home_city']}, {P['home_country']}"
    elif row["workplace"] == "remote":
        loc_line = f"{P['home_city']}, {P['home_country']} (open to remote)"
    else:
        loc_line = f"{P['home_city']}, {P['home_country']} (open to relocation)"
    return {
        "headline": row["title"],
        "top_requirements": row["duties"][:3],
        "keywords_on_record": have,
        "gaps_to_name_not_cover": missing + (["years asked above the record"] if row["years_required"] >= P["years_on_record"] + 2 else []),
        "location_line": loc_line,
        "ats": ats,
        "ats_advice": advice,
        "note_to_person": "Draft a note under 100 words to the hiring manager: the role, one proof with a number, one gap named honestly, a call ask.",
    }

# ---- step 9: learning loop ---------------------------------------------------


def learning(path):
    rows = list(csv.DictReader(open(path)))
    out = []
    for key in ("role_shape", "company_size", "note_to_named_person"):
        by = defaultdict(Counter)
        for r in rows:
            by[r[key]][r["outcome"]] += 1
        for val, c in sorted(by.items()):
            n = sum(c.values())
            out.append({"split": key, "value": val, "applications": n, "calls": c["call"],
                        "call_rate": round(c["call"] / n, 2), "rejected_at_cv": c["rejected at CV"]})
    return out

# ---- board html --------------------------------------------------------------


def board_html(P, main, ref, seen, dropped, unverified, closed, loop):
    def table(rows, cols):
        head = "".join(f"<th>{html.escape(c)}</th>" for c, _ in cols)
        body = "".join("<tr>" + "".join(f"<td>{html.escape(str(f(r)))}</td>" for _, f in cols) + "</tr>" for r in rows)
        return f"<table><thead><tr>{head}</tr></thead><tbody>{body or '<tr><td>none</td></tr>'}</tbody></table>"
    link = lambda r: r["url"]
    cols_main = [("Company", lambda r: r["company"]), ("Role", lambda r: r["title"]), ("Location", lambda r: f"{r['location']}, {r['workplace']}"),
                 ("Fit line", lambda r: r["fit_line"]), ("ATS", lambda r: ats_of(r["url"])[0]), ("Found on", lambda r: ", ".join(r["sources"])), ("Posting", link)]
    cols_seen = [("Company", lambda r: r["company"]), ("Role", lambda r: r["title"]), ("Why not", lambda r: r["why"])]
    loop_rows = [("Split", lambda r: r["split"]), ("Value", lambda r: r["value"]), ("Applications", lambda r: r["applications"]),
                 ("Calls", lambda r: r["calls"]), ("Call rate", lambda r: r["call_rate"])]
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>{html.escape(P['name'])} board (synthetic)</title>
<style>body{{font-family:system-ui,sans-serif;margin:24px;color:#1d1b16;background:#faf7f0}}h1{{font-size:22px}}h2{{font-size:16px;margin-top:28px}}
table{{border-collapse:collapse;width:100%;font-size:13px;background:#fff}}th,td{{border:1px solid #e3ddd0;padding:6px 8px;text-align:left;vertical-align:top}}
th{{background:#f1ece0;font-weight:600}}p{{color:#5c574c;font-size:14px}}</style></head><body>
<h1>{html.escape(P['name'])}: job board (synthetic data)</h1>
<p>Built by scan.py. Every company and posting is invented. Only roles on the company's own list count as open.</p>
<h2>Strong fit or worth applying (total 8+), {len(main)}</h2>{table(main, cols_main)}
<h2>Below the 8 bar, listed for reference, {len(ref)}</h2>{table(ref, cols_main)}
<h2>Could not verify (company list unreadable or board only), {len(unverified)}</h2>{table(unverified, cols_seen)}
<h2>Seen, not a fit (role fit under {P['show_bar_role']}), {len(seen)}</h2>{table(seen, cols_seen)}
<h2>Checked and dropped, {len(dropped)}</h2>{table(dropped, cols_seen)}
<h2>Closed on the company's own list, still up on a board, {len(closed)}</h2>{table(closed, cols_seen)}
<h2>Learning loop: past applications</h2>{table(loop, loop_rows)}
</body></html>"""

# ---- main -------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="output")
    args = ap.parse_args()
    P = json.load(open(args.profile))
    postings = json.load(open(os.path.join(args.data, "postings.json")))
    lists = json.load(open(os.path.join(args.data, "company_lists.json")))

    rows, dup_copies = dedupe(postings)
    main_list, ref, seen, dropped, unverified, closed = [], [], [], [], [], []
    for r in rows:
        if title_scope(r["title"], P) == "out":
            continue  # other job families stay silent
        status = verify(r, lists)
        r["verify"] = status
        if status == "closed on own list":
            closed.append(dict(r, why="gone from the company's list; a board copy is not proof"))
            continue
        reason, scope = gate(r, P)
        if reason:
            dropped.append(dict(r, why=reason))
            continue
        rf, share, above = role_fit(r, P, scope)
        r["role_fit"] = rf
        r["total"], r["fit_line"] = total_fit(r, P, rf, share)
        if above:
            r["fit_line"] += "; title above the record, name the leadership gap"
        if rf < P["show_bar_role"]:
            seen.append(dict(r, why=f"role {rf:g}: {'run shape' if share < 0.5 else 'tools and title'}"))
            continue
        if status in ("could not verify", "board only"):
            unverified.append(dict(r, why=f"{status}; {r['fit_line']}"))
            continue
        (main_list if r["total"] >= P["cv_bar_total"] else ref).append(r)

    main_list.sort(key=lambda r: (-r["total"], -r["role_fit"]))
    ref.sort(key=lambda r: (-r["total"], -r["role_fit"]))
    for r in main_list:
        r["verdict"] = "Strong fit" if r["total"] >= 9 else "Worth applying"
        r["brief"] = brief(r, P)
    for r in ref:
        r["verdict"] = "Below the 8 bar, listed for reference"

    loop = learning(os.path.join(args.data, "applications.csv"))
    os.makedirs(os.path.join(args.out, "jds"), exist_ok=True)
    for r in main_list:
        jd = [r["title"], f"{r['company']}, {r['location']} ({r['workplace']})", "", "What you will do:"]
        jd += [f"- {d}" for d in r["duties"]] + ["", "Tools: " + ", ".join(r["tools"]),
                                                 f"Experience: {r['years_required']}+ years"]
        with open(os.path.join(args.out, "jds", f"{r['id']}.txt"), "w") as f:
            f.write("\n".join(jd) + "\n")

    keep = ["id", "company", "title", "location", "workplace", "url", "sources", "verify", "role_fit", "total", "fit_line", "verdict", "brief", "why"]
    slim = lambda rs: [{k: r[k] for k in keep if k in r} for r in rs]
    board = {"profile": P["name"], "main": slim(main_list), "reference": slim(ref), "could_not_verify": slim(unverified),
             "seen_not_a_fit": slim(seen), "dropped": slim(dropped), "closed_on_own_list": slim(closed), "learning_loop": loop}
    with open(os.path.join(args.out, "board.json"), "w") as f:
        json.dump(board, f, indent=1)
    with open(os.path.join(args.out, "board.html"), "w") as f:
        f.write(board_html(P, main_list, ref, seen, dropped, unverified, closed, loop))

    in_scope = len(main_list) + len(ref) + len(seen) + len(dropped) + len(unverified) + len(closed)
    summary = {
        "profile": P["name"], "board_copies": len(postings), "unique_roles": len(rows),
        "duplicate_copies_collapsed": dup_copies, "reposts": sum(1 for r in rows if r["repost"]),
        "in_scope": in_scope, "main_8_plus": len(main_list), "reference": len(ref), "could_not_verify": len(unverified),
        "seen_not_a_fit": len(seen), "dropped": len(dropped), "closed_on_own_list": len(closed),
        "drop_reasons": dict(Counter(r["why"] for r in dropped)),
        "top": [{"company": r["company"], "title": r["title"], "fit_line": r["fit_line"], "verdict": r["verdict"],
                 "ats": r["brief"]["ats"]} for r in main_list[:5]],
    }
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    # checks: the run stops if any rule broke
    assert all(r["verify"] == "verified" for r in main_list + ref), "an unverified role reached the list"
    assert all(r["role_fit"] >= P["show_bar_role"] for r in main_list + ref), "a weak role reached the list"
    assert all(r["total"] >= P["cv_bar_total"] for r in main_list), "a role under the bar got a CV brief"
    assert not any(r["company"] in P["rejected_before"] for r in main_list + ref), "a done story came back"
    ids = [r["id"] for r in main_list + ref]
    assert len(ids) == len(set(ids)), "a role is listed twice"
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
