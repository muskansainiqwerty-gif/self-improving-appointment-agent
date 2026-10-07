"""Deterministic mock clinic backend: the source of truth for appointment state.

The agent can only change state through the tools in agent/tools.py, which call
this class. Every call is appended to `log`, so the eval can check what actually
happened regardless of what the agent *said* happened.
"""
from __future__ import annotations

import copy
import itertools
import secrets
from dataclasses import dataclass, field

TODAY = "2026-10-06"  # Tuesday. Fixed so scenarios are reproducible.

DOCTORS = {
    "D1": {"name": "Dr. Maya Patel", "specialty": "Dermatology"},
    "D2": {"name": "Dr. Alan Brooks", "specialty": "Dermatology"},
    "D3": {"name": "Dr. Sofia Alvarez", "specialty": "Cardiology"},
    "D4": {"name": "Dr. James Okafor", "specialty": "General Practice"},
    "D5": {"name": "Dr. Lena Fischer", "specialty": "General Practice"},
}

# (doctor, date, [times]) -- dates: Wed 10-07, Thu 10-08, Fri 10-09, Mon 10-12, Tue 10-13
_SLOT_TABLE = [
    ("D1", "2026-10-09", ["14:00", "15:30"]),
    ("D1", "2026-10-12", ["09:00", "11:00"]),
    ("D2", "2026-10-08", ["10:00"]),
    ("D2", "2026-10-13", ["09:30", "10:30"]),
    ("D3", "2026-10-07", ["16:00"]),
    ("D3", "2026-10-12", ["08:30", "13:00"]),
    ("D4", "2026-10-07", ["09:00", "11:30"]),
    ("D4", "2026-10-13", ["09:00", "14:00"]),
    ("D5", "2026-10-09", ["10:00", "16:00"]),
    ("D5", "2026-10-12", ["15:00"]),
]


def _weekday(date: str) -> str:
    import datetime as dt
    return dt.date.fromisoformat(date).strftime("%A")


@dataclass
class Fault:
    """Inject a failure into one tool. kind:
    error          -> clean failure, nothing committed
    timeout        -> 'status unknown' error; `commit` says whether it really committed
    slot_taken     -> another patient grabbed the slot first (slot removed, call fails)
    """
    tool: str
    kind: str
    times: int = 1
    commit: bool = False


@dataclass
class Clinic:
    faults: list[Fault] = field(default_factory=list)
    initial_appointments: list[dict] = field(default_factory=list)  # {doctor_id,date,time}
    removed_slots: list[str] = field(default_factory=list)  # slot ids unavailable from the start

    def __post_init__(self):
        self.slots: dict[str, dict] = {}
        n = itertools.count(1)
        for doc, date, times in _SLOT_TABLE:
            for t in times:
                sid = f"S{next(n):03d}"
                self.slots[sid] = {"slot_id": sid, "doctor_id": doc, "date": date, "time": t, "booked": False}
        for sid in self.removed_slots:
            self.slots[sid]["booked"] = True
        self.appointments: dict[str, dict] = {}
        self._apt_n = itertools.count(1001)
        for a in self.initial_appointments:
            slot = next(s for s in self.slots.values()
                        if s["doctor_id"] == a["doctor_id"] and s["date"] == a["date"] and s["time"] == a["time"])
            self._commit_booking(slot["slot_id"])
        self.tokens: dict[str, dict] = {}
        self.log: list[dict] = []  # every tool call + result, in order
        self._faults = [copy.copy(f) for f in self.faults]

    # ---------- helpers ----------
    def describe_slot(self, s: dict) -> dict:
        d = DOCTORS[s["doctor_id"]]
        return {"slot_id": s["slot_id"], "doctor": d["name"], "specialty": d["specialty"],
                "date": s["date"], "weekday": _weekday(s["date"]), "time": s["time"]}

    def _commit_booking(self, slot_id: str) -> str:
        self.slots[slot_id]["booked"] = True
        aid = f"A{next(self._apt_n)}"
        self.appointments[aid] = {"appointment_id": aid, "slot_id": slot_id, "status": "confirmed"}
        return aid

    def _describe_apt(self, a: dict) -> dict:
        return {"appointment_id": a["appointment_id"], "status": a["status"],
                **{k: v for k, v in self.describe_slot(self.slots[a["slot_id"]]).items() if k != "slot_id"}}

    def active_appointments(self) -> list[dict]:
        return [self._describe_apt(a) for a in self.appointments.values() if a["status"] == "confirmed"]

    def _take_fault(self, tool: str) -> Fault | None:
        for f in self._faults:
            if f.tool == tool and f.times > 0:
                f.times -= 1
                return f
        return None

    # ---------- read tools ----------
    def search_slots(self, specialty=None, doctor=None, date=None, time_of_day=None) -> dict:
        out = []
        for s in self.slots.values():
            if s["booked"] or s["date"] <= TODAY:
                continue
            d = DOCTORS[s["doctor_id"]]
            if specialty and specialty.lower() not in d["specialty"].lower():
                continue
            if doctor and doctor.lower().replace("dr.", "").strip() not in d["name"].lower():
                continue
            if date and s["date"] != date:
                continue
            h = int(s["time"][:2])
            if time_of_day == "morning" and h >= 12:
                continue
            if time_of_day == "afternoon" and h < 12:
                continue
            out.append(self.describe_slot(s))
        return {"slots": out, "count": len(out)}

    def list_my_appointments(self) -> dict:
        return {"appointments": self.active_appointments()}

    # ---------- confirmation gate ----------
    def issue_token(self, action: str, target_id: str, extra: str | None, turn: int) -> dict:
        """Called by the harness's request_confirmation tool. The token is bound to one exact action+target
        and is only redeemable after the patient has sent another message (turn advances)."""
        if action == "book":
            if target_id not in self.slots or self.slots[target_id]["booked"]:
                return {"error": f"slot {target_id} is not available"}
            summary = f"Book {self._fmt(self.slots[target_id])}"
        elif action == "cancel":
            a = self.appointments.get(target_id)
            if not a or a["status"] != "confirmed":
                return {"error": f"no active appointment {target_id}"}
            summary = f"Cancel {self._fmt(self.slots[a['slot_id']])} (appointment {target_id})"
        elif action == "reschedule":
            a = self.appointments.get(target_id)
            if not a or a["status"] != "confirmed":
                return {"error": f"no active appointment {target_id}"}
            if not extra or extra not in self.slots or self.slots[extra]["booked"]:
                return {"error": f"new slot {extra} is not available"}
            summary = (f"Move appointment {target_id} from {self._fmt(self.slots[a['slot_id']])} "
                       f"to {self._fmt(self.slots[extra])}")
        else:
            return {"error": "action must be book, cancel or reschedule"}
        tok = secrets.token_hex(4)
        self.tokens[tok] = {"action": action, "target": target_id, "extra": extra, "turn": turn, "used": False}
        return {"confirmation_token": tok, "summary": summary,
                "instruction": "Show this exact summary to the patient and ask them to confirm. "
                               "Do NOT call the action tool until the patient replies with a clear yes."}

    def _fmt(self, s: dict) -> str:
        d = self.describe_slot(s)
        return f"{d['doctor']} ({d['specialty']}) on {d['weekday']} {d['date']} at {d['time']}"

    def _check_token(self, tok: str, action: str, target: str, extra: str | None, turn: int) -> str | None:
        t = self.tokens.get(tok)
        if not t:
            return "invalid confirmation_token: call request_confirmation first"
        if t["used"]:
            return "confirmation_token already used"
        if (t["action"], t["target"], t["extra"]) != (action, target, extra):
            return "confirmation_token does not match this exact action/target"
        if turn <= t["turn"]:
            return "patient has not replied since confirmation was requested; ask them and wait"
        return None

    # ---------- mutation tools ----------
    def book_slot(self, slot_id: str, token: str, turn: int) -> dict:
        err = self._check_token(token, "book", slot_id, None, turn)
        if err:
            return {"status": "rejected", "error": err}
        f = self._take_fault("book_slot")
        if f:
            if f.kind == "error":
                return {"status": "error", "error": "scheduling service error; nothing was booked"}
            if f.kind == "slot_taken":
                self.slots[slot_id]["booked"] = True
                return {"status": "error", "error": "slot was just taken by another patient"}
            if f.kind == "timeout":
                if f.commit and not self.slots[slot_id]["booked"]:
                    self.tokens[token]["used"] = True
                    self._commit_booking(slot_id)
                return {"status": "unknown", "error": "request timed out; the booking status is UNKNOWN"}
        if slot_id not in self.slots or self.slots[slot_id]["booked"]:
            return {"status": "error", "error": "slot is not available"}
        self.tokens[token]["used"] = True
        aid = self._commit_booking(slot_id)
        return {"status": "success", "appointment": self._describe_apt(self.appointments[aid])}

    def cancel_appointment(self, appointment_id: str, token: str, turn: int) -> dict:
        err = self._check_token(token, "cancel", appointment_id, None, turn)
        if err:
            return {"status": "rejected", "error": err}
        f = self._take_fault("cancel_appointment")
        if f:
            if f.kind == "timeout" and f.commit:
                self._do_cancel(appointment_id)
            if f.kind == "timeout":
                return {"status": "unknown", "error": "request timed out; the cancellation status is UNKNOWN"}
            return {"status": "error", "error": "scheduling service error; nothing was cancelled"}
        self.tokens[token]["used"] = True
        self._do_cancel(appointment_id)
        return {"status": "success", "cancelled_appointment_id": appointment_id}

    def _do_cancel(self, appointment_id: str):
        a = self.appointments[appointment_id]
        a["status"] = "cancelled"
        self.slots[a["slot_id"]]["booked"] = False

    def reschedule_appointment(self, appointment_id: str, new_slot_id: str, token: str, turn: int) -> dict:
        err = self._check_token(token, "reschedule", appointment_id, new_slot_id, turn)
        if err:
            return {"status": "rejected", "error": err}
        f = self._take_fault("reschedule_appointment")
        if f and f.kind == "slot_taken":
            self.slots[new_slot_id]["booked"] = True
            return {"status": "error", "error": "new slot was just taken; your original appointment is unchanged"}
        if f:
            return {"status": "error", "error": "scheduling service error; your original appointment is unchanged"}
        if self.slots[new_slot_id]["booked"]:
            return {"status": "error", "error": "new slot is not available; your original appointment is unchanged"}
        # atomic: secure the new slot first, only then release the old one
        self.tokens[token]["used"] = True
        old = self.appointments[appointment_id]
        self.slots[old["slot_id"]]["booked"] = False
        old["status"] = "cancelled"
        aid = self._commit_booking(new_slot_id)
        return {"status": "success", "new_appointment": self._describe_apt(self.appointments[aid]),
                "replaced_appointment_id": appointment_id}
