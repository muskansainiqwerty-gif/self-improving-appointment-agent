"""Offline tests for the backend + confirmation gate (no API key needed):  python3 -m unittest discover tests"""
import unittest

from sim.clinic import Clinic, Fault


def tok(c, action, target, extra=None, turn=1):
    return c.issue_token(action, target, extra, turn)["confirmation_token"]


class Gate(unittest.TestCase):
    def test_book_needs_token(self):
        c = Clinic()
        self.assertEqual(c.book_slot("S001", "bogus", 2)["status"], "rejected")

    def test_same_turn_rejected(self):
        c = Clinic(); t = tok(c, "book", "S001", turn=1)
        self.assertEqual(c.book_slot("S001", t, 1)["status"], "rejected")  # patient hasn't replied yet
        self.assertEqual(c.book_slot("S001", t, 2)["status"], "success")

    def test_token_bound_to_target_and_single_use(self):
        c = Clinic(); t = tok(c, "book", "S001")
        self.assertEqual(c.book_slot("S002", t, 2)["status"], "rejected")
        self.assertEqual(c.book_slot("S001", t, 2)["status"], "success")
        self.assertEqual(c.book_slot("S001", t, 3)["status"], "rejected")

    def test_cancel_token_cannot_book(self):
        c = Clinic(initial_appointments=[{"doctor_id": "D4", "date": "2026-10-13", "time": "14:00"}])
        aid = c.active_appointments()[0]["appointment_id"]
        t = tok(c, "cancel", aid)
        self.assertEqual(c.book_slot("S001", t, 2)["status"], "rejected")


class State(unittest.TestCase):
    def test_booked_slot_leaves_search(self):
        c = Clinic(); t = tok(c, "book", "S001"); c.book_slot("S001", t, 2)
        self.assertNotIn("S001", [s["slot_id"] for s in c.search_slots()["slots"]])

    def test_no_double_booking(self):
        c = Clinic(); t1 = tok(c, "book", "S001"); t2 = tok(c, "book", "S001")
        self.assertEqual(c.book_slot("S001", t1, 2)["status"], "success")
        self.assertEqual(c.book_slot("S001", t2, 2)["status"], "error")

    def test_cancel_frees_slot(self):
        c = Clinic(initial_appointments=[{"doctor_id": "D4", "date": "2026-10-13", "time": "14:00"}])
        aid = c.active_appointments()[0]["appointment_id"]
        c.cancel_appointment(aid, tok(c, "cancel", aid), 2)
        self.assertEqual(c.active_appointments(), [])

    def test_reschedule_atomic_success(self):
        c = Clinic(initial_appointments=[{"doctor_id": "D4", "date": "2026-10-13", "time": "14:00"}])
        aid = c.active_appointments()[0]["appointment_id"]
        r = c.reschedule_appointment(aid, "S017", tok(c, "reschedule", aid, "S017"), 2)
        self.assertEqual(r["status"], "success"); self.assertEqual(len(c.active_appointments()), 1)

    def test_reschedule_failure_keeps_original(self):
        c = Clinic(initial_appointments=[{"doctor_id": "D4", "date": "2026-10-13", "time": "14:00"}],
                   faults=[Fault("reschedule_appointment", "slot_taken")])
        aid = c.active_appointments()[0]["appointment_id"]
        r = c.reschedule_appointment(aid, "S017", tok(c, "reschedule", aid, "S017"), 2)
        self.assertEqual(r["status"], "error")
        self.assertEqual([a["time"] for a in c.active_appointments()], ["14:00"])


class Faults(unittest.TestCase):
    def test_timeout_committed_is_unknown_but_booked(self):
        c = Clinic(faults=[Fault("book_slot", "timeout", commit=True)])
        r = c.book_slot("S001", tok(c, "book", "S001"), 2)
        self.assertEqual(r["status"], "unknown"); self.assertEqual(len(c.active_appointments()), 1)

    def test_timeout_not_committed(self):
        c = Clinic(faults=[Fault("book_slot", "timeout", commit=False)])
        r = c.book_slot("S001", tok(c, "book", "S001"), 2)
        self.assertEqual(r["status"], "unknown"); self.assertEqual(c.active_appointments(), [])

    def test_past_and_today_slots_hidden(self):
        self.assertTrue(all(s["date"] > "2026-10-06" for s in Clinic().search_slots()["slots"]))


if __name__ == "__main__":
    unittest.main()
