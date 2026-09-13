# Store credit as a payment method
- id: project-9-store-credit
- type: project
- priority: 9
- status: blocked
- blocked_reason:
- intro:
- timeline
  - start: 2026-08-11
  - end: 2026-11-05
  - tasks
    - task-1
      - who: Alan Turing
      - start: 2026-08-11
      - end: 2026-11-05
      - note: payment orchestrator
- dates
  - target_delivery: 2026-11-05
  - deadline_text: 2026-11-05
  - deadline_type: soft
- tech_footprint
  - platforms
    - iOS
    - Android
    - Backend (dev)
  - qa_effort: high
  - content_impact: false
- stakeholders
  - tech_lead: stakeholder-alan-turing
- dependencies
  - upstream
    - upstream-1
      - project_or_service: Payment orchestrator
      - team: Payments
      - contact: stakeholder-alan-turing
      - criticality: high
- jira
  - request: NIMBUS-1180

## Notes

Blocked with no reason recorded on purpose: the status pill must render
without a hover tooltip, and the empty intro must show its empty state.
