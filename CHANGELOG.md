# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[semantic versioning](https://semver.org/).

## 1.2.1 - 2026-09-16

### Fixed

- A project whose id holds a `.` can have its notes and milestones edited from
  the structure view again. The view addresses a value by a dotted path, and a
  note or a milestone carries the project id inside its own id, so a dot in it
  split the path in the wrong place and the row answered *not found*. New rows
  no longer take the dot with them; rows written before this release keep the
  id they were given, and are still reached from the panel and the markdown
  tab.
- The access cookie is renewed on every visit. It was set for a week when the
  token link was opened and never extended, so a dashboard reachable from the
  network locked itself out on the seventh day however much it had been used
  in between — and an application installed to the home screen has no address
  bar to open the link in again. The week now runs from the last request.

## 1.2.0 - 2026-09-16

### Fixed

- A project saved with an empty name stopped being a project. The name is the
  card's `# title` line, so a blank one left a file that no longer read as a
  card at all: it dropped out of the chart, the list, the project count and the
  snapshot, and the application could no longer load it to put the name back.
  An empty name is refused before anything is written now, wherever it is
  typed — the panel, the advanced form, the structure view.
- The `- id:` of a card is no longer edited from the structure view. It is the
  name of the file the card lives in, and changing one without the other left a
  card the chart could still draw but nothing could address.
- The whole-vault snapshot holds every card again. It looked each card up by
  the `- id:` the card itself declares, so a card whose id and file name had
  drifted apart was quietly missing from the document that *Download the
  snapshot* and the markdown tab hand you. It reads the file each card was read
  from instead.
- The notes of a hand-edited card no longer answer with an internal error. A
  `- todos:` holding a line of text rather than a list of notes is a card
  somebody typed, and editing, completing, deleting or reordering the notes
  around it now answers normally and leaves that line exactly where it was.
- Reordering the notes refuses a payload it cannot read, instead of failing
  with an internal error, and still moves nothing it was not asked to move.
- *Ask before discarding* only asks when there is something to discard. Opening
  the advanced editor and closing it again, or opening a field and cancelling
  it, asked you to confirm the loss of text nobody had typed. The setting reads
  "leaving an editor with unsaved text", and now that is what it does — and
  clicking outside the advanced editor, which used to close it without asking
  anything at all, asks the same question the Close button does.
- A deadline a year away reads *in 1 year* rather than *in 1 years*.
- `--migrate-vault` writes each converted card the way every other write in the
  application goes out: a sibling temp file, renamed into place. It was the one
  path left that truncated the file it was rewriting.
- A link whose address hides a control character in front of its scheme is
  refused like the scheme it hides. The content security policy already stopped
  it from doing anything; the check agrees with it now.

## 1.1.0 - 2026-09-13

- A project can be created from the interface. *New project* in the header,
  and beside the search field on a phone, asks for a name and nothing else:
  the id is the name as a slug, the card lands at the end of the live list
  with `status: active`, and the page comes back with its panel open. The
  markdown tab of the hierarchy page still creates cards too; this is the
  short way.
- A note no longer needs a project. *Actions & notes* opens with an *Inbox*
  card and a field to write into it; the first note creates `inbox.md`, a
  card like any other on disk. The chart, the phone's list and the project
  count leave it out, the hierarchy page shows it apart above the projects,
  and the markdown tab puts it first. The id is reserved: a project cannot be
  created with it.
- The hierarchy page reads at the chart's four levels. Every branch of the
  tree folds, and *Compact*, *Projects*, *Stakeholders* and *All details* say
  what a project's line shows — the name; then its status, span and deadline;
  then the people on it — and whether the project opens. A level is absolute,
  and a project folded or opened by hand against it is remembered.
- Beside the level, how much of a line: *All* is every key and value as the
  file holds them, *No keys* drops the key of every value and keeps the name
  of every branch, *Relevant* (the default) also drops `id`, `type`,
  `priority`, `status` and every empty value, prints the timeline as one line
  per row, and keeps the key where a value says nothing without it — a date,
  a role, a severity. A list of plain values, platforms or flags, is one line
  at every level.
- A value in the tree edits in place. Double-click it, or press Enter on it,
  and it becomes a field with Save and Cancel; the change goes to the card at
  the path the tree shows, through the same validation as the form where the
  schema knows the field, and as text where it does not. Keys are not edited
  here, and nothing is added or removed: that is the markdown tab.
- The hierarchy page remembers its tab, its level, its detail and its folds,
  stored in the browser like every other preference.
- The button on a card in *Actions & notes* now goes to the project: it opens
  the panel and scrolls to it, and on a phone it switches to the list, where
  the panel sits under its card. It used to toggle the panel where it stood,
  in the chart below the fold on a desktop and on a surface that was not on
  screen on a phone, which looked like nothing at all.
- Settings ends with an About group: the version that is running, the release
  notes that shipped with it behind a fold, and a link to the releases page.
  The notes are the `## <version>` section of `CHANGELOG.md`, rendered by the
  same markdown pass a card's notes go through, so a release describes itself
  in one place and the panel reads it.
- That link is the whole of the update check, deliberately. It opens a new tab
  and the application makes no request of its own, on a click or otherwise,
  which keeps the content security policy at `default-src 'self'` and leaves
  the offline guarantee exactly as it was.

### Fixed

- On the hierarchy page the footer appeared long before the tree ended. The
  box around the tree was capped to the window's height like the chart's, so
  the tree overflowed it and the sticky footer followed the box. The tree now
  scrolls with the page, and each page keeps a scroll position of its own,
  so leaving the chart halfway down no longer opens the hierarchy in the void.
- The *open / done* badge on *Actions & notes* drifted after a change: the
  page counted the notes of every panel, finished and abandoned projects
  included, while the server had counted the live ones. Both count the live
  ones now.
- A `summary` could not open the `details` it belongs to inside an overlay.
  The click router cancels the default of any click that reaches an element
  carrying an action, an overlay's backdrop carries one, and the list of
  controls whose default belongs to them named inputs, selects, textareas and
  labels but not summaries. Same shape as the checkbox that could not be
  ticked; the list is what was incomplete, so that is what was fixed.
- A logo. A gem beside three bars, drawn as one small SVG, replaces the
  diamond in the header of the dashboard and of the docs page; the gem alone
  is the favicon and the icon of the installed app. The diamond stays on the
  timeline, where it marks a milestone.

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
