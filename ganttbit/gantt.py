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
)
from .markup import attrs, esc, icon

def caret(open_state=True):
    """The one collapse glyph: an SVG chevron, turned by CSS when it closes."""
    return f'<span class="caret{"" if open_state else " is-closed"}">{icon("caret")}</span>'


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

    disabled = '' if rows_of_project else ' disabled'
    bar = _summary_bar(project, timeline, status, config)
    warning = _warning(any(task['outside'] for task in rows_of_project),
                       'A task on this project falls outside the span it declares')

    # One line: identity, then the two things that change (status, deadline),
    # then the row actions, which only appear on hover or keyboard focus.
    # The platform tags left the chart entirely; the detail panel lists them.
    return f'''<tr class="project-main-row" data-group-child="{esc(group)}" data-proj-id="{esc(project_id)}" data-status="{esc(status)}" style="--at:{at:.2f}%" draggable="true">
  <td class="sticky-col project-cell">
    <div class="project-line project-line--head">
      <div class="project-identity">
        <span class="drag-handle" title="Drag to reorder">{icon('grip')}</span>
        <button type="button" class="btn btn--ghost btn--sm btn--icon" id="btn-toggle-proj-{esc(project_id)}" data-action="toggle-project" data-project="{esc(project_id)}" title="Collapse or expand the resources" aria-label="Collapse or expand the resources of {esc(name)}"{disabled}>{caret()}</button>
        <span class="prio-badge">{esc(project.get('priority', ''))}</span>
        <strong class="project-title" role="button" tabindex="0" title="{esc(project_id)} — click to rename" data-action="project-title" data-project="{esc(project_id)}" data-name="{esc(name)}">{esc(name)}</strong>{warning}
      </div>
      <span class="project-row__signals">
        <span class="status-wrapper" tabindex="0">
          <span class="status-pill" style="background:{status_style['bg']};color:{status_style['fg']}">{esc(status.upper())}</span>
          {tooltip}
        </span>
        <span class="deadline-pill" style="background:{deadline_style['bg']};color:{deadline_style['fg']}">{esc(format_date_long(deadline_raw, config))} [{esc(deadline_type.upper())}]</span>
      </span>
      <span class="project-row__actions">
        <button type="button" class="btn btn--ghost btn--sm btn--icon" title="Notes &amp; actions" aria-label="Notes and actions for {esc(name)}" data-action="toggle-detail" data-project="{esc(project_id)}">{icon('panel')}</button>
        <button type="button" class="btn btn--ghost btn--sm btn--icon" title="Advanced edit" aria-label="Advanced edit of {esc(name)}" data-action="advanced-edit-open" data-project="{esc(project_id)}">{icon('sliders')}</button>
      </span>
    </div>
  </td>
  <td class="timeline-cell">
    <div class="timeline-row timeline-row--project" data-lane="{esc(project_id)}">{bar}{_milestones(project, timeline, config)}</div>
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
