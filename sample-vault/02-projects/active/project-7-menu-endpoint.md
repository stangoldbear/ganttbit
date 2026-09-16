# Top categories endpoint
- id: project-7-menu-endpoint
- type: project
- priority: 7
- status: active
- intro: New endpoint for the top categories carousel. No timeline task yet: the expand caret must render disabled.
- dates
  - target_delivery: 2026-12-10
  - deadline_text: 2026-12-10
  - deadline_type: soft
- timeline
  - start: 2026-10-05
  - days: 20
- tech_footprint
  - platforms
    - Backend (dev)
  - qa_effort: low
  - content_impact: false
- jira
  - request: NIMBUS-1244
- todos
  - todo-project-7-menu-endpoint-1-1788000040
    - text: Ask the platform team to schedule the work
    - deadline:

## Notes

Shares priority 3 with project 6 on purpose: the chart numbers rows by
position, so two cards claiming the same priority must still render #3 and #4.

Its bar is the other way of declaring one: a start and a count of working
days, with no end date. The chart draws it like any other, and a form with two
dates has to open on the day that count lands on.
