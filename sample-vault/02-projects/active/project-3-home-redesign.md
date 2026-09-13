# Home page redesign
- id: project-3-home-redesign
- type: project
- priority: 3
- status: active
- intro: Full rebrand of the home page, including the top banner and the new editorial modules.
- timeline
  - start: 2026-09-01
  - end: 2026-10-15
  - tasks
    - task-1
      - who: Nikola Tesla
      - start: 2026-09-01
      - end: 2026-10-13
      - flags
        - active
      - note: home modules
    - task-2
      - who: Barbara McClintock
      - start: 2026-09-01
      - end: 2026-10-13
      - flags
        - active
      - note: home modules
    - task-3
      - who: Jean Bartik
      - start: 2026-10-05
      - end: 2026-10-15
      - note: A/B validation
- dates
  - target_delivery: 2026-10-20
  - deadline_text: mid October
  - deadline_type: soft
- tech_footprint
  - platforms
    - iOS
    - Android
    - Content
    - QA
  - qa_effort: high
  - content_impact: true
- stakeholders
  - business_owner: stakeholder-mary-jackson
  - tech_lead: stakeholder-nikola-tesla
- dependencies
  - upstream
    - upstream-1
      - project_or_service: Design system 3.0
      - team: Design Systems
      - contact: stakeholder-hedy-lamarr
      - criticality: medium
  - downstream
    - downstream-1
      - project_or_service: Push campaign templates
      - team: CRM
      - contact: stakeholder-mary-jackson
      - criticality: low
- risks_and_criticalities
  - RISK-01
    - description: A/B test window overlaps with the peak season freeze
    - severity: medium
    - mitigation: Run the test two weeks earlier
    - owner: stakeholder-nikola-tesla
- planning_factors
  - team_capacity_needed: 2 iOS + 2 Android, ~5 weeks
  - critical_path: Design system tokens → module build → A/B test
- jira
  - request: NIMBUS-1120
  - epics
    - NIMBUS-1121
- confluence
  - https://confluence.example.com/display/HOME/Redesign-brief
- figma
  - https://www.figma.com/design/cccc1111/Home-redesign
- todos
  - todo-project-3-home-redesign-1-1788000020
    - text:
      ```md
      Review the copy deck with marketing:
      the hero claim is still the old one.
      Reference: https://confluence.example.com/display/HOME/Copy "final v3"
      ```
    - deadline: 2026-09-22
- done
  - todo-project-3-home-redesign-2-1787000020
    - text: Freeze the module list for release 8.4
    - deadline: 2026-09-04
    - completed_at: 2026-09-04 11:15
  - todo-project-3-home-redesign-3-1787000021
    - text: Align with the web team on the banner ratio
    - deadline:
    - completed_at: 2026-08-29 09:02

## Notes

The A/B test needs at least two full weeks of traffic.
