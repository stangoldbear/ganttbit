"""
The project card schema, declared once.

`api` validates and applies updates from it, and the browser renders the
Advanced Edit form from the same declaration served as JSON. Adding a field
is a one-line change here, instead of three edits kept in sync by hand.
"""

from . import settings as settings_module
from .repository import csv_to_list, ensure_dict

TEXT, LIST, BOOL, ROWS, BODY = 'text', 'list', 'bool', 'rows', 'body'
DEADLINE_TYPES = [value for value, _label in settings_module.DEADLINE_OPTIONS]


class ValidationError(ValueError):
    """Rejected input, with a message meant for the user."""


def field(path, label, kind=TEXT, *, param=None, choices=None, readonly=False, help=''):
    return {
        'path': path,
        'param': param or path,
        'label': label,
        'kind': kind,
        'choices': list(choices) if choices else None,
        'readonly': readonly,
        'help': help,
    }


def _row(key, label, choices=None):
    return {'key': key, 'label': label, 'choices': list(choices) if choices else None}


DEPENDENCY_COLUMNS = [
    _row('project_or_service', 'Project / service'),
    _row('team', 'Team'),
    _row('contact', 'Contact'),
    _row('criticality', 'Criticality', settings_module.SEVERITY_OPTIONS),
]
TASK_COLUMNS = [
    _row('id', 'ID'),
    _row('who', 'Who'),
    _row('start', 'Start'),
    _row('end', 'End'),
    _row('days', 'Days'),
    _row('flags', 'Flags'),
    _row('note', 'Note'),
]
MILESTONE_COLUMNS = [
    _row('id', 'ID'),
    _row('date', 'Date'),
    _row('text', 'Text'),
]
RISK_COLUMNS = [
    _row('id', 'ID'),
    _row('description', 'Description'),
    _row('severity', 'Severity', settings_module.SEVERITY_OPTIONS),
    _row('mitigation', 'Mitigation'),
    _row('owner', 'Owner'),
]


def sections(settings=None):
    """Advanced Edit layout: ordered sections of fields and row tables."""
    config = settings or settings_module.current()
    return [
        {'key': 'general', 'legend': 'General', 'fields': [
            field('name', 'Project name'),
            field('priority', 'Priority', readonly=True,
                  help='Set by drag & drop in the chart'),
            field('status', 'Status', choices=settings_module.STATUS_OPTIONS),
            field('blocked_reason', 'Blocking reason'),
        ]},
        {'key': 'dates', 'legend': 'Reference dates', 'fields': [
            field('dates.soft_deadline', 'Soft deadline'),
            field('dates.mandatory_deadline', 'Mandatory deadline'),
            field('dates.target_delivery', 'Target delivery'),
            field('dates.deadline_text', 'Deadline (chart badge)'),
            field('dates.deadline_type', 'Deadline type', choices=DEADLINE_TYPES),
        ]},
        {'key': 'timeline', 'legend': 'Timeline', 'fields': [
            field('timeline.start', 'Start', help='YYYY-MM-DD; the project bar starts here'),
            field('timeline.end', 'End', help='YYYY-MM-DD, or leave empty and set Days'),
            field('timeline.days', 'Days', help='Working days, when there is no end date'),
        ]},
        {'key': 'timeline_tasks', 'legend': 'Timeline rows', 'kind': ROWS,
         'path': 'timeline.tasks', 'columns': TASK_COLUMNS},
        {'key': 'milestones', 'legend': 'Milestones', 'kind': ROWS,
         'path': 'milestones', 'columns': MILESTONE_COLUMNS},
        {'key': 'tech_footprint', 'legend': 'Technical footprint', 'fields': [
            field('tech_footprint.platforms', 'Platforms', LIST,
                  help='Comma separated'),
            field('tech_footprint.qa_effort', 'QA effort',
                  choices=settings_module.QA_EFFORT_OPTIONS),
            field('tech_footprint.content_impact', 'Content impact', BOOL),
        ]},
        {'key': 'stakeholders', 'legend': 'Stakeholders', 'fields': [
            field('stakeholders.business_owner', 'Business owner'),
            field('stakeholders.tech_lead', 'Tech lead'),
            field('stakeholders.delivery_manager', 'Delivery manager'),
            field('stakeholders.qa_lead', 'QA lead'),
        ]},
        {'key': 'dependencies_upstream', 'legend': 'Upstream dependencies', 'kind': ROWS,
         'path': 'dependencies.upstream', 'columns': DEPENDENCY_COLUMNS},
        {'key': 'dependencies_downstream', 'legend': 'Downstream dependencies', 'kind': ROWS,
         'path': 'dependencies.downstream', 'columns': DEPENDENCY_COLUMNS},
        {'key': 'risks', 'legend': 'Risks & criticalities', 'kind': ROWS,
         'path': 'risks_and_criticalities', 'columns': RISK_COLUMNS},
        {'key': 'planning', 'legend': 'Planning factors', 'fields': [
            field('planning_factors.team_capacity_needed', 'Team capacity needed'),
            field('planning_factors.critical_path', 'Critical path'),
        ]},
        {'key': 'links', 'legend': 'Jira & links', 'fields': [
            field('jira.request', 'Jira request'),
            field('jira.epics', 'Jira epics', LIST, help='Comma separated'),
            field('confluence', 'Confluence links', LIST, help='Comma separated'),
            field('figma', 'Figma links', LIST, help='Comma separated'),
        ]},
        {'key': 'body', 'legend': 'Notes (markdown body)', 'fields': [
            field('_new_body', 'Notes', BODY, param='body'),
        ]},
    ]


def advanced_fields(settings=None):
    """Every scalar/list field of the advanced form, sections flattened."""
    return [entry for section in sections(settings)
            for entry in section.get('fields', [])]


def row_sections(settings=None):
    return [section for section in sections(settings) if section.get('kind') == ROWS]


# ─── Quick edit (the inline detail panel) ────────────────────────────────────
def quick_fields():
    return [
        field('name', 'Project name'),
        field('status', 'Status', choices=settings_module.STATUS_OPTIONS),
        field('blocked_reason', 'Blocking reason'),
        field('intro', 'Intro'),
        field('dates.deadline_text', 'Deadline', param='deadline_text'),
        field('dates.deadline_type', 'Deadline type', param='deadline_type',
              choices=DEADLINE_TYPES),
        field('tech_footprint.platforms', 'Platforms', LIST, param='platforms'),
        field('jira.request', 'Jira request', param='jira_request'),
        field('jira.epics', 'Jira epics', LIST, param='jira_epics'),
        field('confluence', 'Confluence links', LIST, param='confluence_links'),
        field('figma', 'Figma links', LIST, param='figma_links'),
    ]


# ─── Nested path access ──────────────────────────────────────────────────────
_MISSING = object()


def get_path(mapping, path):
    cursor = mapping
    for part in path.split('.'):
        if not isinstance(cursor, dict) or part not in cursor:
            return _MISSING
        cursor = cursor[part]
    return cursor


def set_path(mapping, path, value):
    parts = path.split('.')
    cursor = mapping
    for part in parts[:-1]:
        cursor = ensure_dict(cursor, part)
    cursor[parts[-1]] = value


# ─── Coercion and validation ─────────────────────────────────────────────────
def coerce(entry, value):
    """Turn a payload value into what the card stores. Raises ValidationError."""
    kind = entry['kind']
    if kind == LIST:
        return csv_to_list(value)
    if kind == BOOL:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ('true', '1', 'yes', 'on')
    if kind == BODY:
        return str(value)

    text = '' if value is None else str(value).strip()
    choices = entry['choices']
    if choices and text and text not in choices:
        raise ValidationError(
            f"Invalid value for `{entry['label']}`: {text!r}. "
            f"Allowed: {', '.join(choices)}.")
    return text


def clean_rows(rows, columns=None):
    """Drop entirely empty rows from a dynamic table, and validate choices."""
    cleaned = []
    by_key = {column['key']: column for column in (columns or [])}
    for row in rows or []:
        if not isinstance(row, dict):
            if str(row).strip():
                cleaned.append(row)
            continue
        if not any(str(value).strip() for value in row.values()):
            continue
        for key, value in row.items():
            column = by_key.get(key)
            text = str(value).strip()
            if column and column['choices'] and text and text not in column['choices']:
                raise ValidationError(
                    f"Invalid value for `{column['label']}`: {text!r}. "
                    f"Allowed: {', '.join(column['choices'])}.")
        cleaned.append({key: str(value).strip() for key, value in row.items()})
    return cleaned


def apply_fields(data, params, fields):
    """Apply the payload to the card, one declared field at a time."""
    for entry in fields:
        if entry['readonly']:
            continue
        value = get_path(params, entry['param'])
        if value is _MISSING:
            continue
        set_path(data, entry['path'], coerce(entry, value))


def apply_rows(data, params, settings=None):
    for section in row_sections(settings):
        rows = get_path(params, section['path'])
        if rows is _MISSING:
            continue
        set_path(data, section['path'], clean_rows(rows, section['columns']))


def as_json(settings=None):
    """The schema the browser renders the Advanced Edit form from."""
    return {'sections': sections(settings)}
