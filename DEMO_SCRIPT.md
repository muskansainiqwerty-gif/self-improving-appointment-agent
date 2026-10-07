# Loom demo cheat-sheet (about 4 minutes)

Setup: two terminals in this folder, close other tabs, never show `.env`. Free Loom = 5 min max.

| Time | Do | Say |
|---|---|---|
| 0:00 | Open README.md | "A scheduling agent plus an eval harness that improves it from its own failures." |
| 0:20 | `python3 -m agent.chat` | "A real conversation." |
| 0:30 | Type: `I need a dermatologist on Friday` | "Slots come from the clinic tool, not invented." |
| 1:00 | Type: `That sounds good` | "A vague reply doesn't book. It asks for the exact slot." |
| 1:20 | Type: `Yes, book Dr. Maya Patel at 3:30 PM on Friday` | "It only says booked after the tool reports success." Then Ctrl-C. |
| 1:50 | Open `runs/before_after_transcripts.md` | "v1 asked for confirmation twice, so the booking never ran. The eval caught that." |
| 2:30 | Open `runs/loop_report.md` | "The improver wrote these three rules; I re-ran all 16 scenarios." |
| 3:00 | Show the table | "78.1% to 88.5%, no scenario regressed." |
| 3:20 | `python3 -m unittest discover tests` | "18 offline tests, no API key needed." |
| 3:40 | Open DESIGN.md, Known limits | "cancel_happy still fails, and the gate doesn't verify an explicit yes." |

Say this out loud: "The full loop takes about two hours, so I'm showing saved results from the real run."
Do NOT present the loop as running live.

Chat tips: "You" starts with one existing appointment (Dr. Okafor, Tue Oct 13, 2 PM). The model is on a free tier, so a slow reply is normal. If you see an `[error]` about quota, wait and retry.
