"""
API actions: each handler describes ONLY the mutation to apply.

Loading, serialising and writing the file are centralised in
`ProjectRepository.mutate`; the fields themselves are declared once in
`schema.py`. Adding an endpoint means registering a function in `ROUTES`,
the server never changes.
"""

import re
import unicodedata
from datetime import datetime

from . import schema, settings as settings_module
from .domain import display_group, search_text
from .markup import render_markdown
from .repository import SAFE_ID_RE, csv_to_list, ensure_dict


class ApiError(Exception):
    """An application error carrying the HTTP status to answer with."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


# ─── Mutations ───────────────────────────────────────────────────────────────
def _update_project(data, params, _now):
    """Quick edit: the fields exposed by the inline detail panel."""
    schema.apply_fields(data, params, schema.quick_fields())
    # Free text is markdown, and the browser cannot render it: the value is
    # handed back as HTML by the one renderer there is.
    if 'intro' in params:
        return {'html': {'intro': render_markdown(data.get('intro'))}}


def _simple_update_project(data, params, now):
    """
    Simple edit: the fields the simple form asks for, on a card that exists.

    The same declaration the form is drawn from, applied the same way an
    update from the panel is applied. Unlike a creation, an empty answer is an
    answer: it clears the field, because the form showed what was there.
    """
    _check_optional_span(params)
    schema.apply_fields(data, params, schema.simple_fields())
    # The form's two dates are the whole truth about the bar. `days` is the
    # other way of saying it, and keeping both is how they come to disagree —
    # the same rule a dragged bar already follows.
    if 'start' in params or 'end' in params:
        ensure_dict(data, 'timeline').pop('days', None)
    _record_estimate(data, now)


def _advanced_update_project(data, params, _now):
    """
    Advanced edit: every field of the card schema.

    Fields absent from the payload are left untouched, so an editor that does
    not know about `todos` or `intro` cannot erase them.
    """
    schema.apply_fields(data, params, schema.advanced_fields())
    schema.apply_rows(data, params)


def _raw_update_project(repository, project_id, params):
    """Store the card text as typed in the markdown tab."""
    text = params.get('raw_text')
    if not text or not str(text).strip():
        raise ApiError('The card text cannot be empty.')
    try:
        repository.write_raw(project_id, text)
    except ValueError as exc:
        raise ApiError(str(exc))


def _set_value(data, params, _now):
    """
    One value at a path, from the structure view.

    The path walks the card as the tree prints it: a key steps into a map, an
    id or an index into a list. Only a value that exists can be set, so a typo
    cannot grow a card. A path the schema knows is validated as the form
    validates it; the rest is stored as typed, which is what the file held.
    """
    path = str(params.get('path', '')).strip()
    if not path:
        raise ApiError('Missing `path`.')
    value = params.get('value', '')
    if path == '_body':
        data['_new_body'] = str(value)
        return {'value': str(value).strip()}
    if path == 'id':
        raise ApiError('`id` is the name of the file the card lives in: renaming '
                       'one means renaming the other, which is not an edit.')

    parent, key = _walk(data, path)
    entry = schema.entry_for(path)
    existing = parent[key]
    if entry and entry['readonly']:
        raise ApiError(f'`{path}` is not edited by hand: the list order sets it.')
    if entry:
        stored = schema.coerce(entry, value)
    elif isinstance(existing, bool):
        stored = str(value).strip().lower() in ('true', '1', 'yes', 'on')
    elif isinstance(existing, list):
        stored = csv_to_list(value)
    else:
        stored = '' if value is None else str(value).strip()
    parent[key] = stored
    return {'value': stored}


def _walk(data, path):
    """The container and the key of the value at `path`, or a 404."""
    parts = path.split('.')
    cursor = data
    for part in parts[:-1]:
        cursor = _step(cursor, part, path)
    last = parts[-1]
    if isinstance(cursor, list):
        return cursor, _index_of(cursor, last, path)
    if isinstance(cursor, dict) and last in cursor:
        return cursor, last
    raise ApiError(f'No value at {path}.', status=404)


def _step(cursor, part, path):
    if isinstance(cursor, dict) and part in cursor:
        return cursor[part]
    if isinstance(cursor, list):
        return cursor[_index_of(cursor, part, path)]
    raise ApiError(f'No value at {path}.', status=404)


def _index_of(items, part, path):
    for index, item in enumerate(items):
        if isinstance(item, dict) and str(item.get('id', '')) == part:
            return index
    if part.isdigit() and int(part) < len(items):
        return int(part)
    raise ApiError(f'No value at {path}.', status=404)


def _row_id(kind, data, count, now):
    """
    The id of a new row on a card, unique within the card.

    The project id goes into it with its dots flattened: the structure view
    addresses a value by a dotted path, so a dot here would split the id in
    two and leave the row unreachable — `todos.todo-p.x-1-…` is read as three
    steps, not two, and answers 404.
    """
    owner = str(data.get('id', 'project')).replace('.', '-')
    return f'{kind}-{owner}-{count}-{int(now.timestamp())}'


def _add_todo(data, params, now):
    text = str(params.get('text', '')).strip()
    if not text:
        raise ApiError('The note text is required.')

    todos = csv_to_list(data.get('todos'))
    todo = {
        'id': _row_id('todo', data, len(todos) + 1, now),
        'text': text,
        'deadline': str(params.get('deadline', '')).strip(),
    }
    todos.append(todo)
    data['todos'] = todos
    # Handed back so the browser can add the row without reloading the page.
    return {'todo': todo, 'html': render_markdown(text)}


def _update_todo(data, params, _now):
    todo_id = _require_todo_id(params)
    text = str(params.get('text', '')).strip()
    if not text:
        raise ApiError('The note text is required.')

    for collection in ('todos', 'done'):
        for item in csv_to_list(data.get(collection)):
            if _is_note(item, todo_id):
                item['text'] = text
                item['deadline'] = str(params.get('deadline', '')).strip()
                return {'todo': item, 'html': render_markdown(text)}
    raise ApiError('Note not found.', status=404)


def _toggle_todo(data, params, now):
    todo_id = _require_todo_id(params)
    todos = csv_to_list(data.get('todos'))
    history = csv_to_list(data.get('done'))

    # The category is the state: a note is open because it sits under `todos`
    # and completed because it sits under `done`. There is no flag to disagree
    # with the list it is in.
    completed = True
    for index, item in enumerate(todos):
        if _is_note(item, todo_id):
            moved = todos.pop(index)
            moved['completed_at'] = now.strftime('%Y-%m-%d %H:%M')
            history.insert(0, moved)
            break
    else:
        for index, item in enumerate(history):
            if _is_note(item, todo_id):
                moved = history.pop(index)
                moved.pop('completed_at', None)
                todos.append(moved)
                completed = False
                break
        else:
            raise ApiError('Note not found.', status=404)

    data['todos'] = todos
    data['done'] = history
    return {'todo': moved, 'completed': completed,
            'html': render_markdown(moved.get('text'))}


def _delete_todo(data, params, _now):
    todo_id = _require_todo_id(params)
    for collection in ('todos', 'done'):
        if collection in data:
            data[collection] = [item for item in csv_to_list(data.get(collection))
                                if not _is_note(item, todo_id)]


_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _save_milestone(data, params, now):
    """
    Add or update one dated mark.

    A milestone without a date is not a milestone, so the date is required and
    checked here rather than stored and skipped at render time.
    """
    date = str(params.get('date', '')).strip()
    if not _DATE_RE.match(date):
        raise ApiError('A milestone needs a date, as YYYY-MM-DD.')

    text = str(params.get('text', '')).strip()
    milestones = csv_to_list(data.get('milestones'))
    milestone_id = str(params.get('milestone_id', '') or '').strip()

    for item in milestones:
        if isinstance(item, dict) and item.get('id') == milestone_id:
            item['date'], item['text'] = date, text
            data['milestones'] = milestones
            return {'milestone': item}

    created = {
        'id': _row_id('milestone', data, len(milestones) + 1, now),
        'date': date,
        'text': text,
    }
    milestones.append(created)
    data['milestones'] = milestones
    return {'milestone': created}


def _checked_span(params):
    """
    The two dates of a bar, refused unless the card can hold them.

    One rule, wherever a bar is written: a drag that ends outside the scale, a
    date typed into the span dialog, and the dates a project is created with
    are all checked here rather than stored and skipped at render time.
    """
    start = str(params.get('start', '')).strip()
    end = str(params.get('end', '')).strip()
    if not _DATE_RE.match(start) or not _DATE_RE.match(end):
        raise ApiError('A bar needs a start and an end, as YYYY-MM-DD.')
    if end < start:
        raise ApiError('A bar cannot end before it starts.')
    return start, end


def _check_optional_span(params):
    """A span is two dates or none: half of one would draw a one-day project."""
    if str(params.get('start', '')).strip() or str(params.get('end', '')).strip():
        _checked_span(params)


def _save_timeline(data, params, now):
    """
    Write one bar: a row when `task_id` is given, the project span otherwise.

    The same endpoint serves a drag, which sends two dates, and the row dialog,
    which also sends who it belongs to and its note.
    """
    start, end = _checked_span(params)

    timeline = ensure_dict(data, 'timeline')
    task_id = str(params.get('task_id', '') or '').strip()
    tasks = csv_to_list(timeline.get('tasks'))

    # A drag of the summary bar sends two dates and nothing else; the row
    # dialog sends who it belongs to, and `new` when there is no row yet.
    if task_id in ('', 'new') and 'who' not in params:
        timeline['start'], timeline['end'] = start, end
        timeline.pop('days', None)      # one way of saying it, not two
        return {'timeline': {'start': start, 'end': end}}

    if task_id in ('', 'new'):
        who = str(params.get('who', '')).strip()
        if not who:
            raise ApiError('A timeline row needs someone to belong to.')
        created = {
            'id': f"task-{len(tasks) + 1}-{int(now.timestamp())}",
            'who': who, 'start': start, 'end': end,
        }
        note = str(params.get('note', '')).strip()
        if note:
            created['note'] = note
        tasks.append(created)
        timeline['tasks'] = tasks
        return {'task': created}

    task = next((entry for entry in tasks
                 if isinstance(entry, dict) and entry.get('id') == task_id), None)
    if task is None:
        raise ApiError('Timeline row not found.', status=404)

    task['start'], task['end'] = start, end
    task.pop('days', None)
    # Only what the caller sent: a drag knows nothing about who or why.
    if 'who' in params:
        who = str(params.get('who', '')).strip()
        if not who:
            raise ApiError('A timeline row needs someone to belong to.')
        task['who'] = who
    if 'note' in params:
        task['note'] = str(params.get('note', '')).strip()
    timeline['tasks'] = tasks
    return {'task': task}


def _delete_timeline_task(data, params, _now):
    task_id = str(params.get('task_id', '') or '').strip()
    if not task_id:
        raise ApiError('Missing `task_id` parameter.')
    timeline = ensure_dict(data, 'timeline')
    timeline['tasks'] = [entry for entry in csv_to_list(timeline.get('tasks'))
                         if not (isinstance(entry, dict) and entry.get('id') == task_id)]


# ─── Estimates ───────────────────────────────────────────────────────────────
# A number given for a project is never a correction of the last one: it came
# out of a later conversation, with more known, and the one before it was true
# when it was given. So the card keeps all of them, oldest first, and the last
# row is the one in force. What the simple form asks for is therefore an event
# rather than a value, and this is where it becomes a row.
def _record_estimate(data, now):
    """
    Turn what the simple form typed into an estimate, if it moved.

    Re-opening the form and saving it writes nothing: the value it showed is
    the one already on the card. A value or a stage that differs is a new
    estimate, dated today, keeping the ones before it.
    """
    value = str(data.pop('_new_estimate', '') or '').strip()
    stage = str(data.pop('_new_estimate_stage', '') or '').strip()
    if not value:
        return

    estimates = csv_to_list(data.get('estimates'))
    last = estimates[-1] if estimates and isinstance(estimates[-1], dict) else {}
    if str(last.get('value', '')).strip() == value and str(last.get('stage', '')).strip() == stage:
        return

    estimates.append({
        'id': _row_id('estimate', data, len(estimates) + 1, now),
        'stage': stage or settings_module.ESTIMATE_STAGES[0],
        'value': value,
        'date': now.strftime('%Y-%m-%d'),
    })
    data['estimates'] = estimates


def _save_estimate(data, params, now):
    """Add or correct one row of the history, from the panel."""
    value = str(params.get('value', '')).strip()
    if not value:
        raise ApiError('An estimate needs a value.')
    stage = str(params.get('stage', '')).strip() or settings_module.ESTIMATE_STAGES[0]
    if stage not in settings_module.ESTIMATE_STAGES:
        raise ApiError(f'Unknown estimate stage: {stage}. '
                       f'Allowed: {", ".join(settings_module.ESTIMATE_STAGES)}.')
    date = str(params.get('date', '')).strip()
    if date and not _DATE_RE.match(date):
        raise ApiError('An estimate is dated YYYY-MM-DD, or not at all.')

    estimates = csv_to_list(data.get('estimates'))
    estimate_id = str(params.get('estimate_id', '') or '').strip()
    note = str(params.get('note', '')).strip()

    for row in estimates:
        if isinstance(row, dict) and row.get('id') == estimate_id:
            row.update({'stage': stage, 'value': value, 'date': date, 'note': note})
            data['estimates'] = estimates
            return {'estimate': row}

    created = {
        'id': _row_id('estimate', data, len(estimates) + 1, now),
        'stage': stage, 'value': value, 'date': date or now.strftime('%Y-%m-%d'),
    }
    if note:
        created['note'] = note
    estimates.append(created)
    data['estimates'] = estimates
    return {'estimate': created}


def _delete_estimate(data, params, _now):
    estimate_id = str(params.get('estimate_id', '') or '').strip()
    if not estimate_id:
        raise ApiError('Missing `estimate_id` parameter.')
    data['estimates'] = [row for row in csv_to_list(data.get('estimates'))
                         if not (isinstance(row, dict) and row.get('id') == estimate_id)]


def _delete_milestone(data, params, _now):
    milestone_id = str(params.get('milestone_id', '') or '').strip()
    if not milestone_id:
        raise ApiError('Missing `milestone_id` parameter.')
    data['milestones'] = [item for item in csv_to_list(data.get('milestones'))
                          if not (isinstance(item, dict) and item.get('id') == milestone_id)]


def _reorder_todos(data, params, _now):
    """
    Reorder the open notes.

    A note the browser did not mention keeps its place at the end rather than
    disappearing: a reorder is not a delete, whatever the payload forgot.
    """
    order = params.get('order')
    if not isinstance(order, list):
        raise ApiError('Missing or invalid `order` parameter.')

    # The ids as text, and where each one goes: the payload comes from a
    # browser, and a list holding anything else has to be read by the sort
    # rather than raise underneath it.
    wanted = {str(todo_id): position for position, todo_id in enumerate(order)}

    def rank(item):
        identity = str(item.get('id', '')) if isinstance(item, dict) else ''
        return wanted.get(identity, len(wanted))

    # A stable sort, so a note the browser did not mention keeps its place at
    # the end, in the order the card had it, whatever shape it is in.
    todos = sorted(csv_to_list(data.get('todos')), key=rank)
    data['todos'] = todos
    return {'order': [item.get('id') for item in todos if isinstance(item, dict)]}


def _is_note(item, todo_id):
    """
    True when this entry of `todos` or `done` is the note `todo_id` names.

    A card is hand-edited, so the key can hold anything: a bare string, a list
    of them, a value typed in the wrong shape. Only an object is a note; the
    rest is left where it is rather than crashing a handler that assumed.
    """
    return isinstance(item, dict) and item.get('id') == todo_id


def _require_todo_id(params):
    todo_id = params.get('todo_id')
    if not todo_id:
        raise ApiError('Missing `todo_id` parameter.')
    return todo_id


# ─── Routing table ───────────────────────────────────────────────────────────
ROUTES = {
    'update': _update_project,
    'simple-update': _simple_update_project,
    'advanced-update': _advanced_update_project,
    'set': _set_value,
    'todo/add': _add_todo,
    'todo/update': _update_todo,
    'todo/toggle': _toggle_todo,
    'todo/delete': _delete_todo,
    'todo/reorder': _reorder_todos,
    'timeline/save': _save_timeline,
    'timeline/delete': _delete_timeline_task,
    'milestone/save': _save_milestone,
    'milestone/delete': _delete_milestone,
    'estimate/save': _save_estimate,
    'estimate/delete': _delete_estimate,
}

# "Raw" actions bypass the parse → dict → dump round trip and work on the file
# text directly (used by the markdown tab of the advanced editor).
RAW_ROUTES = {
    'raw-update': _raw_update_project,
}

BATCH_ID = '_batch'


def _reorder_projects(repository, params, _now):
    """
    Apply a new ordering: `order` is a list of {id, group} in display order.

    A group is the live list or one of the two closing groups, and the drop
    target decides what happens: dropped into the live list a project comes
    back to life if it was finished or abandoned; dropped onto DONE or DROPPED
    it takes that status. Nothing else about the card changes.

    `priority` is the project's position over the whole chart, so the number in
    the card is the number on the screen. Only the cards whose position or
    group actually changed are written.
    """
    order = params.get('order')
    if not isinstance(order, list):
        raise ApiError("Missing or invalid `order` parameter.")

    groups = {settings_module.LIVE_GROUP} | set(settings_module.DISPLAY_GROUPS)
    position, updated = 0, 0

    for item in order:
        if not isinstance(item, dict):
            continue
        project_id, group = item.get('id'), item.get('group')
        if not project_id:
            continue
        # A project named with nowhere to put it used to be skipped, so a
        # payload that had lost its groups answered `updated: 0` — a success,
        # and a chart that looked like it had simply snapped back.
        if not group:
            raise ApiError(f'No group given for `{project_id}`.')
        if group not in groups:
            raise ApiError(f'Unknown group: {group}')
        data, _ = repository.load(project_id)
        if data is None:
            continue

        position += 1
        wanted = _placement(data, group, position)
        if all(str(data.get(key, '')) == value for key, value in wanted.items()):
            continue

        repository.mutate(project_id, lambda card, values=wanted: card.update(values))
        updated += 1

    return {'updated': updated}


def _placement(data, group, rank):
    """What the card should say after being dropped into `group` at `rank`."""
    if group in settings_module.DISPLAY_GROUPS:
        return {'status': group, 'priority': str(rank)}

    status = str(data.get('status', 'active')).lower()
    if status in settings_module.DISPLAY_GROUPS:
        status = 'active'          # dragged back up: it is being worked on again
    return {'status': status, 'priority': str(rank)}


def _slug(name):
    """`Résumé builder` → `resume-builder`: an id you can type at a shell."""
    ascii_name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', ascii_name.lower()).strip('-')


def _filled(params):
    """
    The payload without the values that were left empty.

    An update clears a field by sending it empty; a creation has nothing to
    clear, and writing `- dates` with an empty deadline under it would put a
    group in the file for an answer nobody gave.
    """
    return {key: value for key, value in params.items()
            if not (isinstance(value, str) and not value.strip())}


def _create_project(repository, params, now):
    """
    A card from a name, and whatever else the dialog carried.

    The id is the name as a slug unless one is given, and the position is the
    end of the live list. Everything beyond that is optional and declared in
    `schema.simple_fields`: a field the payload does not mention is not
    written, because every one of them already has a meaning when absent and
    the card should be as small as the format allows.
    """
    name = str(params.get('name', '')).strip()
    if not name:
        raise ApiError('The project needs a name.')
    project_id = str(params.get('id') or _slug(name)).strip()
    if not SAFE_ID_RE.match(project_id):
        raise ApiError('An id may only hold letters, digits, . _ and -.')
    if project_id == settings_module.INBOX_ID:
        raise ApiError(f'`{project_id}` is reserved for the notes of no project.')
    if repository.exists(project_id):
        raise ApiError(f'A card with the id {project_id} already exists.', status=409)

    live = [project for project in repository.list_all()
            if display_group(project, repository.settings) == settings_module.LIVE_GROUP]
    rank = 1 + max((project['_prio_num'] for project in live), default=0)
    card = {'id': project_id, 'name': name, 'type': 'project',
            'priority': str(rank), 'status': 'active'}

    _check_optional_span(params)
    schema.apply_fields(card, _filled(params), schema.simple_fields(repository.settings))
    _record_estimate(card, now)

    repository.save(project_id, card)
    return {'project': project_id}


def _create_inbox(repository):
    """The inbox exists from the first note on; nobody has to create it."""
    repository.save(settings_module.INBOX_ID, {
        'id': settings_module.INBOX_ID, 'name': settings_module.INBOX_TITLE,
        'type': 'inbox', 'priority': '0', 'status': 'active'})


def _write_vault_markdown(repository, params, _now):
    """
    Apply a whole-vault document: one card per `# title` block.

    Never a delete: a card whose block is not in the text is left alone, so an
    edit that happens not to mention something cannot remove it.
    """
    text = params.get('markdown')
    if not text or not str(text).strip():
        raise ApiError('The document is empty.')

    result = repository.apply_vault_markdown(text)
    if not result['created'] and not result['updated']:
        raise ApiError('No card block found: every card starts with a `# title` line.')
    return result


BATCH_ROUTES = {
    'create': _create_project,
    'reorder': _reorder_projects,
    'markdown': _write_vault_markdown,
}


# ─── Attachments ─────────────────────────────────────────────────────────────
# Not JSON mutations of a card: the payload is the file itself and nothing is
# written into the card, so they sit beside the routing table rather
# than in it.
_ATTACHMENT_NAME_MAX = 200
_ATTACHMENT_NAME_BAD = re.compile(r'[\x00-\x1f/\\]')


def clean_attachment_name(name):
    """A plain file name: no path separators, no control characters."""
    text = str(name or '').strip()
    if (not text or text in ('.', '..') or len(text) > _ATTACHMENT_NAME_MAX
            or _ATTACHMENT_NAME_BAD.search(text)):
        raise ApiError('Invalid file name.')
    return text


def upload_attachment(repository, project_id, name, data):
    """Store one uploaded file. Never overwrites: removing is a separate, explicit act."""
    _require_project(repository, project_id)
    name = clean_attachment_name(name)
    if not data:
        raise ApiError('The file is empty.')
    try:
        repository.save_attachment(project_id, name, data)
    except FileExistsError:
        raise ApiError(f'An attachment named {name} already exists. Remove it first.',
                       status=409)
    except ValueError as exc:
        raise ApiError(str(exc))
    return {'success': True, 'project': project_id, 'attachment': name}


def delete_attachment(repository, project_id, name):
    _require_project(repository, project_id)
    name = clean_attachment_name(name)
    try:
        removed = repository.delete_attachment(project_id, name)
    except ValueError as exc:
        raise ApiError(str(exc))
    if not removed:
        raise ApiError('Attachment not found.', status=404)
    return {'success': True, 'project': project_id, 'attachment': name}


def dispatch(repository, project_id, action, params, *, now=None):
    """Run the requested action. Raises ApiError on invalid input."""
    now = now or datetime.now()

    try:
        if project_id == BATCH_ID:
            handler = BATCH_ROUTES.get(action)
            if handler is None:
                raise ApiError(f'Unknown batch action: {action}', status=404)
            result = handler(repository, params, now) or {}
            return {'success': True, 'action': action, **result}

        if action in RAW_ROUTES:
            _require_project(repository, project_id)
            RAW_ROUTES[action](repository, project_id, params)
            return {'success': True, 'project': project_id, 'action': action}

        mutator = ROUTES.get(action)
        if mutator is None:
            raise ApiError(f'Unknown action: {action}', status=404)
        if project_id == settings_module.INBOX_ID and not repository.exists(project_id):
            _create_inbox(repository)
        _require_project(repository, project_id)

        # A mutator may hand back what it created or moved, so the browser can
        # patch that one row instead of reloading the whole document.
        result = {}
        repository.mutate(project_id,
                          lambda data: result.update(mutator(data, params, now) or {}))
        return {'success': True, 'project': project_id, 'action': action,
                'search': _search_text_of(repository, project_id), **result}
    except schema.ValidationError as exc:
        raise ApiError(str(exc))


def _search_text_of(repository, project_id):
    """
    The card as one text, for the search index its chart row carries.

    The browser searches the text `gantt._project_row` put on the row, and
    most edits are patched in place without a reload: without this, a note
    just deleted would still be found and a note just written would not be.
    Every mutation answers with the card as it is now.
    """
    data, body = repository.load(project_id)
    if data is None:
        return ''
    data['_body'] = body
    return search_text(data)


def _require_project(repository, project_id):
    if not repository.exists(project_id):
        raise ApiError(f'Project not found: {project_id}', status=404)
