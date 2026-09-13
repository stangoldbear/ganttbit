# Expected delivery date on order status
- id: project-10-delivery-estimate
- type: project
- priority: 11
- status: done
- intro: Surface the expected delivery date in the order status screen.
- timeline
  - start: 2026-07-20
  - end: 2026-09-12
  - tasks
    - task-1
      - who: Enrico Fermi
      - start: 2026-07-20
      - end: 2026-09-12
      - flags
        - done
      - note: delivery estimate
- dates
  - target_delivery: 2026-09-12
  - deadline_text:
  - deadline_type: soft
- tech_footprint
  - platforms
    - iOS
    - Android
  - qa_effort: low
  - content_impact: false
- jira
  - request: NIMBUS-1099
  - epics
    - NIMBUS-1100
- confluence
  - https://confluence.example.com/display/ORD/Delivery-estimate
- done
  - todo-project-10-delivery-estimate-1-1786000000
    - text: Validate the estimate with the logistics team
    - deadline: 2026-08-14
    - completed_at: 2026-08-14 15:30
  - todo-project-10-delivery-estimate-2-1786000001
    - text: Add the tracking event to the analytics plan
    - deadline:
    - completed_at: 2026-08-20 10:05

## Notes

`deadline_text` is empty on purpose: the badge must fall back to
`target_delivery`, and only then to N/A.
