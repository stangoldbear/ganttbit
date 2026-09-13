"""
Domain logic: dates, the priority ramp, roles, the timeline a card declares,
calendar.

Pure and testable: no I/O, no HTML, and no hidden clock; "today" is passed
in so every rendering decision can be reproduced in a test.
"""

import re
from datetime import date, datetime, timedelta

from . import settings as settings_module

_ISO_DATE_RE = re.compile(r'^(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?:[ T](\d{1,2}:\d{2}))?$')
_EU_DATE_RE = re.compile(r'^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})(?:[ T](\d{1,2}:\d{2}))?$')


def _settings(settings=None):
    return settings or settings_module.current()


# ─── Dates ───────────────────────────────────────────────────────────────────
def format_date_long(value, settings=None):
    """
    Spell a date out: `24 August 26`.

    Accepts date/datetime, ISO (`2026-08-24`) and EU (`24/08/2026`). Any other
    text is returned untouched, so free-form deadlines ("mid September") survive.
    """
    if not value:
        return ''

    config = _settings(settings)
    if isinstance(value, (datetime, date)):
        return _compose(config, value.day, value.month, str(value.year))

    text = str(value).strip()

    iso = _ISO_DATE_RE.match(text)
    if iso:
        return _compose(config, int(iso.group(3)), int(iso.group(2)), iso.group(1), iso.group(4))

    eu = _EU_DATE_RE.match(text)
    if eu:
        return _compose(config, int(eu.group(1)), int(eu.group(2)), eu.group(3), eu.group(4))

    return text


def _compose(config, day, month, year, clock=None):
    if not 1 <= month <= 12:
        return f'{day}/{month}/{year}'
    result = f'{day} {config.months[month - 1]} {str(year)[-2:]}'
    return f'{result}, {clock}' if clock else result


def format_relative(value, today=None, settings=None):
    """
    How far away a date is, in words: `in 9 weeks`, `tomorrow`, `2 days ago`.

    A deadline is read as time remaining, not as a date to subtract from today
    in your head, and a date that is not a date ("mid October") has no distance
    to report, so it reports none.
    """
    today = today or date.today()
    when = _as_datetime(value)
    if when is None:
        return ''

    days = (when.date() - today).days
    if days == 0:
        return 'today'
    if days == 1:
        return 'tomorrow'
    if days == -1:
        return 'yesterday'

    ahead = days > 0
    days = abs(days)
    if days < 14:
        amount = f'{days} days'
    elif days < 60:
        amount = f'{round(days / 7)} weeks'
    elif days < 365:
        amount = f'{round(days / 30)} months'
    else:
        amount = f'{days / 365:.1f} years'.replace('.0 ', ' ')
    return f'in {amount}' if ahead else f'{amount} ago'


# ─── The priority ramp ───────────────────────────────────────────────────────
# A project's rank is its whole visual identity now that tiers are gone: the
# band down its left edge travels from the accent colour at the top of the list
# to a near-grey at the bottom. The two ends are theme tokens the browser
# resolves, so all that has to be worked out here is how far along a project
# sits, which is arithmetic and belongs where it can be tested.
def band_position(index, total):
    """
    How far down the ramp the project at `index` of `total` sits, in percent.

    A list of one is the top of the ramp rather than the bottom: the only
    project there is is the most important one.
    """
    if total <= 1 or index <= 0:
        return 0.0
    return min(index, total - 1) / (total - 1) * 100


# ─── Display groups ─────────────────────────────────────────────────────────
# Every live project is drawn in one flat list, ranked; DONE and DROPPED follow
# at the very bottom, under a heading each. They are the only two groups left,
# and a project lands in one because of its status alone.
def display_group(project, settings=None):
    status = str(project.get('status', '') or '').lower()
    if status in settings_module.DISPLAY_GROUPS:
        return status
    return settings_module.LIVE_GROUP


def group_order(settings=None):
    return [settings_module.LIVE_GROUP] + list(settings_module.DISPLAY_GROUPS)


def is_display_group(key):
    return key in settings_module.DISPLAY_GROUPS


def group_title(key, settings=None):
    group = settings_module.DISPLAY_GROUPS.get(key)
    return group['title'] if group else settings_module.LIVE_GROUP_TITLE


def group_color(key, settings=None):
    group = settings_module.DISPLAY_GROUPS.get(key)
    return settings_module.hex_color(group['rgb']) if group else ''


def group_by_display(projects, settings=None):
    """Group projects by the band they are drawn in, in drawing order."""
    config = _settings(settings)
    grouped = {key: [] for key in group_order(config)}
    for project in projects:
        grouped[display_group(project, config)].append(project)
    return grouped


def group_rank(key, settings=None):
    order = group_order(settings)
    return order.index(key) if key in order else len(order)


# ─── Roles and people ───────────────────────────────────────────────────────
def resolve_person(who, settings=None):
    """
    Who a timeline row belongs to: {'name', 'role', 'color'}.

    The roster in settings.toml is matched by name first, because that is what
    a card writes. A label carrying a squad prefix (`iOS Dev #1`) still
    resolves, longest prefix first, so a card written against the old plan
    keeps working. Anything else falls back to a keyword rule and then to the
    fallback role.
    """
    config = _settings(settings)
    text = str(who or '').strip()

    members = [member for squad in config.squads.values() for member in squad]
    for member in members:
        if member['name'].lower() == text.lower():
            role = config.role(member['role'])
            return {'name': member['name'], 'role': role['label'], 'color': role['color']}

    for member in sorted(members, key=lambda entry: -len(entry['prefix'])):
        if text.startswith(member['prefix']):
            role = config.role(member['role'])
            return {'name': member['name'], 'role': role['label'], 'color': role['color']}

    for role in config.roles:
        if any(word in text for word in role['keywords']):
            return {'name': text, 'role': role['label'], 'color': role['color']}

    fallback = config.fallback_role
    return {'name': text or fallback['label'],
            'role': fallback['label'], 'color': fallback['color']}


# ─── The timeline a card declares ────────────────────────────────────────────
def add_working_days(start, count):
    """
    `days` counts working days, which is how a delivery plan is written.

    The end is the working day `count` days after the start, so a span of one
    day covers exactly one column and a span of 34 lands where the same task
    written with an explicit end date lands.
    """
    end, counted = start, 0
    while counted < max(1, count):
        end += timedelta(days=1)
        if end.weekday() < 5:
            counted += 1
    return end


def _as_datetime(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    text = str(value or '').strip()
    match = _ISO_DATE_RE.match(text)
    if not match:
        return None
    try:
        return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _span(block, settings=None):
    """(start, end) from `start` plus either `end` or `days`, or None."""
    if not isinstance(block, dict):
        return None
    start = _as_datetime(block.get('start'))
    if start is None:
        return None

    end = _as_datetime(block.get('end'))
    if end is None:
        try:
            days = int(str(block.get('days', '')).strip())
        except (TypeError, ValueError):
            days = 0
        end = add_working_days(start, days) if days else start
    return start, max(end, start)


def flags_of(task):
    """`flags` reads as a list or as an inline `crit, active`."""
    value = task.get('flags') if isinstance(task, dict) else None
    if isinstance(value, str):
        return [flag.strip() for flag in value.split(',') if flag.strip()]
    return [str(flag).strip() for flag in (value or [])]


def _task_type(flags):
    for candidate in ('done', 'crit', 'active'):
        if candidate in flags:
            return candidate
    return 'default'


def project_tasks(project, settings=None):
    """
    The rows a card declares, as the chart consumes them.

    A task carries who it belongs to, its span, its flags and whether it falls
    outside the span its own project declares, which is a warning, never a
    reason to drop the row.
    """
    timeline = project.get('timeline') or {}
    span = _span(timeline)
    rows = []

    for entry in timeline.get('tasks') or []:
        if not isinstance(entry, dict):
            continue
        bounds = _span(entry)
        if bounds is None:
            continue
        start, end = bounds
        flags = flags_of(entry)
        person = resolve_person(entry.get('who'), settings)
        rows.append({
            'id': entry.get('id', ''),
            'project_id': project.get('id', ''),
            'who': person['name'],
            'role': person['role'],
            'color': person['color'],
            'note': str(entry.get('note', '') or ''),
            'start': start,
            'end': end,
            'type': _task_type(flags),
            'outside': bool(span and (start < span[0] or end > span[1])),
        })
    return rows


def project_milestones(project, settings=None):
    """The dated marks a card declares, in date order, invalid dates dropped."""
    marks = []
    for entry in project.get('milestones') or []:
        if not isinstance(entry, dict):
            continue
        when = _as_datetime(entry.get('date'))
        if when is None:
            continue
        marks.append({
            'id': str(entry.get('id', '') or ''),
            'date': when,
            'text': str(entry.get('text', '') or ''),
        })
    return sorted(marks, key=lambda mark: mark['date'])


def project_span(project, settings=None):
    """
    The bar drawn for the project itself.

    The declared span wins and exists even with no tasks; a card that has not
    declared one yet still draws, derived from its rows.
    """
    span = _span((project.get('timeline') or {}))
    if span:
        return span
    rows = project_tasks(project, settings)
    if not rows:
        return None
    return min(row['start'] for row in rows), max(row['end'] for row in rows)


def chart_spans(projects, settings=None):
    """Every bar in the chart, as the calendar needs to see it: {start, end}."""
    spans = []
    for project in projects:
        span = project_span(project, settings)
        if span:
            spans.append({'start': span[0], 'end': span[1]})
        spans.extend({'start': row['start'], 'end': row['end']}
                     for row in project_tasks(project, settings))
    return spans


# ─── The window the chart is drawn through ──────────────────────────────────
# What the toolbar offers, in the order it offers it. `all` is the whole span
# the cards describe; a plain YYYY-MM-DD starts the scale on that day.
RANGE_TODAY, RANGE_30D, RANGE_YEAR, RANGE_ALL = 'today', '30d', 'year', 'all'
RANGES = (RANGE_TODAY, RANGE_30D, RANGE_YEAR, RANGE_ALL)


def resolve_zoom(value):
    """
    (column width, key) for a `zoom=` value.

    A column is always one working day; the zoom decides how wide it is drawn,
    and the header decides what it can still say at that width.
    """
    key = str(value or '').strip().lower()
    if key not in settings_module.ZOOM_LEVELS:
        key = settings_module.DEFAULT_ZOOM
    return settings_module.ZOOM_LEVELS[key], key


def resolve_range(value, today=None):
    """
    (start, end, key) for a `from=` value.

    Anything unrecognised is today: the chart opening on live work is the one
    default worth defending, and a typo in a URL should not undo it.
    """
    today = today or date.today()
    text = str(value or '').strip().lower()

    if text == RANGE_ALL:
        return None, None, RANGE_ALL
    if text == RANGE_30D:
        return today - timedelta(days=30), None, RANGE_30D
    if text == RANGE_YEAR:
        return date(today.year, 1, 1), date(today.year, 12, 31), RANGE_YEAR

    match = _ISO_DATE_RE.match(text)
    if match:
        try:
            chosen = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return today, None, RANGE_TODAY
        return chosen, None, chosen.isoformat()

    return today, None, RANGE_TODAY


# ─── Timeline calendar ───────────────────────────────────────────────────────
class Timeline:
    """Working days, grouped months and bar geometry for the gantt chart."""

    def __init__(self, tasks, *, settings=None, col_width=None, today=None,
                 start_from=None, end_at=None, horizon=0):
        config = _settings(settings)
        self.col_width = col_width or settings_module.COL_W
        self.today = today or date.today()
        self.start_from = start_from
        self.end_at = end_at
        self.days = self._build_days(tasks, config.chart_min_end, self.today,
                                     start_from, end_at, horizon)
        self.months = self._group_months(self.days)
        self.years = self._group_years(self.days)
        self.width = len(self.days) * self.col_width

    @staticmethod
    def _build_days(tasks, min_end, today, start_from=None, end_at=None, horizon=0):
        """
        Every working day the chart draws, inside the window it was asked for.

        The scale is built from what the cards describe and then cut to the
        window, rather than the other way round: a window that happens to catch
        no work still has to draw something, so an empty cut falls back to a
        month from where the window starts.
        """
        bounds = [task['start'] for task in tasks] + [task['end'] for task in tasks]
        if not bounds:
            reference = datetime.combine(start_from or today, datetime.min.time())
            bounds = [reference, reference + timedelta(days=30)]

        start = min(bounds)
        start -= timedelta(days=start.weekday())            # snap to Monday
        end = max(max(bounds), datetime.combine(min_end, datetime.min.time()))
        # A zoomed-out scale keeps going past the last bar: the window is the
        # one thing allowed to say where the chart stops, so a window with an
        # end of its own is left alone.
        if horizon and not end_at:
            end = max(end, datetime.combine(today, datetime.min.time())
                      + timedelta(days=horizon))

        days, cursor = [], start
        while cursor <= end:
            if cursor.weekday() < 5:                        # working days only
                days.append(cursor)
            cursor += timedelta(days=1)

        if start_from:
            days = [day for day in days if day.date() >= start_from]
        if end_at:
            days = [day for day in days if day.date() <= end_at]
        if days:
            return days

        cursor = datetime.combine(start_from or today, datetime.min.time())
        fallback = []
        while len(fallback) < 22:                           # about a month of work
            if cursor.weekday() < 5:
                fallback.append(cursor)
            cursor += timedelta(days=1)
        return fallback

    @staticmethod
    def _group_years(days):
        """(year, number of days) runs, for the row above the months."""
        years, current, count = [], None, 0
        for day in days:
            if day.year != current:
                if current:
                    years.append((current, count))
                current, count = day.year, 1
            else:
                count += 1
        if current:
            years.append((current, count))
        return years

    @staticmethod
    def _group_months(days):
        months, current, count = [], None, 0
        for day in days:
            key = (day.year, day.month)
            if key != current:
                if current:
                    months.append((current, count))
                current, count = key, 1
            else:
                count += 1
        if current:
            months.append((current, count))
        return months

    def geometry(self, start, end):
        """(left, width) of a bar in px, or None when it falls outside the scale."""
        first = next((i for i, day in enumerate(self.days) if day.date() >= start.date()), None)
        if first is None:
            return None
        last = next((i for i, day in enumerate(self.days) if day.date() >= end.date()),
                    len(self.days))
        left = first * self.col_width + 2
        width = max((last - first) * self.col_width - 4, self.col_width - 4)
        return left, width

    @property
    def grid_background(self):
        return ('repeating-linear-gradient(to right, #808080 0, #808080 1px, '
                f'transparent 1px, transparent {self.col_width}px)')

    def day_state(self, day):
        """Classify a day against today: 'past' | 'today' | 'future'."""
        value = day.date()
        if value < self.today:
            return 'past'
        if value == self.today:
            return 'today'
        return 'future'

    @property
    def today_index(self):
        for index, day in enumerate(self.days):
            if day.date() == self.today:
                return index
        return None
