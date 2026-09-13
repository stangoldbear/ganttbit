# Checkout hardening
- id: project-11-checkout-hardening
- type: project
- priority: 10
- status: on-hold
- intro: Deliberately malformed card: unknown status, non-numeric priority.
- timeline
  - start: 2026-09-28
  - end: 2026-10-14
  - tasks
    - task-1
      - who: Grace Hopper
      - start: 2026-09-28
      - end: 2026-10-14
      - note: checkout hardening
- dates
  - target_delivery: 2026-10-15
  - deadline_text: 2026-10-15
  - deadline_type: whenever
- tech_footprint
  - platforms
    - Backend (dev)
  - qa_effort: medium
  - content_impact: false
- jira
  - request: NIMBUS-1300
- todos
  - todo-project-11-checkout-hardening-1-1788000060
    - text: Fix the status of this card from the Advanced Edit form
    - deadline:

## Notes

Fixture for the fallback paths: the unknown status keeps its stored value
in a disabled option instead
of being silently rewritten, and the non-numeric priority sorts last.
