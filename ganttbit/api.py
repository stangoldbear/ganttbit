"""
API actions: each handler describes ONLY the mutation to apply.

Loading, serialising and writing the file are centralised in
`ProjectRepository.mutate`; the fields themselves are declared once in
`schema.py`. Adding an endpoint means registering a function in `ROUTES`,
the server never changes.
"""

import re
from datetime import datetime

from . import schema, settings as settings_module
from .markup import render_markdown
from .repository import csv_to_list, ensure_dict


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


def _add_todo(data, params, now):
    text = str(params.get('text', '')).strip()
    if not text:
        raise ApiError('The note text is required.')

    todos = csv_to_list(data.get('todos'))
    todo = {
        'id': f"todo-{data.get('id', 'project')}-{len(todos) + 1}-{int(now.timestamp())}",
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
            if item.get('id') == todo_id:
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
        if item.get('id') == todo_id:
            moved = todos.pop(index)
            moved['completed_at'] = now.strftime('%Y-%m-%d %H:%M')
            history.insert(0, moved)
            break
    else:
        for index, item in enumerate(history):
            if item.get('id') == todo_id:
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
                                if item.get('id') != todo_id]


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
        'id': f"milestone-{data.get('id', 'project')}-{len(milestones) + 1}-{int(now.timestamp())}",
        'date': date,
        'text': text,
    }
    milestones.append(created)
    data['milestones'] = milestones
    return {'milestone': created}


def _save_timeline(data, params, now):
    """
    Write one bar: a row when `task_id` is given, the project span otherwise.

    The same endpoint serves a drag, which sends two dates, and the row dialog,
    which also sends who it belongs to and its note. Both dates are checked
    here: a drag that ends outside the scale, or a date typed by hand, must not
    be able to write something the card cannot represent.
    """
    start = str(params.get('start', '')).strip()
    end = str(params.get('end', '')).strip()
    if not _DATE_RE.match(start) or not _DATE_RE.match(end):
        raise ApiError('A bar needs a start and an end, as YYYY-MM-DD.')
    if end < start:
        raise ApiError('A bar cannot end before it starts.')

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

    remaining = {item.get('id'): item for item in csv_to_list(data.get('todos'))
                 if isinstance(item, dict)}
    reordered = [remaining.pop(todo_id) for todo_id in order if todo_id in remaining]
    reordered.extend(remaining.values())
    data['todos'] = reordered
    return {'order': [item.get('id') for item in reordered]}


def _require_todo_id(params):
    todo_id = params.get('todo_id')
    if not todo_id:
        raise ApiError('Missing `todo_id` parameter.')
    return todo_id


# ─── Routing table ───────────────────────────────────────────────────────────
ROUTES = {
    'update': _update_project,
    'advanced-update': _advanced_update_project,
    'todo/add': _add_todo,
    'todo/update': _update_todo,
    'todo/toggle': _toggle_todo,
    'todo/delete': _delete_todo,
    'todo/reorder': _reorder_todos,
    'timeline/save': _save_timeline,
    'timeline/delete': _delete_timeline_task,
    'milestone/save': _save_milestone,
    'milestone/delete': _delete_milestone,
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
        if not project_id or not group:
            continue
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
        _require_project(repository, project_id)

        # A mutator may hand back what it created or moved, so the browser can
        # patch that one row instead of reloading the whole document.
        result = {}
        repository.mutate(project_id,
                          lambda data: result.update(mutator(data, params, now) or {}))
        return {'success': True, 'project': project_id, 'action': action, **result}
    except schema.ValidationError as exc:
        raise ApiError(str(exc))


def _require_project(repository, project_id):
    if not repository.exists(project_id):
        raise ApiError(f'Project not found: {project_id}', status=404)
