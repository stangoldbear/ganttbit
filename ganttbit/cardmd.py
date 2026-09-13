"""
The card format: markdown outline ⇄ Python data.

Single responsibility: text ⇄ data. No HTTP, no HTML, no paths.

A card is a markdown document a person can read, grep and multi-edit:

    # Navigation menu — second level
    - id: project-1-navigation-menu
    - intro:
      ```md
      Two lines of free text,
      fenced so nothing needs escaping.
      ```
    - timeline
      - start: 2026-08-24
      - tasks
        - task-1
          - who: Ada Lovelace
    - platforms
      - iOS
      - Android

    ## Notes

    Everything from the first heading onwards is kept verbatim.

The title is the project name. A `- ` item is a key/value pair only when the
text before the first colon matches KEY and the colon is not followed by `//`,
so `- https://example.com/x` stays a value.

A group is read as one of three shapes, decided by its children:

    children look like        the group is
    - key: value              a map
    - value (no grandchild)   a list of strings
    - some-id + grandchildren a list of objects, `some-id` being its `id`

which is why an object identifier always carries a dash: `task-1` and
`RISK-01` cannot be mistaken for the key of a nested group, and `crit` in a
list of flags cannot be mistaken for an object.
"""

import re

KEY_RE = re.compile(r'^[a-z][a-z0-9_]*$')
_FENCE_RE = re.compile(r'^(`{3,})\s*(\w*)\s*$')
_HEADING_RE = re.compile(r'^#{1,6} ')
INDENT = 2


# ─── Reading ─────────────────────────────────────────────────────────────────
NOTES_HEADING = '## Notes'


def parse_card(text):
    """Return (data, body). A document without a `# title` is not a card."""
    lines = str(text).replace('\r\n', '\n').split('\n')
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1

    if index >= len(lines) or not lines[index].startswith('# '):
        return {}, str(text).strip()

    data = {'name': lines[index][2:].strip()}
    entries, body_at = _read_group(lines, index + 1, 0, root=True)
    data.update(entries)

    return data, _body_of(lines[body_at:])


def _body_of(lines):
    """
    The free markdown after the entries, without its own `## Notes` heading.

    The heading is structure and belongs to the format, so `build_card` writes
    it back; any other heading a card happens to start its body with is kept
    verbatim.
    """
    text = '\n'.join(lines).strip()
    if text.startswith(NOTES_HEADING):
        return text[len(NOTES_HEADING):].strip()
    return text


def _indent_of(line):
    return len(line) - len(line.lstrip())


def _children_start(lines, index, indent):
    """The index of the first child line of the item that ends at `index`."""
    cursor = index
    while cursor < len(lines) and not lines[cursor].strip():
        cursor += 1
    if cursor < len(lines) and _indent_of(lines[cursor]) > indent \
            and lines[cursor].lstrip().startswith('- '):
        return cursor
    return None


def _read_group(lines, index, indent, root=False):
    """
    Read the items sitting at `indent`, from `index` on.

    Returns (value, next_index) where value is a dict, a list of strings or a
    list of objects, whichever the children describe.
    """
    items = []                       # (kind, key_or_value, value)
    cursor = index

    while cursor < len(lines):
        line = lines[cursor]
        if not line.strip():
            cursor += 1
            continue

        # The entries end at the first line that is not one of them: a
        # heading, free text, anything. Whatever follows is the body and is
        # kept verbatim: a card is hand-edited, and text that was typed into
        # it must never be dropped just because it is in the wrong shape.
        if _indent_of(line) != indent or not line.lstrip().startswith('- '):
            break

        content = line.lstrip()[2:].rstrip()
        cursor += 1

        key, rest = _split_key(content)
        if key is not None and rest == '':
            # `- key:` followed by a fenced block, or the empty string.
            value, cursor = _read_fence(lines, cursor, indent + INDENT)
            items.append(('entry', key, value))
            continue
        if key is not None:
            items.append(('entry', key, _coerce(rest)))
            continue

        child_at = _children_start(lines, cursor, indent)
        if child_at is None:
            items.append(('bare', content, None))
            continue

        value, cursor = _read_group(lines, child_at, _indent_of(lines[child_at]))
        if KEY_RE.match(content):
            items.append(('entry', content, value))
        else:
            items.append(('object', content, value))

    return _shape(items, root), cursor


def _split_key(content):
    """(key, rest) when the item is a key/value pair, (None, None) otherwise."""
    marker = content.find(':')
    if marker == -1 or content[marker + 1:marker + 3] == '//':
        return None, None
    key = content[:marker]
    if not KEY_RE.match(key):
        return None, None
    return key, content[marker + 1:].strip()


def _shape(items, root=False):
    """Turn the read items into a map, a list of strings or a list of objects."""
    if not items:
        return {} if root else []
    if root or any(kind == 'entry' for kind, _, _ in items):
        result = {}
        for kind, key, value in items:
            if kind == 'entry':
                result[key] = value
            elif kind == 'bare' and KEY_RE.match(key):
                result[key] = []       # `- key` with nothing under it
            else:                      # a value where a key was expected
                result.setdefault('_stray', []).append(key)
        return result

    if all(kind == 'bare' for kind, _, _ in items):
        return [value for _, value, _ in items]

    objects = []
    for kind, key, value in items:
        entry = dict(value) if isinstance(value, dict) else {}
        objects.append({'id': key, **entry})
    return objects


def _read_fence(lines, index, indent):
    """
    Read a fenced block starting at `index`, or return the empty string.

    The fence may be any run of three or more backticks; the closing fence is
    the first run at least as long, which is what makes nesting unambiguous.
    """
    cursor = index
    while cursor < len(lines) and not lines[cursor].strip():
        cursor += 1
    if cursor >= len(lines):
        return '', index

    opening = _FENCE_RE.match(lines[cursor].strip())
    if not opening or _indent_of(lines[cursor]) < indent:
        return '', index

    ticks = opening.group(1)
    body, cursor = [], cursor + 1
    while cursor < len(lines):
        stripped = lines[cursor].strip()
        if stripped.startswith(ticks) and _FENCE_RE.match(stripped):
            cursor += 1
            break
        body.append(lines[cursor][indent:] if lines[cursor][:indent].isspace()
                    or not lines[cursor].strip() else lines[cursor].lstrip())
        cursor += 1

    return '\n'.join(body).strip('\n'), cursor


def _coerce(value):
    if value == 'true':
        return True
    if value == 'false':
        return False
    # A convenience on read only: an inline list is rewritten as bullets by
    # the next save.
    return value


# ─── Writing ─────────────────────────────────────────────────────────────────
def build_card(data, body=''):
    """Render the card. `data['name']` is the title; `_private` keys are dropped."""
    lines = [f"# {data.get('name', '')}".rstrip()]

    for key, value in data.items():
        if key == 'name' or str(key).startswith('_'):
            continue
        lines.extend(_render(key, value, 0))

    text = '\n'.join(lines).rstrip() + '\n'
    body = str(body or '').strip()
    if not body:
        return text
    if not body.startswith('#'):
        body = f'{NOTES_HEADING}\n\n{body}'
    return f'{text}\n{body}\n'


def _render(key, value, indent):
    pad = ' ' * indent

    if isinstance(value, bool):
        return [f'{pad}- {key}: {"true" if value else "false"}']

    if value is None:
        return [f'{pad}- {key}:']

    if isinstance(value, dict):
        if not value:
            return []
        lines = [f'{pad}- {key}']
        for name, item in value.items():
            if str(name).startswith('_'):
                continue
            lines.extend(_render(name, item, indent + INDENT))
        return lines

    if isinstance(value, list):
        if not value:
            return []
        lines = [f'{pad}- {key}']
        for position, item in enumerate(value, start=1):
            lines.extend(_render_item(key, item, position, indent + INDENT))
        return lines

    text = str(value)
    if text == '':
        return [f'{pad}- {key}:']
    if '\n' in text or text != text.strip():
        return [f'{pad}- {key}:'] + _fence(text, indent + INDENT)
    return [f'{pad}- {key}: {text}']


def _render_item(key, item, position, indent):
    pad = ' ' * indent
    if not isinstance(item, dict):
        text = str(item)
        if '\n' in text:
            return _fence(text, indent)
        return [f'{pad}- {text}']

    identifier = str(item.get('id') or '').strip()
    if not identifier or identifier == 'new':
        # Every object carries an identity, and it always has a dash in it:
        # that is what keeps `- task-1` from reading as a nested group.
        identifier = f'{key}-{position}'

    lines = [f'{pad}- {identifier}']
    for name, value in item.items():
        if name == 'id' or str(name).startswith('_'):
            continue
        lines.extend(_render(name, value, indent + INDENT))
    return lines


def _fence(text, indent):
    """A fence one backtick longer than the longest run inside the value."""
    longest = max((len(run) for run in re.findall(r'`+', text)), default=0)
    ticks = '`' * max(3, longest + 1)
    pad = ' ' * indent
    lines = [f'{pad}{ticks}md']
    lines.extend(f'{pad}{line}'.rstrip() for line in text.split('\n'))
    lines.append(f'{pad}{ticks}')
    return lines
