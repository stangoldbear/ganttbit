"""
One-way migration off the pre-0.1.0 formats.

Two things used to live outside the cards: the YAML front matter, and the
hand-written mermaid delivery plan that owned every bar in the chart. This
module is the only place that still understands either, it only reads them,
nothing else in `ganttbit` imports it, and it can be deleted the day no such
vault is left.
"""

import glob
import os
import re
import tomllib
from datetime import datetime, timedelta

from .cardmd import build_card, parse_card
from .domain import add_working_days
from .repository import write_atomic

_MERMAID_RE = re.compile(r'```mermaid\n(.*?)\n```', re.DOTALL)
_GANTT_KEYWORDS = ('gantt', 'title', 'dateFormat', 'axisFormat', 'tickInterval', 'excludes')
_DURATION_RE = re.compile(r'^\d+d$')
_PLAN_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}')

import re

_FRONTMATTER_RE = re.compile(r'^---\n(.*?)\n---(.*)', re.DOTALL)
_BLOCK_HEADERS = {'|', '|-', '|+', '>', '>-', '>+'}
_URL_SCHEME_RE = re.compile(r'^[\w.+-]+://')


def strip_comment(raw):
    """
    Drop a trailing `# comment` from a scalar, YAML-style.

    A `#` only starts a comment at the start of the value or after a space,
    and never inside a quoted string, so `"a # b"` and `http://x/#frag`
    keep their hash.
    """
    value = raw.strip()
    if value[:1] in ('"', "'"):
        quote = value[0]
        end = value.find(quote, 1)
        while end != -1 and value[end - 1] == '\\':
            end = value.find(quote, end + 1)
        if end != -1:
            return value[:end + 1].strip()
        return value
    hash_at = value.find('#')
    while hash_at != -1:
        if hash_at == 0 or value[hash_at - 1] in ' \t':
            return value[:hash_at].strip()
        hash_at = value.find('#', hash_at + 1)
    return value


def _coerce(raw):
    """Normalise a YAML scalar into a Python value."""
    value = strip_comment(raw)
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        # Quoted string: drop the delimiters and undo the escapes `_scalar`
        # produces (quotes and newlines).
        value = value[1:-1].replace('\\"', '"').replace('\\n', '\n')
    else:
        value = value.strip("'")
    lowered = value.lower()
    if lowered == 'true':
        return True
    if lowered == 'false':
        return False
    return value


def _next_line_is_list(lines, index):
    for line in lines[index + 1:]:
        if line.strip():
            return line.strip().startswith('- ')
    return False


def _read_block_scalar(lines, index, key_indent, header):
    """
    Collect the body of a `key: |` block starting after `index`.

    Returns (text, next_index). Trailing newline follows the chomping
    indicator: `|` keeps one, `|-` strips it, `|+` keeps them all.
    """
    body, cursor = [], index + 1
    while cursor < len(lines):
        line = lines[cursor]
        if line.strip() and (len(line) - len(line.lstrip())) <= key_indent:
            break
        body.append(line)
        cursor += 1

    while body and not body[-1].strip():
        body.pop()
    if not body:
        return '', cursor

    indent = min(len(line) - len(line.lstrip()) for line in body if line.strip())
    text = '\n'.join(line[indent:] if line.strip() else '' for line in body)
    if header.startswith('>'):
        text = text.replace('\n', ' ')
    if not header.endswith('-'):
        text += '\n'
    return text, cursor


def parse_yaml_text(text):
    """Convert an indented YAML subset into a nested dict."""
    data = {}
    stack = [(data, -1)]
    lines = text.split('\n')
    index = 0

    while index < len(lines):
        line = lines[index]
        index += 1
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue

        indent = len(line) - len(line.lstrip())
        while len(stack) > 1 and indent <= stack[-1][1]:
            stack.pop()
        parent = stack[-1][0]

        # List item
        if stripped.startswith('- '):
            if not isinstance(parent, list):
                continue
            item = stripped[2:].strip()
            # A quoted scalar or a URL is never an inline map, even though it
            # contains `:`; only an unquoted `key: value` is.
            is_inline_map = (
                ':' in item
                and not item.startswith(('{', '[', '"', "'"))
                and not _URL_SCHEME_RE.match(item)
            )
            if is_inline_map:
                key, raw = item.split(':', 1)
                entry = {key.strip(): _coerce(raw)}
                parent.append(entry)
                stack.append((entry, indent))
            else:
                parent.append(_coerce(item))
            continue

        if ':' not in stripped:
            continue

        key, raw = stripped.split(':', 1)
        key, raw = key.strip(), raw.strip()

        if raw in _BLOCK_HEADERS:
            parent[key], index = _read_block_scalar(lines, index - 1, indent, raw)
        elif not raw or strip_comment(raw) == '':
            container = [] if _next_line_is_list(lines, index - 1) else {}
            parent[key] = container
            stack.append((container, indent))
        elif raw.startswith('[') and raw.endswith(']'):
            parent[key] = [_coerce(x) for x in raw[1:-1].split(',') if x.strip()]
        elif raw.startswith('{') and raw.endswith('}'):
            parent[key] = {}
        else:
            parent[key] = _coerce(raw)

    return data


def parse_frontmatter(content):
    """Return (front_matter_data, markdown_body)."""
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content.strip()
    return parse_yaml_text(match.group(1)), match.group(2).strip()

# ─── Conversion ──────────────────────────────────────────────────────────────
def convert(text):
    """
    YAML card text → markdown card text.

    Two renames the format brings with it: the completed notes live under
    `done` rather than `todos_history`, and the per-item `done: true` flag is
    dropped: the category is the state, and the two could contradict.
    """
    data, body = parse_frontmatter(text)
    if not data:
        raise ValueError('No YAML front matter to convert.')

    converted = {}
    for key, value in data.items():
        if key == 'todos_history':
            converted['done'] = [_without_flag(item) for item in value or []]
        elif key == 'todos':
            converted['todos'] = [_without_flag(item) for item in value or []]
        else:
            converted[key] = value

    return build_card(converted, body)


def _without_flag(item):
    if not isinstance(item, dict):
        return item
    return {key: value for key, value in item.items() if key != 'done'}


def migrate_vault(directory):
    """
    Convert every YAML card in `directory`, in place.

    Each rewritten file leaves a `<name>.md.bak` beside it, and a file that is
    already a markdown card is skipped: running twice cannot destroy a backup
    or double-convert a card.
    """
    converted, skipped, failed = [], [], []

    for path in sorted(glob.glob(os.path.join(directory, '*.md'))):
        name = os.path.basename(path)
        with open(path, 'r', encoding='utf-8') as handle:
            text = handle.read()

        if parse_card(text)[0]:
            skipped.append(name)
            continue

        try:
            card = convert(text)
        except ValueError as exc:
            failed.append((name, str(exc)))
            continue

        backup = path + '.bak'
        if not os.path.exists(backup):
            with open(backup, 'w', encoding='utf-8') as handle:
                handle.write(text)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(card)
        converted.append(name)

    return {'converted': converted, 'skipped': skipped, 'failed': failed}


# ─── Tiers, read one last time ───────────────────────────────────────────────
# An older vault gave every card a tier, and `priority` ranked it inside that
# tier, so three cards could all be "1". This version has no tier and makes
# `priority` the position in one flat list, which means the numbers have to be
# rewritten while the tiers are still there to say what the order was.
_CLOSING_STATUSES = ('done', 'dropped')


def read_tier_order(settings_path):
    """
    The retired `[[tiers]]` table, in declaration order, straight from the file.

    A vault being upgraded may sit beside a settings file that still declares
    them, or beside a current one that no longer does. Both are expected: the
    caller falls back to the order the cards themselves imply.
    """
    try:
        with open(settings_path, 'rb') as handle:
            entries = tomllib.load(handle).get('tiers') or []
    except (OSError, tomllib.TOMLDecodeError):
        return []
    return [str(entry['key']) for entry in entries
            if isinstance(entry, dict) and entry.get('key')]


def _old_position(data, tier_order):
    """Where a card sat before: closing statuses last, then tier, then priority."""
    status = str(data.get('status', '') or '').lower()
    tier = str(data.get('tier', '') or '').lower()
    try:
        priority = int(str(data.get('priority', '')).strip())
    except (TypeError, ValueError):
        priority = 99
    return (
        _CLOSING_STATUSES.index(status) + 1 if status in _CLOSING_STATUSES else 0,
        tier_order.index(tier) if tier in tier_order else len(tier_order),
        priority,
        str(data.get('id', '')),
    )


def drop_tiers(directory, settings_path, apply=False):
    """
    Remove `tier` from every card and renumber `priority` 1..N, in place.

    Read-only unless `apply` is true, so the change can be inspected first.
    A vault with no `tier` left and priorities already in sequence reports no
    change at all, which is what makes running it twice harmless.
    """
    cards = []
    for path in sorted(glob.glob(os.path.join(directory, '*.md'))):
        with open(path, 'r', encoding='utf-8') as handle:
            text = handle.read()
        data, body = parse_card(text)
        if data:
            cards.append((path, data, body))

    tier_order = read_tier_order(settings_path)
    if not tier_order:
        # No table to read: the tiers the cards name, in their own order.
        tier_order = sorted({str(data.get('tier', '') or '').lower()
                             for _, data, _ in cards if data.get('tier')})

    cards.sort(key=lambda card: _old_position(card[1], tier_order))

    changed = []
    for rank, (path, data, body) in enumerate(cards, start=1):
        was_tier, was_priority = data.get('tier'), str(data.get('priority', ''))
        if was_tier is None and was_priority == str(rank):
            continue

        data.pop('tier', None)
        data['priority'] = str(rank)
        if apply:
            write_atomic(path, build_card(data, body))
        changed.append({'file': os.path.basename(path), 'id': data.get('id', ''),
                        'tier': was_tier, 'from': was_priority, 'to': str(rank)})

    return {'total': len(cards), 'changed': changed, 'applied': bool(apply)}


# ─── The delivery plan, read one last time ───────────────────────────────────
def parse_plan(text):
    """Turn the mermaid gantt block of a delivery plan into rows."""
    match = _MERMAID_RE.search(text)
    if not match:
        return []

    rows, section = [], 'Default'
    for raw in match.group(1).split('\n'):
        line = raw.strip()
        if not line or line.startswith(_GANTT_KEYWORDS) or line.startswith('%%'):
            continue
        if line.startswith('section '):
            section = line[8:].strip()
            continue

        label, remainder = _split_task_line(line)
        if not label or not remainder:
            continue

        modifiers, date_parts = [], []
        for part in (piece.strip() for piece in remainder.split(',')):
            if _PLAN_DATE_RE.match(part) or _DURATION_RE.match(part):
                date_parts.append(part)
            else:
                modifiers.extend(part.split())

        if not date_parts:
            continue

        try:
            start = datetime.strptime(date_parts[0], '%Y-%m-%d')
            if len(date_parts) > 1:
                duration = date_parts[1]
                end = (add_working_days(start, int(duration[:-1]))
                       if _DURATION_RE.match(duration)
                       else datetime.strptime(duration, '%Y-%m-%d'))
            else:
                end = start + timedelta(days=1)
        except ValueError:
            continue

        rows.append({'label': label, 'section': section, 'start': start, 'end': end,
                     'flags': [flag for flag in ('crit', 'active', 'done')
                               if flag in modifiers]})
    return rows


def _split_task_line(line):
    marker = line.rfind(' :')
    if marker != -1:
        return line[:marker].strip(), line[marker + 2:].strip()
    marker = line.find(':')
    if marker == -1:
        return None, None
    return line[:marker].strip(), line[marker + 1:].strip()


def _who_and_note(label, settings):
    """Split `iOS Dev #1 P1 menu integration` into a person and a note."""
    members = [member for squad in settings.squads.values() for member in squad]
    for member in sorted(members, key=lambda entry: -len(entry['prefix'])):
        if label.startswith(member['prefix']):
            return member['name'], label[len(member['prefix']):].strip()
    return label, ''


def _project_of(label, codes):
    """The project a row names through its short code, longest code first."""
    for code in sorted(codes, key=len, reverse=True):
        if re.search(r'\b' + re.escape(code) + r'\b', label):
            return codes[code], re.sub(r'\b' + re.escape(code) + r'\b', '', label, count=1)
    return None, label


DEFAULT_PLAN = os.path.join('03-delivery-patterns', 'delivery-plan.md')


def read_project_codes(settings_path):
    """
    The retired `[project_codes]` table, read straight from the settings file.

    The application no longer knows about short codes, because a card owns its rows,
    but the plan being imported is still written in them.
    """
    try:
        with open(settings_path, 'rb') as handle:
            return dict(tomllib.load(handle).get('project_codes', {}))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def import_plan(repository, plan_path, codes):
    """
    Move every plan row carrying a project code into that project's card.

    The file itself is left untouched: it is read once and then has no reader
    left. Rows with no code, or with a code for a card that is gone, are
    reported rather than dropped silently.
    """
    if not os.path.isfile(plan_path):
        raise ValueError(f'No delivery plan at {plan_path}')

    with open(plan_path, 'r', encoding='utf-8') as handle:
        rows = parse_plan(handle.read())

    settings = repository.settings
    imported, skipped = {}, []

    for row in rows:
        project_id, label = _project_of(row['label'], codes)
        if not project_id:
            skipped.append((row['label'], 'no project code'))
            continue
        if not repository.exists(project_id):
            skipped.append((row['label'], f'no card for {project_id}'))
            continue

        who, note = _who_and_note(label, settings)
        imported.setdefault(project_id, []).append({
            'who': who,
            'start': row['start'].strftime('%Y-%m-%d'),
            'end': row['end'].strftime('%Y-%m-%d'),
            'flags': row['flags'],
            'note': note,
        })

    for project_id, tasks in imported.items():
        repository.mutate(project_id, lambda data, tasks=tasks: _write_timeline(data, tasks))

    return {'imported': {key: len(value) for key, value in imported.items()},
            'skipped': skipped}


def _write_timeline(data, tasks):
    """
    Write the rows into the card, and give the project the span they cover.

    `dates.started` is absorbed here: the date a project started is the start
    of its timeline, and two fields for one fact is how they come to disagree.
    """
    for position, task in enumerate(tasks, start=1):
        task['id'] = f'task-{position}'
        if not task['flags']:
            task.pop('flags')
        if not task['note']:
            task.pop('note')

    dates = data.get('dates') or {}
    started = str(dates.pop('started', '') or '').strip()
    starts = [task['start'] for task in tasks] + ([started] if started else [])

    ordered = []
    for task in tasks:
        ordered.append({'id': task['id'], 'who': task['who'], 'start': task['start'],
                        'end': task['end'],
                        **({'flags': task['flags']} if 'flags' in task else {}),
                        **({'note': task['note']} if 'note' in task else {})})

    timeline = {
        'start': min(starts),
        'end': max(task['end'] for task in tasks),
        'tasks': ordered,
    }

    # Put it where it reads: the timeline is the point of the card, so it goes
    # under the free-text intro rather than at the bottom, behind the history.
    if 'timeline' in data:
        data['timeline'] = timeline
        return
    rebuilt = {}
    for key, value in data.items():
        rebuilt[key] = value
        if key == 'intro':
            rebuilt['timeline'] = timeline
    rebuilt.setdefault('timeline', timeline)
    data.clear()
    data.update(rebuilt)
