"""Tool declarations exposed to the model, and the dispatcher that binds them to the clinic backend."""
from __future__ import annotations

from google.genai import types

from sim.clinic import Clinic

S = types.Schema
T = types.Type


def _decl(name, desc, props, required=()):
    return types.FunctionDeclaration(
        name=name, description=desc,
        parameters=S(type=T.OBJECT, properties=props, required=list(required)))


DECLARATIONS = types.Tool(function_declarations=[
    _decl("search_slots",
          "Search available appointment slots. All filters optional. Dates are YYYY-MM-DD. "
          "Only returns bookable future slots; this is the only source of availability.",
          {"specialty": S(type=T.STRING, description="e.g. Dermatology, Cardiology, General Practice"),
           "doctor": S(type=T.STRING, description="doctor name"),
           "date": S(type=T.STRING, description="YYYY-MM-DD"),
           "time_of_day": S(type=T.STRING, enum=["morning", "afternoon"])}),
    _decl("list_my_appointments",
          "List the patient's current confirmed appointments (with appointment IDs). "
          "Use to identify an appointment to change, or to verify state after an uncertain tool result.", {}),
    _decl("request_confirmation",
          "Step 1 of any booking, cancellation or reschedule. Returns an exact summary and a confirmation_token. "
          "Show the summary to the patient and wait for their clear 'yes' in a LATER message before using the action tool. "
          "For book: target_id=slot_id. For cancel: target_id=appointment_id. "
          "For reschedule: target_id=appointment_id and new_slot_id=slot_id.",
          {"action": S(type=T.STRING, enum=["book", "cancel", "reschedule"]),
           "target_id": S(type=T.STRING),
           "new_slot_id": S(type=T.STRING)}, ["action", "target_id"]),
    _decl("book_slot", "Book a slot. Requires the confirmation_token from request_confirmation(action=book) AND the patient's explicit yes.",
          {"slot_id": S(type=T.STRING), "confirmation_token": S(type=T.STRING)}, ["slot_id", "confirmation_token"]),
    _decl("cancel_appointment", "Cancel an appointment. Requires a confirmation_token (action=cancel) AND the patient's explicit yes.",
          {"appointment_id": S(type=T.STRING), "confirmation_token": S(type=T.STRING)},
          ["appointment_id", "confirmation_token"]),
    _decl("reschedule_appointment",
          "Atomically move an appointment to a new slot (the original is kept if the new slot can't be secured). "
          "Requires a confirmation_token (action=reschedule) AND the patient's explicit yes.",
          {"appointment_id": S(type=T.STRING), "new_slot_id": S(type=T.STRING), "confirmation_token": S(type=T.STRING)},
          ["appointment_id", "new_slot_id", "confirmation_token"]),
])

MUTATIONS = {"book_slot", "cancel_appointment", "reschedule_appointment"}


def dispatch(clinic: Clinic, name: str, args: dict, turn: int) -> dict:
    """Run a tool call against the backend and record it in clinic.log (the eval's ground truth)."""
    try:
        if name == "search_slots":
            res = clinic.search_slots(**{k: args.get(k) for k in ("specialty", "doctor", "date", "time_of_day")})
        elif name == "list_my_appointments":
            res = clinic.list_my_appointments()
        elif name == "request_confirmation":
            res = clinic.issue_token(args.get("action"), args.get("target_id"), args.get("new_slot_id"), turn)
        elif name == "book_slot":
            res = clinic.book_slot(args.get("slot_id"), args.get("confirmation_token"), turn)
        elif name == "cancel_appointment":
            res = clinic.cancel_appointment(args.get("appointment_id"), args.get("confirmation_token"), turn)
        elif name == "reschedule_appointment":
            res = clinic.reschedule_appointment(args.get("appointment_id"), args.get("new_slot_id"),
                                                args.get("confirmation_token"), turn)
        else:
            res = {"error": f"unknown tool {name}"}
    except Exception as e:  # noqa: BLE001  (model passed bad args; report, don't crash)
        res = {"status": "error", "error": f"bad arguments: {e}"}
    clinic.log.append({"turn": turn, "tool": name, "args": args, "result": res})
    return res
