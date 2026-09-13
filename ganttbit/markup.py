"""
HTML primitives shared by the view modules.

Rule for every renderer: user data reaches the browser only through escaped
text or escaped `data-*` attributes, never inside executable code.
"""

import html
import re


def esc(value):
    """Escape for both text content and attribute values."""
    return html.escape('' if value is None else str(value), quote=True)


def ensure_list(value):
    """
    Wrap a value in a list for rendering, without ever splitting a string.

    The API boundary uses `repository.csv_to_list`, which does split: keep the
    two apart, a rendered value must survive commas untouched.
    """
    if not value:
        return []
    return [value] if isinstance(value, str) else list(value)


def attrs(**data):
    """Render `data-*` attributes from keyword arguments (underscores become dashes)."""
    return ''.join(f' data-{key.replace("_", "-")}="{esc(value)}"'
                   for key, value in data.items() if value is not None)


def select(select_id, options, current, param, css_class='form-input'):
    """A `<select>` whose current value is always representable.

    An out-of-vocabulary stored value is shown as a disabled option instead of
    silently displaying the first choice, because otherwise the next save would
    overwrite the real value with something the user never picked.
    """
    values = [value for value, _ in options]
    choices = ''
    if current and current not in values:
        choices += (f'<option value="{esc(current)}" selected disabled>'
                    f'{esc(current)} (invalid)</option>')
    choices += ''.join(
        f'<option value="{esc(value)}"{" selected" if value == current else ""}>'
        f'{esc(label)}</option>'
        for value, label in options
    )
    return (f'<select id="{esc(select_id)}" class="{css_class}" '
            f'data-param="{esc(param)}" data-value="{esc(current)}">{choices}</select>')


def safe_url(value):
    """Return the URL only when it uses a scheme a link may safely open."""
    text = str(value or '').strip()
    lowered = text.lower()
    if lowered.startswith(('http://', 'https://')):
        return text
    if text and '://' not in text and not lowered.startswith(('javascript:', 'data:', 'vbscript:')):
        return text          # relative path or bare ticket key resolved by a base URL
    return ''


def human_size(size):
    """1.2 MB style, for attachment rows."""
    value = float(size or 0)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if value < 1024 or unit == 'GB':
            return f'{int(value)} {unit}' if unit == 'B' else f'{value:.1f} {unit}'
        value /= 1024


# ─── Icons ───────────────────────────────────────────────────────────────────
# Monochrome inline SVG, drawn at currentColor so a glyph inherits the text
# colour and the theme. Emoji are bitmaps: they render differently on every
# platform and outweigh 11px type wherever they land.
_ICON_PATHS = {
    'diamond': '<path d="M8 1.2 14.8 8 8 14.8 1.2 8Z"/>',
    'grip': '<path d="M6 4h.01M6 8h.01M6 12h.01M10 4h.01M10 8h.01M10 12h.01"/>',
    'panel': '<rect x="2" y="3" width="12" height="10" rx="1.5"/><path d="M9.5 3v10"/>',
    'sliders': '<path d="M3 5h5M11 5h2M3 11h2M8 11h5"/><circle cx="9.5" cy="5" r="1.6"/>'
               '<circle cx="6.5" cy="11" r="1.6"/>',
    'link': '<path d="M9.5 3H13v3.5M12.8 3.2 7.5 8.5"/><path d="M11 9.5V13H3V5h3.5"/>',
    'plus': '<path d="M8 3.5v9M3.5 8h9"/>',
    'clip': '<path d="M11.6 6.4 7 11a2.5 2.5 0 0 1-3.5-3.5l5.2-5.2a1.7 1.7 0 0 1 2.4 2.4l-5.2 5.2'
            'a.9.9 0 0 1-1.2-1.2l4.6-4.6"/>',
    # Open, and rotated 90° by CSS when it is closed. It used to be the text
    # glyphs ▲ and ►, which iOS renders from a fallback font with metrics of
    # its own: they arrived on the phone stretched flat.
    'caret': '<path d="M4 10.5 8 6.5l4 4"/>',
    # Three depths, one glyph each: how far down the chart is unfolded.
    'level-compact': '<path d="M2.5 8h11"/>',
    'level-projects': '<path d="M2.5 5.5h11M6 10.5h7.5"/>',
    'level-people': '<path d="M2.5 3.5h11M6 8h7.5M9.5 12.5h4"/>',
    'level-details': '<path d="M2.5 2.5h11M5.5 6h8M8.5 9.5h5M11 13h2.5"/>',
    'warning': '<path d="M8 2.6 14.5 13.4h-13Z"/><path d="M8 6.6v3.2M8 11.6h.01"/>',
    'calendar': '<rect x="2.5" y="3.5" width="11" height="10" rx="1.5"/>'
                '<path d="M2.5 6.5h11M5.5 2v3M10.5 2v3"/>',
    'pencil': '<path d="M11.4 2.6 13.4 4.6 5.4 12.6 2.5 13.5 3.4 10.6Z"/>'
              '<path d="M9.6 4.4 11.6 6.4"/>',
}


def icon(name, extra_class=''):
    """One inline SVG glyph. Unknown names fail loudly rather than silently."""
    path = _ICON_PATHS[name]
    classes = f'icon icon--{name}' + (f' {extra_class}' if extra_class else '')
    return (f'<svg class="{classes}" viewBox="0 0 16 16" aria-hidden="true" '
            f'focusable="false">{path}</svg>')


# ─── Minimal markdown ────────────────────────────────────────────────────────
# Free text typed into a card, an intro or a note, is markdown, and this is the
# subset that earns its place: headings, lists, bold, italic, code and links.
#
# ORDER MATTERS AND IS THE SAFETY PROPERTY: the text is escaped first and only
# then transformed, so nothing a person types can become markup. Code spans are
# pulled out before the inline rules run, so a `*` inside them stays a `*`.
_CODE_RE = re.compile(r'`([^`]+)`')
_BOLD_RE = re.compile(r'\*\*(\S(?:.*?\S)?)\*\*')
_ITALIC_RE = re.compile(r'(?<![\w*])[*_](\S(?:.*?\S)?)[*_](?![\w*])')
_LINK_RE = re.compile(r'\[([^\]]+)\]\(([^)\s]+)\)')
_BARE_URL_RE = re.compile(r'(?<![\"\'=>])\bhttps?://[^\s<]+[^\s<.,;:!?)\]]')
_HEADING_RE = re.compile(r'^(#{1,6})\s+(.*)$')
_BULLET_RE = re.compile(r'^[-*]\s+(.*)$')
_NUMBER_RE = re.compile(r'^\d+[.)]\s+(.*)$')


def _anchor(href, label):
    target = safe_url(href)
    if not target:
        return label
    return (f'<a href="{esc(target)}" target="_blank" rel="noopener noreferrer">'
            f'{label}</a>')


def _inline(text):
    """Inline rules over already-escaped text."""
    codes = []

    def stash(match):
        codes.append(match.group(1))
        return f'\x00{len(codes) - 1}\x00'

    text = _CODE_RE.sub(stash, text)
    text = _LINK_RE.sub(lambda m: _anchor(m.group(2), m.group(1)), text)
    text = _BARE_URL_RE.sub(lambda m: _anchor(m.group(0), m.group(0)), text)
    text = _BOLD_RE.sub(r'<strong>\1</strong>', text)
    text = _ITALIC_RE.sub(r'<em>\1</em>', text)

    for index, code in enumerate(codes):
        text = text.replace(f'\x00{index}\x00', f'<code>{code}</code>')
    return text


def render_markdown(value):
    """Render the free-text subset. Returns HTML; the input is escaped first."""
    text = esc('' if value is None else str(value))
    if not text.strip():
        return ''

    html, paragraph, list_tag, items = [], [], None, []

    def flush_paragraph():
        if paragraph:
            html.append('<p>' + '<br>'.join(_inline(line) for line in paragraph) + '</p>')
            paragraph.clear()

    def flush_list():
        nonlocal list_tag
        if items:
            body = ''.join(f'<li>{_inline(item)}</li>' for item in items)
            html.append(f'<{list_tag}>{body}</{list_tag}>')
            items.clear()
        list_tag = None

    for raw in text.split('\n'):
        line = raw.rstrip()
        if not line.strip():
            flush_paragraph()
            flush_list()
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            flush_paragraph()
            flush_list()
            level = min(6, 3 + len(heading.group(1)))     # a card is not a page
            html.append(f'<h{level}>{_inline(heading.group(2))}</h{level}>')
            continue

        bullet = _BULLET_RE.match(line)
        numbered = _NUMBER_RE.match(line)
        if bullet or numbered:
            flush_paragraph()
            wanted = 'ul' if bullet else 'ol'
            if list_tag and list_tag != wanted:
                flush_list()
            list_tag = wanted
            items.append((bullet or numbered).group(1))
            continue

        flush_list()
        paragraph.append(line)

    flush_paragraph()
    flush_list()
    return ''.join(html)
