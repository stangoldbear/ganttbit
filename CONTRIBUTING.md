# Contributing

Thanks for looking at the code. This is a small tool with a deliberately small
surface: the guidance below is mostly about what *not* to add.

## How this repository is published

This repository is a **published snapshot**. Development happens in a separate
private workspace and every release lands here as a single commit, so the
history is one entry per version rather than a stream of working commits.

That has one practical consequence: a pull request cannot be merged here
directly. Open one anyway, or open an issue: patches are applied upstream and
ship in the following release, with attribution in the changelog. Bug reports
and design discussion are just as welcome as code.

## Running it

```bash
python3 dashboard.py --vault sample-vault --port 8099
python3 -m unittest test_ganttbit -v
```

Python 3.11 or newer, no dependencies, no build step. Adding a dependency needs
a reason that a few lines of the standard library cannot cover.

3.11 is a floor, and one piece of syntax walks straight through it. An
f-string expression holding another f-string of the *same quote* is [PEP
701](https://peps.python.org/pep-0701/), which lands in 3.12. On 3.11 the module
does not import at all: the application refuses to start and the whole test
suite fails to load, with a `SyntaxError` pointing at a line that reads
perfectly well. It has happened twice: in `gantt.py`, and again in `view.py` in
1.4.0, which is why the suite also runs on 3.11 before a change lands.

```python
# 3.12 only — an f-string inside an f-string expression, same quote.
return f'''<tbody>{f'''<tr>{value}</tr>''' if value else ''}</tbody>'''

# Build the piece above the return instead. Works everywhere.
row = f'''<tr>{value}</tr>''' if value else ''
return f'''<tbody>{row}</tbody>'''
```

The view layer is one long f-string per component, so this is easy to reach for
without noticing. If you develop on 3.12 or later, the check that catches it is:

```bash
python3.11 -c 'import ganttbit.view, ganttbit.gantt, ganttbit.api'
```

## Invariants

These are the rules that keep the codebase small. Breaking one is how a
500-line module becomes a 5,000-line one.

1. Only `repository` touches the filesystem. `domain` is pure: no file
   access, and no `date.today()` or `datetime.now()` buried inside it. The
   clock is passed in, which is what makes the timeline testable.
2. Python never emits CSS or JavaScript. `ganttbit/static/app.css` and
   `app.js` are real files. Values reach the browser as escaped text or escaped
   `data-*` attributes, never interpolated into executable code.
3. Layout metrics have one home. `settings.py` declares them and the view
   emits them as CSS custom properties. If you find yourself writing `340` in
   the stylesheet or in the script, stop.
4. The card schema is declared once, in `ganttbit/schema.py`. The API
   validates and applies from it; the browser renders its forms — Advanced
   Edit, and New project — from the same declaration, served at
   `/api/schema`. A form is a list of declared fields, never a list of
   controls written in the script.
5. Validate at the boundary. An unknown `status` or `severity` is
   refused with a 400 before it can reach a file. Never let an invalid value
   land in the vault to be normalised later.
6. Writes are atomic. Go through `repository.write_atomic`; a half-written
   card is a destroyed card.
7. Unknown keys in a card survive. Someone's private field must not be
   deleted by a save it was not part of.

## Where to change what

| Goal | Where |
|---|---|
| add a card field | `ganttbit/schema.py`, one entry; form and API follow |
| ask for a field in the simple form (New project, Edit) | `schema.simple_fields`, one entry |
| add an API action | register a function in `ganttbit/api.ROUTES` |
| adjust the small-screen layout | the `@media` blocks at the end of `app.css`; the server emits the metrics before the stylesheet so a media query can narrow them |
| change how access is granted | `server._authorised`, the single gate every verb passes through |
| let a new file type open inline | `settings.INLINE_ATTACHMENT_TYPES`, only for types that cannot carry script |
| add a role or a squad member | `settings.toml` |
| add a band under the live list | `settings.DISPLAY_GROUPS`, one entry; `closed` says whether its notes leave the action list |
| change a colour or a metric | `settings.py`, and `ganttbit/static/theme.js` for the priority band, which is solved per theme |
| change the wording of the chrome | `settings.toml`, `[app]` |

## The vault format

A project card is a markdown outline. The title is the project name, every
field is a `- ` item, a group is two spaces deeper, and free text lives under
`## Notes`. A multi-line value is a fenced block, so nothing is ever escaped.

````markdown
# Navigation menu — second level
- id: project-1-navigation-menu      (must match the file name)
- priority: 1                        (position in the list, set by drag & drop)
- status: active                     (active | blocked | inactive | done | dropped)
- intro:
  ```md
  Free-form context. Not actions.
  ```
- dates
  - deadline_text: 2026-11-14        (what the chart badge shows; free text is fine)
  - deadline_type: hard              (soft | hard)
- tech_footprint
  - platforms
    - iOS
    - Android
  - content_impact: true
- risks_and_criticalities
  - RISK-01
    - description: …
    - severity: high
- jira
  - request: NIMBUS-1042
  - epics
    - NIMBUS-1043
- estimates                            (the history, oldest first; the last
  - estimate-1                          one is the estimate in force)
    - stage: raw                       (raw | preview | detailed)
    - value: 40d                       (free text: 40d, 6w, 2 sprint, L)
    - date: 2026-07-14
    - note: before any analysis
- todos
  - todo-1788000000
    - text: …
    - deadline: 2026-09-18
- done
  - todo-1787000000
    - text: …
    - completed_at: 2026-08-26 17:40

## Notes

Free markdown, kept verbatim through a save.
````

Three rules are worth knowing before hand-editing a card:

- A `- ` item is a key/value pair only when the text before the first colon is
  a key (`[a-z][a-z0-9_]*`) and the colon is not followed by `//`, so
  `- https://example.com/x` stays a value.
- A group is a map when its children are `- key: value`, a list of strings
  when they are bare values, and a list of objects when a bare child has
  children of its own. An object identifier therefore always carries a dash
  (`task-1`, `RISK-01`), which is what keeps it from reading as a key.
- Comments are not preserved: a save rewrites the outline. Free text belongs
  under `## Notes`.

Attachments live in `<projects>/attachments/<project-id>/`, one folder per
card, listed straight from the filesystem: the card never mentions them, so
there is nothing to drift. Dropping a file in the folder and uploading it from
the panel have the same result.

An estimate is never overwritten. A number came out of a conversation and was
true when it was given, so a new one is appended rather than replacing the last
— which is why `estimates` is a list and nothing in it says which row is
current: the last one is, the same way a note is open because it sits under
`todos`.

The chart is drawn from the cards alone. `timeline.start` with `end` or
`days` gives the project its bar, each `timeline.tasks` row gives one person
theirs, and `who` resolves against `[[squads]]` by name (a squad `prefix` is
still matched, so a card written against the old plan file keeps working).
`flags` may carry `crit`, `active` and `done`. A task outside the span its own
project declares is drawn with a warning marker: the card is wrong, and hiding
that would be worse.

## Before you send a patch

- `python3 -m unittest test_ganttbit` passes, and new behaviour has a test.
  `sample-vault/` is the fixture; extend it rather than inventing a new one.
  Read the exit code rather than the last lines of the output: piping the run
  through `tail` reports whether `tail` succeeded, which it always does.
- The package still imports on Python 3.11, if you develop on anything newer.
- `node --check ganttbit/static/app.js`, and `theme.js` too, if you touched
  either.
- Keep the diff proportionate to the problem. A fix that also reorganises three
  modules is two changes, and only one of them was asked for.
