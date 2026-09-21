# GanttBit

A local, dependency-free control center for a delivery manager: a markdown
knowledge vault on disk, rendered as an interactive Gantt chart with per
project notes, actions, links, attachments and an editable card schema.

Nothing leaves your machine, nothing is installed: it is Python 3.11+ standard
library, two stylesheets and two scripts.

![projects → people](docs/hierarchy.svg)

## Quick start

```bash
python3 dashboard.py --vault sample-vault --port 8099
```

Open <http://localhost:8099>. That runs against `sample-vault/`, a fictional
organisation used both as a demo and as the test fixture.

To use your own vault, point the settings at it and just run:

```bash
python3 dashboard.py
```

| Flag | Meaning |
|---|---|
| `--settings PATH` | one settings file, instead of `settings.toml` with `settings.local.toml` layered over it |
| `--vault PATH` | vault root, keeping the folder layout from the settings |
| `--projects PATH` | directory of project cards (overrides `--vault`) |
| `--host`, `--port` | bind address and port (default `127.0.0.1:8080`) |
| `--token` | shared secret demanded off loopback (generated when omitted) |

The server binds to loopback by default. Bind it anywhere else and it demands
an access token on every request. One is generated at startup and printed
inside the URL to open:

```
GanttBit listening on http://127.0.0.1:8099?k=8mQ2vN7pLxKd4RtYwZ
Reachable from other machines: that link carries the access token.
```

Opening that link sets an HttpOnly cookie and redirects to the clean URL. Set
your own with `--token` or `[server] token` in `settings.toml`. It is a shared
secret over plain HTTP, so it keeps strangers on the same Wi-Fi out. On a
hostile network it is no substitute for TLS.

The first thing printed is a small heading with the version and, when the
tree is a git checkout, the commit it is at, which is the only build a tool
with no build step has:

```
GanttBit 1.4.2 · build 3f9c2a1
──────────────────────────────
GanttBit listening on http://127.0.0.1:8099
```

Start it where a GanttBit is already listening and it says so, with the
version and the process id of the other one, and asks whether to stop that one
and take its place. Anything but a yes leaves it running and exits with status
1, and so does having no terminal to answer at: a copy started from a script
never stops another. A port held by something that is not GanttBit is never
touched either; pick another with `--port`. Finding the process is `lsof`'s
job, which ships with macOS and with every Linux desktop.

## The chart

The toolbar carries a search, a depth, a zoom and a window. The depth levels
are **Compact**, **Projects**, **Stakeholders** and **All details**: absolute
levels rather than toggles, so each one does the same thing whatever is folded
right now. **Compact** is one line per project, the drag handle, the number,
the name and its span bar, which is a third shorter than a normal row. The
zoom is **Day**, **Week** or **Month**; a column is always a working day, and
the zoom decides how wide it is drawn. The window is what the chart is drawn
through: from today, the last 30 days, this year, all dates, or
from a date you pick. The choice travels in the URL (`?from=…`) and is
remembered per browser, and so is everything you collapsed, opened and scrolled
to: a save reloads the page and puts you back where you were, including the
chart's own horizontal position.

**Settings**, the button in the footer, holds four groups: the theme (System,
Light, Dark, or one of twenty-three palettes borrowed from well-known editors
behind **More…**), the priority band, the chart's weekday letters, and whether
saving and discarding ask first. They are per-browser preferences.

Bars are dragged and resized in the chart: grab one in the middle to move it,
or either edge to change where it starts or ends. Whole working days, applied
to the dates the card holds, so a bar whose start is hidden by "show from
today" still moves by exactly what you dragged.

A new project has no bar to grab, because a card that says nothing about its
dates is drawn with nothing: **Project span** in its panel is where the first
one is written, and where an existing one is edited without aiming at it. A
card that declares no span of its own but carries timeline rows already has a
bar, derived from them, and the panel says so rather than claiming the card
states it.

A **milestone** is a dated mark on the project's own lane, drawn as the
diamond this interface uses for nothing else. Click an empty day in a lane to
propose one there, or add it from the panel; clicking the diamond opens the
same overlay, with a delete that asks first. Hovering it tells you the date and
what happens on it.

Three bands sit under the live list. A project nobody has started yet goes in
**INACTIVE**, one that is finished in **DONE**, one that was abandoned in
**DROPPED** — by dragging it onto the heading, or with the status select in its
panel, and it comes back by being dragged into the list above them. DONE and
DROPPED leave the aggregated action list, so finished work stops asking for
attention; INACTIVE does not, because a project that has not started is not
finished, and the note to chase its estimate is exactly the one worth keeping
in sight. `priority` is the project's position over the whole chart, so the
number in the card is the number on the screen.

A note that belongs to no project yet goes in the **Inbox**, the first card of
the aggregated list: write it there and it lands in `inbox.md`, a card like any
other on disk, which the chart and the project count leave out.

**New project** in the header asks, in one overlay, for what somebody has in
their head when a project turns up: the name, whether it has started, the span
the bar is drawn from, the deadline the chart badge shows, the platforms, the
QA effort, the Jira request and the Confluence pages — those two usually exist
before any analysis does — and why it exists, as markdown, so *Why* and *Scope*
are headings if that is how you write them. The name is the only answer
required, and every field left empty is left out of the card rather than
written empty: created with a name alone, the card is the five lines it was
before. It comes back with the new card's panel open.

The same form edits a card that exists: the pencil on a chart row opens it on
that project, and **Advanced edit** at its corner hands the card over to the
full editor, which hands it back the same way. Two views of one card, never two
sources for it, so the way over reloads from the file rather than carrying half
a form with it.

**Estimates are a history, not a number.** A project is sized more than once —
roughly by the architects before it reaches anyone, refined in the preview
meeting, then in detail with the squads, and again whenever an open point
closes or a surprise lands — and the earlier numbers do not stop being true:
they are what somebody was told. So the card keeps all of them, oldest first,
and the last one is the one in force. Typing a value in the form adds one when
it has moved and writes nothing when it has not; the panel lists them, and each
one opens to be corrected, dated, or given a line on what moved it.

**Platforms is an open vocabulary.** Clicking the field offers every tag the
vault already uses — what `settings.toml` names, plus whatever has been typed
since — and typing narrows the list to the tags that start with what you typed.
A new one is still accepted, and offered the next time. The form is
`schema.simple_fields`; adding a field to it is one line there.

Every project carries a coloured band down its left edge, and the colour is its
rank: full accent at the top of the list, fading to a near-grey at the bottom.
With a dozen projects two neighbours barely differ, because the band is meant
to be read as a ramp down the list rather than as a project's identity, and the
number beside it is what names a position. The two ends are worked out against
whichever theme is on, so the band holds the same contrast on all of them.
Colour, intensity, fade and tint are in **Settings**, with four presets.

## On a phone

Below 900px the chart stops being the interface. A bar at the bottom carries
four surfaces over the same cards, **Projects**, **Chart**, **Notes** and
**More**, and the default is a list of project cards: the number and the name,
the status, the deadline as time remaining, a sparkline of the span with today
and the milestones on it, the people as initials, and how many notes are
waiting. Tapping one opens the project full screen with its notes first;
tapping any value opens its editor. Projects move with **Move up / Move down /
Move to**, because HTML5 drag and drop does not exist on iOS.

The detail panel becomes a single column and the page never scrolls sideways.
The chart still does, because a timeline is wide by nature, inside its own
container. Two controls are hidden on touch because they need a pointing
device: resizing the label column, and dragging rows to reorder them.

It also installs. Behind a stable address — a named tunnel, a Tailscale
address, a domain — the browser offers to add it to the home screen, and it
opens in its own window with its own icon. A service worker caches the shell,
so the page paints before the data arrives; `/api/` is never cached and never
intercepted, because a chart drawn from a cache that then refuses to save is
worse than a page that says it is not connected. A random per-run hostname is
not worth installing: a PWA belongs to its origin, and tomorrow's tunnel is a
different one.

## Two views over the vault

The chart is one reading of the cards; **Hierarchy** is the other, and the
header switches between them. *Structure* is the vault as a tree: every
project, then every value the card holds under the names the card uses (the
keys this codebase knows nothing about included, and the `## Notes` body),
every branch foldable. It reads at the chart's four levels, *Compact*,
*Projects*, *Stakeholders* and *All details*, and at three amounts of detail:
*All*, *No keys*, and *Relevant*, which drops the keys, the ids and the empty
values and prints the timeline as one line per row. Double-click a value to
edit it where it stands; the change goes to the card at that path, validated
where the schema knows the field. *Markdown* is every card concatenated in the same order,
editable in one go: a block whose
`- id:` is unknown creates a card, and a card whose block is not in the text is
left alone. Nothing is ever deleted from that screen. The same document
downloads as `vault-YYYY-MM.md`, which is the monthly snapshot.

## Configuration

Everything an organisation changes lives in [`settings.toml`](settings.toml):
squads and the people in them, roles, Jira/Confluence/Figma base URLs,
wording, vault paths. A base URL only ever resolves a bare key
(`NIMBUS-1042`); a whole address pasted into one of those fields is the link,
left exactly as it was typed. Adding a team member or a project never requires touching
Python. The priority band is not there: it is a per-browser preference, set in
**Settings** beside the theme.

Put the keys that differ in a `settings.local.toml` next to it (git-ignored):
it is layered over `settings.toml`, so it only carries what you change, and
your real names stay out of the repository.

```toml
[app]
owner = "Your name"

[vault]
root = "/path/to/your/vault"
```

## The vault

```
<vault>/
├── 02-projects/active/<project-id>.md              one card per project
└── 02-projects/active/attachments/<project-id>/    its files, any type
```

A card is a markdown outline: the title is the project name, every field is
a `- key: value` item, and free text lives under `## Notes`. Everything in
[`ganttbit/schema.py`](ganttbit/schema.py) is editable from the UI; unknown
keys are preserved untouched, so you can keep your own fields in a card.

````markdown
# Navigation menu — second level
- id: project-1-navigation-menu
- status: active                     (done and dropped give it its own group)
- priority: 1                        (position in the list, set by drag & drop)
- intro:
  ```md
  Multi-line values are fenced, so nothing has to be escaped.
  ```
- dates
  - deadline_text: 2026-11-14
  - deadline_type: hard
- tech_footprint
  - platforms
    - iOS
    - Android
- estimates                          (the history; the last one is in force)
  - estimate-1
    - stage: raw                     (raw | preview | detailed)
    - value: 40d                     (free text: 40d, 6w, 2 sprint, L)
    - date: 2026-07-14
    - note: before any analysis

## Notes

Free markdown, kept verbatim.
````

A vault written before 0.1.0 is converted once with
`./dashboard.py --migrate-vault`, which leaves a `.bak` beside every file it
rewrites and refuses to convert the same card twice.

A project owns its bars. `timeline.start` plus either `timeline.end` or
`timeline.days` (working days) draws the project bar, which exists even with no
tasks, and each row under `timeline.tasks` draws one person's bar:

````markdown
- timeline
  - start: 2026-08-24
  - end: 2026-11-20
  - tasks
    - task-1
      - who: Ada Lovelace
      - start: 2026-08-24
      - days: 34
      - flags
        - crit
      - note: Menu API v2
````

`who` is matched against the roster in `[[squads]]` by name, which gives the
row its role and colour. A task falling outside the span its project declares
is marked rather than hidden. A delivery plan written as a mermaid `gantt`
block, as earlier versions used, is moved into the cards once with
`./dashboard.py --import-plan`, which reports every row it could not place and
leaves the file untouched.

## What a card becomes

![one markdown card, read into the chart and written back](docs/dataflow.svg)

Every request parses the vault again, so a card you changed in your editor
shows up on the next reload and there is no index to fall out of step. An edit
goes the other way as one action against one card: the schema refuses an
invalid value with a 400 before anything reaches the disk, and the save writes
a sibling temp file and renames it. A key this codebase has never heard of
makes the whole round trip untouched.

The same diagram is a page you can explore at
[dataflow.html](https://stangoldbear.github.io/ganttbit/dataflow.html),
with the outward path, the way back and the round trip traced one at a time.
Its source is [`docs/dataflow.json`](docs/dataflow.json).

## Architecture

Layers, each with one reason to change; dependencies point inward and only
`repository` touches the filesystem.

| Module | Responsibility |
|---|---|
| `settings` | `settings.toml` parsing, fails fast; presentation constants |
| `cardmd` | the markdown card format ⇄ Python data |
| `repository` | the vault on disk, atomic writes |
| `domain` | dates, the priority ramp, roles, gantt parsing, timeline (pure, clock injected) |
| `schema` | the card schema, declared once |
| `markup` / `gantt` / `view` | HTML rendering |
| `api` | mutations, behind a routing table |
| `server` | HTTP, static assets, JSON |

Two rules worth keeping:

- Data never reaches the browser inside executable code. Values travel as
  escaped text or escaped `data-*` attributes; every file under `static/` is a
  real file that Python never generates.
- Layout metrics live in one place. `settings.py` emits them as CSS custom
  properties; the stylesheet and the resize script read them, they never
  restate them.

## Tests

```bash
python3 -m unittest test_ganttbit -v
```

142 tests, standard library only. The sample vault is the fixture: it contains
a blocked project, a malformed card, a project with no timeline task, notes
with quotes and newlines, deliberately awkward names and past/future tasks.

## License

MIT. See [LICENSE](LICENSE).
