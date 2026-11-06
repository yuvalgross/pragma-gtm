"""Guards for the rules that must never move. python3 -m unittest test_crm_cleanup"""
import os
import unittest
from collections import Counter
from datetime import date

import crm_cleanup as cc
import make_synthetic_crm

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


class Rules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        make_synthetic_crm.main(DATA)
        cls.log, cls.book, cls.owners, cls.companies, cls.deals = cc.run(DATA, date(2026, 11, 6))
        cls.rows = cls.log.rows

    def test_merges_and_owner_changes_are_never_auto(self):
        for r in self.rows:
            if r["field"] in ("merge", "hubspot_owner_id"):
                self.assertNotEqual(r["tier"], "auto", r)

    def test_name_only_matches_go_to_a_person(self):
        for r in self.rows:
            if r["field"] == "merge" and "same name" in r["reason"]:
                self.assertEqual(r["tier"], "review", r)

    def test_primary_keeps_the_deals(self):
        deals = Counter(d["company_id"] for d in self.deals)
        for r in self.rows:
            if r["object"] == "company" and r["field"] == "merge":
                self.assertGreaterEqual(deals[r["new"]], deals[r["old"]], r)

    def test_auto_changes_log_the_old_value(self):
        for r in self.rows:
            if r["tier"] == "auto":
                self.assertTrue(r["old"], r)

    def test_payloads_hold_only_auto_and_approve(self):
        ids = {r["record_id"] for r in self.rows if r["tier"] in ("auto", "approve")}
        p = cc.payloads(self.log)
        for u in p["updates"]:
            for i in u["body"]["inputs"]:
                self.assertIn(i["id"], ids)
        for m in p["merges"]:
            self.assertIn(m["body"]["objectIdToMerge"], ids)

    def test_strategic_accounts_always_get_a_human(self):
        for r in self.book:
            if r["tier"] == "strategic":
                self.assertEqual(r["channel"], "human", r)

    def test_no_arr_lost_in_the_merge(self):
        self.assertEqual(sum(r["arr_eur"] for r in self.book), sum(c["arr_eur"] for c in self.companies))

    def test_merged_records_leave_the_book(self):
        losers = {r["record_id"] for r in self.rows if r["field"] == "merge" and r["tier"] == "approve"}
        self.assertFalse(losers & {r["company_id"] for r in self.book})


if __name__ == "__main__":
    unittest.main()
