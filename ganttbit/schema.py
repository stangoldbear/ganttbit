"""
The project card schema, declared once.

`api` validates and applies updates from it, and the browser renders its forms
— Advanced Edit, and New project — from the same declaration served as JSON.
Adding a field is a one-line change here, instead of three edits kept in sync
by hand.
"""

from . import settings as settings_module
from .domain import used_values
from .repository import csv_to_list, ensure_dict

# DATE and LONG are TEXT with a shape: a calendar day, and a value that needs
# more than one line. Coercion treats both as TEXT — only the control the
# browser draws for them differs.
TEXT, DATE, LONG, LIST, BOOL, ROWS, BODY = (
    'text', 'date', 'long', 'list', 'bool', 'rows', 'body')
DEADLINE_TYPES = [value for value, _label in settings_module.DEADLINE_OPTIONS]


class ValidationError(ValueError):
    """Rejected input, with a message meant for the user."""


def field(path, label, kind=TEXT, *, param=None, choices=None, readonly=False,
          required=False, suggest=None, help=''):
    """
    One declared value.

    `choices` is a closed vocabulary: anything else is refused. `suggest` is an
    open one — the values named here are offered, the vault's own are added to
    them by `as_json`, and something new is still accepted. That is the
    difference between a status and a tag.
    """
    return {
        'path': path,
        'param': param or path,
        'label': label,
        'kind': kind,
        'choices': list(choices) if choices else None,
        'readonly': readonly,
        'required': required,
        'suggest': None if suggest is None else list(suggest),
        'help': help,
    }


def _row(key, label, choices=None, kind=TEXT):
    """One column of a row table. `kind` is what the browser draws for it."""
    return {'key': key, 'label': label, 'kind': kind,
            'choices': list(choices) if choices else None}


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
ESTIMATE_COLUMNS = [
    _row('id', 'ID'),
    _row('stage', 'Stage', settings_module.ESTIMATE_STAGES),
    _row('value', 'Value', kind=LONG),
    _row('date', 'Given on'),
    _row('note', 'What moved it'),
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
            field('name', 'Project name', required=True),
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
        {'key': 'estimates', 'legend': 'Estimates', 'kind': ROWS,
         'path': 'estimates', 'columns': ESTIMATE_COLUMNS},
        {'key': 'tech_footprint', 'legend': 'Technical footprint', 'fields': [
            field('tech_footprint.platforms', 'Platforms', LIST,
                  suggest=config.platforms, help='Comma separated'),
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
        {'key': 'intro', 'legend': 'Why & scope', 'fields': [
            field('intro', 'Intro', LONG,
                  help='Markdown, shown at the top of the panel. It is the '
                       '`- intro:` key of the card, not the notes below.'),
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
        field('name', 'Project name', required=True),
        field('status', 'Status', choices=settings_module.STATUS_OPTIONS),
        field('blocked_reason', 'Blocking reason'),
        field('intro', 'Intro', LONG),
        field('dates.deadline_text', 'Deadline', param='deadline_text'),
        field('dates.deadline_type', 'Deadline type', param='deadline_type',
              choices=DEADLINE_TYPES),
        field('tech_footprint.platforms', 'Platforms', LIST, param='platforms'),
        field('jira.request', 'Jira request', param='jira_request'),
        field('jira.epics', 'Jira epics', LIST, param='jira_epics'),
        field('confluence', 'Confluence links', LIST, param='confluence_links'),
        field('figma', 'Figma links', LIST, param='figma_links'),
    ]


# ─── Simple edit (New project, and the same form over a card that exists) ────
def simple_fields(settings=None):
    """
    What the simple form asks for, in the order it asks.

    The card as somebody has it in their head when a project turns up: what it
    is called, whether it has started, when it runs, how big it is, and what is
    already written down about it elsewhere. Everything else has a meaning when
    absent and is one gesture away in the panel or in Advanced Edit, so it is
    not asked for here. The dialog is rendered from this list, as the Advanced
    Edit form is rendered from `sections`.
    """
    config = settings or settings_module.current()
    return [
        field('name', 'Project name', required=True),
        field('status', 'Status', choices=settings_module.STATUS_OPTIONS,
              help='A project nobody has started yet is `inactive`: its own band '
                   'under the list.'),
        field('timeline.start', 'Start', DATE, param='start',
              help='The project bar. Both dates, or neither.'),
        field('timeline.end', 'End', DATE, param='end'),
        field('dates.deadline_text', 'Deadline (chart badge)', param='deadline_text',
              help='A date, or free text: mid September'),
        field('dates.deadline_type', 'Deadline type', param='deadline_type',
              choices=DEADLINE_TYPES),
        field('tech_footprint.platforms', 'Platforms', LIST, param='platforms',
              suggest=config.platforms, help='Comma separated'),
        field('tech_footprint.qa_effort', 'QA effort', param='qa_effort',
              choices=settings_module.QA_EFFORT_OPTIONS),
        # Not a value at a path: an answer here is a new estimate, and the
        # endpoint turns it into one. The `_` prefix is the card format's own
        # convention for a key that never reaches the file.
        field('_new_estimate', 'Effort estimate', LONG, param='estimate',
              help='Kept as history: a value that moved is added, the old ones stay. '
                   'A number, or the breakdown behind it.'),
        field('_new_estimate_stage', 'Estimate stage', param='estimate_stage',
              choices=settings_module.ESTIMATE_STAGES,
              help='Which conversation the number came out of.'),
        field('jira.request', 'Jira request', param='jira_request',
              help=config.jira_placeholder),
        field('confluence', 'Confluence links', LIST, param='confluence_links',
              help='Comma separated'),
        field('intro', 'Why & scope', LONG, help='Markdown. Headings, lists and links.'),
    ]


# ─── Nested path access ──────────────────────────────────────────────────────
def entry_for(path, settings=None):
    """
    What the schema declares at `path`, or None.

    The structure view edits any value the card holds; this is how a value the
    schema knows gets the form's own validation, and one it does not know is
    stored as the text it was.
    """
    for entry in quick_fields() + advanced_fields(settings):
        if entry['path'] == path:
            return entry
    parts = path.split('.')
    for section in row_sections(settings):
        prefix = section['path'].split('.')
        # <section>.<row id>.<column>
        if parts[:len(prefix)] == prefix and len(parts) == len(prefix) + 2:
            for column in section['columns']:
                if column['key'] == parts[-1]:
                    return {'kind': column['kind'], 'choices': column['choices'],
                            'label': column['label'], 'readonly': False}
    return None


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
    # A required value is what the card cannot be read without. `name` is the
    # `# title` line: written empty, the file stops parsing as a card at all.
    if entry.get('required') and not text:
        raise ValidationError(f"`{entry['label']}` cannot be empty.")
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


def _offer(fields, projects):
    """Complete every open vocabulary with the values the cards already use."""
    for entry in fields:
        if entry['suggest'] is not None:
            entry['suggest'] = used_values(projects, entry['path'], entry['suggest'])
    return fields


def as_json(settings=None, projects=()):
    """
    The schema the browser renders its forms from: Advanced Edit, and simple.

    `projects` is the loaded vault, and the only thing it is read for: an open
    vocabulary is declared with the values settings knows and served with those
    the cards have grown since, so a tag typed once can be picked next time.
    """
    config = settings or settings_module.current()
    blocks = sections(config)
    for block in blocks:
        if 'fields' in block:
            _offer(block['fields'], projects)
    return {'sections': blocks, 'simple': _offer(simple_fields(config), projects)}
