# Eco labels & durability sheet
- id: project-2-eco-labels
- type: project
- priority: 2
- status: blocked
- blocked_reason: Waiting for the legal text approved by compliance
- intro:
  ```md
  Regulatory requirement: the durability sheet must be reachable from the
  product page in every EU market.

  Legal signed off on the wording on 2026-09-01, the translated copy is
  still missing for 4 markets.
  ```
- timeline
  - start: 2026-08-18
  - end: 2026-11-27
  - tasks
    - task-1
      - who: Enrico Fermi
      - start: 2026-09-21
      - end: 2026-11-27
      - note: durability sheet
    - task-2
      - who: Linus Pauling
      - start: 2026-09-21
      - end: 2026-11-27
      - note: durability sheet
    - task-3
      - who: Margaret Hamilton
      - start: 2026-11-16
      - end: 2026-11-26
      - note: compliance checklist
- dates
  - mandatory_deadline: 2026-12-15
  - target_delivery: 2026-12-01
  - deadline_text: 2026-12-01
  - deadline_type: hard
- tech_footprint
  - platforms
    - iOS
    - Android
    - Content
  - qa_effort: medium
  - content_impact: true
- stakeholders
  - business_owner: stakeholder-mary-jackson
  - tech_lead: stakeholder-rita-levi
  - qa_lead: stakeholder-jean-bartik
- dependencies
  - upstream
    - upstream-1
      - project_or_service: Compliance copy deck
      - team: Legal
      - contact: stakeholder-mary-jackson
      - criticality: high
- risks_and_criticalities
  - RISK-01
    - description: Regulatory deadline cannot move
    - severity: high
    - mitigation: Ship with English copy if translations slip
    - owner: stakeholder-mary-jackson
- planning_factors
  - team_capacity_needed: 1 iOS + 1 Android, ~3 weeks
  - critical_path: Legal copy → client integration
- jira
  - request: NIMBUS-1088
  - epics
    - NIMBUS-1089
- figma
  - https://www.figma.com/design/bbbb1111/Durability-sheet
- todos
  - todo-project-2-eco-labels-1-1788000010
    - text: Chase the 4 missing translations
    - deadline: 2026-09-30

## Notes

Blocked since 2026-09-03. Reassess at the next steering committee.
