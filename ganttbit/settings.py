"""
Deployment settings and presentation constants.

`settings.toml` holds everything an organisation changes (squads, roles,
project codes, links, wording); this module parses it once, fails fast on a
malformed file, and exposes it as a frozen `Settings` value.

Composition root: `configure()` is called once by the entry point. Modules read
the result through `current()`. A single process-wide value is a deliberate
simplification for a single-tenant local tool; tests call `configure()` with
their own fixture path.
"""

import ipaddress
import os
import re
import secrets
import tomllib
from dataclasses import dataclass
from datetime import date

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(PACKAGE_DIR)
STATIC_DIR = os.path.join(PACKAGE_DIR, 'static')
DEFAULT_SETTINGS_PATH = os.path.join(BASE_DIR, 'settings.toml')
LOCAL_SETTINGS_PATH = os.path.join(BASE_DIR, 'settings.local.toml')

# ─── Presentation constants (not deployment-specific: kept in code) ──────────
BLOCKED_COLOR = '#e74c3c'

STATUS_STYLES = {
    'active':   {'bg': '#e8f5e9', 'fg': '#2e7d32'},
    'blocked':  {'bg': '#ffebee', 'fg': '#b71c1c'},
    'inactive': {'bg': '#eceff1', 'fg': '#546e7a'},
    'done':     {'bg': '#e0f2f1', 'fg': '#00695c'},
    'dropped':  {'bg': '#f3f3f4', 'fg': '#6b7280'},
}
STATUS_FALLBACK = {'bg': '#f5f5f5', 'fg': '#555555'}
STATUS_OPTIONS = list(STATUS_STYLES)

# The live list has no heading of its own: it is simply the chart. The two
# groups below it are drawn under one each, and a project lands in one because
# of its status alone. Dropping a project onto a heading is what sets it.
LIVE_GROUP = 'live'
LIVE_GROUP_TITLE = 'IN FLIGHT'
DONE_GROUP, DROPPED_GROUP = 'done', 'dropped'
DISPLAY_GROUPS = {
    DONE_GROUP:    {'title': 'DONE', 'rgb': (0, 105, 92)},
    DROPPED_GROUP: {'title': 'DROPPED', 'rgb': (107, 114, 128)},
}

# One reserved card for the notes that belong to no project yet. On disk it is
# a card like any other, so it can be read, grepped and archived with the rest;
# the chart, the list and the project count leave it out, the aggregated
# actions put it first, and the first note written creates it.
INBOX_ID = 'inbox'
INBOX_TITLE = 'Inbox'

DEADLINE_STYLES = {
    'hard': {'bg': '#ffebee', 'fg': '#c62828'},
    'soft': {'bg': '#fff8e1', 'fg': '#f57f17'},
}
DEADLINE_OPTIONS = [('soft', 'Soft target'), ('hard', 'Hard deadline')]

SEVERITY_OPTIONS = ['high', 'medium', 'low']

# Attachment types the browser may render inline. Anything else is served as a
# download: an uploaded HTML or SVG file rendered same-origin would run script.
INLINE_ATTACHMENT_TYPES = frozenset({
    'application/pdf', 'image/png', 'image/jpeg', 'image/gif', 'image/webp',
    'text/plain', 'text/markdown',
})
QA_EFFORT_OPTIONS = ['low', 'medium', 'high']

# Gantt layout metrics. Emitted as CSS custom properties by the view so that
# stylesheet and script never restate them (single source of truth).
COL_W = 17           # day column width in px
LABEL_W = 340        # sticky left column, initial width
LABEL_W_MIN = 160    # drag limits for the sticky column
LABEL_W_MAX = 900
# How wide one working day is drawn, per zoom level. A column is always a day,
# what changes is how many of them fit, and therefore what the header can say.
ZOOM_LEVELS = {'day': COL_W, 'week': 6, 'month': 2}
# How far ahead the scale runs when the window has not said where to stop.
# Zooming out is asking to see further, and at 2px a day a scale that ends
# with the last bar leaves two thirds of the screen empty: a month view of one
# quarter is not a month view. Calendar days, measured from today; a window
# with an end date of its own always wins.
ZOOM_HORIZON = {'day': 0, 'week': 190, 'month': 760}
DEFAULT_ZOOM = 'day'

ROW_H = 34           # project row (one line: identity, signals, actions)
COMPACT_ROW_H = 22   # the same row at the Compact level: rank, name, span
SUB_ROW_H = 20       # resource row

# ─── The project, as opposed to the deployment ───────────────────────────────
# Upstream, not a setting: a fork points at its own releases by editing this
# line, and an organisation running the tool has nothing to configure here.
CHANGELOG_PATH = os.path.join(BASE_DIR, 'CHANGELOG.md')
RELEASES_URL = 'https://github.com/stangoldbear/ganttbit/releases/latest'

_VERSION_HEADING = r'^##\s+\[?{}\]?\b'


def _unwrap(lines):
    """
    Join a hard-wrapped line back onto the one above it.

    The CHANGELOG is written to 80 columns and continues a bullet by indenting
    it, which is the markdown convention and also the only signal needed here.
    The renderer takes a newline literally, on purpose, because a card's notes
    come from a textarea where pressing Enter means it. A file wrapped by its
    author is the other case, so the wrapping comes out here rather than the
    renderer learning to guess which of the two it is looking at.
    """
    joined = []
    for line in lines:
        if joined and joined[-1].strip() and line[:1].isspace() and line.strip():
            joined[-1] = joined[-1].rstrip() + ' ' + line.strip()
        else:
            joined.append(line)
    return joined


def release_notes(version, path=CHANGELOG_PATH):
    """
    The body of the `## <version>` section of the CHANGELOG, as markdown.

    Yields nothing when the file is missing or names no such version, and
    never raises: a Settings panel that cannot say what changed is a smaller
    problem than a page that refuses to open because of it.
    """
    try:
        with open(path, encoding='utf-8') as handle:
            lines = handle.read().splitlines()
    except OSError:
        return ''

    heading = re.compile(_VERSION_HEADING.format(re.escape(version)))
    start = next((i for i, line in enumerate(lines) if heading.match(line)), None)
    if start is None:
        return ''
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].startswith('## ')), len(lines))
    return '\n'.join(_unwrap(lines[start + 1:end])).strip()


class SettingsError(Exception):
    """Raised when settings.toml is missing, malformed or inconsistent."""


@dataclass(frozen=True)
class Settings:
    title: str
    subtitle: str
    owner: str
    footer: str
    host: str
    port: int
    token: str
    vault_root: str
    projects_dir: str
    max_upload_bytes: int
    jira_base_url: str
    jira_placeholder: str
    confluence_placeholder: str
    figma_placeholder: str
    chart_min_end: date
    months: tuple
    month_abbr: tuple
    weekday_initials: tuple
    platforms: tuple
    roles: tuple           # ({'key','label','color','keywords'}, ...)
    fallback_role: dict
    squads: dict           # section -> ({'prefix','name','role'}, ...)

    @property
    def attachments_dir(self):
        """Attachments live next to the cards: <projects>/attachments/<project-id>/."""
        return os.path.join(self.projects_dir, 'attachments')

    def role(self, key):
        for entry in self.roles:
            if entry['key'] == key:
                return entry
        return self.fallback_role

    def css_variables(self):
        """Layout metrics shared with app.css / app.js."""
        return {
            '--col-w': f'{COL_W}px',
            '--label-w': f'{LABEL_W}px',
            '--label-w-min': f'{LABEL_W_MIN}px',
            '--label-w-max': f'{LABEL_W_MAX}px',
            '--row-h': f'{ROW_H}px',
            '--compact-row-h': f'{COMPACT_ROW_H}px',
            '--sub-row-h': f'{SUB_ROW_H}px',
        }


# ─── Colour helpers (single source of truth: RGB triples) ────────────────────
def hex_color(rgb):
    return '#%02x%02x%02x' % tuple(rgb)


# ─── Parsing ─────────────────────────────────────────────────────────────────
def _require(mapping, key, where):
    if key not in mapping:
        raise SettingsError(f'Missing `{key}` in [{where}].')
    return mapping[key]


def _resolve(path, root=BASE_DIR):
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(root, path))


def is_loopback(host):
    """True when a bind address can only be reached from this machine."""
    if host in ('localhost', ''):
        return host == 'localhost'
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _parse(raw, source):
    app = raw.get('app', {})
    server = raw.get('server', {})
    vault = raw.get('vault', {})
    links = raw.get('links', {})
    locale = raw.get('locale', {})
    defaults = raw.get('defaults', {})

    roles = tuple(
        {
            'key': _require(entry, 'key', 'roles'),
            'label': _require(entry, 'label', 'roles'),
            'color': _require(entry, 'color', 'roles'),
            'keywords': tuple(entry.get('keywords', ())),
        }
        for entry in raw.get('roles', [])
    )
    role_keys = {entry['key'] for entry in roles}

    squads = {}
    for squad in raw.get('squads', []):
        section = _require(squad, 'section', 'squads')
        members = []
        for member in squad.get('members', []):
            role_key = member.get('role')
            if role_key and role_key not in role_keys:
                raise SettingsError(
                    f'{source}: squad `{section}` references unknown role `{role_key}`.')
            members.append({
                'prefix': _require(member, 'prefix', f'squads.{section}'),
                'name': _require(member, 'name', f'squads.{section}'),
                'role': role_key,
            })
        # Longest prefix first: "iOS Dev #1" must win over a hypothetical "iOS".
        members.sort(key=lambda m: len(m['prefix']), reverse=True)
        squads[section] = tuple(members)

    months = tuple(locale.get('months', ()))
    month_abbr = tuple(locale.get('month_abbr', ()))
    if len(months) != 12 or len(month_abbr) != 12:
        raise SettingsError(f'{source}: [locale] months and month_abbr need 12 entries each.')
    weekday_initials = tuple(locale.get('weekday_initials',
                                        ('M', 'T', 'W', 'T', 'F', 'S', 'S')))
    if len(weekday_initials) != 7:
        raise SettingsError(f'{source}: [locale] weekday_initials needs 7 entries, '
                            f'Monday first.')

    min_end = raw.get('timeline', {}).get('min_end', date(date.today().year, 12, 31))
    if not isinstance(min_end, date):
        raise SettingsError(f'{source}: timeline.min_end must be a date (YYYY-MM-DD).')

    vault_root = _resolve(vault.get('root', '.knowledge'))

    return Settings(
        title=app.get('title', 'GanttBit'),
        subtitle=app.get('subtitle', ''),
        owner=app.get('owner', ''),
        footer=app.get('footer', ''),
        host=server.get('host', '127.0.0.1'),
        port=int(server.get('port', 8080)),
        token=str(server.get('token', '') or ''),
        max_upload_bytes=int(float(server.get('max_upload_mb', 25)) * 1024 * 1024),
        vault_root=vault_root,
        projects_dir=_resolve(vault.get('projects', '02-projects/active'), vault_root),
        jira_base_url=links.get('jira_base_url', ''),
        jira_placeholder=links.get('jira_placeholder', ''),
        confluence_placeholder=links.get('confluence_placeholder', ''),
        figma_placeholder=links.get('figma_placeholder', ''),
        chart_min_end=min_end,
        months=months,
        month_abbr=month_abbr,
        weekday_initials=weekday_initials,
        platforms=tuple(defaults.get('platforms', ())),
        roles=roles,
        fallback_role=dict(defaults.get('fallback_role', {'label': 'Member', 'color': '#78909c'})),
        squads=squads,
    )


def _read_toml(path):
    try:
        with open(path, 'rb') as handle:
            return tomllib.load(handle)
    except FileNotFoundError:
        raise SettingsError(f'Settings file not found: {path}')
    except tomllib.TOMLDecodeError as exc:
        raise SettingsError(f'{path}: invalid TOML: {exc}')


def _overlay(base, override):
    """
    Merge one settings mapping over another, table by table.

    Only tables merge. A list (the roles, the squads) is replaced
    whole: half of one roster grafted onto half of another is nobody's idea of
    an override.
    """
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _overlay(merged[key], value)
        else:
            merged[key] = value
    return merged


def load(path=None):
    """
    Read and validate the settings. Raises SettingsError, never guesses.

    With no path given, `settings.local.toml` is layered over `settings.toml`
    rather than replacing it, so a local file can carry the two lines that
    actually differ.
    """
    if path is not None:
        return _parse(_read_toml(path), os.path.basename(path))

    raw = _read_toml(DEFAULT_SETTINGS_PATH)
    source = os.path.basename(DEFAULT_SETTINGS_PATH)
    if os.path.isfile(LOCAL_SETTINGS_PATH):
        raw = _overlay(raw, _read_toml(LOCAL_SETTINGS_PATH))
        source = os.path.basename(LOCAL_SETTINGS_PATH)
    return _parse(raw, source)


def _rebase(path, old_root, new_root):
    """Move a vault path under a different vault root, keeping its shape."""
    try:
        relative = os.path.relpath(path, old_root)
    except ValueError:
        return path
    if relative.startswith(os.pardir):
        return path
    return os.path.normpath(os.path.join(new_root, relative))


_current = None


def configure(path=None, *, vault=None, projects_dir=None,
              host=None, port=None, token=None):
    """Load settings once, applying command-line overrides. Returns the value."""
    global _current
    settings = load(path)
    overrides = {}
    if vault:
        root = _resolve(vault, os.getcwd())
        overrides['vault_root'] = root
        overrides['projects_dir'] = _rebase(settings.projects_dir, settings.vault_root, root)
    if projects_dir:
        overrides['projects_dir'] = _resolve(projects_dir, os.getcwd())
    if host:
        overrides['host'] = host
    if port is not None:
        overrides['port'] = int(port)
    if token is not None:
        overrides['token'] = str(token)
    if overrides:
        settings = Settings(**{**settings.__dict__, **overrides})

    # Reachable from another machine and no shared secret: mint one rather than
    # serve an unauthenticated write API to whatever network this is on.
    if not is_loopback(settings.host) and not settings.token:
        settings = Settings(**{**settings.__dict__, 'token': secrets.token_urlsafe(16)})

    _current = settings
    return settings


def current():
    """Settings for this process; loads the default file on first use."""
    if _current is None:
        configure()
    return _current
