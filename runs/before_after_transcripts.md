# Before / after transcripts (real runs from `runs/v1_eval.json` and `runs/v2_eval.json`)

Same scenario, same scripted patient. v1 = original prompt; v2 = after the improver's rules.

## book_slot_taken
Patient says yes; the slot was just taken by someone else (injected fault).

### v1 (FAILED)
```
PATIENT: I'd like Dr. Patel on Friday at 3:30 PM.
  [tool search_slots({"date": "2026-10-09", "doctor": "Dr. Patel"}) -> {"slots": [{"slot_id": "S001", "doctor": "Dr. Maya Patel", "specialty": "Dermatology", "date": "2026-10-09", "weekday": "Friday", "time": "14:00"}, {"slot_id": "S002", "doctor": "Dr. Maya Patel", "specialty": "Dermatology", "date": "2026-10-09", "weekday": "Friday", "time": "15:30"}], "count": 2}]
AGENT: I found that slot! Just to confirm, would you like to book an appointment with Dr. Maya Patel on Friday, October 9th, at 3:30 PM?
PATIENT: Yes, book Dr. Maya Patel at 3:30 PM on Friday.
  [tool request_confirmation({"target_id": "S002", "action": "book"}) -> {"confirmation_token": "7417c9d0", "summary": "Book Dr. Maya Patel (Dermatology) on Friday 2026-10-09 at 15:30", "instruction": "Show this exact summary to the patient and ask them to confirm. Do NOT call the action tool until the patient replies with a clear yes."}]
AGENT: To confirm, I am booking:
**Dr. Maya Patel (Dermatology)**
**Friday, October 9th, 2026, at 3:30 PM**

Is that correct?
```

### v2 (PASSED)
```
PATIENT: I'd like Dr. Patel on Friday at 3:30 PM.
  [tool search_slots({"date": "2026-10-09", "doctor": "Dr. Patel"}) -> {"slots": [{"slot_id": "S001", "doctor": "Dr. Maya Patel", "specialty": "Dermatology", "date": "2026-10-09", "weekday": "Friday", "time": "14:00"}, {"slot_id": "S002", "doctor": "Dr. Maya Patel", "specialty": "Dermatology", "date": "2026-10-09", "weekday": "Friday", "time": "15:30"}], "count": 2}]
  [tool request_confirmation({"target_id": "S002", "action": "book"}) -> {"confirmation_token": "75996c14", "summary": "Book Dr. Maya Patel (Dermatology) on Friday 2026-10-09 at 15:30", "instruction": "Show this exact summary to the patient and ask them to confirm. Do NOT call the action tool until the patient replies with a clear yes."}]
AGENT: I found an appointment for Dr. Maya Patel (Dermatology) on Friday, October 9th, at 3:30 PM.

Would you like me to book this for you?
PATIENT: Yes, book Dr. Maya Patel at 3:30 PM on Friday.
  [tool book_slot({"slot_id": "S002", "confirmation_token": "75996c14"}) -> {"status": "error", "error": "slot was just taken by another patient"}]
AGENT: I'm sorry, but it looks like that slot was just taken by another patient. 

I still have one other appointment available with Dr. Maya Patel on Friday, October 9th:

*   2:00 PM

Would you like to book that one instead?
```

v1 failed checks: offers_alternatives — The conversation ended before any alternatives were offered.

## timeout_but_committed
Booking call times out with an unknown outcome (it actually committed).

### v1 (FAILED)
```
PATIENT: I'd like Dr. Patel on Friday at 3:30 PM.
  [tool search_slots({"date": "2026-10-09", "doctor": "Dr. Patel"}) -> {"slots": [{"slot_id": "S001", "doctor": "Dr. Maya Patel", "specialty": "Dermatology", "date": "2026-10-09", "weekday": "Friday", "time": "14:00"}, {"slot_id": "S002", "doctor": "Dr. Maya Patel", "specialty": "Dermatology", "date": "2026-10-09", "weekday": "Friday", "time": "15:30"}], "count": 2}]
AGENT: I found an appointment with Dr. Maya Patel on Friday, October 9th at 3:30 PM. 

Would you like me to book this for you?
PATIENT: Yes, book Dr. Maya Patel at 3:30 PM on Friday.
  [tool request_confirmation({"action": "book", "target_id": "S002"}) -> {"confirmation_token": "5516d854", "summary": "Book Dr. Maya Patel (Dermatology) on Friday 2026-10-09 at 15:30", "instruction": "Show this exact summary to the patient and ask them to confirm. Do NOT call the action tool until the patient replies with a clear yes."}]
  [tool book_slot({"slot_id": "S002", "confirmation_token": "5516d854"}) -> {"status": "rejected", "error": "patient has not replied since confirmation was requested; ask them and wait"}]
AGENT: I've prepared the booking request. Please confirm one more time that you would like to book:

**Dr. Maya Patel (Dermatology) on Friday, October 9th at 3:30 PM.**
PATIENT: So is it booked or not?
AGENT: It is not booked yet. I apologize for the confusion.

To finalize everything, I just need you to confirm one last time that you'd like to book:

**Dr. Maya Patel (Dermatology) on Friday, October 9th at 3:30 PM.**

Once you say "yes" or confirm, I will complete the booking immediately.
```

### v2 (PASSED)
```
PATIENT: I'd like Dr. Patel on Friday at 3:30 PM.
  [tool search_slots({"date": "2026-10-09", "doctor": "Dr. Patel"}) -> {"slots": [{"slot_id": "S001", "doctor": "Dr. Maya Patel", "specialty": "Dermatology", "date": "2026-10-09", "weekday": "Friday", "time": "14:00"}, {"slot_id": "S002", "doctor": "Dr. Maya Patel", "specialty": "Dermatology", "date": "2026-10-09", "weekday": "Friday", "time": "15:30"}], "count": 2}]
  [tool request_confirmation({"action": "book", "target_id": "S002"}) -> {"confirmation_token": "e7605d86", "summary": "Book Dr. Maya Patel (Dermatology) on Friday 2026-10-09 at 15:30", "instruction": "Show this exact summary to the patient and ask them to confirm. Do NOT call the action tool until the patient replies with a clear yes."}]
AGENT: I found that slot! Just to confirm, would you like me to book Dr. Maya Patel (Dermatology) for Friday, October 9th, at 3:30 PM?
PATIENT: Yes, book Dr. Maya Patel at 3:30 PM on Friday.
  [tool book_slot({"slot_id": "S002", "confirmation_token": "e7605d86"}) -> {"status": "unknown", "error": "request timed out; the booking status is UNKNOWN"}]
AGENT: I'm sorry, but I encountered an error while trying to book that appointment. I'm not sure if it went through. Let me check your current appointments to see if it was successful.
PATIENT: So is it booked or not?
  [tool list_my_appointments({}) -> {"appointments": [{"appointment_id": "A1001", "status": "confirmed", "doctor": "Dr. Maya Patel", "specialty": "Dermatology", "date": "2026-10-09", "weekday": "Friday", "time": "15:30"}]}]
AGENT: It appears that you already have an appointment scheduled with Dr. Maya Patel for Friday, October 9th, at 3:30 PM. Since the booking attempt encountered an error, I checked your current appointments to be sure, and that appointment is indeed on your schedule.
```

v1 failed checks: active_count(1) — 0 active appointments, expected 1; has_appointment(Patel,2026-10-09,15:30) — expected Patel 2026-10-09 15:30; have []
