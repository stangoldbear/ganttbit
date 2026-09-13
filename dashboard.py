#!/usr/bin/env python3
"""
GanttBit: entry point and composition root.

    ./dashboard.py                      default settings.toml
    ./dashboard.py --port 8090
    ./dashboard.py --vault sample-vault --port 8090
    ./dashboard.py --migrate-vault              convert a pre-0.1.0 YAML vault
    ./dashboard.py --import-plan                move a delivery plan into the cards
    ./dashboard.py --drop-tiers                 flatten a vault that has tiers
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ganttbit import settings as settings_module
from ganttbit.migrate import (DEFAULT_PLAN, drop_tiers, import_plan, migrate_vault,
                           read_project_codes)
from ganttbit.repository import ProjectRepository
from ganttbit.server import run


def parse_args(argv):
    parser = argparse.ArgumentParser(description='GanttBit dashboard.')
    parser.add_argument('--settings', help='path to a settings TOML file')
    parser.add_argument('--vault', help='vault root holding the project cards')
    parser.add_argument('--projects', help='directory of project cards (overrides --vault)')
    parser.add_argument('--host', help='bind address (default: loopback)')
    parser.add_argument('--port', type=int, help='TCP port')
    parser.add_argument('--token', help='access token required when not on loopback '
                                        '(generated when omitted)')
    parser.add_argument('--migrate-vault', nargs='?', const=True, metavar='PATH',
                        help='convert YAML cards to the markdown format, in place, '
                             'leaving a .bak beside every file rewritten')
    parser.add_argument('--import-plan', nargs='?', const=True, metavar='PATH',
                        help='move the rows of a mermaid delivery plan into the cards '
                             'that own them; the plan file is left untouched')
    parser.add_argument('--drop-tiers', nargs='?', const=True, metavar='PATH',
                        help='flatten a vault that still has tiers: remove `tier` from every '
                             'card and renumber `priority` over the whole list; prints '
                             'what it would do unless --apply is given too')
    parser.add_argument('--apply', action='store_true',
                        help='let --drop-tiers write the cards instead of only listing them')
    return parser.parse_args(argv[1:])


def main(argv):
    args = parse_args(argv)

    try:
        config = settings_module.configure(
            args.settings, vault=args.vault, projects_dir=args.projects,
            host=args.host, port=args.port, token=args.token)
    except settings_module.SettingsError as exc:
        print(f'Settings error: {exc}', file=sys.stderr)
        return 2

    if args.import_plan:
        plan = (os.path.join(config.vault_root, DEFAULT_PLAN)
                if args.import_plan is True else args.import_plan)
        return import_the_plan(config, plan, args.settings or 'settings.toml')

    if args.migrate_vault:
        directory = (config.projects_dir if args.migrate_vault is True
                     else args.migrate_vault)
        return migrate(directory)

    if args.drop_tiers:
        directory = (config.projects_dir if args.drop_tiers is True else args.drop_tiers)
        return drop_the_tiers(directory, args.settings or 'settings.toml', args.apply)

    run(config)
    return 0


def import_the_plan(config, plan_path, settings_path):
    """Read a delivery plan once and hand every row to the card that owns it."""
    codes = read_project_codes(settings_path)
    if not codes:
        print(f'No [project_codes] table in {settings_path}: a plan row names its '
              f'project through a short code, so there is nothing to map.', file=sys.stderr)
        return 2

    try:
        summary = import_plan(ProjectRepository(settings=config), plan_path, codes)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    for project_id, count in sorted(summary['imported'].items()):
        print(f'imported {count:>3} rows into {project_id}')
    for label, reason in summary['skipped']:
        print(f'skipped      {label}  ({reason})')

    total = sum(summary['imported'].values())
    print(f"\n{total} rows imported into {len(summary['imported'])} cards, "
          f"{len(summary['skipped'])} skipped. {plan_path} is left untouched.")
    return 0


def drop_the_tiers(directory, settings_path, apply):
    """Renumber a tiered vault, listing every card it touches before it does."""
    if not os.path.isdir(directory):
        print(f'Not a directory: {directory}', file=sys.stderr)
        return 2

    summary = drop_tiers(directory, settings_path, apply=apply)
    for entry in summary['changed']:
        tier = entry['tier'] or '—'
        print(f"{entry['file']:<44}  {tier:<8}  priority {entry['from'] or '—':>3} → {entry['to']}")

    if not summary['changed']:
        print(f"{summary['total']} cards, nothing to change: no tier is left and the "
              f"priorities are already a sequence.")
        return 0

    print(f"\n{len(summary['changed'])} of {summary['total']} cards", end=' ')
    if apply:
        print('rewritten. There is no backup: check `git diff`, or your own copy.')
    else:
        print('would change. Nothing was written; add --apply to do it.')
    return 0


def migrate(directory):
    """Convert a vault of YAML cards and report what happened to each file."""
    if not os.path.isdir(directory):
        print(f'Not a directory: {directory}', file=sys.stderr)
        return 2

    summary = migrate_vault(directory)
    for name in summary['converted']:
        print(f'converted  {name}  (backup: {name}.bak)')
    for name in summary['skipped']:
        print(f'skipped    {name}  (already a markdown card)')
    for name, reason in summary['failed']:
        print(f'FAILED     {name}  {reason}', file=sys.stderr)

    print(f"\n{len(summary['converted'])} converted, {len(summary['skipped'])} skipped, "
          f"{len(summary['failed'])} failed, in {directory}")
    return 1 if summary['failed'] else 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
