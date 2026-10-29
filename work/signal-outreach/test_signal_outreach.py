"""
Checks for signal_outreach.py. Standard library only.

    python3 -m unittest test_signal_outreach.py

The first group pins single rules on hand written rows. The second runs the
whole pipeline on the synthetic file and checks properties that must hold for
any input: nobody held appears in ready, no company gets two first emails on
one day, no day goes over the cap, nothing is sent on a weekend.
"""
import csv
import os
import unittest
from collections import Counter
from datetime import date

import signal_outreach as so

HERE = os.path.dirname(os.path.abspath(__file__))
START = date(2026, 11, 2)


def contact(**over):
    row = {
        "contact_id": "t-001", "first_name": "Ada", "title": "Head of Revenue Operations",
        "email": "ada@test-co.example", "company_name": "Test Co", "domain": "test-co.example",
        "timezone": "Europe/Berlin", "crm_status": "none", "last_contacted_days": "",
        "opted_out": "no", "email_status": "valid", "signals": "hiring|5|a RevOps lead",
    }
    row.update(over)
    return row


class Rules(unittest.TestCase):
    def outcome(self, **over):
        ready, review, held = so.build([contact(**over)], START)
        if ready:
            return "ready", ""
        if review:
            return "review", review[0]["problems"]
        return held[0]["stage"], held[0]["reason"]

    def test_clean_row_is_ready(self):
        self.assertEqual(self.outcome()[0], "ready")

    def test_gate_rules(self):
        cases = {
            "opted out": {"opted_out": "yes"},
            "existing customer": {"crm_status": "customer"},
            "open deal, owned by an AE": {"crm_status": "open_deal"},
            "contacted in the last 30 days": {"last_contacted_days": "29"},
            "personal email": {"domain": "gmail.com", "email": "ada@gmail.com"},
            "email status invalid": {"email_status": "invalid"},
            "title matches no persona, check by hand": {"title": "Office Manager"},
        }
        for reason, over in cases.items():
            with self.subTest(reason):
                self.assertEqual(self.outcome(**over), ("gate", reason))

    def test_cooldown_boundary(self):
        self.assertEqual(self.outcome(last_contacted_days="30")[0], "ready")

    def test_freshness(self):
        self.assertEqual(self.outcome(signals="hiring|21|x")[0], "ready")      # full weight, 3
        self.assertEqual(self.outcome(signals="hiring|22|x")[0], "signal")     # half weight, 1.5
        self.assertEqual(self.outcome(signals="hiring|46|x")[1],
                         "nurture, no signal in the last 45 days")

    def test_extra_signal_counts_only_while_fresh(self):
        fresh, score = so.pick_signal(so.parse_signals("hiring|9|a;tech_change|30|b"))
        self.assertEqual((fresh["type"], score), ("hiring", 3))
        _, score = so.pick_signal(so.parse_signals("hiring|9|a;event|12|b"))
        self.assertEqual(score, 4)

    def test_tie_goes_to_fresher_signal(self):
        best, _ = so.pick_signal(so.parse_signals("hiring|15|old;tech_change|3|new"))
        self.assertEqual(best["detail"], "new")

    def test_copy_check(self):
        self.assertEqual(self.outcome(signals="content|5|a free webinar")[0], "review")
        self.assertEqual(self.outcome(email_status="risky")[0], "review")
        self.assertEqual(self.outcome(signals="content|5|a freelance network")[0], "ready")

    def test_every_bridge_fits_every_detail_in_the_data(self):
        # the line after the opener must not claim more than the signal says, e.g. a CRM move
        for line in so.BRIDGE.values():
            self.assertNotIn("CRM", line)

    def test_bad_signal_is_held_not_guessed(self):
        self.assertEqual(self.outcome(signals="hiring|five|x")[0], "clean")
        self.assertEqual(self.outcome(signals="rumour|3|x")[0], "clean")

    def test_duplicates_ignore_case(self):
        rows = [contact(), contact(contact_id="t-002", email="ADA@test-co.example")]
        ready, _, held = so.build(rows, START)
        self.assertEqual(len(ready), 1)
        self.assertEqual(held[0]["reason"], "duplicate of t-001")

    def test_two_people_one_company_start_on_different_days(self):
        rows = [contact(), contact(contact_id="t-002", email="bo@test-co.example", first_name="Bo")]
        ready, _, _ = so.build(rows, START)
        self.assertEqual(sorted(r["step1_date"] for r in ready), ["2026-11-02", "2026-11-03"])

    def test_send_time_is_local(self):
        ready, _, _ = so.build([contact(timezone="Europe/London")], START)
        self.assertEqual(ready[0]["step1_utc"], "2026-11-02 08:30")


class FullRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(HERE, "data", "contacts_synthetic.csv"), newline="") as f:
            rows = list(csv.DictReader(f))
        cls.n = len(rows)
        cls.ready, cls.review, cls.held = so.build(rows, START)

    def test_every_row_accounted_for(self):
        self.assertEqual(len(self.ready) + len(self.review) + len(self.held), self.n)

    def test_nobody_held_is_ready(self):
        held = {h["contact_id"] for h in self.held}
        self.assertFalse(held & {r["contact_id"] for r in self.ready})

    def test_one_company_per_day_and_cap(self):
        per_company_day = Counter((r["domain"], r["step1_date"]) for r in self.ready)
        self.assertLessEqual(max(per_company_day.values()), so.PER_COMPANY_PER_DAY)
        per_day = Counter(r["step1_date"] for r in self.ready)
        self.assertLessEqual(max(per_day.values()), so.DAILY_CAP)

    def test_weekdays_only_and_follow_ups_in_order(self):
        for r in self.ready:
            for key in ("step1_date", "step2_date", "step3_date"):
                self.assertLess(date.fromisoformat(r[key]).weekday(), 5)
            self.assertTrue(r["step1_date"] < r["step2_date"] < r["step3_date"])

    def test_ready_copy_passes_its_own_check(self):
        for r in self.ready:
            self.assertEqual(so.check_copy(r, {"email_status": "valid"}), [])


if __name__ == "__main__":
    unittest.main()
