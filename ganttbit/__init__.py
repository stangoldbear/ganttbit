"""
GanttBit: application package.

Layers, each with one reason to change:

    settings     deployment configuration (settings.toml) + presentation constants
    cardmd       the markdown card format ⇄ Python data
    migrate      one-way conversion of a pre-0.1.0 YAML vault
    repository   the knowledge vault on disk (the only I/O)
    domain       dates, the priority ramp, roles, gantt parsing, calendar (pure)
    schema       the project card schema, declared once
    markup       HTML escaping primitives
    gantt        chart rendering
    view         page and detail panel rendering
    api          mutations, exposed through a routing table
    server       HTTP, static assets, JSON
    static/      app.css, themes.css, app.js and theme.js, real files that
                 Python never generates
"""

__version__ = '1.4.0'
