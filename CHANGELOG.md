# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[semantic versioning](https://semver.org/).

## 1.7.0 - 2026-09-22

### Added

- **Fortnight, between Week and Month.** A fourth zoom, halfway between the
  two: four pixels a day, the week boxes still drawn, about a year on one
  screen, and the scale runs a year past today when the window does not say
  where to stop. Week showed a season and Month two years, with nothing in
  between.

### Changed

- **The tags of a project sit under its title, on two lines of the same
  shape.** The status at the left and the deadline at the right on the first
  line, the platforms on the second, and the second line is there whether the
  card names a platform or not, so every project row stands the same height
  and the list reads as rows of one shape. They used to sit after the title
  and wrap as the column allowed: two lines for one project, three for the
  next.

## 1.6.0 - 2026-09-21

### Added

- **A note has a title, owners and tags.** A note is a line of text first,
  and may now also say what it is called, who it is for and what it is
  about: the title in bold above the text, the owners and the tags as chips
  under it. The composer in a project's panel and on the inbox card asks for
  all of them, and so does the editor a double-click opens. Owners are
  offered from the roster in `settings.toml` and from every name typed
  since, tags from every tag typed, the way platforms are offered, and a
  name typed for the first time is offered from then on without a reload.
  The card holds them as `title`, `owners` and `tags` under the note; a note
  without them is the line it always was, and a note with none of them
  stays as small as it was.
- **A note that is due says so.** Due today, due tomorrow, or already
  overdue: an alert to the left of the text, in the warning hue, with the
  word beside it for anyone who cannot see the hue. Nothing for a note due
  later, or with no date: the list would otherwise be all alerts.
- **The open notes read three ways.** *Actions & notes* orders the open
  notes of every card as the card lists them — the order they were written
  or dragged to — or by due date, soonest first or latest first, a note with
  no date last either way. *Owners* narrows the list to the notes of the
  people ticked, the same menu as the platforms over the chart, and says
  how many open notes are left. *By owner* turns the list inside out: one
  section per person across every project, in the order chosen, each note
  with its project's name, a note with two owners under both, the notes of
  nobody last. All three are remembered per browser, like the chart's own
  filters. Up and Down in an editor of the aggregated list go quiet while
  the list is ordered, narrowed or grouped: they edit the card's order, and
  that is not the order on screen then; in the panel they always work.
- **Platforms on the project row.** At the Projects level and above, the
  platforms a project touches sit after its status and deadline, as tags,
  and a tick in the panel changes them at once.
- **Every project has its own level switch.** Four glyphs at the right end
  of the row, shown on hover with Edit beside them: Compact, Projects,
  Stakeholders and All details, for that one project. The toolbar's switch
  still sets every project, and points at a level only when every row is at
  it. Compact is a level per row now, and it is remembered across a reload,
  which the whole-chart Compact never was. The row's *Notes & actions*
  button went with it: All details is what it did.
- **A line to add a timeline row, under every project's people.** At
  Stakeholders and All details, the last line under a project's people adds
  one, opening the row dialog on the project's own span. A project with
  nobody on it yet unfolds to that line, so its caret is never dead.
- **Timeline rows in the simple form.** Who, when and what, one row per
  line, with *Add row* under them: the people on a project are written where
  the project is, and *New project* offers the same table, so a card is born
  with its people on it. A row written as a start and a count of working
  days opens on the end the chart draws, and saving writes that end down,
  one way of saying it rather than two, the rule the project's own span
  already followed. The columns the form does not show, `days` and `flags`,
  survive the save.

### Changed

- **One edit per project.** The chart row and the panel each carry one
  *Edit*, which opens the simple form; *Advanced edit* is reached from
  inside it and nowhere else.
- **No row table asks for an id.** In Advanced edit the timeline rows, the
  milestones, the estimates and the risks no longer show an ID column. A new
  row is given an id when it is saved, as a note or a milestone always was,
  and an existing row keeps its own, unseen. A row that names its id is that
  row, updated in the columns posted and left alone in the rest, so a save
  from a form that shows four columns of a row cannot drop the other two.
- **The row tables of Advanced edit sit on one line each.** Their grid mixed
  an auto-fit repeat with an intrinsic track, which no browser accepts, and
  every table had stacked one field per line for as long as it existed. The
  remove button has a fixed track now, pinned to the end of the row.

### Fixed

- *Up* and *Down* in the editor of an inbox note threw an error instead of
  moving it: the inbox has no panel, and the order was read back from a list
  that did not exist. The inbox card's own list is read now.

## 1.5.0 - 2026-09-21

### Added

- **The search reads the whole card, in every band.** It used to look at what
  the page showed — titles, people, notes, intros — and the panel shows only
  some of a card, so a risk, an estimate's note, a Jira key or the `## Notes`
  body could not be found at all. Every project row now carries its card as
  text, and the search reads that: a word in the notes body of a dropped
  project is found, and typing it opens the band the project sits in. Every
  save answers with the card as it is, so the row's text follows an edit
  made in place without a reload: a note just deleted stops being found, a
  note just written is.
- **Several words, all or any.** The words of a query are separate
  conditions. *All words* keeps the projects that hold every one of them,
  *Any word* the projects that hold at least one, and the count beside the
  field says how many projects match rather than how many words were found.
  Marks are drawn only inside the projects the mode accepts, so a word that
  is in a card the mode rejects is never lit up as if it were a hit.
- **Only matches.** A flag beside the search that turns it from a
  highlighter into a filter: the projects the search does not find leave the
  chart, and the list on a phone, until it is switched off or the field is
  emptied. Their rows are hidden, never removed, so a collapse, a depth level
  and the filter never fight over the same row.
- **A platform filter.** *Platforms* in the toolbar is a menu of checkboxes:
  every platform `settings.toml` names, then every one a card in the vault
  already carries. Tick some and the chart keeps the projects on any of them
  — iOS and Android together is the mobile work, not the projects that touch
  both — and a project that names no platform leaves with the first tick.
  Ticking a platform in a project's panel is read by the filter at once.
- **A partial view says so.** Whenever a filter hides a project, a line over
  the rows — and over the list on a phone — says how many of the projects are
  shown and what is hiding the rest, with *Show all* beside it, which unticks
  the platforms and switches *Only matches* off. The search text stays,
  because a search that only marks its matches hides nothing. The words, the
  mode, the flag and the platforms are remembered per browser, like the
  collapse state, so a save that reloads the page comes back filtered as it
  was — with its folds where they were: typing is what opens a band that
  hides a match, a reload does not. A card just created is shown whatever
  the filter would say, and a remembered platform that no card names any
  more is dropped rather than left hiding the whole chart with no tick to
  remove.

### Fixed

- Setting a project to `inactive` from its panel moves it to the INACTIVE
  band at once, as `done` and `dropped` already did. The band list the
  browser checked a status change against was written down as two, before
  INACTIVE became a band: the row stayed in the live list until the next
  reload, and the next drag inside the list sent it up as live, which turned
  it `active` again without anyone asking. The bands the page draws are what
  a status change is checked against now.
- A status changed in the panel reaches the row and the card at once: a
  project set to `blocked` turns red in the list without a reload, and the
  pill on its card on a phone changes with it, instead of both waiting for
  the next reload.
- A platform toggle in the panel says whether it is pressed to a screen
  reader, not only to the eye.
- The first page after an upgrade opens on the script and stylesheet of
  that upgrade. The shell is cached first and revalidated behind the page,
  which is what makes it paint at once, and it handed the previous release's
  `app.js` to the new page exactly once: every action the new page named
  was unregistered until the next load. The page now asks for the assets of
  its own version, which the cache has never seen.

## 1.4.2 - 2026-09-21

### Added

- **The terminal says which GanttBit this is.** The first lines printed at
  startup are a small heading with the version and the build: the commit the
  tree is checked out at, when there is a repository to read it from. There
  is no build step, so the commit is the one thing that tells two copies of
  the same version apart. A zip download has no repository and shows the
  version alone.
- **A port that is already taken is named, and can be taken over.** Starting
  the dashboard on an address and port where a GanttBit is already listening
  used to end in a traceback and a hunt for the process to stop. It now says
  which GanttBit is there, with its version and its process id, and asks
  whether to stop it and start this one in its place. Anything but a yes
  leaves the other one running and exits with status 1, and nothing on the
  machine is touched; the same when there is no terminal to answer at, so a
  copy started from a script never stops another. A port held by something
  that is not GanttBit is never touched either: it is reported, and the way
  past it is `--port`. Finding the process is `lsof`'s job, which ships with
  macOS and with every Linux desktop; without it the other instance is named
  and left alone.

### Fixed

- The application starts on Python 3.11 again. 1.4.0 wrote an f-string inside
  an f-string expression with the same quote, which is 3.12 syntax and exactly
  the trap CONTRIBUTING.md describes, this time in `view.py`. On 3.11 the
  module did not import, so the dashboard refused to start and the whole test
  suite failed to load, with a `SyntaxError` on a line that reads perfectly
  well. The piece is built above the return now, and the suite runs on 3.11
  as well as 3.12 before a change lands.

## 1.4.1 - 2026-09-16

### Fixed

- Dragging a project to reorder it inside the live list does something again.
  The browser worked out which band each project belonged to by remembering
  the last band heading it had passed — and the live list is the chart itself
  and carries no heading, so every project in it was sent with no band at all.
  The server could not place a project with nowhere to go, skipped it, and
  answered that it had changed nothing: the bar snapped back and the chart
  looked untouched. Each row already states the band it is drawn in, which is
  what *Move up* and *Move down* have always read, and the drag reads it now
  too. Dropping a project onto DONE, DROPPED or INACTIVE was never affected —
  those bands do have a heading.
- A reorder that names a project without a band is refused and says so,
  instead of being quietly skipped. That silence is what made the bug above
  look like a chart that had simply decided not to move.

## 1.4.0 - 2026-09-16

### Added

- **An estimate is as long as the answer was.** A project is sized in a
  sentence as often as in a number — how the work splits, what it assumes,
  what is still unknown — and the value now takes as many lines as you type,
  in the simple form, in the panel and in the Estimates table of Advanced
  edit. Nothing about the card format changed: a value holding newlines has
  always been written as a fenced block, so the file stays a file you can read
  and grep. The panel shows the line that summarises an estimate and says
  there is more; the whole of it is one click away, and the structure view
  prints it as the card holds it.
- **The Advanced edit form reaches `intro`.** *Why & scope* — the markdown
  block at the top of the panel — was editable by double-clicking it there and
  from the simple form, but the one form that claims to hold every field of
  the card did not show it. It has a section of its own now, above the notes,
  and the two markdown blocks of a card sit together.

## 1.3.0 - 2026-09-16

### Fixed

- A project whose bar is declared as a start and a count of working days
  (`timeline.days`, with no end date) is no longer unsavable from a form with
  two dates: the form opens on the day that count lands on, and saving settles
  the card on the two dates, dropping `days` the way a dragged bar already
  does. Two ways of saying it is how they come to disagree.
- A link field holding a whole address is no longer prefixed with the base
  URL. `jira_base_url` exists to resolve a bare key (`NIMBUS-1042`); pasting
  `https://…/browse/ABC-7` into the Jira request or an epic used to produce
  `https://jira.example.com/browse/https://…`, a link that could not open.
  A value that already names a scheme is now its own target, in the page the
  server renders and in the chip the browser patches in after a save.
- Leaving a dialog with text in it asks before losing it, wherever the dialog
  is. *Ask before discarding* covered the editors that open in the page; the
  overlays did not ask at all, which cost a name when the only one of them was
  *Rename* and costs most of a card now that the form below is one of them.
  Cancel, Escape, a click outside and the step across to Advanced edit all ask
  the same question, and a form nobody has typed in still closes without one.

### Added

- **It installs.** Behind a stable address — a named tunnel, a Tailscale
  address, a domain — the browser offers to put GanttBit on the home screen,
  and it opens in its own window with its own icon. A service worker caches
  the shell so the page paints before the data arrives; `/api/` is never
  cached and never intercepted, because a chart drawn from a cache that then
  refuses to save is worse than a page that says it is not connected, and a
  navigation that cannot reach the server gets a plain page saying so. The
  access cookie now renews on every request (1.2.1), which is what a window
  with no address bar needs. A hostname that changes every run is not worth
  installing: an installed app belongs to its origin.

- **Estimates** are a history on the card. A project is sized more than once —
  roughly by the architects before it reaches anyone, refined in the preview
  meeting, then in detail with the squads, and again when an open point closes
  or a surprise lands — and the earlier numbers do not stop being true. So
  `estimates` is a list, oldest first, each row carrying the stage it came out
  of (`raw`, `preview`, `detailed`), the value as free text (`40d`, `6w`, `2
  sprint`, `L`), the day it was given and what moved it. Nothing marks the
  current one: the last row is, the way a note is open because it sits under
  `todos`. The simple form asks for the value and adds one when it has moved,
  writing nothing when it has not; the panel lists them all and opens each to
  be corrected or removed; the Advanced editor gets the table for free.
- **Edit** on a chart row opens the simple form on that project: the same
  overlay *New project* uses, filled in from the card. **Advanced edit** at
  its corner hands the card to the full editor, and **Simple edit** in that
  editor's header hands it back — two views of one card, so the way over
  reloads from the file rather than carrying half a form with it. Saving from
  the simple form clears what it showed and you emptied, which is the
  difference between editing a card and creating one.
- The simple form also asks for the **status**, the **Jira request** and the
  **Confluence pages**: a project often turns up with a ticket and a page
  before it has an analysis, or a start date, or anyone on it.
- **Platforms is an open vocabulary.** Clicking the field offers every tag the
  vault already uses — what `settings.toml` names, plus whatever has been typed
  since — and typing narrows it to the tags starting with what you typed.
  Arrow keys walk the list, Enter takes one, and a new tag is still accepted
  and offered the next time. The values travel with the schema, so the form
  never restates them.
- **INACTIVE** is a band of its own under the live list, above DONE and
  DROPPED: a project nobody has started yet is not in flight, and it is not
  finished either. Unlike the two below it, its notes stay on the aggregated
  action list — the note to chase an estimate is exactly the one worth seeing
  before the work begins.
- **New project** asks for a project, not for a name. One overlay carries what
  somebody has in their head when they start one: the name, the span the bar is
  drawn from, the deadline badge, the platforms, the QA effort, and why it
  exists, as markdown. Only the name is required, and a field left empty is
  left out of the card rather than written empty, so a card created from the
  name alone is the same five lines it has always been. The form is not written
  in the script: it is `schema.creation_fields`, served with the schema and
  drawn by the renderer the Advanced Edit form already uses, so adding a field
  to it is one line in `schema.py`.
- **Project span** in the project panel: the dates of the project's own bar,
  set and edited from the interface. A new card declares no span, so there
  was no bar in the chart to grab and no way to draw the first one short of
  the Advanced editor. A card that carries timeline rows but declares no span
  of its own is shown the bar those rows derive, named as derived, and the
  dialog opens on it.

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
