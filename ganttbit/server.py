"""
HTTP layer: routing, static assets, JSON serialisation.

No domain logic and no markup here: it only wires repository, domain and
view together.
"""

import hmac
import json
import mimetypes
import os
import re
import sys
from datetime import datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import quote, unquote, urlencode

from . import __version__, schema, settings as settings_module, startup, view
from .domain import declared_span, latest_estimate
from .api import ApiError, delete_attachment, dispatch, upload_attachment
from .repository import ProjectRepository

_API_PATH_RE = re.compile(r'^/api/project/([^/]+)/(.+)$')
_ATTACHMENT_PATH_RE = re.compile(r'^/api/project/([^/]+)/attachments/([^/]+)$')
_MAX_JSON_BYTES = 1 << 20  # 1 MB: a card never comes close
_MAX_DRAIN_BYTES = 256 << 20  # how much of an oversized upload we read before giving up
_TOKEN_PARAM = 'k'
_TOKEN_COOKIE = 'dah_token'

mimetypes.add_type('text/markdown', '.md')
mimetypes.add_type('application/manifest+json', '.webmanifest')

# Text that does not say so in its type. Everything else under static/ is bytes.
_TEXT_TYPES = frozenset({
    'application/javascript', 'text/javascript', 'application/json',
    'application/manifest+json', 'image/svg+xml',
})

# The page carries one inline <style> block with the layout custom properties;
# everything else is same-origin, so no external request ever leaves the host.
_SECURITY_HEADERS = {
    'Content-Security-Policy': (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'"),
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
}


_TOKEN_PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Access token required</title><link rel="stylesheet" href="/static/app.css">
</head><body><div class="container"><div class="dialog" style="margin:12vh auto">
<h3 class="dialog__title">Access token required</h3>
<p class="dialog__body">This dashboard is reachable from the network, so every request
carries a shared secret. Open the link it was started with, or paste the token
here. It is stored as a cookie, good for a week after your last visit.</p>
<form class="dialog__fields" method="get" action="/">
  <label class="dialog__field"><span class="field-label">Token</span>
  <input class="form-input" type="password" name="k" autocomplete="current-password"
   autofocus></label>
  <div class="dialog__actions"><button class="btn btn--default btn--sm" type="submit">
  Open</button></div>
</form></div></div></body></html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = f'GanttBit/{__version__}'
    repository = None            # injected by create_server
    _renew_cookie = False        # this request came in on the cookie: reset its week

    # ─── Access control ──────────────────────────────────────────────────────
    # Only when the server is reachable from another machine: on loopback the
    # settings carry no token and every check below is a no-op.
    def _token_cookie(self, token):
        """The access cookie, good for a week from the moment it is sent."""
        # Lax, not Strict: the link is opened from somewhere else, a chat,
        # a mail or a note, and Strict withholds the cookie on a navigation
        # that started off-site, which is the only way this link is ever
        # used. Lax still refuses to travel with a cross-site POST/PUT/
        # DELETE, and every mutation here is one of those.
        flags = 'Path=/; HttpOnly; SameSite=Lax; Max-Age=604800'
        if self.headers.get('X-Forwarded-Proto', '').lower() == 'https':
            flags += '; Secure'
        return f'{_TOKEN_COOKIE}={quote(token)}; {flags}'

    def _authorised(self):
        self._renew_cookie = False
        token = self.repository.settings.token
        if not token:
            return True

        path, query = self._split_path()
        supplied = query.get(_TOKEN_PARAM)
        if supplied is not None and hmac.compare_digest(supplied, token):
            # Hand the browser a cookie and bounce to the clean URL, so the
            # secret stops travelling in links, titles and the address bar.
            rest = {k: v for k, v in query.items() if k != _TOKEN_PARAM}
            target = path + ('?' + urlencode(rest) if rest else '')
            self._respond(302, b'', 'text/plain; charset=utf-8', extra_headers={
                'Location': target,
                'Set-Cookie': self._token_cookie(token),
            })
            return False

        cookie = SimpleCookie(self.headers.get('Cookie', ''))
        morsel = cookie.get(_TOKEN_COOKIE)
        if morsel is not None and hmac.compare_digest(unquote(morsel.value), token):
            # Sent again on the way out, so the week runs from the last visit
            # rather than from the link. An installed app opens in a window
            # with no address bar: a cookie that expires on a fixed day expires
            # in front of somebody who has been using it daily.
            self._renew_cookie = True
            return True

        self._refuse()
        return False

    def _refuse(self):
        if self.path.startswith('/api/'):
            return self._send_json(
                {'success': False, 'error': 'Access token required.'}, 401)
        # An installed app has no address bar to paste a new link into, so the
        # refusal carries the field itself.
        self._respond(401, _TOKEN_PAGE.encode('utf-8'), 'text/html; charset=utf-8')

    # ─── GET ─────────────────────────────────────────────────────────────────
    def do_GET(self):
        if not self._authorised():
            return
        path, query = self._split_path()

        if path == '/':
            # The chart opens on today unless the URL says otherwise: without a
            # parameter every visit landed months in the past and needed a click.
            return self._send_html(
                self._render_dashboard(query.get('from', ''), query.get('zoom', '')))
        if path == '/hierarchy':
            return self._send_html(self._render_hierarchy())
        if path == '/api/vault/markdown':
            return self._send_snapshot()
        if path == '/api/health':
            return self._send_json({'success': True, 'status': 'ok'})
        if path == '/api/schema':
            # The vault travels with the declaration: an open vocabulary is
            # completed with the values the cards already use.
            return self._send_json({'success': True, **schema.as_json(
                self.repository.settings, self.repository.list_all())})

        raw_match = re.match(r'^/api/project/([^/]+)/raw$', path)
        if raw_match:
            return self._send_project_raw(raw_match.group(1))
        attachment = _ATTACHMENT_PATH_RE.match(path)
        if attachment:
            return self._send_attachment(attachment.group(1), unquote(attachment.group(2)))
        if path.startswith('/static/'):
            return self._send_static(path[len('/static/'):])

        self._send_error_page(404, 'Not found')

    # ─── POST / PUT / DELETE ─────────────────────────────────────────────────
    def do_POST(self):
        if not self._authorised():
            return
        path, _ = self._split_path()
        match = _API_PATH_RE.match(path)
        if not match:
            return self._send_json({'success': False, 'error': 'Unknown endpoint'}, 404)
        project_id, action = match.group(1), match.group(2).strip('/')
        self._answer(lambda: dispatch(self.repository, project_id, action,
                                      self._read_json_body()))

    def do_PUT(self):
        """Upload an attachment: the request body is the file, no multipart."""
        if not self._authorised():
            return
        project_id, name = self._attachment_target()
        if project_id is None:
            return
        self._answer(lambda: upload_attachment(
            self.repository, project_id, name,
            self._read_body(self.repository.settings.max_upload_bytes)))

    def do_DELETE(self):
        if not self._authorised():
            return
        project_id, name = self._attachment_target()
        if project_id is None:
            return
        self._answer(lambda: delete_attachment(self.repository, project_id, name))

    def _attachment_target(self):
        path, _ = self._split_path()
        match = _ATTACHMENT_PATH_RE.match(path)
        if not match:
            self._send_json({'success': False, 'error': 'Unknown endpoint'}, 404)
            return None, None
        return match.group(1), unquote(match.group(2))

    def _answer(self, action):
        """Run an API action and turn its outcome into a JSON response."""
        try:
            payload = action()
        except ApiError as exc:
            return self._send_json({'success': False, 'error': str(exc)}, exc.status)
        except Exception as exc:                      # noqa: BLE001 - API surface
            self.log_error('Internal error on %s: %s', self.path, exc)
            return self._send_json({'success': False, 'error': 'Internal server error'}, 500)
        self._send_json(payload)

    # ─── Response building ───────────────────────────────────────────────────
    def _split_path(self):
        path, _, raw_query = self.path.partition('?')
        query = {}
        for pair in raw_query.split('&'):
            if '=' in pair:
                key, _, value = pair.partition('=')
                query[unquote(key)] = unquote(value)
        return unquote(path), query

    def _render_dashboard(self, window, zoom):
        return view.render_page(self.repository.list_all(), window=window, zoom=zoom)

    def _render_hierarchy(self):
        return view.render_hierarchy_page(self.repository.list_all(),
                                          self.repository.vault_markdown())

    def _send_snapshot(self):
        """The whole vault as one markdown file, named for the month."""
        stamp = datetime.now().strftime('%Y-%m')
        body = self.repository.vault_markdown().encode('utf-8')
        self._respond(200, body, 'text/markdown; charset=utf-8', extra_headers={
            'Content-Disposition': f'attachment; filename="vault-{stamp}.md"',
        })

    def _send_project_raw(self, project_id):
        data, body = self.repository.load(project_id)
        if data is None:
            return self._send_json({'success': False, 'error': 'Project not found'}, 404)
        # Two answers the simple form asks for are not plain values in the card,
        # so they are resolved here rather than guessed at in the browser: a bar
        # may be written as a start and a count of working days, and the
        # estimate in force is the last of a list.
        span = declared_span(data)
        return self._send_json({
            'success': True,
            'data': data,
            'body': body,
            'span': {'start': span[0].strftime('%Y-%m-%d'),
                     'end': span[1].strftime('%Y-%m-%d')} if span else None,
            'estimate': latest_estimate(data),
            'raw_text': self.repository.read_raw(project_id),
        })

    def _read_body(self, max_bytes):
        try:
            length = int(self.headers.get('Content-Length', 0))
        except (TypeError, ValueError):
            raise ApiError('Invalid Content-Length header.')
        if length <= 0:
            return b''
        if length > max_bytes:
            # Answering before the client has finished sending makes it see a
            # connection reset instead of this message. Drain what it sends,
            # within reason, so the 413 actually arrives.
            self._drain(min(length, _MAX_DRAIN_BYTES))
            self.close_connection = True
            raise ApiError(f'Payload too large (limit {max_bytes // (1024 * 1024)} MB).',
                           status=413)
        # The whole body sits in memory; stream it to the temp file instead if
        # the upload cap ever grows past what a laptop shrugs at.
        return self.rfile.read(length)

    def _drain(self, count):
        while count > 0:
            chunk = self.rfile.read(min(count, 1 << 16))
            if not chunk:
                break
            count -= len(chunk)

    def _read_json_body(self):
        raw = self._read_body(_MAX_JSON_BYTES)
        if not raw:
            return {}
        try:
            return json.loads(raw.decode('utf-8')) or {}
        except (ValueError, UnicodeDecodeError):
            raise ApiError('Request body is not valid JSON.')

    def _send_attachment(self, project_id, name):
        try:
            path = self.repository.attachment_path(project_id, name)
        except ValueError:
            return self._send_error_page(404, 'Attachment not found')
        if not os.path.isfile(path):
            return self._send_error_page(404, 'Attachment not found')

        content_type = mimetypes.guess_type(path)[0] or 'application/octet-stream'
        if content_type.startswith('text/'):
            content_type += '; charset=utf-8'
        # Only known-inert types render in the tab; everything else downloads,
        # so an uploaded HTML or SVG file can never run script on this origin.
        disposition = ('inline' if content_type.split(';')[0]
                       in settings_module.INLINE_ATTACHMENT_TYPES else 'attachment')
        ascii_name = name.encode('ascii', 'replace').decode('ascii').replace('"', '_')
        with open(path, 'rb') as handle:
            body = handle.read()
        self._respond(200, body, content_type, extra_headers={
            'Content-Disposition':
                f'{disposition}; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(name)}',
            'Cache-Control': 'no-cache',
        })

    def _send_static(self, relative_path):
        static_dir = settings_module.STATIC_DIR
        target = os.path.normpath(os.path.join(static_dir, relative_path))
        # Refuse anything that escapes static/.
        if not target.startswith(static_dir + os.sep) or not os.path.isfile(target):
            return self._send_error_page(404, 'Asset not found')

        content_type = mimetypes.guess_type(target)[0] or 'application/octet-stream'
        # An encoding belongs to text: declaring one on a PNG says the file is
        # something it is not.
        if content_type.startswith('text/') or content_type in _TEXT_TYPES:
            content_type += '; charset=utf-8'
        with open(target, 'rb') as handle:
            body = handle.read()

        headers = {'Cache-Control': 'no-cache'}
        # A worker served from /static/ may only control /static/ unless the
        # response says otherwise, and the shell it caches is the whole site.
        if relative_path == 'sw.js':
            headers['Service-Worker-Allowed'] = '/'
        self._respond(200, body, content_type, extra_headers=headers)

    def _send_html(self, markup):
        self._respond(200, markup.encode('utf-8'), 'text/html; charset=utf-8')

    def _send_json(self, payload, status=200):
        self._respond(status, json.dumps(payload).encode('utf-8'),
                      'application/json; charset=utf-8')

    def _send_error_page(self, status, message):
        body = f'<!DOCTYPE html><meta charset="utf-8"><h1>{status}</h1><p>{message}</p>'
        self._respond(status, body.encode('utf-8'), 'text/html; charset=utf-8')

    def _respond(self, status, body, content_type, extra_headers=None):
        headers = {**_SECURITY_HEADERS, **(extra_headers or {})}
        if self._renew_cookie and 'Set-Cookie' not in headers:
            headers['Set-Cookie'] = self._token_cookie(self.repository.settings.token)
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        """Silence the access log; errors still go to stderr."""


def create_server(settings=None, repository=None):
    config = settings or settings_module.current()
    handler = type('BoundDashboardHandler', (DashboardHandler,),
                   {'repository': repository or ProjectRepository(settings=config)})
    return HTTPServer((config.host, config.port), handler)


def _report_empty_vault(config):
    """
    Say what to do, not just what is missing.

    A fresh clone has no vault: this is the first thing a new user sees, and
    "warning: directory absent" leaves them with an empty page and no next step.
    """
    if os.path.isdir(config.projects_dir) and any(
            name.endswith('.md') for name in os.listdir(config.projects_dir)):
        return

    demo = os.path.join(settings_module.BASE_DIR, 'sample-vault')
    print(f'\nNo project cards in {config.projects_dir}: the dashboard will be empty.')
    print('  Point it at your own vault:   dashboard.py --vault PATH')
    if os.path.isdir(demo):
        print('  Or take the demo for a spin:  dashboard.py --vault sample-vault')
    print()


def run(settings=None):
    """
    Serve until interrupted.

    Returns the exit status: 0 after a clean stop, 1 when nothing was started
    because the port is taken and was left that way.
    """
    config = settings or settings_module.current()
    print(startup.banner(), flush=True)
    httpd = startup.bind(lambda: create_server(config), config.host, config.port)
    if httpd is None:
        return 1
    host, port = httpd.server_address[0], httpd.server_address[1]
    shown = startup.reachable_host(host)
    if config.token:
        print(f'{config.title} listening on http://{shown}:{port}'
              f'?{_TOKEN_PARAM}={config.token}')
        print('Reachable from other machines: that link carries the access token.')
    else:
        print(f'{config.title} listening on http://{shown}:{port}')
    _report_empty_vault(config)
    # Everything said so far reaches a log file before the server goes quiet.
    sys.stdout.flush()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down.')
    finally:
        httpd.server_close()
    return 0
