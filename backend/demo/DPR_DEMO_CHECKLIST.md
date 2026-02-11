# CareSync DPR Demo Checklist (9-Step Flow)

## Setup
- Start app: `cd /Users/suhas/Developer/Clavis/backend && python3 -m uvicorn main:app --reload --port 8000`
- Reset data: `curl http://localhost:8000/demo/reset`
- Login page: `http://localhost:8000/login`

## Demo Accounts
- Doctor: `doctor@clavis.local / doctor123`
- Nurse: `nurse@clavis.local / nurse123`
- Pharmacist: `pharmacy@clavis.local / pharmacy123`
- Lab Tech: `lab@clavis.local / lab123`
- Radiology: `radiology@clavis.local / radiology123`
- Admin: `admin@clavis.local / admin123`

## 9 Steps
1. Doctor login and open patient thread.
   - URL: `/patients/1/view`
   - Verify computed summary card is visible and shows no active actions initially.

2. Doctor creates diagnostic request.
   - Type: `DIAGNOSTIC`
   - Title: `Chest X-Ray`
   - Priority: `URGENT`
   - Verify routed to `Radiology`.

3. Doctor creates medication.
   - Type: `MEDICATION`
   - Title: `Amoxicillin 500mg`
   - Priority: `ROUTINE`
   - Verify state is `PRESCRIBED` and queue is `Pharmacy`.

4. Radiology queue live update.
   - Login as radiology in another tab.
   - URL: `/departments/Radiology/view`
   - Transition `Chest X-Ray`: `REQUESTED -> PROCESSING`.
   - Verify doctor tab updates in real time.

5. Pharmacy dispenses medication.
   - Login as pharmacist tab.
   - URL: `/departments/Pharmacy/view`
   - Transition medication: `PRESCRIBED -> DISPENSED`.

6. Nursing administers medication.
   - Login as nurse tab.
   - URL: `/departments/Nursing/view`
   - Transition medication: `DISPENSED -> ADMINISTERED`.

7. Radiology completes diagnostic with notes.
   - Back to radiology tab.
   - Transition: `PROCESSING -> COMPLETED`
   - Add notes: `Bilateral infiltrates noted — suggest follow-up CT`.

8. SLA escalation (optional).
   - Use admin view: `/status-board/view`.
   - Optional API demo: set one active action `sla_deadline` to past in DB, then open `/actions/escalations`.

9. Final computed summary.
   - Return to doctor tab `/patients/1/view`.
   - Verify summary reflects completed medication and diagnostic, plus current overdue count.
