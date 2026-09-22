"""
Gantt chart rendering: header, group rows, project rows, resource rows.

Geometry comes from `domain`; layout metrics travel as CSS custom properties,
so the stylesheet and the resize script never restate them.

Rank reaches the markup as one custom property, `--at`: how far down the
priority ramp the row sits, as a percentage. The two ends of that ramp are
theme tokens the browser resolves, so no colour is computed here: the
stylesheet decides how much of it to spend (a rail and a tint), and the
timeline lane beside it never takes it at all.
"""

import json

from . import settings as settings_module
from .domain import (
    band_position,
    format_date_long,
    group_by_display,
    group_color,
    group_order,
    group_title,
    is_display_group,
    project_milestones,
    project_span,
    project_tasks,
    search_text,
)
from .markup import attrs, ensure_list, esc, icon

# How much of the chart is unfolded, from the toolbar over the whole chart and
# from the switch every project row carries over itself: (key, label, what the
# level means for the chart, what it means for one project). Four levels, one
# glyph each, and the same four on the hierarchy page.
DEPTH_LEVELS = (
    ('compact', 'Compact',
     'One line per project: the order, the name and its span',
     'One line: the name and the span'),
    ('projects', 'Projects',
     'Every project with its status, deadline and platforms',
     'The status, the deadline and the platforms'),
    ('people', 'Stakeholders',
     'Every project and the people on it',
     'The people on it, and where to add one'),
    ('details', 'All details',
     'Show everything, including the notes and actions of every project',
     'Everything, the notes and actions included'),
)


def caret(open_state=True):
    """The one collapse glyph: an SVG chevron, turned by CSS when it closes."""
    return f'<span class="caret{"" if open_state else " is-closed"}">{icon("caret")}</span>'


def depth_switch(action='depth', dom_id='depth-switch'):
    """
    Four levels, not four toggles, over the whole chart.

    A toggle answers "what is it now?", which is the one thing a toolbar cannot
    know when half the chart is collapsed and half is not. A level is absolute:
    it always means the same thing and always does it.

    Compact is the stylesheet's job alone: the rows keep every attribute they
    have, and a class on the row tells the chart to stop drawing what a ranked
    reading does not need. No second markup, no second state.
    """
    buttons = ''.join(
        f'<button type="button" class="tab" data-action="{action}" data-depth="{key}" '
        f'title="{esc(title)}" aria-label="{esc(title)}">{icon("level-" + key)}{esc(label)}'
        f'</button>'
        for key, label, title, _own in DEPTH_LEVELS
    )
    return f'<div class="tabs tabs--sm" id="{dom_id}">{buttons}</div>'


def _row_depth_switch(project_id, name):
    """
    The same four levels, over one project.

    What the toolbar does to every row, this does to the row it sits on: fold
    the people away, show them, open the notes under them. It took the place
    of the button that only opened the notes, because that was one of the
    four and the other three were a toolbar away.
    """
    buttons = ''.join(
        f'<button type="button" class="tab" data-action="project-depth" '
        f'data-project="{esc(project_id)}" data-depth="{key}" '
        f'title="{esc(label)}: {esc(own)}" aria-label="{esc(label)}, {esc(name)}">'
        f'{icon("level-" + key)}</button>'
        for key, label, _title, own in DEPTH_LEVELS
    )
    return (f'<span class="tabs tabs--sm row-depth" role="group" '
            f'aria-label="How much of {esc(name)} to show">{buttons}</span>')


def render(projects, timeline, *, detail_row, settings=None):
    """
    The whole chart as one `<table>`.

    Every bar comes from the card that owns it: the chart asks a project for
    its span and its rows and draws them. `detail_row(project, group, at)` is
    injected, so the chart places the expandable panel but knows nothing about
    its contents.
    """
    config = settings or settings_module.current()
    grouped = group_by_display(projects, config)

    parts = [_header(timeline, config)]

    for group in group_order(config):
        members = grouped.get(group, [])
        # The live list is the chart and carries no heading of its own. DONE and
        # DROPPED always get one, even with nothing under it, because dropping a
        # project onto that heading is how it gets there.
        closed = is_display_group(group)
        if closed:
            parts.append(_group_header(group, len(members), config))

        for index, project in enumerate(members):
            # A finished project has no rank left to show: it takes the cold end
            # of the ramp, where a live project in last place would sit.
            at = 100.0 if closed else band_position(index, len(members))
            parts.extend(_project_block(project, group, at, timeline, detail_row, config))

    parts.append('</tbody></table></div>')
    return '\n'.join(parts)


def _day_classes(day, timeline):
    """
    The calendar header boxes every Monday-to-Friday run.

    The weekday reads from the box rather than from a printed letter, and a
    week cut in half by the start or the end of the scale is closed off where
    it is cut.
    """
    classes = ['day-cell', f'day-cell--{timeline.day_state(day)}']
    if day.weekday() >= 5:
        classes.append('day-cell--weekend')
        return classes

    classes.append('day-cell--wd')
    if day.weekday() == 0 or day == timeline.days[0]:
        classes.append('day-cell--w-start')
    if day.weekday() == 4 or day == timeline.days[-1]:
        classes.append('day-cell--w-end')
    return classes


def _header(timeline, config):
    # A month gets its year back only when there is room to print it, and when
    # there is not, the year is not dropped but promoted to a row of its own:
    # zoomed out is exactly where a chart crosses a new year.
    wide = timeline.col_width >= settings_module.COL_W / 2
    months = ''.join(
        f'<div class="month-cell" style="width:calc(var(--col-w) * {count})">'
        f'{config.month_abbr[month - 1]}{f" {year}" if wide else ""}</div>'
        for (year, month), count in timeline.months
    )
    years = '' if wide else ''.join(
        f'<div class="year-cell" style="width:calc(var(--col-w) * {count})">{year}</div>'
        for year, count in timeline.years
    )
    # The date travels with the cell: it is what turns a click at an x offset
    # in a lane into the day the pointer is over.
    # The number is dropped when it cannot be read; the week boxes and the
    # month bands keep saying where you are.
    numbered = timeline.col_width >= 12
    days = ''.join(
        f'<div class="{" ".join(_day_classes(day, timeline))}" '
        f'data-date="{day.strftime("%Y-%m-%d")}">{day.day if numbered else ""}</div>'
        for day in timeline.days
    )

    grid = _grid_lines(timeline)
    initials = ''.join(
        f'<div class="day-name day-name--{timeline.day_state(day)}">'
        f'{esc(config.weekday_initials[day.weekday()])}</div>'
        for day in timeline.days
    )
    # Built before the document below, not inside it: an f-string expression
    # holding another f-string of the same quote only parses on Python 3.12,
    # and the stated floor is 3.11.
    year_row = f'''<tr class="year-row">
      <th class="label-head sticky-col"></th>
      <th class="timeline-head">
        <div class="timeline-strip">{years}</div>
      </th>
    </tr>''' if years else ''

    today_index = timeline.today_index
    band = ''
    if today_index is not None:
        offset = today_index * timeline.col_width
        band = (f'<div class="today-band" data-offset="{offset}" '
                f'style="--today-offset:{offset}px"></div>')

    return f'''<div class="gantt-scroll" id="gantt-scroll">
{grid}
{band}
<div class="col-resize-handle" id="col-resize-handle"><div class="col-resize-handle__bar" title="Drag to resize"></div></div>
<div class="scroll-shades" aria-hidden="true"><div class="scroll-shade scroll-shade--left"></div><div class="scroll-shade scroll-shade--right"></div></div>
<table class="gantt-table" id="gantt-table">
  <colgroup>
    <col class="label-col">
    <col class="timeline-col">
  </colgroup>
  <thead>
    {year_row}
    <tr>
      <th class="label-head sticky-col">
        <div class="label-head__title">Project &amp; assigned resources</div>
      </th>
      <th class="timeline-head">
        <div class="timeline-strip">{months}</div>
      </th>
    </tr>
    <tr>
      <th class="label-head sticky-col"></th>
      <th class="timeline-head">
        <div class="timeline-strip">{days}</div>
      </th>
    </tr>
    <tr class="weekday-row">
      <th class="label-head sticky-col"></th>
      <th class="timeline-head">
        <div class="timeline-strip">{initials}</div>
      </th>
    </tr>
  </thead>
  <tbody>'''


def _grid_lines(timeline):
    """
    Where a week and a month begin, drawn down the whole chart.

    The day grid is a repeating gradient on every lane, which cannot know when
    a month changes, because months have different numbers of working days. These two
    are positioned once, here, from the scale itself.
    """
    lines, previous = [], None
    for index, day in enumerate(timeline.days):
        if index and previous and day.month != previous.month:
            kind = 'month'
        elif index and day.weekday() == 0:
            kind = 'week'
        else:
            previous = day
            continue
        left = index * timeline.col_width
        lines.append(f'<div class="grid-line grid-line--{kind}" style="left:{left}px"></div>')
        previous = day

    return f'<div class="grid-lines" aria-hidden="true">{"".join(lines)}</div>' if lines else ''


def _group_header(group, count, config):
    title = group_title(group, config)
    return f'''<tr class="group-row" data-group="{esc(group)}" style="--marker:{group_color(group, config)}">
  <td class="sticky-col group-row__cell">
    <div class="group-row__inner">
      <button type="button" class="btn btn--ghost btn--sm btn--icon" id="btn-group-{esc(group)}" data-action="toggle-group" data-group="{esc(group)}" title="Collapse or expand this group" aria-label="Collapse or expand {esc(title)}">{caret()}</button>
      <span class="group-row__marker"></span>
      <span class="group-row__title">{esc(title)}</span>
      <span class="badge">{count}</span>
    </div>
  </td>
  <td class="group-row__band"></td>
</tr>'''


def _project_block(project, group, at, timeline, detail_row, config):
    rows_of_project = project_tasks(project, config)

    rows = [_project_row(project, group, at, rows_of_project, timeline, config)]
    rows.extend(_resource_row(project['id'], group, at, task, timeline, config)
                for task in rows_of_project)
    # After the people, the place for one more: a line of the same shape that
    # opens the row dialog, so a project with nobody on it yet still unfolds
    # to something at the Stakeholders level, and the first row is written
    # from the chart rather than from a form behind it.
    rows.append(_add_row(project, group, at, config))
    rows.append(detail_row(project, group, at))
    return rows


def _summary_bar(project, timeline, status, config):
    span = project_span(project, config)
    if not span:
        return ''
    start, end = span
    geometry = timeline.geometry(start, end)
    if not geometry:
        return ''
    left, width = geometry
    # Blocked is a signal and outranks the rank: it floods the bar. Every other
    # project takes the rail its position already earned, resolved by the
    # stylesheet rather than named here.
    fill = settings_module.BLOCKED_COLOR if status == 'blocked' else 'var(--rail)'
    blocked = ' summary-bar--blocked' if status == 'blocked' else ''
    span = (f'{format_date_long(start, config)} → {format_date_long(end, config)}')
    return (f'<div class="task-bar summary-bar{blocked}" style="left:{left}px;width:{width}px;'
            f'background:{fill}" title="Project span: {esc(span)}"'
            f'{attrs(project=project["id"])} data-start="{start.strftime("%Y-%m-%d")}" '
            f'data-end="{end.strftime("%Y-%m-%d")}">{_grips()}</div>')


def _project_row(project, group, at, rows_of_project, timeline, config):
    project_id = project['id']
    name = project.get('name', project_id)
    status = str(project.get('status', 'active')).lower()
    dates = project.get('dates') or {}

    status_style = settings_module.STATUS_STYLES.get(status, settings_module.STATUS_FALLBACK)
    deadline_raw = dates.get('deadline_text') or dates.get('target_delivery') or 'N/A'
    deadline_type = str(dates.get('deadline_type', 'soft')).lower()
    deadline_style = settings_module.DEADLINE_STYLES.get(
        deadline_type, settings_module.DEADLINE_STYLES['soft'])

    reason = project.get('blocked_reason', '')
    tooltip = ''
    if status == 'blocked' and reason:
        tooltip = f'<span class="blocked-tooltip"><strong>Blocked:</strong> {esc(reason)}</span>'

    bar = _summary_bar(project, timeline, status, config)
    warning = _warning(any(task['outside'] for task in rows_of_project),
                       'A task on this project falls outside the span it declares')

    # What the browser filters on travels with the row, escaped: the platforms
    # as a list, and the whole card as one text, so a search reaches the notes
    # body and a risk that the panel never shows, and a project in a collapsed
    # band as easily as one on screen. The platform tags themselves left the
    # chart entirely; the detail panel lists them.
    # Spelled the way the menu spells them (`domain.used_values`): as text,
    # trimmed, and never empty, so a tick in the menu and a tag on the card
    # compare equal.
    platforms = [str(item).strip()
                 for item in ensure_list((project.get('tech_footprint') or {}).get('platforms'))
                 if str(item).strip()]
    filter_data = (f' data-platforms="{esc(json.dumps(platforms))}"'
                   f' data-search="{esc(search_text(project))}"')

    # Three lines, the same three on every row. The first is identity, with
    # the row actions over its right end, shown on hover or keyboard focus:
    # the level switch for this one project, and Edit. Advanced edit is not
    # here: it is reached from inside the simple form, so a project has one
    # way in, and the second editor sits behind it. Under the title, the two
    # signals on a line of their own, the status at the left and the deadline
    # at the right; under those, the platforms, on a line that is drawn even
    # when there is nothing on it, so a project with no platform stands as
    # tall as one with three and the list reads as rows of one shape.
    return f'''<tr class="project-main-row" data-group-child="{esc(group)}" data-proj-id="{esc(project_id)}" data-status="{esc(status)}"{filter_data} style="--at:{at:.2f}%" draggable="true">
  <td class="sticky-col project-cell">
    <div class="project-line project-line--head">
      <div class="project-identity">
        <span class="drag-handle" title="Drag to reorder">{icon('grip')}</span>
        <button type="button" class="btn btn--ghost btn--sm btn--icon" id="btn-toggle-proj-{esc(project_id)}" data-action="toggle-project" data-project="{esc(project_id)}" title="Collapse or expand the resources" aria-label="Collapse or expand the resources of {esc(name)}">{caret()}</button>
        <span class="prio-badge">{esc(project.get('priority', ''))}</span>
        <strong class="project-title" role="button" tabindex="0" title="{esc(project_id)} — click to rename" data-action="project-title" data-project="{esc(project_id)}" data-name="{esc(name)}">{esc(name)}</strong>{warning}
      </div>
      <span class="project-row__actions">
        {_row_depth_switch(project_id, name)}
        <button type="button" class="btn btn--ghost btn--sm btn--icon" title="Edit" aria-label="Edit {esc(name)}" data-action="simple-edit-open" data-project="{esc(project_id)}">{icon('pencil')}</button>
      </span>
    </div>
    <div class="project-row__signals">
      <span class="project-row__state">
        <span class="status-wrapper" tabindex="0">
          <span class="status-pill" style="background:{status_style['bg']};color:{status_style['fg']}">{esc(status.upper())}</span>
          {tooltip}
        </span>
        <span class="deadline-pill" style="background:{deadline_style['bg']};color:{deadline_style['fg']}">{esc(format_date_long(deadline_raw, config))} [{esc(deadline_type.upper())}]</span>
      </span>
      {_platform_tags(platforms)}
    </div>
  </td>
  <td class="timeline-cell">
    <div class="timeline-row timeline-row--project" data-lane="{esc(project_id)}">{bar}{_milestones(project, timeline, config)}</div>
  </td>
</tr>'''


def _platform_tags(platforms):
    """
    The platforms a project touches, as tags on its row.

    They belong to the Projects level, on the line under the status and the
    deadline: the two signals first, then what the project touches. The span
    is always rendered, empty or not: the stylesheet keeps its height, so a
    project with no platform stands as tall as one with three, and a tick in
    the panel patches it in place.
    """
    tags = ''.join(f'<span class="platform-tag">{esc(name)}</span>' for name in platforms)
    return f'<span class="project-row__platforms">{tags}</span>'


def _add_row(project, group, at, config):
    """
    The last line under a project's people: where the next one is added.

    The same shape as a resource row and the same dialog its people open,
    with nothing in it but the project's own span to start from. It folds
    with the people, so it is there at Stakeholders and All details and gone
    at Projects and Compact, and it is why a project with no rows still has
    something to unfold.
    """
    project_id = project['id']
    name = project.get('name', project_id)
    drawn = project_span(project, config)
    start = drawn[0].strftime('%Y-%m-%d') if drawn else ''
    end = drawn[1].strftime('%Y-%m-%d') if drawn else ''
    return f'''<tr class="resource-sub-row resource-sub-row--add" data-group-child="{esc(group)}" data-proj-child="{esc(project_id)}" style="--at:{at:.2f}%">
  <td class="sticky-col resource-cell">
    <div class="resource-line resource-line--add" role="button" tabindex="0" title="Add a timeline row to {esc(name)}" data-action="row-open"{attrs(project=project_id, task='new', who='', note='')} data-start="{start}" data-end="{end}">
      <span class="resource-line__branch">└─</span>
      {icon('plus')}<span>Add a timeline row</span>
    </div>
  </td>
  <td class="timeline-cell">
    <div class="timeline-row timeline-row--resource"></div>
  </td>
</tr>'''


def _milestones(project, timeline, config):
    """
    The one motif of the interface, used for the one thing it means: a date
    that matters. Centred on its day, and never hidden behind a bar.
    """
    marks = []
    for mark in project_milestones(project, config):
        geometry = timeline.geometry(mark['date'], mark['date'])
        if not geometry:
            continue
        left = geometry[0] + (settings_module.COL_W / 2) - 2
        label = f"{format_date_long(mark['date'], config)}"
        if mark['text']:
            label += f" — {mark['text']}"
        marks.append(
            f'<button type="button" class="milestone" style="left:{left:.0f}px" '
            f'title="{esc(label)}" aria-label="{esc(label)}" data-action="milestone-open"'
            f'{attrs(project=project["id"], milestone=mark["id"], text=mark["text"])}'
            f' data-date="{mark["date"].strftime("%Y-%m-%d")}">{icon("diamond")}</button>')
    return ''.join(marks)


def _grips():
    """The two edges a bar can be resized from; the middle moves the whole bar."""
    return ('<span class="bar-grip bar-grip--start" data-grip="start"></span>'
            '<span class="bar-grip bar-grip--end" data-grip="end"></span>')


def _warning(condition, message):
    """A row that does not add up says so, and says what does not add up."""
    if not condition:
        return ''
    return (f'<span class="row-warning" title="{esc(message)}" '
            f'aria-label="{esc(message)}">{icon("warning")}</span>')


def _resource_row(project_id, group, at, task, timeline, config):
    geometry = timeline.geometry(task['start'], task['end'])
    if not geometry:
        return ''

    left, width = geometry
    color = task['color']
    span = f"{format_date_long(task['start'], config)} → {format_date_long(task['end'], config)}"
    label = task['note'] or task['who']
    classes = 'task-bar sub-bar' + (f' sub-bar--{task["type"]}' if task['type'] != 'default' else '')

    bar = (f'<div class="{classes}" style="left:{left}px;width:{width}px;background:{color}" '
           f'title="{esc(label)} — {esc(span)}"'
           f'{attrs(project=project_id, task=task["id"])} '
           f'data-start="{task["start"].strftime("%Y-%m-%d")}" '
           f'data-end="{task["end"].strftime("%Y-%m-%d")}">'
           f'<span class="bar-text">{esc(task["who"])}</span>{_grips()}</div>')

    return f'''<tr class="resource-sub-row" data-group-child="{esc(group)}" data-proj-child="{esc(project_id)}" style="--at:{at:.2f}%">
  <td class="sticky-col resource-cell">
    <div class="resource-line" role="button" tabindex="0" title="Click to edit this row" data-action="row-open"{attrs(project=project_id, task=task['id'], who=task['who'], note=task['note'])} data-start="{task['start'].strftime('%Y-%m-%d')}" data-end="{task['end'].strftime('%Y-%m-%d')}">
      <span class="resource-line__branch">└─</span>
      <span class="resource-line__role" style="color:{color}">{esc(task['role'])}:</span>
      <span>{esc(task['who'])}</span>
      {_warning(task['outside'], 'This task falls outside the span its project declares')}
    </div>
  </td>
  <td class="timeline-cell">
    <div class="timeline-row timeline-row--resource">{bar}</div>
  </td>
</tr>'''
