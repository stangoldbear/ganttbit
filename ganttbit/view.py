"""
Presentation layer: HTML only.

RULE: no CSS and no JavaScript is written here. Assets live in
`static/app.css` and `static/app.js`; layout metrics are handed over as CSS
custom properties so neither side restates a number the other owns.
"""

import json
from urllib.parse import quote

from . import __version__, gantt, settings as settings_module
from .domain import (
    RANGES,
    Timeline,
    band_position,
    chart_spans,
    declared_span,
    format_date_long,
    format_relative,
    group_by_display,
    group_color,
    group_order,
    group_title,
    is_closed_group,
    latest_estimate,
    is_display_group,
    project_estimates,
    project_milestones,
    project_span,
    project_tasks,
    resolve_range,
    resolve_zoom,
)
from .cardmd import NOTES_HEADING
from .gantt import caret
from .markup import (
    attrs, ensure_list, esc, human_size, icon, join_url, render_markdown, safe_url,
    select,
)

_LINK_FIELD_CLASS = {
    'epics': 'jira-epic-field-',
    'confluence': 'confluence-field-',
    'figma': 'figma-field-',
}

# The gem alone is the icon; with the three bars beside it, the logo in the
# header. Both are drawn once, in static/, and the docs page carries a copy.
_FAVICON = '/static/icon.svg'


# ─── Reusable fragments ──────────────────────────────────────────────────────
def _editable_field(label, view, form, *, wrap_id='', style=''):
    """
    A value that reads as information and becomes a form on double click.

    Both halves are rendered here, and the browser only flips which one is
    hidden: an editor whose markup lives in JavaScript is a second source of
    truth for the same field.
    """
    identifier = f' id="{esc(wrap_id)}"' if wrap_id else ''
    inline_style = f' style="{style}"' if style else ''
    return f'''<div class="detail-field editable-field"{identifier}{inline_style}>
  <span class="field-label">{label}</span>
  <div class="editable-view" tabindex="0" title="Double-click to edit">{view}</div>
  <div class="editable-form" hidden>
    {form}
    <div class="editable-actions">
      <button type="button" class="btn btn--default btn--sm" data-action="field-save">Save</button>
      <button type="button" class="btn btn--secondary btn--sm" data-action="field-cancel">Cancel</button>
    </div>
  </div>
</div>'''


def _link_chip(value, base_url, link_class):
    text = str(value).strip()
    if not text:
        return ''
    href = safe_url(join_url(base_url, text))
    if not href:
        return f'<span class="badge badge--outline">{esc(text)}</span>'
    return (f'<a class="{link_class}" href="{esc(href)}" target="_blank" '
            f'rel="noopener noreferrer">{icon("link")}{esc(text)}</a>')

def _todo_row(project_id, todo, *, done, dom_prefix):
    todo_id = todo.get('id', '')
    text = todo.get('text', '')
    deadline = todo.get('deadline', '')

    if done:
        completed = format_date_long(todo.get('completed_at', ''))
        badge = f'<span class="todo-done-at">{esc(completed)}</span>' if completed else ''
    else:
        formatted = format_date_long(deadline)
        badge = f'<span class="todo-dl">{esc(formatted)}</span>' if formatted else ''

    checked = ' checked' if done else ''
    text_class = 'todo-text done' if done else 'todo-text'
    row_class = 'todo-item-row done' if done else 'todo-item-row'
    target = attrs(project=project_id, todo=todo_id)

    draggable = '' if done else ' draggable="true"'
    return f'''<div class="{row_class}" id="{dom_prefix}-{esc(project_id)}-{esc(todo_id)}" data-text="{esc(text)}" data-dl="{esc(deadline)}"{target}{draggable}>
  <label class="todo-check"><input type="checkbox"{checked} data-action="todo-toggle"{target}></label>
  <span class="{text_class}" title="Double-click to edit">{render_markdown(text)}</span>
  {badge}
  <button type="button" class="btn btn--ghost btn--sm btn--icon btn--danger" title="Delete" aria-label="Delete this note" data-action="todo-delete"{target}>✕</button>
</div>'''


def _todo_list(project_id, todos, *, done, dom_prefix, empty_label):
    if not todos:
        return f'<div class="todo-empty">{esc(empty_label)}</div>'
    return ''.join(_todo_row(project_id, todo, done=done, dom_prefix=dom_prefix)
                   for todo in todos)


def _link_row(project_id, kind, value, *, placeholder, param):
    field_class = _LINK_FIELD_CLASS.get(kind, f'{kind}-field-') + project_id
    return f'''<div class="link-row">
  <input type="text" class="form-input form-input--grow {field_class}" value="{esc(value)}" placeholder="{esc(placeholder)}" data-param="{esc(param)}" data-kind="list">
  <button type="button" class="btn btn--ghost btn--sm btn--icon btn--danger" title="Remove" aria-label="Remove this link" data-action="link-remove"{attrs(project=project_id, kind=kind)}>✕</button>
</div>'''


def _link_section(project_id, kind, label, values, *, param, placeholder, base_url='',
                  link_class='jira-link'):
    chips = ''.join(_link_chip(value, base_url, link_class) for value in values)
    rows = ''.join(
        _link_row(project_id, kind, value, placeholder=placeholder, param=param)
        for value in (values or [''])
    )
    view = (f'<div class="chips" data-list="{esc(param)}" data-base-url="{esc(base_url)}" '
            f'data-link-class="{esc(link_class)}">{chips}</div>' if chips
            else f'<div class="chips" data-list="{esc(param)}" data-base-url="{esc(base_url)}" '
                 f'data-link-class="{esc(link_class)}">'
                 f'<span class="editable-empty">None</span></div>')
    form = f'''<div id="{esc(kind)}-container-{esc(project_id)}">{rows}</div>
    <div><button type="button" class="btn btn--outline btn--sm" data-action="link-add"{attrs(project=project_id, kind=kind)}>{icon('plus')}Add</button></div>'''
    return _editable_field(f'{esc(label)} (<span data-count="{esc(param)}">{len(values)}</span>)',
                           view, form)


def _attachment_rows(project_id, attachments):
    if not attachments:
        rows = '<div class="todo-empty">No file attached.</div>'
    else:
        rows = ''.join(
            f'<div class="attachment-row">'
            f'<a class="attachment-row__name" href="/api/project/{esc(quote(project_id))}/attachments/{esc(quote(entry["name"]))}" '
            f'target="_blank" rel="noopener noreferrer" title="{esc(entry["name"])}">'
            f'{icon("clip")}{esc(entry["name"])}</a>'
            f'<span class="attachment-row__size">{esc(human_size(entry["size"]))}</span>'
            f'<button type="button" class="btn btn--ghost btn--sm btn--icon btn--danger" title="Remove" '
            f'aria-label="Remove this attachment" data-action="attachment-delete"'
            f'{attrs(project=project_id, name=entry["name"])}>✕</button>'
            f'</div>'
            for entry in attachments
        )
    return f'''<div class="field-stack">
  <div id="attachments-{esc(project_id)}">{rows}</div>
  <label class="attachment-upload">
    <input type="file" multiple data-change="attachment-upload" data-project="{esc(project_id)}">
  </label>
</div>'''


# ─── Project detail panel ────────────────────────────────────────────────────
def render_detail_row(project, group, at=100.0, settings=None):
    config = settings or settings_module.current()
    project_id = project['id']
    name = project.get('name', project_id)
    status = str(project.get('status', 'active')).lower()
    dates = project.get('dates') or {}
    footprint = project.get('tech_footprint') or {}
    jira = project.get('jira') or {}

    deadline_raw = dates.get('deadline_text') or dates.get('target_delivery') or 'N/A'
    deadline_type = str(dates.get('deadline_type', 'soft')).lower()
    platforms = ensure_list(footprint.get('platforms'))
    todos = project.get('todos') or []
    history = project.get('done') or []
    attachments = project.get('_attachments') or []

    status_select = select(f'status-sel-{project_id}',
                           [(value, value.capitalize())
                            for value in settings_module.STATUS_OPTIONS],
                           status, 'status')
    deadline_select = select(f'deadline-type-{project_id}',
                             settings_module.DEADLINE_OPTIONS, deadline_type,
                             'deadline_type', 'form-input form-input--narrow')
    status_style = settings_module.STATUS_STYLES.get(status, settings_module.STATUS_FALLBACK)
    deadline_style = settings_module.DEADLINE_STYLES.get(
        deadline_type, settings_module.DEADLINE_STYLES['soft'])

    tags = ''.join(
        f'<button type="button" class="tag-opt-btn{" active" if platform in platforms else ""}" '
        f'aria-pressed="{"true" if platform in platforms else "false"}" '
        f'data-action="platform-toggle"{attrs(project=project_id, platform=platform)}>'
        f'{esc(platform)}</button>'
        for platform in config.platforms
    )

    jira_request = str(jira.get('request', '') or '')
    jira_href = safe_url(join_url(config.jira_base_url, jira_request)) if jira_request else ''
    jira_open = (f'<a href="{esc(jira_href)}" target="_blank" rel="noopener noreferrer" '
                 f'class="jira-link">{icon("link")}Open</a>') if jira_href else ''

    epics = _link_section(project_id, 'epics', 'Epics', ensure_list(jira.get('epics')),
                          param='jira_epics', placeholder=config.jira_placeholder,
                          base_url=config.jira_base_url)
    confluence = _link_section(project_id, 'confluence', 'Confluence',
                               ensure_list(project.get('confluence')),
                               param='confluence_links',
                               placeholder=config.confluence_placeholder)
    figma = _link_section(project_id, 'figma', 'Figma', ensure_list(project.get('figma')),
                          param='figma_links', placeholder=config.figma_placeholder)

    # The rows of the timeline, reachable without the chart: on a phone the
    # chart is a glance, and this is where a row is actually edited.
    rows = project_tasks(project, config)
    row_chips = ''.join(
        f'<button type="button" class="badge badge--outline" data-action="row-open"'
        f'{attrs(project=project_id, task=row["id"], who=row["who"], note=row["note"])}'
        f' data-start="{row["start"].strftime("%Y-%m-%d")}"'
        f' data-end="{row["end"].strftime("%Y-%m-%d")}">'
        f'<span style="color:{row["color"]}">{esc(row["role"])}</span>&nbsp;{esc(row["who"])}'
        f'<span class="chip-when">{esc(format_date_long(row["start"], config))} → '
        f'{esc(format_date_long(row["end"], config))}</span></button>'
        for row in rows
    ) or '<span class="editable-empty">None</span>'

    # The bar of the project itself, and the only place it can be drawn from
    # scratch: a new card declares no span, so there is nothing in the chart to
    # grab. What is written and what is drawn are kept apart, because a card
    # with rows and no `timeline.start` already has a bar derived from them.
    declared = declared_span(project)
    drawn = project_span(project, config)
    # The dialog opens on the bar that is there, declared or derived: writing
    # a derived span down is then two clicks rather than two dates.
    span_start = drawn[0].strftime('%Y-%m-%d') if drawn else ''
    span_end = drawn[1].strftime('%Y-%m-%d') if drawn else ''
    if declared:
        span_chip = (f'<span class="badge badge--outline">'
                     f'{esc(format_date_long(declared[0], config))} → '
                     f'{esc(format_date_long(declared[1], config))}</span>')
    elif drawn:
        span_chip = (f'<span class="editable-empty">Derived from the rows: '
                     f'{esc(format_date_long(drawn[0], config))} → '
                     f'{esc(format_date_long(drawn[1], config))}</span>')
    else:
        span_chip = '<span class="editable-empty">None</span>'
    span_button = (
        f'<button type="button" class="btn btn--outline btn--sm" data-action="span-open"'
        f'{attrs(project=project_id)} data-start="{span_start}" data-end="{span_end}">'
        f'{icon("pencil") if declared else icon("plus")}'
        f'{"Edit" if declared else "Set"}</button>')

    # The estimates, oldest first: the history is the point, because the number
    # a project was given before anyone looked at it is still what somebody was
    # told. The last one is the one in force, and says so in a word rather than
    # only in its position.
    estimates = project_estimates(project)
    in_force = latest_estimate(project)
    estimate_chips = ''.join(
        f'<button type="button" class="badge badge--outline" data-action="estimate-open"'
        f'{attrs(project=project_id, estimate=row.get("id", ""), stage=row.get("stage", ""), note=row.get("note", ""))}'
        f' data-value="{esc(row.get("value", ""))}" data-date="{esc(row.get("date", ""))}">'
        f'<span class="chip-when">{esc(row.get("stage", ""))}</span>'
        f'{esc(row.get("value", ""))}'
        f'{" — now" if row is in_force else ""}</button>'
        for row in estimates
    ) or '<span class="editable-empty">None</span>'

    milestones = project_milestones(project, config)
    milestone_chips = ''.join(
        f'<button type="button" class="badge badge--outline" data-action="milestone-open"'
        f'{attrs(project=project_id, milestone=mark["id"], text=mark["text"])}'
        f' data-date="{mark["date"].strftime("%Y-%m-%d")}">{icon("diamond")}'
        f'{esc(format_date_long(mark["date"], config))}'
        f'{" — " + esc(mark["text"]) if mark["text"] else ""}</button>'
        for mark in milestones
    ) or '<span class="editable-empty">None</span>'

    blocked_display = 'block' if status == 'blocked' else 'none'
    intro_text = str(project.get('intro') or '')
    intro_display = (
        f'<span class="intro-text" title="Double-click to edit">'
        f'{render_markdown(intro_text)}</span>'
        if intro_text.strip()
        else '<span class="intro-text intro-text--empty" title="Double-click to edit">'
             'No general information yet. Double-click to add some.</span>'
    )

    return f'''<tr class="detail-row" data-detail-group="{esc(group)}" data-proj-id="{esc(project_id)}" id="detail-panel-{esc(project_id)}" style="display:none;--at:{at:.2f}%">
  <td colspan="2" class="detail-cell">
    <div class="detail-panel-wrapper">
      <div class="detail-panel-box">
        <div class="detail-header">
          <h4>Notes &amp; actions <span class="detail-header__of">of {esc(name)}</span></h4>
          <span class="detail-header__actions">
            <button type="button" class="btn btn--outline btn--sm" data-action="project-rename" data-project="{esc(project_id)}" data-name="{esc(name)}" title="Rename this project">{icon('pencil')}Rename</button>
            <button type="button" class="btn btn--outline btn--sm" data-action="project-move" data-project="{esc(project_id)}" title="Move this project">{icon('grip')}Move</button>
            <button type="button" class="btn btn--outline btn--sm" data-action="advanced-edit-open" data-project="{esc(project_id)}" title="Every field of this project">{icon('sliders')}Advanced</button>
            <button type="button" class="btn btn--secondary btn--sm" data-action="toggle-detail" data-project="{esc(project_id)}">Close</button>
          </span>
        </div>

        <div class="intro-box" id="intro-box-{esc(project_id)}" data-project="{esc(project_id)}" data-text="{esc(intro_text)}">
          {intro_display}
        </div>

        <div class="detail-grid">
          <div class="detail-col">
            {_editable_field(
                'Project name',
                f'<span data-from="name" data-empty="Untitled">{esc(name)}</span>',
                f'<input type="text" class="form-input" value="{esc(name)}" '
                f'data-param="name" data-value="{esc(name)}" '
                f'aria-label="Project name">')}

            {_editable_field(
                'Project status',
                f'<span class="status-pill" data-from="status" data-format="status" '
                f'style="background:{status_style["bg"]};color:{status_style["fg"]}">'
                f'{esc(status.upper())}</span>',
                f'<div class="field-row">{status_select}</div>')}

            {_editable_field(
                'Blocking reason (shown on hover)',
                f'<span data-from="blocked_reason" data-empty="Not set">'
                f'{esc(project.get("blocked_reason", "")) or "Not set"}</span>',
                f'<input type="text" id="blocked-reason-{esc(project_id)}" class="form-input" '
                f'value="{esc(project.get("blocked_reason", ""))}" data-param="blocked_reason" '
                f'data-value="{esc(project.get("blocked_reason", ""))}" '
                f'placeholder="e.g. waiting for UX mockups...">',
                wrap_id=f'blocked-reason-wrap-{project_id}',
                style=f'display:{blocked_display}')}

            {_editable_field(
                'Deadline &amp; type',
                f'<span data-from="deadline_text" data-format="date">'
                f'{esc(format_date_long(deadline_raw, config))}</span> '
                f'<span class="deadline-pill" data-from="deadline_type" data-format="deadline" '
                f'style="background:{deadline_style["bg"]};color:{deadline_style["fg"]}">'
                f'{esc(deadline_type.upper())}</span>',
                f'<div class="field-row">'
                f'<input type="text" id="deadline-text-{esc(project_id)}" '
                f'class="form-input form-input--grow" value="{esc(deadline_raw)}" '
                f'data-param="deadline_text" data-value="{esc(deadline_raw)}" '
                f'placeholder="e.g. 2026-09-27 or mid September">{deadline_select}</div>')}

            <div class="detail-field">
              <label>Platforms / impacted teams</label>
              <div class="tags-container" id="tags-box-{esc(project_id)}">{tags}</div>
            </div>

            {_editable_field(
                'Jira request',
                f'<span data-from="jira_request" data-empty="Not set" '
                f'data-link-base="{esc(config.jira_base_url)}">'
                f'{esc(jira_request) or "Not set"}</span> {jira_open}',
                f'<input type="text" id="jira-req-{esc(project_id)}" '
                f'class="form-input form-input--grow" value="{esc(jira_request)}" '
                f'data-param="jira_request" data-value="{esc(jira_request)}" '
                f'placeholder="{esc(config.jira_placeholder)}">')}

            {epics}

            {confluence}

            {figma}

            <div class="detail-field">
              <div class="field-heading">
                <span class="field-label">Estimates ({len(estimates)})</span>
                <button type="button" class="btn btn--outline btn--sm" data-action="estimate-open" data-project="{esc(project_id)}">{icon('plus')}Add</button>
              </div>
              <div class="chips" id="estimates-{esc(project_id)}">{estimate_chips}</div>
            </div>

            <div class="detail-field">
              <div class="field-heading">
                <span class="field-label">Project span</span>
                {span_button}
              </div>
              <div class="chips">{span_chip}</div>
            </div>

            <div class="detail-field">
              <div class="field-heading">
                <span class="field-label">Timeline ({len(rows)})</span>
                <button type="button" class="btn btn--outline btn--sm" data-action="row-open" data-project="{esc(project_id)}" data-task="new" data-who="" data-note="" data-start="" data-end="">{icon('plus')}Add</button>
              </div>
              <div class="chips">{row_chips}</div>
            </div>

            <div class="detail-field">
              <div class="field-heading">
                <span class="field-label">Milestones ({len(milestones)})</span>
                <button type="button" class="btn btn--outline btn--sm" data-action="milestone-open" data-project="{esc(project_id)}">{icon('plus')}Add</button>
              </div>
              <div class="chips" id="milestones-{esc(project_id)}">{milestone_chips}</div>
            </div>

            <div class="detail-field">
              <label>Attachments ({len(attachments)})</label>
              {_attachment_rows(project_id, attachments)}
            </div>
          </div>

          <div class="detail-col">
            <div class="detail-field">
              <label for="new-todo-text-{esc(project_id)}">Project action to-do list (<span id="todos-count-{esc(project_id)}">{len(todos)}</span>)</label>
              <div class="todos-box" id="todos-container-{esc(project_id)}">{_todo_list(project_id, todos, done=False, dom_prefix='todo-row', empty_label='No open note or action.')}</div>
              <div class="add-todo-form">
                <textarea id="new-todo-text-{esc(project_id)}" class="add-todo-form__textarea" placeholder="New note / action item..."></textarea>
                <div class="add-todo-form__row">
                  <label class="due-field"><span class="field-label">Due</span>
                    <input type="date" id="new-todo-dl-{esc(project_id)}" class="form-input form-input--date" aria-label="Due date"></label>
                  <button type="button" class="btn btn--default btn--sm" data-action="todo-add" data-project="{esc(project_id)}">Save</button>
                  <button type="button" class="btn btn--secondary btn--sm" data-action="todo-add-cancel" data-project="{esc(project_id)}">Cancel</button>
                </div>
              </div>
            </div>

            <div class="detail-field">
              <button type="button" class="btn btn--outline btn--sm btn--wide" id="btn-hist-{esc(project_id)}" data-action="toggle-history" data-project="{esc(project_id)}"><span class="hist-label">Completed actions (<span class="hist-count">{len(history)}</span>)</span>{caret()}</button>
              <div class="history-box" id="history-box-{esc(project_id)}" data-proj-id="{esc(project_id)}" style="display:none">{_todo_list(project_id, history, done=True, dom_prefix='todo-row', empty_label='Nothing in the history yet.')}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </td>
</tr>'''


# ─── Aggregated to-do view ───────────────────────────────────────────────────
def split_inbox(projects):
    """The reserved inbox card apart from the projects: (inbox or None, projects)."""
    inbox = next((p for p in projects if p.get('id') == settings_module.INBOX_ID), None)
    return inbox, [p for p in projects if p is not inbox]


def render_global_todos(projects, settings=None, inbox=None):
    """
    Open actions, in priority order, the inbox first.

    Finished and abandoned work is left out: it should not keep asking for
    attention. Its notes stay readable in its own panel. A project that has not
    started is not finished work, so it stays on the list: the note to chase an
    estimate is exactly the one worth seeing before the work begins.
    """
    config = settings or settings_module.current()
    grouped = group_by_display(projects, config)
    listed = [project for group in group_order(config) if not is_closed_group(group)
              for project in grouped.get(group, [])]
    cards, total_active, total_done = [], 0, 0

    for index, project in enumerate(listed):
        todos = project.get('todos') or []
        history = project.get('done') or []
        total_active += len(todos)
        total_done += len(history)
        if todos or history:
            cards.append(_todo_card(project, band_position(index, len(listed)),
                                    todos, history, config))

    inbox_todos = (inbox or {}).get('todos') or []
    inbox_done = (inbox or {}).get('done') or []
    total_active += len(inbox_todos)
    total_done += len(inbox_done)
    cards.insert(0, _inbox_card(inbox_todos, inbox_done))

    return ''.join(cards), total_active, total_done


def _todo_sections(project_id, todos, history):
    sections = ''
    if todos:
        sections += ('<div class="todo-group" data-group="open">'
                     '<div class="todo-group-label">Open actions</div>'
                     + _todo_list(project_id, todos, done=False,
                                  dom_prefix='global-todo-row', empty_label='')
                     + '</div>')

    if history:
        sections += ('<div class="todo-group" data-group="done">'
                     '<div class="todo-group-label todo-group-label--history">Completed</div>'
                     + _todo_list(project_id, history, done=True,
                                  dom_prefix='global-todo-row', empty_label='')
                     + '</div>')
    return sections


def _todo_card(project, at, todos, history, config):
    project_id = project['id']
    name = project.get('name', project_id)

    return f'''<div class="global-todo-card" style="--at:{at:.2f}%">
  <div class="global-todo-card__head" data-card="{esc(project_id)}">
    <strong class="global-todo-card__title" title="{esc(project_id)}">{esc(name)}</strong>
    <button type="button" class="btn btn--ghost btn--sm" data-action="go-project" data-project="{esc(project_id)}" title="Open the project with these notes">{icon('panel')}Open project</button>
  </div>
  {_todo_sections(project_id, todos, history)}
</div>'''


def _inbox_card(todos, history):
    """
    The notes of no project, first and always there.

    It has no panel to open, so the field to write a note is on the card
    itself, and an empty inbox is that field: the empty state is the composer.
    """
    project_id = settings_module.INBOX_ID
    return f'''<div class="global-todo-card global-todo-card--inbox" data-inbox>
  <div class="global-todo-card__head" data-card="{esc(project_id)}">
    <strong class="global-todo-card__title" title="{esc(project_id)}">{esc(settings_module.INBOX_TITLE)}</strong>
    <span class="global-todo-card__hint">Notes of no project</span>
  </div>
  <div class="add-todo-form add-todo-form--inbox">
    <textarea id="new-todo-text-{esc(project_id)}" class="add-todo-form__textarea" placeholder="A note or an action, for no project in particular" aria-label="New note for the inbox"></textarea>
    <div class="add-todo-form__row">
      <label class="due-field"><span class="field-label">Due</span>
        <input type="date" id="new-todo-dl-{esc(project_id)}" class="form-input form-input--date" aria-label="Due date"></label>
      <button type="button" class="btn btn--default btn--sm" data-action="todo-add" data-project="{esc(project_id)}">Save</button>
      <button type="button" class="btn btn--secondary btn--sm" data-action="todo-add-cancel" data-project="{esc(project_id)}">Cancel</button>
    </div>
  </div>
  {_todo_sections(project_id, todos, history)}
</div>'''


# ─── Toolbar ─────────────────────────────────────────────────────────────────
_DEPTH_LEVELS = (
    ('compact', 'Compact', 'One line per project: the order, the name and its span'),
    ('projects', 'Projects', 'Every project with its status and deadline'),
    ('people', 'Stakeholders', 'Every project and the people on it'),
    ('details', 'All details', 'Show everything, including the notes and actions '
                               'of every project'),
)
_WINDOW_LABELS = {
    'today': ('From today', 'Start the scale on today'),
    '30d': ('Last 30 days', 'Start the scale 30 days ago'),
    'year': ('This year', 'January to December of the current year'),
    'all': ('All dates', 'Everything the cards describe'),
}


def _depth_switch(action='depth', dom_id='depth-switch'):
    """
    Three levels, not four toggles.

    A toggle answers "what is it now?", which is the one thing a toolbar cannot
    know when half the chart is collapsed and half is not. A level is absolute:
    it always means the same thing and always does it.

    Compact is the stylesheet's job alone: the rows keep every attribute they
    have, and a root attribute tells the chart to stop drawing what a ranked
    reading does not need. No second markup, no second state.
    """
    buttons = ''.join(
        f'<button type="button" class="tab" data-action="{action}" data-depth="{key}" '
        f'title="{esc(title)}" aria-label="{esc(title)}">{icon("level-" + key)}{esc(label)}'
        f'</button>'
        for key, label, title in _DEPTH_LEVELS
    )
    return f'<div class="tabs tabs--sm" id="{dom_id}">{buttons}</div>'


_TREE_DETAIL_LEVELS = (
    ('all', 'All', 'Every key and every value, as the file holds them'),
    ('keys-off', 'No keys', 'Values only; a branch keeps its name'),
    ('relevant', 'Relevant', 'What a day needs: no keys, no ids, the timeline on a line'),
)


def _tree_detail_switch():
    buttons = ''.join(
        f'<button type="button" class="tab" data-action="tree-detail" data-detail="{key}" '
        f'title="{esc(title)}" aria-label="{esc(title)}">{esc(label)}</button>'
        for key, label, title in _TREE_DETAIL_LEVELS
    )
    return f'<div class="tabs tabs--sm" id="tree-detail-switch">{buttons}</div>'


_ZOOM_LABELS = (
    ('day', 'Day', 'One column per day'),
    ('week', 'Week', 'A column per day, a box per week'),
    ('month', 'Month', 'The whole scale, a band per month'),
)


def _zoom_switch(current):
    """How much of the scale fits on screen. A column is always a day."""
    buttons = ''.join(
        f'<button type="button" class="tab{" tab--active" if key == current else ""}" '
        f'data-action="zoom" data-zoom="{key}" title="{esc(title)}">{esc(label)}</button>'
        for key, label, title in _ZOOM_LABELS
    )
    return f'<div class="tabs tabs--sm" id="zoom-switch">{buttons}</div>'


def _window_switch(current):
    """The span the chart is drawn through, and the date behind the last one."""
    custom = current not in _WINDOW_LABELS
    options = ''.join(
        f'<option value="{key}"{" selected" if key == current else ""}>'
        f'{esc(_WINDOW_LABELS[key][0])}</option>'
        for key in RANGES
    )
    options += (f'<option value="date"{" selected" if custom else ""}>'
                f'From a date…</option>')
    chosen = current if custom else ''
    return f'''<span class="window-switch">
        {icon('calendar')}
        <select class="form-input" id="window-select" aria-label="What the chart shows" data-change="window">{options}</select>
        <input type="date" class="form-input form-input--date" id="window-date" aria-label="Show from this date" value="{esc(chosen)}" data-change="window-date"{'' if custom else ' hidden'}>
      </span>'''


# ─── Full document ───────────────────────────────────────────────────────────
def _css_variables(timeline, settings):
    """
    Layout metrics for the stylesheet and the script.

    Emitted before app.css on purpose: these are the defaults, and a media
    query in the stylesheet may narrow them for a small screen. Python owns
    the numbers, CSS owns the responsive policy.
    """
    variables = dict(settings.css_variables())
    if timeline is not None:
        variables['--timeline-w'] = f'{timeline.width}px'
        variables['--col-w'] = f'{timeline.col_width}px'
    body = ''.join(f'{name}:{value};' for name, value in variables.items())
    return f'<style>:root{{{body}}}</style>'


def _shell(config, *, timeline, header_side, content, overlays='', zoom=''):
    """The page around the content: head, header, footer, toasts."""
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <title>{esc(config.title)}</title>
  <link rel="icon" href="{_FAVICON}">
  <link rel="apple-touch-icon" href="/static/apple-touch-icon.png">
  <link rel="manifest" href="/static/manifest.webmanifest">
  <meta name="theme-color" content="#f6f7f9" media="(prefers-color-scheme: light)">
  <meta name="theme-color" content="#0b1220" media="(prefers-color-scheme: dark)">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="default">
  <meta name="apple-mobile-web-app-title" content="{esc(config.title)}">
  {_css_variables(timeline, config)}
  <link rel="stylesheet" href="/static/app.css">
  <link rel="stylesheet" href="/static/themes.css">
  <script src="/static/theme.js"></script>
</head>
<body>
<div class="container" data-shell="{"chart" if timeline is not None else "page"}" data-zoom="{esc(zoom)}" data-months="{esc(",".join(config.months))}" data-status-styles="{esc(json.dumps(settings_module.STATUS_STYLES))}" data-deadline-styles="{esc(json.dumps(settings_module.DEADLINE_STYLES))}">
  <header>
    <div class="wordmark">
      <img class="wordmark__logo" src="/static/logo.svg" alt="">
      <h1>{esc(config.title)}</h1>
    </div>
    {header_side}
  </header>

  {content}

  {_tabbar() if timeline is not None else ''}

  <footer data-surface="more">
    <div class="footer-more">
      <a class="btn btn--outline btn--sm" href="/hierarchy">{icon('panel')}Hierarchy &amp; markdown</a>
      <a class="btn btn--outline btn--sm" href="/api/vault/markdown" download>{icon('clip')}Download the snapshot</a>
    </div>
    <div class="footer-line">{esc(config.footer)}</div>
    <button type="button" class="btn btn--outline btn--sm footer-settings" data-action="settings-open">{icon('sliders')}Settings</button>
  </footer>
</div>

<div id="settings-overlay" class="advedit-overlay" style="display:none" data-action="settings-backdrop" role="dialog" aria-modal="true" aria-labelledby="settings-title">
  <div class="advedit-panel settings-panel">
    <div class="advedit-header">
      <h3 id="settings-title">Settings</h3>
      <button type="button" class="btn btn--secondary btn--sm" data-action="settings-close">Close</button>
    </div>
    <div class="advedit-body settings-body">
      <section class="settings-group">
        <h4 class="settings-group__title">Theme</h4>
        <span class="tabs tabs--sm" id="theme-switch">
          <button type="button" class="tab" data-action="theme" data-theme="system">System</button>
          <button type="button" class="tab" data-action="theme" data-theme="light">Light</button>
          <button type="button" class="tab" data-action="theme" data-theme="dark">Dark</button>
          <button type="button" class="tab" id="theme-more" data-action="theme-gallery" title="More themes">More…</button>
        </span>
      </section>

      <section class="settings-group">
        <h4 class="settings-group__title">Priority band</h4>
        <p class="settings-group__note">Every project carries a band down its left
          edge: full colour at the top of the list, fading to grey at the bottom.
          The shade is worked out against whichever theme is on.</p>
        <div class="settings-presets" id="band-presets"></div>
        <label class="settings-range">
          <span class="settings-range__label">Colour</span>
          <input type="range" id="band-hue" class="hue-track" min="0" max="359"
                 data-change="band" data-band="hue" aria-label="Band colour">
          <output class="settings-range__value" id="band-hue-out"></output>
        </label>
        <label class="settings-range">
          <span class="settings-range__label">Intensity</span>
          <input type="range" id="band-sat" min="0" max="95"
                 data-change="band" data-band="sat" aria-label="Band intensity">
          <output class="settings-range__value" id="band-sat-out"></output>
        </label>
        <label class="settings-range">
          <span class="settings-range__label">Fade</span>
          <input type="range" id="band-fade" min="12" max="45"
                 data-change="band" data-band="fade" aria-label="How far the last band fades">
          <output class="settings-range__value" id="band-fade-out"></output>
        </label>
        <label class="settings-range">
          <span class="settings-range__label">Tint</span>
          <input type="range" id="band-tint" min="0" max="40"
                 data-change="band" data-band="tint" aria-label="How much the band tints the row">
          <output class="settings-range__value" id="band-tint-out"></output>
        </label>
        <label class="settings-option">
          <input type="checkbox" data-change="preference" data-pref="blockedTitle">
          <span class="settings-option__text">Blocked colours the project title
            <span class="settings-option__hint">A blocked project reads red in the list, not only on its pill.</span></span>
        </label>
      </section>

      <section class="settings-group">
        <h4 class="settings-group__title">The chart</h4>
        <label class="settings-option">
          <input type="checkbox" data-change="preference" data-pref="weekdays">
          <span class="settings-option__text">Weekday initials
            <span class="settings-option__hint">A row of letters under the day numbers.</span></span>
        </label>
      </section>

      <section class="settings-group">
        <h4 class="settings-group__title">Confirmations</h4>
        <label class="settings-option">
          <input type="checkbox" data-change="preference" data-pref="save">
          <span class="settings-option__text">Ask before saving
            <span class="settings-option__hint">Every write to a card is confirmed first.</span></span>
        </label>
        <label class="settings-option">
          <input type="checkbox" data-change="preference" data-pref="cancel">
          <span class="settings-option__text">Ask before discarding
            <span class="settings-option__hint">Leaving an editor with unsaved text is confirmed first.</span></span>
        </label>
      </section>

      <section class="settings-group">
        <h4 class="settings-group__title">About</h4>
        <p class="settings-about__line">GanttBit <span class="settings-about__version">{esc(__version__)}</span></p>
        <details class="settings-about">
          <summary class="settings-about__summary">What is in this version</summary>
          <div class="settings-about__notes">{render_markdown(settings_module.release_notes(__version__))}</div>
        </details>
        <p class="settings-group__note">Newer releases are listed on GitHub. The
          link opens a new tab; this application never asks on its own.</p>
        <a class="btn btn--outline btn--sm settings-about__link" href="{settings_module.RELEASES_URL}"
           target="_blank" rel="noopener noreferrer">{icon('link')}Releases on GitHub</a>
      </section>
    </div>
  </div>
</div>
<div id="toast-host"></div>
{overlays}
<script src="/static/app.js"></script>
</body>
</html>'''


_SURFACES = (
    ('projects', 'panel', 'Projects'),
    ('chart', 'sliders', 'Chart'),
    ('notes', 'plus', 'Notes'),
    ('more', 'level-details', 'More'),
)


def _tabbar():
    """
    The phone's shell: four surfaces over the same cards, at the bottom of the
    screen where the thumb is. Never rendered on a desktop, which keeps its
    header nav instead.
    """
    tabs = ''.join(
        f'<button type="button" class="tabbar__tab" data-action="surface" '
        f'data-surface-tab="{key}" aria-label="{esc(label)}">{icon(glyph)}'
        f'<span>{esc(label)}</span></button>'
        for key, glyph, label in _SURFACES
    )
    return f'<nav class="tabbar" aria-label="Views">{tabs}</nav>'


def _new_project_button(*, icon_only=False):
    label = '' if icon_only else 'New project'
    extra = ' btn--icon' if icon_only else ''
    return (f'<button type="button" class="btn btn--outline btn--sm{extra}" '
            f'data-action="project-new" title="New project" aria-label="New project">'
            f'{icon("plus")}{label}</button>')


def _nav(active, count):
    """Two views over the same vault; the count and the new-card button belong to both."""
    links = ''.join(
        f'<a class="btn btn--sm {"btn--secondary" if key == active else "btn--ghost"}" '
        f'href="{href}">{esc(label)}</a>'
        for key, href, label in (('chart', '/', 'Chart'), ('hierarchy', '/hierarchy', 'Hierarchy'))
    )
    return (f'<div class="header-side">{links}{_new_project_button()}'
            f'<span class="header-stat"><strong>{count}</strong> projects</span></div>')


def render_page(projects, *, window='', zoom='', today=None, settings=None):
    config = settings or settings_module.current()
    inbox, projects = split_inbox(projects)
    start_from, end_at, window_key = resolve_range(window, today)
    col_width, zoom_key = resolve_zoom(zoom)
    timeline = Timeline(chart_spans(projects, config), settings=config, col_width=col_width,
                        today=today, start_from=start_from, end_at=end_at,
                        horizon=settings_module.ZOOM_HORIZON.get(zoom_key, 0))
    chart = gantt.render(projects, timeline,
                         detail_row=lambda project, group, at: render_detail_row(project, group, at, config),
                         settings=config)
    todos_html, active_count, done_count = render_global_todos(projects, config, inbox=inbox)

    content = f"""{_project_list(projects, timeline, config, today)}

  <div class="global-todos-box" data-surface="notes">
    <div class="global-todos-header" data-action="toggle-global">
      <div class="global-todos-title">
        <span>Actions &amp; notes</span>
        <span class="badge" id="global-todos-counter" data-open="{active_count}" data-done="{done_count}">{active_count} open / {done_count} done</span>
      </div>
      <button type="button" id="btn-toggle-global-todos" class="btn btn--ghost btn--sm btn--icon" data-action="toggle-global" aria-label="Collapse or expand the aggregated actions">{caret()}</button>
    </div>
    <div id="global-todos-content" class="global-todos-content">{todos_html}</div>
  </div>

  <div class="gantt-box" data-surface="chart">
    <div class="gantt-toolbar">
      <div class="gantt-search">
        <input type="search" id="search-field" class="form-input" placeholder="Search projects, people, notes" aria-label="Search the chart" data-change="search">
        <span class="gantt-search__count" id="search-count"></span>
      </div>
      <div class="gantt-toolbar__actions">
        {_depth_switch()}
        {_zoom_switch(zoom_key)}
        {_window_switch(window_key)}
      </div>
    </div>
    {chart}
  </div>"""

    overlay = f"""<div id="advanced-edit-overlay" class="advedit-overlay" style="display:none" data-action="advanced-edit-backdrop" role="dialog" aria-modal="true" aria-labelledby="advedit-title">
  <div class="advedit-panel">
    <div class="advedit-header">
      <h3 id="advedit-title">Advanced edit</h3>
      <span class="detail-header__actions">
        <button type="button" class="btn btn--outline btn--sm" data-action="advanced-edit-simple" title="The handful of fields, in one form">{icon('pencil')}Simple edit</button>
        <button type="button" class="btn btn--secondary btn--sm" data-action="advanced-edit-close">Close</button>
      </span>
    </div>
    <div class="tabs advedit-tabs">
      <button type="button" class="tab tab--active" id="advedit-tab-form" data-action="advanced-edit-tab" data-tab="form">Form</button>
      <button type="button" class="tab" id="advedit-tab-raw" data-action="advanced-edit-tab" data-tab="raw">Markdown</button>
    </div>
    <div id="advedit-body-form" class="advedit-body">Loading...</div>
    <div id="advedit-body-raw" class="advedit-body" style="display:none">
      <textarea id="advedit-raw-textarea" class="advedit-raw-textarea" spellcheck="false" aria-label="The card as markdown"></textarea>
    </div>
    <div class="advedit-footer">
      <button type="button" class="btn btn--secondary btn--sm" data-action="advanced-edit-close">Cancel</button>
      <button type="button" class="btn btn--default btn--sm" id="advedit-save-form" data-action="advanced-edit-save-form">Save</button>
      <button type="button" class="btn btn--default btn--sm" id="advedit-save-raw" style="display:none" data-action="advanced-edit-save-raw">Save</button>
    </div>
  </div>
</div>"""

    return _shell(config, timeline=timeline, header_side=_nav('chart', len(projects)),
                  content=content, overlays=overlay, zoom=zoom_key)


# ─── The project list: the phone's first surface ─────────────────────────────
def _initials(name):
    parts = [word for word in str(name or '').split() if word]
    if not parts:
        return '?'
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _sparkline(project, timeline, settings):
    """
    The project's span against the whole scale, with today and its milestones.

    A phone cannot show a chart, but it can show where one project sits in the
    year, which is the only thing a card needs from the timeline.
    """
    if not timeline.width:
        return ''

    def percent(pixels):
        return max(0.0, min(100.0, pixels / timeline.width * 100))

    span = project_span(project, settings)
    bar = ''
    if span:
        geometry = timeline.geometry(span[0], span[1])
        if geometry:
            left, width = geometry
            bar = (f'<span class="spark__bar" style="left:{percent(left):.2f}%;'
                   f'width:{max(1.0, percent(width)):.2f}%"></span>')

    marks = ''
    for mark in project_milestones(project, settings):
        geometry = timeline.geometry(mark['date'], mark['date'])
        if geometry:
            marks += (f'<span class="spark__mark" '
                      f'style="left:{percent(geometry[0]):.2f}%"></span>')

    today = ''
    if timeline.today_index is not None:
        offset = timeline.today_index * timeline.col_width
        today = f'<span class="spark__today" style="left:{percent(offset):.2f}%"></span>'

    return f'<span class="spark">{bar}{marks}{today}</span>'


def _project_card(project, at, timeline, settings, today):
    project_id = project['id']
    status = str(project.get('status', 'active')).lower()
    style = settings_module.STATUS_STYLES.get(status, settings_module.STATUS_FALLBACK)
    dates = project.get('dates') or {}
    deadline = dates.get('deadline_text') or dates.get('target_delivery') or ''
    relative = format_relative(deadline, today, settings)
    rows = project_tasks(project, settings)
    todos = project.get('todos') or []

    people = []
    for row in rows:
        mark = _initials(row['who'])
        if mark not in people:
            people.append(mark)
    crowd = ''.join(f'<span class="pcard__who">{esc(mark)}</span>' for mark in people[:4])
    if len(people) > 4:
        crowd += f'<span class="pcard__who pcard__who--more">+{len(people) - 4}</span>'

    when = esc(format_date_long(deadline, settings)) if deadline else 'no deadline'
    if relative:
        when += f' <span class="pcard__relative">· {esc(relative)}</span>'

    notes = (f'<span class="pcard__notes">{len(todos)} note'
             f'{"" if len(todos) == 1 else "s"}</span>') if todos else ''

    return f'''<button type="button" class="pcard" data-action="open-project" aria-expanded="false" data-project="{esc(project_id)}" data-status="{esc(status)}" style="--at:{at:.2f}%">
  <span class="pcard__head">
    <span class="prio-badge">{esc(project.get('priority', ''))}</span>
    <span class="pcard__name">{esc(project.get('name', project_id))}</span>
  </span>
  <span class="pcard__signals">
    <span class="status-pill" style="background:{style['bg']};color:{style['fg']}">{esc(status.upper())}</span>
    <span class="pcard__when">{when}</span>
  </span>
  {_sparkline(project, timeline, settings)}
  <span class="pcard__foot">
    <span class="pcard__people">{crowd}</span>
    {notes}
  </span>
</button>'''


def _project_list(projects, timeline, settings, today):
    """Every project as a card: the ranked list, then DONE and DROPPED."""
    grouped = group_by_display(projects, settings)
    blocks = []

    for group in group_order(settings):
        members = grouped.get(group, [])
        if not members:
            continue
        closed = is_display_group(group)
        cards = ''.join(
            _project_card(project, 100.0 if closed else band_position(index, len(members)),
                          timeline, settings, today)
            for index, project in enumerate(members))
        # The live list needs no heading: it is the page. The two below it do,
        # because the eye has to know where the work stops being current.
        heading = '' if not closed else (
            f'<h3 class="plist__title">'
            f'<span class="group-row__marker" style="background:{group_color(group, settings)}">'
            f'</span>{esc(group_title(group, settings))}'
            f'<span class="badge">{len(members)}</span></h3>')
        blocks.append(f'<section class="plist__group">{heading}{cards}</section>')

    body = ''.join(blocks) or '<div class="todo-empty">No project card in the vault.</div>'
    return f'''<div class="plist" data-surface="projects">
  <div class="plist__search">
    <input type="search" class="form-input" placeholder="Search projects, people, notes" aria-label="Search" data-change="search">
    {_new_project_button(icon_only=True)}
  </div>
  {body}
</div>'''


# ─── Hierarchy: the whole vault as a tree, and as one document ───────────────
def _entry(key, value, path):
    """
    One line of the tree: a leaf, or a branch that folds.

    `data-key` is the name in the file, for the stylesheet to decide what a
    level shows; `data-path` is where the value lives in the card, for an edit
    to say what it changed. A branch is a `details`, so it folds with no
    script and keeps folding when the page reloads under a level.
    """
    if isinstance(value, dict):
        value = {k: v for k, v in value.items() if not str(k).startswith('_')}
    if isinstance(value, list) and value and not any(isinstance(item, dict) for item in value):
        # A list of plain values is one line, not a branch: three platforms
        # or two flags are read at a glance, and each is still its own value.
        items = ''.join(f'<span class="tree__item">{_leaf(item, f"{path}.{index}").strip()}</span>'
                        for index, item in enumerate(value))
        return (f'<li class="tree__entry tree__entry--list" data-key="{esc(key)}">'
                f'<span class="tree__key">{esc(key)}</span> <span class="tree__list">{items}</span></li>')
    is_branch = isinstance(value, (dict, list)) and bool(value)
    if not is_branch:
        return (f'<li class="tree__entry" data-key="{esc(key)}">'
                f'<span class="tree__key">{esc(key)}</span>{_leaf(value, path)}</li>')
    return (f'<li class="tree__entry tree__entry--branch" data-key="{esc(key)}"><details open>'
            f'<summary><span class="tree__key">{esc(key)}</span></summary>'
            f'{_entry_tree(value, path)}</details></li>')


def _leaf(value, path):
    """A value as the file holds it; an empty one says so rather than vanish."""
    if isinstance(value, bool):
        text = 'true' if value else 'false'
    elif isinstance(value, (dict, list)):
        return ' <span class="tree__empty">empty</span>'
    else:
        text = '' if value is None else str(value)
    editable = f' data-path="{esc(path)}" tabindex="0" title="Double-click to edit"'
    if not text.strip():
        return f' <span class="tree__empty tree__leaf"{editable}>empty</span>'
    if '\n' in text:
        return f'<div class="tree__text tree__leaf"{editable}>{esc(text)}</div>'
    return f' <span class="tree__value tree__leaf"{editable}>{esc(text)}</span>'


def _entry_tree(value, path=''):
    """
    Every value a card holds, as it holds it.

    The structure view is a reading of the file, not a summary of it: keys keep
    the names the card uses, an empty value says it is empty rather than
    disappearing, and a key nobody in this codebase knows about is rendered
    like any other.
    """
    def join(part):
        return f'{path}.{part}' if path else str(part)

    if isinstance(value, dict):
        items = ''.join(_entry(key, item, join(key))
                        for key, item in value.items() if not str(key).startswith('_'))
        return f'<ul>{items}</ul>' if items else ''

    if isinstance(value, list):
        items = ''
        for index, item in enumerate(value):
            if isinstance(item, dict):
                # An object in a list is addressed by its id, as the file does.
                identity = str(item.get('id', '') or '') or str(index)
                items += _entry(identity, {k: v for k, v in item.items() if k != 'id'},
                                join(identity))
            else:
                items += (f'<li class="tree__entry" data-key="{esc(index)}">'
                          f'{_leaf(item, join(index)).lstrip()}</li>')
        return f'<ul>{items}</ul>'

    return _leaf(value, path)


def _tree_fields(project):
    """Everything the card says, the body last because it is last in the file."""
    data = {key: value for key, value in project.items() if key != 'name'}
    fields = _entry_tree(data)
    body = str(project.get('_body') or '').strip()
    if body:
        # The body is not an entry: it is the text under `## Notes`, addressed
        # as such so an edit rewrites that and nothing else.
        fields = fields[:-len('</ul>')] + (
            f'<li class="tree__entry" data-key="notes"><span class="tree__key">'
            f'{esc(NOTES_HEADING)}</span>{_leaf(body, "_body")}</li></ul>')
    return fields


def _tree_summary(project, settings):
    """
    Everything the levels can show of a project, on its one line.

    All of it is always here; the root attribute says which parts the level
    reads. One markup, no second state.
    """
    span = project_span(project, settings)
    when = (f'{format_date_long(span[0], settings)} → '
            f'{format_date_long(span[1], settings)}') if span else 'no span declared'
    status = str(project.get('status', 'active')).lower()
    style = settings_module.STATUS_STYLES.get(status, settings_module.STATUS_FALLBACK)

    dates = project.get('dates') or {}
    deadline_raw = dates.get('deadline_text') or dates.get('target_delivery') or ''
    deadline = ''
    if deadline_raw:
        deadline_type = str(dates.get('deadline_type', 'soft')).lower()
        deadline_style = settings_module.DEADLINE_STYLES.get(
            deadline_type, settings_module.DEADLINE_STYLES['soft'])
        deadline = (f'<span class="deadline-pill tree__deadline" style="background:'
                    f'{deadline_style["bg"]};color:{deadline_style["fg"]}">'
                    f'{esc(format_date_long(deadline_raw, settings))} '
                    f'[{esc(deadline_type.upper())}]</span>')

    people = []
    for row in project_tasks(project, settings):
        if row['who'] not in people:
            people.append(row['who'])
    crowd = ''.join(f'<span class="tree__who">{esc(who)}</span>' for who in people)

    return (f'<span class="prio-badge">{esc(project.get("priority", ""))}</span> '
            f'<strong>{esc(project.get("name", project["id"]))}</strong> '
            f'<span class="tree__signals">'
            f'<span class="status-pill" style="background:{style["bg"]};color:{style["fg"]}">'
            f'{esc(status.upper())}</span> '
            f'<span class="tree__when">{esc(when)}</span> {deadline}</span>'
            f'<span class="tree__people">{crowd}</span>')


def _inbox_tree(inbox):
    """The inbox as its own list above the projects: it is not one of them."""
    if inbox is None:
        return ''
    return (f'<ul class="tree tree--inbox"><li class="tree__project" data-project="{esc(inbox["id"])}">'
            f'<details open><summary><strong>{esc(inbox.get("name", inbox["id"]))}</strong> '
            f'<span class="tree__when">notes of no project</span></summary>'
            f'{_tree_fields(inbox)}</details></li></ul>')


def _tree(projects, settings):
    """The hierarchy as a list: project → everything the card says, ranked."""
    grouped = group_by_display(projects, settings)
    blocks = []

    for group in group_order(settings):
        members = grouped.get(group, [])
        if not members:
            continue

        items = [
            f'<li class="tree__project" data-project="{esc(project["id"])}"><details open>'
            f'<summary>{_tree_summary(project, settings)}</summary>'
            f'{_tree_fields(project)}</details></li>'
            for project in members
        ]

        # The live list is the tree; only a closing group announces itself.
        if is_display_group(group):
            blocks.append(
                f'<li class="tree__group">'
                f'<span class="group-row__marker" style="background:{group_color(group, settings)}">'
                f'</span>{esc(group_title(group, settings))} '
                f'<span class="badge">{len(members)}</span>'
                f'<ul>{"".join(items)}</ul></li>')
        else:
            blocks.append(''.join(items))

    return f'<ul class="tree">{"".join(blocks)}</ul>' if blocks else (
        '<div class="todo-empty">No project card in the vault.</div>')


def render_hierarchy_page(projects, markdown, *, settings=None):
    """
    Two readings of the same vault: the structure, and the text behind it.

    The markdown tab is every card in one editable document: the monthly
    snapshot, and the way to edit many cards at once.
    """
    config = settings or settings_module.current()
    inbox, projects = split_inbox(projects)

    content = f"""<div class="gantt-box">
    <div class="view-toolbar">
      <div class="tabs">
        <button type="button" class="tab tab--active" data-action="view-tab" data-tab="structure">Structure</button>
        <button type="button" class="tab" data-action="view-tab" data-tab="markdown">Markdown</button>
      </div>
      <div class="view-toolbar__actions" id="tree-controls">
        {_depth_switch(action='tree-depth', dom_id='tree-depth-switch')}
        {_tree_detail_switch()}
      </div>
    </div>

    <div id="view-structure" class="view-panel">{_inbox_tree(inbox)}{_tree(projects, config)}</div>

    <div id="view-markdown" class="view-panel" hidden>
      <p class="view-hint">Every card, in the order the chart draws them. A block
      with an unknown <code>- id:</code> creates a card; a card whose block is not
      here is left alone. Nothing is ever deleted from this screen.</p>
      <textarea id="vault-markdown" class="advedit-raw-textarea" spellcheck="false" aria-label="Every card as one markdown document">{esc(markdown)}</textarea>
      <div class="view-actions">
        <button type="button" class="btn btn--default btn--sm" data-action="vault-markdown-save">Save all</button>
        <a class="btn btn--outline btn--sm" href="/api/vault/markdown" download>{icon('clip')}Download snapshot</a>
      </div>
    </div>
  </div>"""

    return _shell(config, timeline=None, header_side=_nav('hierarchy', len(projects)),
                  content=content)
