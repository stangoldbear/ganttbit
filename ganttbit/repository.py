"""
Data access: reads and writes the project cards in the knowledge vault.

The only module that touches the filesystem. View, domain and API know
nothing about paths or file format.
"""

import glob
import os
import re
import tempfile

from . import settings as settings_module
from .cardmd import build_card, parse_card
from .domain import display_group, group_rank

_SAFE_ID_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*$')

def write_atomic(path, data):
    """
    Replace a file's content without ever leaving a truncated file behind.

    Writing in place truncates immediately: an error halfway through would
    destroy a knowledge card. Write a sibling temp file, then rename.
    `data` is text (written as UTF-8) or bytes.
    """
    directory = os.path.dirname(path) or '.'
    os.makedirs(directory, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        'wb', dir=directory, prefix='.tmp-', delete=False)
    try:
        with handle:
            handle.write(data.encode('utf-8') if isinstance(data, str) else data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    except BaseException:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise


class ProjectRepository:
    """Markdown cards, one file per project."""

    def __init__(self, directory=None, settings=None):
        self._settings = settings
        self.directory = directory or self.settings.projects_dir

    @property
    def settings(self):
        return self._settings or settings_module.current()

    # ─── Paths ───────────────────────────────────────────────────────────────
    def path_for(self, project_id):
        # Path traversal guard: only a plain file name is ever accepted.
        safe_id = os.path.basename(str(project_id))
        return os.path.join(self.directory, safe_id + '.md')

    def exists(self, project_id):
        return os.path.isfile(self.path_for(project_id))

    # ─── Reads ───────────────────────────────────────────────────────────────
    def load(self, project_id):
        """Return (data, body), or (None, None) when the card is missing."""
        path = self.path_for(project_id)
        if not os.path.isfile(path):
            return None, None
        with open(path, 'r', encoding='utf-8') as handle:
            return parse_card(handle.read())

    def read_raw(self, project_id):
        """Return the card text as it is on disk, or None."""
        path = self.path_for(project_id)
        if not os.path.isfile(path):
            return None
        with open(path, 'r', encoding='utf-8') as handle:
            return handle.read()

    def list_all(self):
        """Every card, ranked: the live list first, then DONE and DROPPED."""
        if not os.path.isdir(self.directory):
            return []

        projects = []
        for path in sorted(glob.glob(os.path.join(self.directory, '*.md'))):
            try:
                with open(path, 'r', encoding='utf-8') as handle:
                    data, body = parse_card(handle.read())
            except OSError as exc:
                print('Could not read project card:', path, exc)
                continue

            if not data:
                continue

            data['_body'] = body
            data['_file'] = os.path.basename(path)
            data['_prio_num'] = as_int(data.get('priority'), 99)
            data['_attachments'] = self.list_attachments(data.get('id', ''))
            projects.append(data)

        # Group first, `priority` second: a number edited by hand into a card
        # can only misplace it inside the live list, never pull a finished
        # project back up among the live ones.
        projects.sort(key=lambda project: (
            group_rank(display_group(project, self.settings), self.settings),
            project.get('_prio_num', 99),
            str(project.get('id', '')),
        ))
        return projects

    # ─── Attachments ─────────────────────────────────────────────────────────
    # Files of any type kept next to the cards, one folder per project. The
    # folder listing is the only source of truth: nothing about attachments is
    # written into the card, so the two can never drift apart.
    def attachment_path(self, project_id, name):
        """Path of one attachment; refuses anything that is not a plain file name."""
        safe_project = os.path.basename(str(project_id))
        safe_name = os.path.basename(str(name))
        if not safe_project or not safe_name or safe_name != name or safe_name in ('.', '..'):
            raise ValueError(f'Invalid attachment name: {name!r}')
        return os.path.join(self.settings.attachments_dir, safe_project, safe_name)

    def list_attachments(self, project_id):
        """[{name, size, modified}] sorted by name, [] when the folder is absent."""
        folder = os.path.join(self.settings.attachments_dir, os.path.basename(str(project_id)))
        if not project_id or not os.path.isdir(folder):
            return []
        entries = []
        for name in sorted(os.listdir(folder)):
            path = os.path.join(folder, name)
            if name.startswith('.') or not os.path.isfile(path):
                continue                                  # temp files, OS junk
            info = os.stat(path)
            entries.append({'name': name, 'size': info.st_size, 'modified': info.st_mtime})
        return entries

    def save_attachment(self, project_id, name, data):
        """Store bytes as a new attachment. Refuses to overwrite: deleting is explicit."""
        path = self.attachment_path(project_id, name)
        if os.path.exists(path):
            raise FileExistsError(name)
        write_atomic(path, data)

    def delete_attachment(self, project_id, name):
        """Remove one attachment. Returns False when it did not exist."""
        path = self.attachment_path(project_id, name)
        if not os.path.isfile(path):
            return False
        os.remove(path)
        folder = os.path.dirname(path)
        if not os.listdir(folder):
            os.rmdir(folder)                      # no empty folders left behind
        return True

    # ─── Writes ──────────────────────────────────────────────────────────────
    def save(self, project_id, data, body=''):
        payload = {key: value for key, value in data.items() if not key.startswith('_')}
        write_atomic(self.path_for(project_id), build_card(payload, body))

    def write_raw(self, project_id, text):
        """
        Write the card text as typed, after validating it.

        It must parse back as a card, with a `# title` and at least one entry,
        so a broken outline in the markdown editor never reaches the file.
        """
        data, _ = parse_card(text)
        if len(data) < 2:
            raise ValueError('The card must start with a `# title` line and hold '
                             'at least one `- key: value` entry.')
        write_atomic(self.path_for(project_id), text if text.endswith('\n') else text + '\n')

    # ─── The whole vault as one document ─────────────────────────────────────
    # Every card, in the order the chart draws them. It is the monthly snapshot
    # and the multi-card editor: one text to read, grep, diff and archive.
    def vault_markdown(self):
        """Every card concatenated, in the order the chart draws them."""
        blocks = []
        for project in self.list_all():
            text = self.read_raw(project['id'])
            if text:
                blocks.append(text.strip())
        return '\n\n'.join(blocks) + '\n' if blocks else ''

    def apply_vault_markdown(self, text):
        """
        Write back a whole-vault document, one card per `# title` block.

        A block whose id is unknown creates a card; a card whose block is
        absent is left alone. Deleting is never a side effect of an edit that
        happens not to mention something.
        """
        created, updated, skipped = [], [], []

        for block in split_cards(text):
            data, body = parse_card(block)
            project_id = str(data.get('id', '') or '').strip()
            if not data:
                skipped.append(('(no title)', 'not a card: no `# title` line'))
                continue
            if not project_id:
                skipped.append((data.get('name', '(untitled)'), 'no `- id:` entry'))
                continue
            if not _SAFE_ID_RE.match(project_id):
                skipped.append((project_id, 'an id may only hold letters, digits, . _ and -'))
                continue

            (updated if self.exists(project_id) else created).append(project_id)
            self.save(project_id, data, body)

        return {'created': created, 'updated': updated, 'skipped': skipped}

    def mutate(self, project_id, mutator):
        """
        Load → apply `mutator(data)` → save.

        Single write path: every API endpoint describes only *what* changes,
        never *how* it is persisted. Returns True when the card existed.
        """
        data, body = self.load(project_id)
        if data is None:
            return False
        mutator(data)
        # Convention: a mutator replaces the markdown body by setting the
        # private `_new_body` key (used by the advanced editor).
        if '_new_body' in data:
            body = data.pop('_new_body')
        self.save(project_id, data, body)
        return True


# ─── Shared helpers ──────────────────────────────────────────────────────────
def split_cards(text):
    """Split a multi-card document on its top-level `# ` headings."""
    blocks, current = [], []
    for line in str(text or '').replace('\r\n', '\n').split('\n'):
        if line.startswith('# '):
            if current:
                blocks.append('\n'.join(current).strip())
            current = [line]
        elif current:
            current.append(line)
    if current:
        blocks.append('\n'.join(current).strip())
    return [block for block in blocks if block]



def as_int(value, fallback):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def ensure_dict(data, key):
    """Guarantee that `data[key]` is a dict and return it."""
    if not isinstance(data.get(key), dict):
        data[key] = {}
    return data[key]


def csv_to_list(value):
    """
    Coerce an API value to a list, splitting a comma-separated string.

    Boundary coercion only: forms submit either a real array or a CSV field.
    For rendering use `view.ensure_list`, which never splits.
    """
    if value is None or value == '':
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(',') if item.strip()]
    if isinstance(value, list):
        return value
    return [value]
