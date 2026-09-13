# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[semantic versioning](https://semver.org/).

## 1.0.0 - 2026-09-13

First public release.

### What it does

- Renders a vault of markdown project cards as an interactive Gantt chart: one
  flat list ordered by `priority`, one row per assigned person, with DONE and
  DROPPED as the two closing groups. Every bar is declared by the card that
  owns it.
- Edits the cards back: name, status, deadlines, platforms,
  Jira/Confluence/Figma links, free-form notes, milestones, attachments of any
  type and an action list with history, saved straight into the vault. A value
  reads as information until you double-click it, and every editor has an
  explicit Save and Cancel.
- Moves and resizes the bars by dragging them, in whole working days, applied
  to the dates the card holds. Reorders projects by drag and drop, finishes one
  by dragging it into DONE, abandons one by dragging it into DROPPED.
- Marks the days that matter: a milestone is a diamond on the project's lane,
  added by clicking an empty day, edited and deleted in place.
- Reads the chart at four depths, Compact, Projects, Stakeholders and All
  details, which are absolute levels rather than toggles, so each one does the
  same thing whatever is folded right now. Compact is one line per project and
  a third shorter than a normal row.
- Draws it at three zooms, Day, Week and Month. A column is always one working
  day and the zoom decides how wide it is drawn. Week looks six months ahead
  and Month two years, unless the window names an end of its own.
- Draws it through a window you choose: from today, the last 30 days, this
  year, all dates, or from a date you pick. The choice travels as `?from=…`.
- Comes back where you left it. The window, everything collapsed or opened and
  both scroll positions, the document's and the chart's own, survive the reload
  a save performs.
- Colours every project by rank. A band runs down the left edge at full accent
  at the top of the list, fading to a near-grey at the bottom, so it is read as
  a ramp down the list and the number beside it is what names a position. Its
  two ends are solved in the browser against the surface of whichever theme is
  on, before the first paint, and hold 4:1 against all 25 of them.
- Carries a Settings overlay behind a button in the footer, in four groups: the
  theme, the priority band, the chart's weekday letters, and whether saving and
  discarding ask first. All of them are per-browser preferences.
- Ships twenty-five themes: System, Light, Dark, and twenty-three palettes
  borrowed from well-known editors, thirteen dark and ten light. A theme is one
  token block in `themes.css` and the picker reads the list back out of that
  stylesheet, so there is no second list to keep in step.
- Shows the whole vault two ways: the chart, and a Hierarchy view whose
  Structure tab lists every value a card holds under the names the card uses,
  including the keys this codebase knows nothing about and the `## Notes` body,
  and whose Markdown tab is every card in one editable document, downloadable
  as the monthly snapshot.
- Searches what the page shows, opens whatever hides a match and marks it.
- Renders the free text people type (headings, lists, bold, italic, code,
  links) escaped before it is transformed.
- Demands a shared access token when bound to anything but loopback; on
  loopback nothing changes and no secret is involved. The 401 page carries a
  token field, so a dashboard reached from the network can be opened from a
  link that has lost its token.

### On a phone

- Below 900px the chart stops being the interface. A bottom tab bar carries
  Projects, Chart, Notes and More over the same cards, and the default is a
  list of project cards with the span, the milestones and what is asking for
  attention. Tapping one opens that project's notes and actions under the card,
  the same panel the chart opens under its row, moved rather than copied.
- Everything a pointing device does has a control beside it, because a finger
  cannot drag: Move up, Move down and Move to for projects, Up and Down for
  notes, and Rename, Move and Advanced edit in the panel header on every
  screen. Reordering from a keyboard works for the first time as a result.
- The page never scrolls sideways. The chart still does, because a timeline is
  wide by nature, inside its own container. Resizing the label column and
  dragging rows to reorder them are hidden on touch.

### The card format

A card is a markdown outline rather than a file with a header: the title is the
project name, every field is a `- key: value` item, a group is two spaces
deeper, a multi-line value is a fenced block, and free text lives under
`## Notes`. Nothing is quoted and nothing is escaped.

`--migrate-vault` converts a vault written in YAML front matter and
`--import-plan` moves a mermaid delivery plan into the cards that own its rows.
Both leave the source untouched or backed up, and both refuse to run twice on
the same file.

### Notable properties

- No dependency and no build step: Python 3.11+ standard library, two
  stylesheets and two scripts. The design language is shadcn/ui, ported by hand
  into custom properties, and light and dark differ by one token block.
- Configuration lives outside the code: squads, roles, links and wording live
  in `settings.toml`, layered over by a git-ignored `settings.local.toml`.
  Running it for a different team needs no Python edit.
- The card schema is declared once and drives the API, its validation and the
  browser form alike.
- Invalid input is refused at the boundary with a 400 rather than stored and
  normalised later, and a stored invalid value is shown as such instead of
  being silently replaced.
- Writes are atomic and unknown keys in a card are preserved, so a save cannot
  truncate or quietly prune your file. Nothing in the interface deletes a card,
  and a delete that does exist asks first, every time.
- Data never reaches the browser inside executable code. Values travel as
  escaped text or escaped `data-*` attributes, and every file under `static/`
  is a real file that Python never generates.
- Every request parses the vault again, so a card changed in an editor shows up
  on the next reload and there is no index to fall out of step.
- Loopback by default, with a content security policy and no external request:
  it works offline.
- 114 standard-library tests over a fictional sample vault that exercises every
  rendering, parsing and failure path.
