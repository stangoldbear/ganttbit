"""
The terminal side of starting up.

Two things happen before the server listens, and neither is HTTP: the
heading that says which GanttBit this is, and what to do when the port is
already taken. A second copy started on a busy port used to end in a
traceback and a hunt for the process to stop. Now the thing on the port is
named, and when it is another GanttBit and the person at the terminal says
so, it is stopped and this one takes its place.

Nothing here writes to disk, and the only process ever signalled is one that
answered as GanttBit and was named by the system as holding the port. Every
other outcome leaves the machine exactly as it was found.
"""

import errno
import http.client
import os
import re
import signal
import subprocess
import sys
import time

from . import __version__, settings as settings_module

# The bind error for a taken port, on both families of operating system.
_ADDRESS_IN_USE = frozenset({errno.EADDRINUSE,
                             getattr(errno, 'WSAEADDRINUSE', errno.EADDRINUSE)})
_SERVER_HEADER = re.compile(r'^GanttBit/(\S+)')
_RELEASE_TIMEOUT = 5.0      # seconds a stopped instance gets to let go of the port
_YES = frozenset({'y', 'yes'})


# ─── Which GanttBit this is ──────────────────────────────────────────────────
def build_id(root=settings_module.BASE_DIR):
    """
    The commit the tree is checked out at, abbreviated; '' when there is none.

    There is no build step, so the commit is the one thing that tells two
    copies of the same version apart. It is asked of git only when a `.git`
    is there to ask about: a zip download has none, and on a Mac without the
    developer tools the first call to `git` opens a dialog box.
    """
    if not os.path.exists(os.path.join(root, '.git')):
        return ''
    try:
        result = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=root,
                                capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ''
    return result.stdout.strip() if result.returncode == 0 else ''


def banner(version=__version__, build=None):
    """The heading printed first: the version, and the build when there is one."""
    build = build_id() if build is None else build
    line = f'GanttBit {version}' + (f' · build {build}' if build else '')
    return f'{line}\n{"─" * len(line)}'


# ─── The one already on the port ─────────────────────────────────────────────
def reachable_host(host):
    """The address a client on this machine opens: a wildcard bind is reached through loopback."""
    return '127.0.0.1' if host in ('', '0.0.0.0') else host


def running_version(host, port, timeout=2.0):
    """
    The version of the GanttBit answering at host:port, or None.

    Every answer the server gives names itself in the Server header, the
    refusal for a missing access token included, so no token is needed to
    ask. Anything else on the port, and nothing on it, is None.
    """
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        connection.request('GET', '/api/health')
        header = connection.getresponse().getheader('Server', '')
    except (OSError, http.client.HTTPException):
        return None
    finally:
        connection.close()
    match = _SERVER_HEADER.match(header)
    return match.group(1) if match else None


def listener_pids(port):
    """
    The processes listening on a TCP port, as lsof reports them.

    lsof ships with macOS and with every Linux desktop. Where it is missing
    the list is empty and the caller says so rather than guess; a port held
    by another user's process looks the same.
    """
    try:
        result = subprocess.run(
            ['lsof', '-nP', f'-iTCP:{port}', '-sTCP:LISTEN', '-t'],
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return []
    return sorted({int(line) for line in result.stdout.split() if line.isdigit()})


def stop(pid):
    """Tell a process to terminate. The caller has already named it as GanttBit."""
    os.kill(pid, signal.SIGTERM)


def confirm(question):
    """Ask at the terminal. Anything but a yes is a no, and so is having no terminal."""
    try:
        interactive = sys.stdin is not None and sys.stdin.isatty()
    except ValueError:              # stdin closed
        interactive = False
    if not interactive:
        return False
    try:
        return input(question).strip().lower() in _YES
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def bind(create, host, port, ask=confirm):
    """
    Create the server, taking the port over from another GanttBit when told to.

    `create` binds and returns the server. It is called once, and once more
    after the other instance has been stopped. None means nothing was
    started: the port is held by something that is not GanttBit, or by a
    process that could not be named or stopped, or the answer was no. On
    every None nothing on the machine has been touched.
    """
    try:
        return create()
    except OSError as exc:
        if exc.errno not in _ADDRESS_IN_USE:
            raise

    where = f'http://{reachable_host(host)}:{port}'
    version = running_version(reachable_host(host), port)
    if version is None:
        _refuse(f'Port {port} is taken by something that is not GanttBit.')
        return None

    pids = listener_pids(port)
    if len(pids) != 1:
        held = (f'the port is held by more than one process (pids {", ".join(map(str, pids))})'
                if pids else 'which process holds the port could not be told: lsof is '
                             'missing, or the process belongs to another user')
        _refuse(f'GanttBit {version} is already listening on {where}, and {held}.')
        return None
    pid = pids[0]

    print(f'GanttBit {version} is already listening on {where} (pid {pid}).', flush=True)
    if not ask('Stop it and start this one in its place? [y/N] '):
        _refuse('Left running.')
        return None
    try:
        stop(pid)
    except ProcessLookupError:
        pass                        # gone in the meantime, which is what was asked for
    except OSError as exc:
        _refuse(f'Could not stop pid {pid}: {exc.strerror or exc}.')
        return None

    httpd = _bind_once_released(create)
    if httpd is None:
        sys.stdout.flush()
        print(f'pid {pid} was told to stop, and the port is still taken '
              f'{_RELEASE_TIMEOUT:g} s later. Nothing was started.', file=sys.stderr)
        return None
    print(f'Stopped GanttBit {version} (pid {pid}).', flush=True)
    return httpd


def _bind_once_released(create):
    """Bind again, for as long as the stopped process may still hold the port."""
    deadline = time.monotonic() + _RELEASE_TIMEOUT
    while True:
        try:
            return create()
        except OSError as exc:
            if exc.errno not in _ADDRESS_IN_USE:
                raise
            if time.monotonic() >= deadline:
                return None
        time.sleep(0.1)


def _refuse(reason):
    """Why nothing was started, and the two ways forward."""
    sys.stdout.flush()
    print(f'{reason} Nothing was changed: stop it yourself, or pick another port '
          f'with --port.', file=sys.stderr)
