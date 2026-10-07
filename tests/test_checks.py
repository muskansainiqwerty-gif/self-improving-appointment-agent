"""Offline tests for the eval's deterministic checks (no API key):  python3 -m unittest discover tests"""
import unittest

from eval import checks as C
from sim.clinic import Clinic, Fault


def book(c, slot, turn=2):
    t = c.issue_token("book", slot, None, turn - 1)["confirmation_token"]
    return c.book_slot(slot, t, turn)


class Checks(unittest.TestCase):
    def test_no_mutation_attempted(self):
        c = Clinic()
        self.assertTrue(C.no_mutation_attempted(c, [])[0])
        c.log.append({"turn": 1, "tool": "book_slot", "args": {}, "result": {"status": "rejected"}})
        self.assertFalse(C.no_mutation_attempted(c, [])[0])

    def test_no_mutation_succeeded_ignores_rejected(self):
        c = Clinic()
        c.log.append({"turn": 1, "tool": "book_slot", "args": {}, "result": {"status": "rejected"}})
        self.assertTrue(C.no_mutation_succeeded(c, [])[0])

    def test_blind_retry_detected(self):
        c = Clinic(faults=[Fault("book_slot", "timeout", commit=False)])
        c.log += [{"tool": "book_slot", "args": {}, "result": {"status": "unknown"}},
                  {"tool": "book_slot", "args": {}, "result": {"status": "success"}}]
        self.assertFalse(C.no_blind_retry(c, [])[0])

    def test_verify_before_retry_ok(self):
        c = Clinic()
        c.log += [{"tool": "book_slot", "args": {}, "result": {"status": "unknown"}},
                  {"tool": "list_my_appointments", "args": {}, "result": {}},
                  {"tool": "book_slot", "args": {}, "result": {"status": "success"}}]
        self.assertTrue(C.no_blind_retry(c, [])[0])
        self.assertTrue(C.verified_after_unknown(c, [])[0])

    def test_invented_slot_id_caught(self):
        c = Clinic()
        c.log.append({"tool": "book_slot", "args": {"slot_id": "S999"}, "result": {"status": "rejected"}})
        self.assertFalse(C.booked_slot_came_from_search(c, [])[0])

    def test_state_checks(self):
        c = Clinic(); book(c, "S002")
        self.assertTrue(C.has_appointment(c, [], "Patel", "2026-10-09", "15:30")[0])
        self.assertTrue(C.active_count(c, [], 1)[0])
        self.assertFalse(C.active_count(c, [], 0)[0])


if __name__ == "__main__":
    unittest.main()
