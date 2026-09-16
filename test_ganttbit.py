#!/usr/bin/env python3
"""
GanttBit: test suite (stdlib unittest, no dependencies).

    python3 -m unittest test_ganttbit -v      or      ./test_ganttbit.py

The sample vault doubles as the fixture: every case the renderer and the API
have to survive is a real card in `sample-vault/`.
"""

import contextlib
import io
import json
import os
import re
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

from ganttbit import (__version__, gantt, markup, schema,
                      settings as settings_module, view)
from ganttbit.api import ApiError, delete_attachment, dispatch, upload_attachment
from ganttbit.domain import (
    Timeline, band_position, chart_spans, display_group, format_date_long,
    format_relative, group_by_display, project_milestones, project_span,
    project_tasks, resolve_person, resolve_range,
)
from ganttbit.cardmd import build_card, parse_card
from ganttbit.migrate import (
    convert, drop_tiers, import_plan, migrate_vault, parse_plan, read_tier_order,
)
from ganttbit.repository import (
    ProjectRepository, csv_to_list, split_cards, write_atomic,
)
from ganttbit import server as server_module
from ganttbit.server import _TOKEN_COOKIE, create_server

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
SAMPLE_VAULT = os.path.join(REPO_ROOT, 'sample-vault')
TODAY = date(2026, 9, 9)
NOW = datetime(2026, 9, 9, 10, 30)


def sample_settings():
    return settings_module.configure(vault=SAMPLE_VAULT)


class CardFormatTest(unittest.TestCase):
    """The card is the storage: what a person types has to survive a save."""

    def test_round_trip_preserves_structure(self):
        data = {
            'name': "Designer's name & \"brand\"",
            'id': 'p1',
            'tech_footprint': {'platforms': ['iOS', 'Backend (dev)'], 'content_impact': True},
            'risks_and_criticalities': [
                {'id': 'RISK-01', 'description': 'Depends on: team X', 'severity': 'high'}],
            'confluence': ['https://x.test/a', 'https://x.test/b'],
        }
        text = build_card(data, 'the body')
        back, body = parse_card(text)
        self.assertEqual(back, data)
        # `## Notes` belongs to the format, not to the text under it.
        self.assertIn('## Notes\n\nthe body', text)
        self.assertEqual(body, 'the body')

    def test_the_title_is_the_project_name(self):
        data, _ = parse_card('# Navigation menu — second level\n- id: p1\n')
        self.assertEqual(data['name'], 'Navigation menu — second level')
        self.assertTrue(build_card(data).startswith('# Navigation menu — second level\n'))

    def test_a_url_is_a_value_and_never_a_key(self):
        """`- https://x` used to read as a key named `https`."""
        data, _ = parse_card('# T\n- confluence\n  - https://x.test/p#frag\n')
        self.assertEqual(data['confluence'], ['https://x.test/p#frag'])
        data, _ = parse_card('# T\n- note: Menu API: v2 is late\n')
        self.assertEqual(data['note'], 'Menu API: v2 is late')

    def test_multi_line_values_are_fenced_and_nest(self):
        card = {'name': 'T', 'intro': 'one\ntwo "quoted"\n\nfour'}
        text = build_card(card)
        self.assertIn('- intro:\n  ```md', text)
        self.assertEqual(parse_card(text)[0], card)

        nested = {'name': 'T', 'intro': 'see:\n```py\nx = 1\n```'}
        # The fence has to be longer than the longest run inside the value.
        self.assertIn('````md', build_card(nested))
        self.assertEqual(parse_card(build_card(nested))[0], nested)

    def test_a_group_reads_as_map_list_or_objects(self):
        data, _ = parse_card(
            '# T\n'
            '- timeline\n'
            '  - start: 2026-08-24\n'
            '  - tasks\n'
            '    - task-1\n'
            '      - who: Ada Lovelace\n'
            '      - flags\n'
            '        - crit\n'
            '- platforms\n'
            '  - iOS\n')
        self.assertEqual(data['timeline']['start'], '2026-08-24')
        self.assertEqual(data['timeline']['tasks'],
                         [{'id': 'task-1', 'who': 'Ada Lovelace', 'flags': ['crit']}])
        self.assertEqual(data['platforms'], ['iOS'])

    def test_booleans_and_the_empty_string(self):
        data, _ = parse_card('# T\n- content_impact: true\n- qa: false\n- blocked_reason:\n')
        self.assertIs(data['content_impact'], True)
        self.assertIs(data['qa'], False)
        self.assertEqual(data['blocked_reason'], '')

    def test_an_object_without_an_id_is_given_one(self):
        text = build_card({'name': 'T', 'upstream': [{'team': 'Backend'}, {'team': 'Infra'}]})
        self.assertIn('- upstream-1', text)
        self.assertEqual(parse_card(text)[0]['upstream'][1],
                         {'id': 'upstream-2', 'team': 'Infra'})
        # `new` is the placeholder a hand-written entry may carry.
        replaced = build_card({'name': 'T', 'todos': [{'id': 'new', 'text': 'x'}]})
        self.assertIn('- todos-1', replaced)

    def test_a_document_without_a_title_is_not_a_card(self):
        self.assertEqual(parse_card('just markdown'), ({}, 'just markdown'))

    def test_unknown_keys_survive_a_round_trip(self):
        data, _ = parse_card('# T\n- id: p1\n- something_nobody_reads: kept\n')
        self.assertIn('- something_nobody_reads: kept', build_card(data))


class MigrationTest(unittest.TestCase):
    """One-way conversion of a pre-0.1.0 YAML vault."""

    YAML_CARD = (
        '---\n'
        'id: "p1"\n'
        'name: "A project"\n'
        'tier: "tier-1" # core\n'
        'intro: |-\n'
        '  first\n'
        '  second\n'
        'confluence:\n'
        '  - "https://x.test/a"\n'
        'todos:\n'
        '  - id: "todo-1"\n'
        '    text: "open one"\n'
        '    done: false\n'
        'todos_history:\n'
        '  - id: "todo-2"\n'
        '    text: "closed one"\n'
        '    done: true\n'
        '    completed_at: "2026-08-26 17:40"\n'
        '---\n'
        '\n'
        '## Notes\n'
        '\n'
        'Body text.\n'
    )

    def test_conversion_renames_the_history_and_drops_the_flag(self):
        data, body = parse_card(convert(self.YAML_CARD))
        self.assertEqual(data['name'], 'A project')
        self.assertEqual(data['tier'], 'tier-1')          # the comment stays dropped
        self.assertEqual(data['intro'], 'first\nsecond')
        self.assertEqual(data['confluence'], ['https://x.test/a'])
        self.assertEqual(data['todos'], [{'id': 'todo-1', 'text': 'open one'}])
        self.assertEqual(data['done'], [{'id': 'todo-2', 'text': 'closed one',
                                         'completed_at': '2026-08-26 17:40'}])
        self.assertNotIn('todos_history', data)
        self.assertEqual(body, 'Body text.')

    PLAN = (
        '# Delivery plan\n'
        '\n'
        '```mermaid\n'
        'gantt\n'
        '    dateFormat YYYY-MM-DD\n'
        '\n'
        '    section iOS\n'
        '    iOS Dev #1 P1 menu integration  :crit, active, 2026-09-14, 25d\n'
        '    QA #2 time off                  :done, 2026-09-21, 5d\n'
        '    iOS Dev #9 P99 unknown project  :2026-09-21, 5d\n'
        '```\n'
    )

    def test_a_plan_row_moves_into_the_card_that_owns_it(self):
        rows = parse_plan(self.PLAN)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]['flags'], ['crit', 'active'])
        self.assertEqual(rows[0]['end'].date(), date(2026, 10, 19))    # 25 working days

        settings = sample_settings()
        with tempfile.TemporaryDirectory() as folder:
            vault = os.path.join(folder, 'vault')
            shutil.copytree(SAMPLE_VAULT, vault)
            config = settings_module.configure(vault=vault)
            repo = ProjectRepository(settings=config)
            plan = os.path.join(folder, 'plan.md')
            with open(plan, 'w', encoding='utf-8') as handle:
                handle.write(self.PLAN)

            summary = import_plan(repo, plan, {'P1': 'project-1-navigation-menu'})
            self.assertEqual(summary['imported'], {'project-1-navigation-menu': 1})
            self.assertEqual([reason for _, reason in summary['skipped']],
                             ['no project code', 'no project code'])

            card = repo.load('project-1-navigation-menu')[0]
            task = card['timeline']['tasks'][0]
            self.assertEqual(task['who'], 'Rita Levi')       # resolved from the prefix
            self.assertEqual(task['note'], 'menu integration')
            self.assertEqual(task['flags'], ['crit', 'active'])
            self.assertEqual(card['timeline']['start'], '2026-09-14')
            # `dates.started` is absorbed: one fact, one field.
            self.assertNotIn('started', card.get('dates', {}))
            # the file it was read from is left alone
            with open(plan, encoding='utf-8') as handle:
                self.assertEqual(handle.read(), self.PLAN)
        settings_module.configure(vault=SAMPLE_VAULT)

    def test_migrating_a_vault_backs_up_and_refuses_to_run_twice(self):
        with tempfile.TemporaryDirectory() as folder:
            card = os.path.join(folder, 'p1.md')
            with open(card, 'w', encoding='utf-8') as handle:
                handle.write(self.YAML_CARD)

            first = migrate_vault(folder)
            self.assertEqual(first['converted'], ['p1.md'])
            with open(card + '.bak', encoding='utf-8') as handle:
                self.assertEqual(handle.read(), self.YAML_CARD)

            with open(card, encoding='utf-8') as handle:
                converted = handle.read()
            second = migrate_vault(folder)
            self.assertEqual(second['converted'], [])
            self.assertEqual(second['skipped'], ['p1.md'])
            with open(card, encoding='utf-8') as handle:
                self.assertEqual(handle.read(), converted)


class DropTiersTest(unittest.TestCase):
    """Bringing a 1.1 vault forward: no tier left, one flat run of priorities."""

    # Written in the order a 1.1 chart drew them, which is not the order the
    # numbers alone imply: tier first, and a finished project at the bottom
    # whatever its tier says.
    CARDS = [
        ('a', 'tier-2', '1', 'active'),
        ('b', 'tier-1', '2', 'active'),
        ('c', 'tier-1', '1', 'done'),
        ('d', 'tier-3', '1', 'active'),
        ('e', 'tier-1', '1', 'dropped'),
    ]
    SETTINGS = ('[[tiers]]\nkey="tier-1"\ntitle="T1"\nrgb=[1,2,3]\n'
                '[[tiers]]\nkey="tier-2"\ntitle="T2"\nrgb=[4,5,6]\n'
                '[[tiers]]\nkey="tier-3"\ntitle="T3"\nrgb=[7,8,9]\n')

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.settings_path = os.path.join(self.tmp, 'settings.toml')
        with open(self.settings_path, 'w', encoding='utf-8') as handle:
            handle.write(self.SETTINGS)
        for card_id, tier, priority, status in self.CARDS:
            with open(os.path.join(self.tmp, f'{card_id}.md'), 'w', encoding='utf-8') as handle:
                handle.write(f'# Project {card_id}\n- id: {card_id}\n- tier: {tier}\n'
                             f'- priority: {priority}\n- status: {status}\n')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ids_in_order(self):
        cards = []
        for name in sorted(os.listdir(self.tmp)):
            if name.endswith('.md'):
                with open(os.path.join(self.tmp, name), encoding='utf-8') as handle:
                    data, _ = parse_card(handle.read())
                cards.append((int(data['priority']), data['id'], data.get('tier')))
        return [(card_id, tier) for _, card_id, tier in sorted(cards)]

    def test_a_dry_run_writes_nothing(self):
        summary = drop_tiers(self.tmp, self.settings_path)
        self.assertEqual(len(summary['changed']), 5)
        self.assertFalse(summary['applied'])
        self.assertEqual(self._ids_in_order()[0], ('a', 'tier-2'))   # untouched on disk

    def test_the_flat_order_is_the_one_the_chart_drew(self):
        drop_tiers(self.tmp, self.settings_path, apply=True)
        # tier-1 before tier-2 before tier-3, then done, then dropped — and no
        # tier survives to say so.
        self.assertEqual(self._ids_in_order(),
                         [('b', None), ('a', None), ('d', None), ('c', None), ('e', None)])

    def test_running_it_twice_changes_nothing(self):
        drop_tiers(self.tmp, self.settings_path, apply=True)
        after = self._ids_in_order()
        summary = drop_tiers(self.tmp, self.settings_path, apply=True)
        self.assertEqual(summary['changed'], [])
        self.assertEqual(self._ids_in_order(), after)

    def test_an_unknown_key_survives_the_renumbering(self):
        with open(os.path.join(self.tmp, 'a.md'), 'a', encoding='utf-8') as handle:
            handle.write('- private_note: keep me\n')
        drop_tiers(self.tmp, self.settings_path, apply=True)
        with open(os.path.join(self.tmp, 'a.md'), encoding='utf-8') as handle:
            data, _ = parse_card(handle.read())
        self.assertEqual(data['private_note'], 'keep me')

    def test_without_a_tiers_table_the_cards_imply_the_order(self):
        """A 1.2 settings.toml no longer declares tiers; the vault still ranks."""
        with open(self.settings_path, 'w', encoding='utf-8') as handle:
            handle.write('[app]\ntitle="X"\n')
        drop_tiers(self.tmp, self.settings_path, apply=True)
        self.assertEqual([card_id for card_id, _ in self._ids_in_order()],
                         ['b', 'a', 'd', 'c', 'e'])

    def test_the_retired_table_is_read_in_declaration_order(self):
        self.assertEqual(read_tier_order(self.settings_path),
                         ['tier-1', 'tier-2', 'tier-3'])
        self.assertEqual(read_tier_order(os.path.join(self.tmp, 'nope.toml')), [])


class SettingsTest(unittest.TestCase):
    def test_sample_settings_load(self):
        config = sample_settings()
        self.assertIn('iOS', config.squads)
        self.assertEqual(config.title, 'GanttBit')

    def test_a_malformed_table_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'bad.toml')
            with open(path, 'w') as handle:
                handle.write('[locale]\nmonths=["a","b","c","d","e","f","g","h","i","j","k","l"]\n'
                             'month_abbr=["a","b","c","d","e","f","g","h","i","j","k","l"]\n'
                             '[[roles]]\nkey="r1"\nlabel="R"\n')
            with self.assertRaises(settings_module.SettingsError):
                settings_module.load(path)

    def test_a_local_file_layers_over_the_shipped_one(self):
        """A two-line override must not have to restate the squads and roles."""
        original = settings_module.LOCAL_SETTINGS_PATH
        with tempfile.TemporaryDirectory() as tmp:
            local = os.path.join(tmp, 'settings.local.toml')
            with open(local, 'w') as handle:
                handle.write('[vault]\nroot = "sample-vault"\n\n[app]\ntitle = "Local name"\n')
            settings_module.LOCAL_SETTINGS_PATH = local
            try:
                merged = settings_module.load()
            finally:
                settings_module.LOCAL_SETTINGS_PATH = original

        self.assertTrue(merged.projects_dir.endswith('sample-vault/02-projects/active'))
        self.assertEqual(merged.title, 'Local name')
        # everything the local file stayed silent about is inherited
        self.assertIn('iOS', merged.squads)
        self.assertEqual(merged.owner,
                         settings_module.load(settings_module.DEFAULT_SETTINGS_PATH).owner)
        self.assertEqual(merged.subtitle,
                         settings_module.load(settings_module.DEFAULT_SETTINGS_PATH).subtitle)

    def test_a_list_in_a_local_file_replaces_it_whole(self):
        base = {'roles': [{'key': 'a'}, {'key': 'b'}], 'app': {'title': 'T', 'owner': 'O'}}
        merged = settings_module._overlay(base, {'roles': [{'key': 'c'}],
                                                 'app': {'title': 'X'}})
        self.assertEqual(merged['roles'], [{'key': 'c'}])
        self.assertEqual(merged['app'], {'title': 'X', 'owner': 'O'})

    def test_missing_file_is_reported(self):
        with self.assertRaises(settings_module.SettingsError):
            settings_module.load('/nonexistent/settings.toml')


class ReleaseNotesTest(unittest.TestCase):
    """The Settings panel reads what shipped out of the CHANGELOG itself."""

    CHANGELOG = ('# Changelog\n\n'
                 '## 2.0.0 - 2026-10-01\n\n'
                 '### Added\n\n- The newer thing.\n\n'
                 '## 1.0.0 - 2026-09-13\n\n'
                 'First public release.\n\n- The older thing.\n')

    def _write(self, tmp, text=None):
        path = os.path.join(tmp, 'CHANGELOG.md')
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(self.CHANGELOG if text is None else text)
        return path

    def test_a_section_stops_at_the_next_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes = settings_module.release_notes('2.0.0', self._write(tmp))
        self.assertIn('The newer thing.', notes)
        self.assertNotIn('The older thing.', notes)
        self.assertNotIn('## 1.0.0', notes)

    def test_the_last_section_runs_to_the_end_of_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes = settings_module.release_notes('1.0.0', self._write(tmp))
        self.assertIn('First public release.', notes)
        self.assertIn('The older thing.', notes)

    def test_an_unknown_version_yields_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(settings_module.release_notes('9.9.9', self._write(tmp)), '')

    def test_a_missing_changelog_is_not_a_reason_to_fail(self):
        self.assertEqual(settings_module.release_notes('1.0.0', '/nonexistent/CHANGELOG.md'), '')

    def test_a_bullet_wrapped_across_lines_arrives_as_one_item(self):
        """The file is written to 80 columns; the panel is not that wide."""
        wrapped = ('# Changelog\n\n## 1.0.0 - 2026-09-13\n\n'
                   '- A bullet long enough that its author had to\n'
                   '  wrap it, twice over, to stay inside the margin.\n'
                   '- A second bullet.\n')
        with tempfile.TemporaryDirectory() as tmp:
            notes = settings_module.release_notes('1.0.0', self._write(tmp, wrapped))
        self.assertIn('had to wrap it, twice over, to stay', notes)
        self.assertEqual(len(notes.splitlines()), 2)
        rendered = markup.render_markdown(notes)
        self.assertEqual(rendered.count('<li>'), 2)
        self.assertNotIn('<p>', rendered)          # no continuation left stranded

    def test_the_shipped_changelog_describes_the_running_version(self):
        """Bumping __version__ without writing the section is caught here."""
        self.assertTrue(settings_module.release_notes(__version__).strip(),
                        f'CHANGELOG.md has no `## {__version__}` section')


class VaultTestCase(unittest.TestCase):
    """Runs against a disposable copy of the sample vault."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.vault = os.path.join(self.tmp, 'vault')
        shutil.copytree(SAMPLE_VAULT, self.vault)
        self.settings = settings_module.configure(vault=self.vault)
        self.repo = ProjectRepository(settings=self.settings)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        sample_settings()


class RepositoryTest(VaultTestCase):
    def test_cards_are_ordered_by_display_group_then_priority(self):
        ids = [project['id'] for project in self.repo.list_all()]
        self.assertEqual(ids[0], 'project-1-navigation-menu')
        # DONE and DROPPED are drawn under every tier, in that order
        self.assertEqual(ids[-2:],
                         ['project-10-delivery-estimate', 'project-12-accessibility-audit'])
        # an unknown tier still sorts with the default one, above them
        self.assertEqual(ids[-3], 'project-11-checkout-hardening')

    def test_path_traversal_is_refused(self):
        path = self.repo.path_for('../../etc/passwd')
        self.assertEqual(os.path.dirname(path), self.repo.directory)
        self.assertFalse(self.repo.exists('../../etc/passwd'))

    def test_atomic_write_leaves_no_partial_file(self):
        target = os.path.join(self.vault, 'card.md')
        write_atomic(target, 'first\n')
        with self.assertRaises(TypeError):
            write_atomic(target, None)
        with open(target) as handle:
            self.assertEqual(handle.read(), 'first\n')
        leftovers = [name for name in os.listdir(self.vault) if name.startswith('.tmp-')]
        self.assertEqual(leftovers, [])

    def test_hand_written_card_survives_a_save_untouched(self):
        """The card with inline comments must survive the parse → save cycle."""
        self.assertTrue(self.repo.mutate('project-2-eco-labels', lambda data: None))
        data, _ = self.repo.load('project-2-eco-labels')
        self.assertEqual(data['priority'], '2')
        self.assertEqual(data['status'], 'blocked')
        self.assertIn('Regulatory requirement', data['intro'])
        self.assertIn('\n', data['intro'])

    def test_write_raw_refuses_invalid_front_matter(self):
        before = self.repo.read_raw('project-1-navigation-menu')
        with self.assertRaises(ValueError):
            self.repo.write_raw('project-1-navigation-menu', 'no front matter here')
        self.assertEqual(self.repo.read_raw('project-1-navigation-menu'), before)

    def test_the_whole_vault_reads_and_writes_as_one_document(self):
        text = self.repo.vault_markdown()
        self.assertEqual(len(split_cards(text)), len(self.repo.list_all()))
        # tier and priority order, the same the chart draws
        self.assertTrue(text.startswith('# Navigation menu'))

        edited = text.replace('- priority: 1\n', '- priority: 1\n- extra_key: kept\n', 1)
        edited += '\n# Brand new\n- id: project-99-brand-new\n- tier: tier-3\n'
        result = self.repo.apply_vault_markdown(edited)

        self.assertEqual(result['created'], ['project-99-brand-new'])
        self.assertEqual(len(result['updated']), len(self.repo.list_all()) - 1)
        self.assertEqual(self.repo.load('project-1-navigation-menu')[0]['extra_key'], 'kept')

    def test_a_card_missing_from_the_document_is_never_deleted(self):
        before = len(self.repo.list_all())
        one = self.repo.read_raw('project-1-navigation-menu')
        self.repo.apply_vault_markdown(one)
        self.assertEqual(len(self.repo.list_all()), before)

    def test_the_snapshot_holds_a_card_whose_id_disagrees_with_its_file(self):
        """A hand-edited `- id:` is a card to fix, never a card to leave out."""
        path = os.path.join(self.repo.directory, 'mismatched.md')
        write_atomic(path, '# Mismatched\n- id: not-the-file-name\n- status: active\n')
        self.assertIn('# Mismatched', self.repo.vault_markdown())
        self.assertEqual(len(split_cards(self.repo.vault_markdown())),
                         len(self.repo.list_all()))

    def test_a_block_that_cannot_name_a_card_is_reported_not_written(self):
        result = self.repo.apply_vault_markdown(
            '# No id here\n- tier: tier-1\n\n'
            '# Bad id\n- id: ../escape\n\n'
            'not a card at all\n')
        self.assertEqual(result['created'], [])
        self.assertEqual(result['updated'], [])
        self.assertEqual([reason for _, reason in result['skipped']],
                         ['no `- id:` entry', 'an id may only hold letters, digits, . _ and -'])

    def test_attachments_are_listed_from_the_folder_and_never_from_the_card(self):
        project = 'project-6-designer-name'
        self.assertEqual(self.repo.list_attachments(project), [])
        self.repo.save_attachment(project, 'brief.pdf', b'%PDF-1.4 stub')
        self.repo.save_attachment(project, 'notes.md', 'hello\n')
        listed = self.repo.list_attachments(project)
        self.assertEqual([(a['name'], a['size']) for a in listed],
                         [('brief.pdf', 13), ('notes.md', 6)])

        card = next(p for p in self.repo.list_all() if p['id'] == project)
        self.assertEqual(len(card['_attachments']), 2)
        self.repo.mutate(project, lambda data: None)
        self.assertNotIn('_attachments', self.repo.read_raw(project))

    def test_attachment_names_cannot_escape_the_folder(self):
        for bad in ('../card.md', 'a/b.txt', '..', '.', ''):
            with self.subTest(name=bad), self.assertRaises(ValueError):
                self.repo.attachment_path('project-1-navigation-menu', bad)

    def test_attachment_upload_never_overwrites(self):
        self.repo.save_attachment('project-1-navigation-menu', 'x.txt', b'one')
        with self.assertRaises(FileExistsError):
            self.repo.save_attachment('project-1-navigation-menu', 'x.txt', b'two')
        self.assertTrue(self.repo.delete_attachment('project-1-navigation-menu', 'x.txt'))
        self.assertFalse(self.repo.delete_attachment('project-1-navigation-menu', 'x.txt'))

        self.repo.save_attachment('project-9-store-credit', 'only.txt', b'x')
        self.repo.delete_attachment('project-9-store-credit', 'only.txt')
        self.assertFalse(os.path.isdir(os.path.join(self.settings.attachments_dir,
                                                    'project-9-store-credit')))

    def test_csv_coercion(self):
        self.assertEqual(csv_to_list('iOS, QA'), ['iOS', 'QA'])
        self.assertEqual(csv_to_list(['iOS']), ['iOS'])
        self.assertEqual(csv_to_list(''), [])


class DomainTest(unittest.TestCase):
    def setUp(self):
        self.settings = sample_settings()
        self.projects = ProjectRepository(settings=self.settings).list_all()
        self.spans = chart_spans(self.projects, self.settings)

    def test_date_formats(self):
        self.assertEqual(format_date_long('2026-08-24', self.settings), '24 August 26')
        self.assertEqual(format_date_long('24/08/2026', self.settings), '24 August 26')
        self.assertEqual(format_date_long('mid October', self.settings), 'mid October')
        self.assertEqual(format_date_long('', self.settings), '')

    def test_a_deadline_reads_as_time_remaining(self):
        def away(days):
            return format_relative((TODAY + timedelta(days=days)).isoformat(), TODAY,
                                   self.settings)

        self.assertEqual(away(0), 'today')
        self.assertEqual(away(1), 'tomorrow')
        self.assertEqual(away(-1), 'yesterday')
        self.assertEqual(away(3), 'in 3 days')
        self.assertEqual(away(14), 'in 2 weeks')
        self.assertEqual(away(90), 'in 3 months')
        self.assertEqual(away(365), 'in 1 year')
        self.assertEqual(away(-730), '2 years ago')
        self.assertEqual(away(500), 'in 1.4 years')
        # A deadline that is not a date has no distance to report.
        self.assertEqual(format_relative('mid October', TODAY, self.settings), '')

    def test_the_ramp_runs_end_to_end_over_the_list(self):
        self.assertEqual(band_position(0, 10), 0.0)
        self.assertEqual(band_position(9, 10), 100.0)
        self.assertAlmostEqual(band_position(5, 11), 50.0)

    def test_the_only_project_there_is_sits_at_the_top_of_the_ramp(self):
        """A one-project list is not a last place: it is a first one."""
        self.assertEqual(band_position(0, 1), 0.0)
        self.assertEqual(band_position(0, 0), 0.0)

    def test_the_ramp_never_runs_past_its_end(self):
        self.assertEqual(band_position(99, 10), 100.0)
        self.assertEqual(band_position(-4, 10), 0.0)

    def test_a_person_resolves_by_name_and_still_by_the_old_prefix(self):
        self.assertEqual(resolve_person('Rita Levi', self.settings),
                         {'name': 'Rita Levi', 'role': 'iOS Dev', 'color': '#1e88e5'})
        # A card written when the timeline lived in a plan file still resolves.
        self.assertEqual(resolve_person('iOS Dev #1 anything', self.settings)['name'],
                         'Rita Levi')
        # Nobody in the roster: the keyword rule, then the fallback role.
        self.assertEqual(resolve_person('iOS contractor', self.settings)['role'], 'iOS Dev')
        self.assertEqual(resolve_person('Somebody Else', self.settings)['role'], 'Member')

    def test_milestones_are_dated_marks_in_date_order(self):
        card = {'id': 'x', 'milestones': [
            {'id': 'milestone-2', 'date': '2026-11-14', 'text': 'Store submission'},
            {'id': 'milestone-1', 'date': '2026-10-09', 'text': 'API frozen'},
            {'id': 'milestone-3', 'text': 'no date, no mark'},
        ]}
        marks = project_milestones(card, self.settings)
        self.assertEqual([mark['id'] for mark in marks], ['milestone-1', 'milestone-2'])

    def test_a_card_owns_its_bars(self):
        card = next(p for p in self.projects if p['id'] == 'project-1-navigation-menu')
        start, end = project_span(card, self.settings)
        self.assertEqual((start.date(), end.date()), (date(2026, 8, 24), date(2026, 11, 20)))

        rows = project_tasks(card, self.settings)
        self.assertEqual(rows[0]['who'], 'Ada Lovelace')
        self.assertEqual(rows[0]['role'], 'Backend Dev')
        self.assertEqual(rows[0]['type'], 'crit')
        self.assertFalse(any(row['outside'] for row in rows))

    def test_a_span_may_be_declared_in_working_days(self):
        card = {'id': 'x', 'timeline': {'start': '2026-09-02', 'days': '10'}}
        start, end = project_span(card, self.settings)
        self.assertEqual((start.date(), end.date()), (date(2026, 9, 2), date(2026, 9, 16)))

    def test_a_project_bar_exists_without_a_single_task(self):
        card = {'id': 'x', 'timeline': {'start': '2026-09-02', 'end': '2026-09-30'}}
        self.assertIsNotNone(project_span(card, self.settings))
        self.assertEqual(project_tasks(card, self.settings), [])

    def test_a_task_outside_its_project_span_is_flagged_not_dropped(self):
        card = {'id': 'x', 'timeline': {
            'start': '2026-09-02', 'end': '2026-09-30',
            'tasks': [{'id': 'task-1', 'who': 'Rita Levi', 'start': '2026-11-02',
                       'end': '2026-11-06'}]}}
        rows = project_tasks(card, self.settings)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['outside'])

    def test_flags_read_as_a_list_or_inline(self):
        card = {'id': 'x', 'timeline': {'tasks': [
            {'id': 't1', 'who': 'x', 'start': '2026-09-02', 'days': '2',
             'flags': 'crit, active'}]}}
        self.assertEqual(project_tasks(card, self.settings)[0]['type'], 'crit')

    def test_timeline_covers_past_and_future_tasks(self):
        timeline = Timeline(self.spans, settings=self.settings, today=TODAY)
        self.assertEqual(timeline.days[0].date(), date(2026, 1, 12))
        self.assertGreaterEqual(timeline.days[-1].date(), date(2027, 3, 31))
        self.assertIsNotNone(timeline.today_index)
        self.assertTrue(all(day.weekday() < 5 for day in timeline.days))

    def test_the_window_cuts_the_scale_on_both_sides(self):
        start, end, key = resolve_range('today', TODAY)
        timeline = Timeline(self.spans, settings=self.settings, today=TODAY,
                            start_from=start, end_at=end)
        self.assertEqual(key, 'today')
        self.assertEqual(timeline.days[0].date(), TODAY)
        self.assertEqual(timeline.today_index, 0)

        start, end, _ = resolve_range('30d', TODAY)
        timeline = Timeline(self.spans, settings=self.settings, today=TODAY,
                            start_from=start, end_at=end)
        self.assertEqual(timeline.days[0].date(), date(2026, 8, 10))   # the Monday after

        start, end, _ = resolve_range('year', TODAY)
        timeline = Timeline(self.spans, settings=self.settings, today=TODAY,
                            start_from=start, end_at=end)
        self.assertGreaterEqual(timeline.days[0].date(), date(2026, 1, 1))
        self.assertLessEqual(timeline.days[-1].date(), date(2026, 12, 31))

        start, end, key = resolve_range('2026-03-02', TODAY)
        self.assertEqual(key, '2026-03-02')
        timeline = Timeline(self.spans, settings=self.settings, today=TODAY,
                            start_from=start, end_at=end)
        self.assertEqual(timeline.days[0].date(), date(2026, 3, 2))

    def test_a_zoomed_out_scale_runs_past_the_last_bar(self):
        """Zooming out is asking to see further; the window still decides the end."""
        from ganttbit.settings import ZOOM_HORIZON
        plain = Timeline(self.spans, settings=self.settings, today=TODAY)
        far = Timeline(self.spans, settings=self.settings, today=TODAY,
                       horizon=ZOOM_HORIZON['month'])
        self.assertGreater(len(far.days), len(plain.days))
        self.assertGreaterEqual(far.days[-1].date(), TODAY + timedelta(days=700))

        # The row above the months groups the same days by year.
        self.assertEqual([year for year, _count in far.years],
                         sorted({day.year for day in far.days}))
        self.assertEqual(sum(count for _year, count in far.years), len(far.days))

        # A window that names its own end is not stretched past it.
        start, end, _ = resolve_range('year', TODAY)
        bounded = Timeline(self.spans, settings=self.settings, today=TODAY,
                           start_from=start, end_at=end,
                           horizon=ZOOM_HORIZON['month'])
        self.assertLessEqual(bounded.days[-1].date(), date(2026, 12, 31))

    def test_the_zoom_only_changes_how_wide_a_day_is_drawn(self):
        from ganttbit.domain import resolve_zoom
        self.assertEqual(resolve_zoom('day'), (17, 'day'))
        self.assertEqual(resolve_zoom('week')[1], 'week')
        self.assertLess(resolve_zoom('month')[0], resolve_zoom('week')[0])
        self.assertEqual(resolve_zoom('whatever'), (17, 'day'))

        wide = Timeline(self.spans, settings=self.settings, today=TODAY)
        narrow = Timeline(self.spans, settings=self.settings, today=TODAY,
                          col_width=resolve_zoom('month')[0])
        # the same days, drawn in less room
        self.assertEqual(len(wide.days), len(narrow.days))
        self.assertLess(narrow.width, wide.width)

    def test_an_unknown_window_falls_back_to_today(self):
        self.assertEqual(resolve_range('whenever', TODAY), (TODAY, None, 'today'))
        self.assertEqual(resolve_range('2026-13-40', TODAY), (TODAY, None, 'today'))
        self.assertEqual(resolve_range('all', TODAY), (None, None, 'all'))

    def test_a_window_with_no_work_in_it_still_draws_a_month(self):
        start, end, _ = resolve_range('2030-01-07', TODAY)
        timeline = Timeline(self.spans, settings=self.settings, today=TODAY,
                            start_from=start, end_at=end)
        self.assertEqual(timeline.days[0].date(), date(2030, 1, 7))
        self.assertEqual(len(timeline.days), 22)

    def test_geometry_is_none_outside_the_scale(self):
        timeline = Timeline([], settings=self.settings, today=TODAY)
        far = datetime(2030, 1, 1)
        self.assertIsNone(timeline.geometry(far, far))

    def test_grouping_is_the_live_list_and_then_the_two_closing_groups(self):
        grouped = group_by_display(
            [{'status': 'active'}, {'status': 'on-hold'},
             {'status': 'done'}, {'status': 'dropped'}],
            self.settings)
        self.assertEqual(list(grouped), ['live', 'done', 'dropped'])
        # An unrecognised status is still work in flight, not an archive.
        self.assertEqual(len(grouped['live']), 2)
        self.assertEqual(len(grouped['done']), 1)
        self.assertEqual(len(grouped['dropped']), 1)

    def test_a_status_is_the_only_thing_that_files_a_project(self):
        self.assertEqual(display_group({'status': 'done'}, self.settings), 'done')
        self.assertEqual(display_group({}, self.settings), 'live')


class SchemaAndApiTest(VaultTestCase):
    PROJECT = 'project-1-navigation-menu'

    def test_invalid_status_is_rejected_before_it_reaches_the_file(self):
        with self.assertRaises(ApiError) as caught:
            dispatch(self.repo, self.PROJECT, 'update', {'status': 'whatever'}, now=NOW)
        self.assertEqual(caught.exception.status, 400)
        self.assertEqual(self.repo.load(self.PROJECT)[0]['status'], 'active')

    def test_invalid_deadline_type_and_severity_are_rejected(self):
        for payload in ({'deadline_type': 'medium'},):
            with self.assertRaises(ApiError):
                dispatch(self.repo, self.PROJECT, 'update', payload, now=NOW)
        with self.assertRaises(ApiError):
            dispatch(self.repo, self.PROJECT, 'advanced-update',
                     {'risks_and_criticalities': [{'id': 'R', 'severity': 'apocalyptic'}]}, now=NOW)

    def test_quick_update_writes_only_the_fields_it_owns(self):
        before, _ = self.repo.load(self.PROJECT)
        dispatch(self.repo, self.PROJECT, 'update',
                 {'status': 'blocked', 'blocked_reason': 'waiting', 'platforms': 'iOS, QA'},
                 now=NOW)
        after, _ = self.repo.load(self.PROJECT)
        self.assertEqual(after['status'], 'blocked')
        self.assertEqual(after['tech_footprint']['platforms'], ['iOS', 'QA'])
        self.assertEqual(after['todos'], before['todos'])
        self.assertEqual(after['risks_and_criticalities'], before['risks_and_criticalities'])

    def test_advanced_update_leaves_untouched_fields_alone(self):
        before, _ = self.repo.load(self.PROJECT)
        dispatch(self.repo, self.PROJECT, 'advanced-update',
                 {'dates': {'soft_deadline': '2026-11-05'}, 'body': 'replaced body'}, now=NOW)
        after, body = self.repo.load(self.PROJECT)
        self.assertEqual(after['dates']['soft_deadline'], '2026-11-05')
        self.assertEqual(after['dates']['deadline_type'], before['dates']['deadline_type'])
        self.assertEqual(after['todos'], before['todos'])
        self.assertEqual(after['intro'], before['intro'])
        self.assertEqual(body, 'replaced body')

    def test_readonly_fields_cannot_be_written(self):
        dispatch(self.repo, self.PROJECT, 'advanced-update',
                 {'id': 'renamed', 'priority': '99'}, now=NOW)
        after, _ = self.repo.load(self.PROJECT)
        self.assertEqual(after['id'], self.PROJECT)
        self.assertEqual(after['priority'], '1')

    def test_an_empty_name_is_refused_by_every_path_that_can_write_one(self):
        """The name is the `# title` line: written empty, the file stops being a card."""
        for action, payload in (('update', {'name': ''}),
                                ('advanced-update', {'name': '   '}),
                                ('set', {'path': 'name', 'value': ''})):
            with self.assertRaises(ApiError) as caught:
                dispatch(self.repo, self.PROJECT, action, payload, now=NOW)
            self.assertEqual(caught.exception.status, 400)

        data, _ = self.repo.load(self.PROJECT)
        self.assertEqual(data['name'], 'Navigation menu — second level')

    def test_the_id_is_not_a_value_the_structure_view_edits(self):
        """It is the name of the file: the card and its file would stop agreeing."""
        with self.assertRaises(ApiError) as caught:
            dispatch(self.repo, self.PROJECT, 'set',
                     {'path': 'id', 'value': 'something-else'}, now=NOW)
        self.assertEqual(caught.exception.status, 400)
        self.assertEqual(self.repo.load(self.PROJECT)[0]['id'], self.PROJECT)

    def test_a_note_handler_answers_rather_than_raises_on_a_hand_edited_card(self):
        """`- todos: buy milk` is a card someone typed, not a reason for a 500."""
        card = os.path.join(self.repo.directory, 'hand.md')
        write_atomic(card, '# Hand edited\n- id: hand\n- todos: buy milk\n')

        for action in ('todo/update', 'todo/toggle'):
            with self.assertRaises(ApiError) as caught:
                dispatch(self.repo, 'hand', action,
                         {'todo_id': 'buy milk', 'text': 'x'}, now=NOW)
            self.assertEqual(caught.exception.status, 404)

        # Deleting what is not a note removes nothing and raises nothing, and
        # the line someone typed is still in the card afterwards.
        dispatch(self.repo, 'hand', 'todo/delete', {'todo_id': 'buy milk'}, now=NOW)
        self.assertIn('buy milk', self.repo.read_raw('hand'))
        dispatch(self.repo, 'hand', 'todo/reorder', {'order': ['buy milk']}, now=NOW)
        self.assertIn('buy milk', self.repo.read_raw('hand'))

    def test_reordering_refuses_a_payload_it_cannot_read_and_deletes_nothing(self):
        dispatch(self.repo, self.PROJECT, 'todo/add', {'text': 'first'}, now=NOW)
        dispatch(self.repo, self.PROJECT, 'todo/add', {'text': 'second'}, now=NOW)
        before = [item['id'] for item in self.repo.load(self.PROJECT)[0]['todos']]

        with self.assertRaises(ApiError):
            dispatch(self.repo, self.PROJECT, 'todo/reorder', {'order': 'nope'}, now=NOW)
        # A list of anything at all: answered, never raised.
        dispatch(self.repo, self.PROJECT, 'todo/reorder',
                 {'order': [{'not': 'an id'}, None, 7]}, now=NOW)
        self.assertEqual([item['id'] for item in self.repo.load(self.PROJECT)[0]['todos']],
                         before)

        # A reorder is not a delete: what the payload forgot keeps its place.
        dispatch(self.repo, self.PROJECT, 'todo/reorder', {'order': [before[-1]]}, now=NOW)
        after = [item['id'] for item in self.repo.load(self.PROJECT)[0]['todos']]
        self.assertEqual(after[0], before[-1])
        self.assertEqual(sorted(after), sorted(before))

    def test_todo_lifecycle(self):
        dispatch(self.repo, self.PROJECT, 'todo/add', {'text': 'new note'}, now=NOW)
        data, _ = self.repo.load(self.PROJECT)
        todo_id = data['todos'][-1]['id']

        dispatch(self.repo, self.PROJECT, 'todo/update',
                 {'todo_id': todo_id, 'text': 'edited', 'deadline': '2026-10-01'}, now=NOW)
        dispatch(self.repo, self.PROJECT, 'todo/toggle', {'todo_id': todo_id}, now=NOW)
        data, _ = self.repo.load(self.PROJECT)
        done = next(item for item in data['done'] if item['id'] == todo_id)
        self.assertEqual(done['text'], 'edited')
        self.assertEqual(done['completed_at'], '2026-09-09 10:30')

        dispatch(self.repo, self.PROJECT, 'todo/toggle', {'todo_id': todo_id}, now=NOW)
        data, _ = self.repo.load(self.PROJECT)
        reopened = next(item for item in data['todos'] if item['id'] == todo_id)
        self.assertNotIn('completed_at', reopened)

        dispatch(self.repo, self.PROJECT, 'todo/delete', {'todo_id': todo_id}, now=NOW)
        data, _ = self.repo.load(self.PROJECT)
        self.assertNotIn(todo_id, [item['id'] for item in data['todos']])

    def test_empty_todo_text_is_refused(self):
        with self.assertRaises(ApiError):
            dispatch(self.repo, self.PROJECT, 'todo/add', {'text': '   '}, now=NOW)

    def test_notes_are_reordered_and_never_lost(self):
        before = [item['id'] for item in self.repo.load(self.PROJECT)[0]['todos']]
        self.assertGreater(len(before), 1)

        dispatch(self.repo, self.PROJECT, 'todo/reorder',
                 {'order': list(reversed(before))}, now=NOW)
        self.assertEqual([item['id'] for item in self.repo.load(self.PROJECT)[0]['todos']],
                         list(reversed(before)))

        # a payload that forgets a note leaves it where it is, at the end
        dispatch(self.repo, self.PROJECT, 'todo/reorder', {'order': [before[0]]}, now=NOW)
        after = [item['id'] for item in self.repo.load(self.PROJECT)[0]['todos']]
        self.assertEqual(after[0], before[0])
        self.assertEqual(sorted(after), sorted(before))

    def test_the_project_name_is_editable_from_the_panel(self):
        dispatch(self.repo, self.PROJECT, 'update', {'name': 'Renamed from the panel'},
                 now=NOW)
        self.assertEqual(self.repo.load(self.PROJECT)[0]['name'], 'Renamed from the panel')
        # the name is the card's title line, so the file says it too
        self.assertTrue(self.repo.read_raw(self.PROJECT)
                        .startswith('# Renamed from the panel\n'))

    def test_a_milestone_is_added_edited_and_deleted(self):
        result = dispatch(self.repo, self.PROJECT, 'milestone/save',
                          {'date': '2026-12-01', 'text': 'Store submission'}, now=NOW)
        created = result['milestone']['id']
        self.assertEqual(self.repo.load(self.PROJECT)[0]['milestones'][-1]['text'],
                         'Store submission')

        dispatch(self.repo, self.PROJECT, 'milestone/save',
                 {'milestone_id': created, 'date': '2026-12-02', 'text': 'Moved'}, now=NOW)
        stored = [item for item in self.repo.load(self.PROJECT)[0]['milestones']
                  if item['id'] == created]
        self.assertEqual(stored, [{'id': created, 'date': '2026-12-02', 'text': 'Moved'}])

        dispatch(self.repo, self.PROJECT, 'milestone/delete',
                 {'milestone_id': created}, now=NOW)
        self.assertNotIn(created, [item['id'] for item
                                   in self.repo.load(self.PROJECT)[0]['milestones']])

    def test_a_bar_is_moved_and_resized_by_dates(self):
        dispatch(self.repo, self.PROJECT, 'timeline/save',
                 {'task_id': 'task-1', 'start': '2026-08-31', 'end': '2026-10-16'}, now=NOW)
        task = self.repo.load(self.PROJECT)[0]['timeline']['tasks'][0]
        self.assertEqual((task['start'], task['end']), ('2026-08-31', '2026-10-16'))

        dispatch(self.repo, self.PROJECT, 'timeline/save',
                 {'start': '2026-08-31', 'end': '2026-11-27'}, now=NOW)
        timeline = self.repo.load(self.PROJECT)[0]['timeline']
        self.assertEqual((timeline['start'], timeline['end']), ('2026-08-31', '2026-11-27'))

    def test_a_timeline_row_is_added_from_the_panel(self):
        before = len(self.repo.load(self.PROJECT)[0]['timeline']['tasks'])
        result = dispatch(self.repo, self.PROJECT, 'timeline/save',
                          {'task_id': 'new', 'who': 'Grace Hopper', 'note': 'spike',
                           'start': '2026-10-05', 'end': '2026-10-16'}, now=NOW)
        tasks = self.repo.load(self.PROJECT)[0]['timeline']['tasks']
        self.assertEqual(len(tasks), before + 1)
        self.assertEqual(tasks[-1]['who'], 'Grace Hopper')
        self.assertEqual(tasks[-1]['id'], result['task']['id'])

        with self.assertRaises(ApiError):     # a row belongs to somebody
            dispatch(self.repo, self.PROJECT, 'timeline/save',
                     {'task_id': 'new', 'who': '  ', 'start': '2026-10-05',
                      'end': '2026-10-16'}, now=NOW)

    def test_a_bar_cannot_be_moved_to_a_date_the_card_cannot_hold(self):
        for payload in ({'start': 'yesterday', 'end': '2026-10-16'},
                        {'start': '2026-10-16', 'end': '2026-08-31'},
                        {'task_id': 'nope', 'start': '2026-10-01', 'end': '2026-10-16'}):
            with self.assertRaises(ApiError):
                dispatch(self.repo, self.PROJECT, 'timeline/save', payload, now=NOW)

    def test_a_milestone_without_a_date_is_refused(self):
        with self.assertRaises(ApiError):
            dispatch(self.repo, self.PROJECT, 'milestone/save',
                     {'text': 'someday'}, now=NOW)
        with self.assertRaises(ApiError):
            dispatch(self.repo, self.PROJECT, 'milestone/save',
                     {'date': 'mid December', 'text': 'someday'}, now=NOW)

    def test_reorder_numbers_projects_over_the_whole_chart(self):
        """`priority` is a position in one flat list, and the list is the chart."""
        result = dispatch(self.repo, '_batch', 'reorder', {'order': [
            {'id': 'project-3-home-redesign', 'group': 'live'},
            {'id': self.PROJECT, 'group': 'live'},
            {'id': 'project-8-banner-defaults', 'group': 'live'},
        ]}, now=NOW)
        self.assertEqual(result['updated'], 3)
        self.assertEqual(self.repo.load('project-3-home-redesign')[0]['priority'], '1')
        self.assertEqual(self.repo.load(self.PROJECT)[0]['priority'], '2')
        self.assertEqual(self.repo.load('project-8-banner-defaults')[0]['priority'], '3')

    def test_a_project_is_finished_by_dropping_it_and_revived_by_dragging_it_back(self):
        dispatch(self.repo, '_batch', 'reorder',
                 {'order': [{'id': self.PROJECT, 'group': 'done'}]}, now=NOW)
        card = self.repo.load(self.PROJECT)[0]
        self.assertEqual(card['status'], 'done')
        self.assertNotIn('tier', card)                    # nothing left to carry

        dispatch(self.repo, '_batch', 'reorder',
                 {'order': [{'id': self.PROJECT, 'group': 'live'}]}, now=NOW)
        card = self.repo.load(self.PROJECT)[0]
        self.assertEqual(card['status'], 'active')        # back to being worked on

    def test_reorder_writes_only_what_moved(self):
        order = [{'id': project['id'], 'group': display_group(project, self.settings)}
                 for project in self.repo.list_all()]
        dispatch(self.repo, '_batch', 'reorder', {'order': order}, now=NOW)
        again = dispatch(self.repo, '_batch', 'reorder', {'order': order}, now=NOW)
        self.assertEqual(again['updated'], 0)

    def test_reorder_refuses_an_unknown_group(self):
        with self.assertRaises(ApiError):
            dispatch(self.repo, '_batch', 'reorder',
                     {'order': [{'id': self.PROJECT, 'group': 'tier-1'}]}, now=NOW)

    def test_unknown_action_and_unknown_project(self):
        for project_id, action in ((self.PROJECT, 'nope'), ('ghost', 'update')):
            with self.assertRaises(ApiError) as caught:
                dispatch(self.repo, project_id, action, {}, now=NOW)
            self.assertEqual(caught.exception.status, 404)

    def test_raw_update_validates_before_writing(self):
        before = self.repo.read_raw(self.PROJECT)
        with self.assertRaises(ApiError):
            dispatch(self.repo, self.PROJECT, 'raw-update', {'raw_text': 'broken'}, now=NOW)
        self.assertEqual(self.repo.read_raw(self.PROJECT), before)

        dispatch(self.repo, self.PROJECT, 'raw-update',
                 {'raw_text': '# Renamed\n- id: %s\n\n## Notes\n\nbody\n' % self.PROJECT},
                 now=NOW)
        self.assertEqual(self.repo.load(self.PROJECT)[0]['name'], 'Renamed')


class CreateProjectTest(VaultTestCase):
    def test_a_name_is_enough_and_the_card_lands_at_the_end_of_the_live_list(self):
        result = dispatch(self.repo, '_batch', 'create', {'name': 'Résumé builder — v2'}, now=NOW)
        self.assertEqual(result['project'], 'resume-builder-v2')
        data, body = self.repo.load('resume-builder-v2')
        self.assertEqual(data['name'], 'Résumé builder — v2')
        self.assertEqual(data['status'], 'active')
        self.assertEqual(body, '')
        live = [p for p in self.repo.list_all() if p['status'] not in ('done', 'dropped')]
        self.assertEqual(live[-1]['id'], 'resume-builder-v2')
        self.assertEqual(data['priority'], str(len(live)))

    def test_an_explicit_id_wins_over_the_slug(self):
        dispatch(self.repo, '_batch', 'create', {'name': 'Watch app', 'id': 'proj-42'}, now=NOW)
        self.assertTrue(self.repo.exists('proj-42'))

    def test_a_duplicate_a_bad_id_and_an_empty_name_are_refused(self):
        with self.assertRaises(ApiError) as caught:
            dispatch(self.repo, '_batch', 'create', {'name': 'Navigation menu', 'id': 'project-1-navigation-menu'}, now=NOW)
        self.assertEqual(caught.exception.status, 409)
        for payload in ({'name': ''}, {'name': '   '}, {'name': 'X', 'id': '../escape'}):
            with self.assertRaises(ApiError):
                dispatch(self.repo, '_batch', 'create', payload, now=NOW)

    def test_the_inbox_id_is_reserved(self):
        with self.assertRaises(ApiError):
            dispatch(self.repo, '_batch', 'create', {'name': 'Inbox'}, now=NOW)

    def test_both_pages_carry_the_button(self):
        projects = self.repo.list_all()
        chart = view.render_page(projects, today=TODAY, settings=self.settings)
        tree = view.render_hierarchy_page(projects, '', settings=self.settings)
        self.assertEqual(chart.count('data-action="project-new"'), 2)   # header, and the phone's list
        self.assertEqual(tree.count('data-action="project-new"'), 1)


class InboxTest(VaultTestCase):
    """Notes of no project live in one reserved card, created by the first note."""

    def test_the_first_note_creates_the_card(self):
        self.assertFalse(self.repo.exists('inbox'))
        result = dispatch(self.repo, 'inbox', 'todo/add', {'text': 'Call the vendor'}, now=NOW)
        data, _ = self.repo.load('inbox')
        self.assertEqual(data['type'], 'inbox')
        self.assertEqual(data['priority'], '0')
        self.assertEqual([t['text'] for t in data['todos']], ['Call the vendor'])
        self.assertEqual(result['todo']['text'], 'Call the vendor')

    def test_the_inbox_is_out_of_the_chart_and_the_count_and_first_everywhere_else(self):
        before = len(self.repo.list_all())
        open_before = int(re.search(r'data-open="(\d+)"', view.render_page(
            self.repo.list_all(), today=TODAY, settings=self.settings)).group(1))
        dispatch(self.repo, 'inbox', 'todo/add', {'text': 'Call the vendor'}, now=NOW)
        projects = self.repo.list_all()
        self.assertEqual(projects[0]['id'], 'inbox')          # first card, first block
        self.assertTrue(self.repo.vault_markdown().startswith('# Inbox\n'))

        page = view.render_page(projects, today=TODAY, settings=self.settings)
        self.assertNotIn('data-proj-id="inbox"', page)
        self.assertIn(f'<strong>{before}</strong> projects', page)
        self.assertIn('Call the vendor', page)
        self.assertIn('id="new-todo-text-inbox"', page)
        self.assertIn(f'data-open="{open_before + 1}"', page)
        self.assertLess(page.index('data-card="inbox"'), page.index('data-card="project-1-navigation-menu"'))

        tree = view.render_hierarchy_page(projects, '', settings=self.settings)
        self.assertIn('class="tree tree--inbox"', tree)
        self.assertLess(tree.index('tree--inbox'), tree.index('project-1-navigation-menu'))

    def test_with_no_inbox_the_composer_is_still_there(self):
        page = view.render_page(self.repo.list_all(), today=TODAY, settings=self.settings)
        self.assertIn('id="new-todo-text-inbox"', page)
        self.assertNotIn('tree--inbox', view.render_hierarchy_page(
            self.repo.list_all(), '', settings=self.settings))


class StructureViewTest(VaultTestCase):
    """The hierarchy page: a tree that folds, and values that edit in place."""
    PROJECT = 'project-1-navigation-menu'

    def test_the_tree_folds_carries_the_levels_and_addresses_every_value(self):
        page = view.render_hierarchy_page(self.repo.list_all(), '', settings=self.settings)
        self.assertIn('id="tree-depth-switch"', page)
        self.assertIn('id="tree-detail-switch"', page)
        self.assertIn('data-action="tree-depth" data-depth="compact"', page)
        self.assertIn(f'<li class="tree__project" data-project="{self.PROJECT}"><details open>', page)
        self.assertIn('class="tree__entry tree__entry--branch" data-key="timeline"', page)
        self.assertIn('data-path="dates.deadline_text"', page)
        self.assertIn('data-path="_body"', page)
        self.assertIn('class="tree__who"', page)          # the people, for the Stakeholders level
        self.assertIn('class="deadline-pill tree__deadline"', page)
        # A row in a list is addressed by its id, a bare value by its index.
        self.assertRegex(page, r'data-path="timeline\.tasks\.task-1\.who"')
        self.assertIn('data-path="tech_footprint.platforms.0"', page)

    def test_set_walks_maps_lists_and_ids(self):
        dispatch(self.repo, self.PROJECT, 'set', {'path': 'dates.deadline_text', 'value': '2026-12-01'}, now=NOW)
        dispatch(self.repo, self.PROJECT, 'set', {'path': 'timeline.tasks.task-1.who', 'value': 'Grace Hopper'}, now=NOW)
        dispatch(self.repo, self.PROJECT, 'set', {'path': 'tech_footprint.platforms.0', 'value': 'Web'}, now=NOW)
        dispatch(self.repo, self.PROJECT, 'set', {'path': '_body', 'value': 'Rewritten notes.'}, now=NOW)
        data, body = self.repo.load(self.PROJECT)
        self.assertEqual(data['dates']['deadline_text'], '2026-12-01')
        self.assertEqual(data['timeline']['tasks'][0]['who'], 'Grace Hopper')
        self.assertEqual(data['tech_footprint']['platforms'][0], 'Web')
        self.assertEqual(body.strip(), 'Rewritten notes.')

    def test_set_validates_what_the_schema_knows_and_refuses_what_is_not_there(self):
        data, _ = self.repo.load(self.PROJECT)
        risk = data['risks_and_criticalities'][0]['id']
        for path, value in (('status', 'whatever'), ('dates.deadline_type', 'medium'),
                            ('priority', '3'),      # drag and drop owns it
                            (f'risks_and_criticalities.{risk}.severity', 'apocalyptic')):
            with self.assertRaises(ApiError, msg=path) as caught:
                dispatch(self.repo, self.PROJECT, 'set', {'path': path, 'value': value}, now=NOW)
            self.assertEqual(caught.exception.status, 400)
        for path in ('nowhere', 'dates.nowhere', 'timeline.tasks.task-99.who', ''):
            with self.assertRaises(ApiError, msg=path):
                dispatch(self.repo, self.PROJECT, 'set', {'path': path, 'value': 'x'}, now=NOW)
        after, _ = self.repo.load(self.PROJECT)
        self.assertEqual(after['status'], data['status'])
        self.assertNotIn('nowhere', after)

    def test_set_keeps_the_type_the_file_had(self):
        dispatch(self.repo, self.PROJECT, 'set', {'path': 'tech_footprint.content_impact', 'value': 'false'}, now=NOW)
        data, _ = self.repo.load(self.PROJECT)
        self.assertIs(data['tech_footprint']['content_impact'], False)


class GlobalTodosTest(VaultTestCase):
    def test_a_card_in_actions_and_notes_opens_its_project(self):
        page = view.render_page(self.repo.list_all(), today=TODAY, settings=self.settings)
        self.assertIn('data-action="go-project" data-project="project-1-navigation-menu"', page)
        # The inbox has no project to go to.
        self.assertNotIn('data-action="go-project" data-project="inbox"', page)


class AttachmentApiTest(VaultTestCase):
    PROJECT = 'project-8-banner-defaults'

    def test_upload_and_delete(self):
        result = upload_attachment(self.repo, self.PROJECT, 'colours.csv', b'market,hex\n')
        self.assertEqual(result['attachment'], 'colours.csv')
        self.assertEqual([a['name'] for a in self.repo.list_attachments(self.PROJECT)],
                         ['colours.csv'])
        delete_attachment(self.repo, self.PROJECT, 'colours.csv')
        self.assertEqual(self.repo.list_attachments(self.PROJECT), [])

    def test_bad_names_empty_files_and_duplicates_are_refused(self):
        for bad in ('', '..', 'a/b.txt', 'a\\b.txt', 'x\x00y', 'n' * 201):
            with self.subTest(name=bad), self.assertRaises(ApiError):
                upload_attachment(self.repo, self.PROJECT, bad, b'data')
        with self.assertRaises(ApiError):
            upload_attachment(self.repo, self.PROJECT, 'empty.txt', b'')

        upload_attachment(self.repo, self.PROJECT, 'once.txt', b'1')
        with self.assertRaises(ApiError) as caught:
            upload_attachment(self.repo, self.PROJECT, 'once.txt', b'2')
        self.assertEqual(caught.exception.status, 409)

    def test_unknown_project_or_attachment_is_404(self):
        with self.assertRaises(ApiError) as caught:
            upload_attachment(self.repo, 'ghost', 'a.txt', b'x')
        self.assertEqual(caught.exception.status, 404)
        with self.assertRaises(ApiError) as caught:
            delete_attachment(self.repo, self.PROJECT, 'missing.txt')
        self.assertEqual(caught.exception.status, 404)


class EmptyVaultTest(VaultTestCase):
    """A fresh clone has no vault; the first message a new user sees must help."""

    def report(self, config):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            server_module._report_empty_vault(config)
        return buffer.getvalue()

    def test_a_vault_with_cards_says_nothing(self):
        self.assertEqual(self.report(self.settings), '')

    def test_a_missing_or_empty_vault_names_the_way_out(self):
        missing = settings_module.configure(
            vault=os.path.join(self.tmp, 'nowhere'))
        empty_dir = os.path.join(self.tmp, 'empty', '02-projects', 'active')
        os.makedirs(empty_dir)
        empty = settings_module.configure(vault=os.path.join(self.tmp, 'empty'))

        for config in (missing, empty):
            text = self.report(config)
            self.assertIn('the dashboard will be empty', text)
            self.assertIn('--vault PATH', text)
            self.assertIn('--vault sample-vault', text)


class ViewTest(unittest.TestCase):
    def setUp(self):
        self.settings = sample_settings()
        self.repo = ProjectRepository(settings=self.settings)
        self.spans = chart_spans(self.repo.list_all(), self.settings)
        self.projects = self.repo.list_all()
        self.html = view.render_page(self.projects, today=TODAY, settings=self.settings)

    def test_the_page_ranks_every_project_and_names_the_two_closing_groups(self):
        for project in self.projects:
            self.assertIn(f'data-proj-id="{project["id"]}"', self.html)
        # No heading over the live list — it is the chart — and one over each of
        # the two groups a project is dropped onto to close it.
        self.assertNotIn('data-group="live"', self.html)
        self.assertIn('data-group="done"', self.html)
        self.assertIn('data-group="dropped"', self.html)

    def test_the_ramp_runs_from_the_top_of_the_list_to_the_bottom(self):
        positions = re.findall(r'project-main-row[^>]*--at:([\d.]+)%', self.html)
        self.assertEqual(positions[0], '0.00')
        # Every closed project sits at the cold end, where last place would be.
        self.assertEqual(positions[-1], '100.00')
        self.assertEqual(sorted(positions, key=float), positions)

    def test_special_characters_are_escaped(self):
        self.assertIn('Designer&#x27;s name &amp; brand page &quot;phase 2&quot;', self.html)
        self.assertNotIn('Designer\'s name & brand page "phase 2"', self.html)

    def test_link_counts_match_the_stored_values(self):
        """An empty section used to claim `(1)` because of its placeholder row."""
        card = next(p for p in self.projects if p['id'] == 'project-6-designer-name')
        detail = view.render_detail_row(card, 'live', settings=self.settings)
        self.assertIn('Confluence (<span data-count="confluence_links">0</span>)', detail)
        self.assertIn('Epics (<span data-count="jira_epics">1</span>)', detail)

    def test_unknown_status_is_not_silently_replaced(self):
        card = next(p for p in self.projects if p['id'] == 'project-11-checkout-hardening')
        detail = view.render_detail_row(card, 'live', settings=self.settings)
        self.assertIn('on-hold (invalid)', detail)

    def test_dangerous_link_schemes_are_dropped(self):
        card = {'id': 'x', 'confluence': ['javascript:alert(1)']}
        detail = view.render_detail_row(card, 'live', settings=self.settings)
        self.assertNotIn('href="javascript:', detail)
        self.assertNotIn('\U0001F517 OPEN', detail)                 # no link button at all
        self.assertIn('value="javascript:alert(1)"', detail)   # kept as text, not as a link

    def test_project_without_tasks_has_a_disabled_caret(self):
        chart = gantt.render(self.projects,
                             Timeline(self.spans, settings=self.settings, today=TODAY),
                             detail_row=lambda project, group, at: '', settings=self.settings)
        button = chart.split('id="btn-toggle-proj-project-7-menu-endpoint"')[1].split('>')[0]
        self.assertIn('data-project="project-7-menu-endpoint"', button)
        self.assertIn('disabled', button)

    def test_layout_metrics_travel_as_css_variables(self):
        self.assertIn('--label-w:340px', self.html)
        self.assertIn('--col-w:17px', self.html)
        head = self.html.split('<body>')[0]
        # No external asset: everything the head names is served from /static/.
        self.assertNotIn('href="http', head)
        self.assertNotIn('src="http', head)
        self.assertIn('<script src="/static/theme.js">', head)   # before the first paint

    def test_the_logo_is_one_drawing_shown_twice(self):
        """The header and the docs page carry the same files, byte for byte."""
        self.assertIn('<img class="wordmark__logo" src="/static/logo.svg" alt="">', self.html)
        self.assertIn('<link rel="icon" href="/static/icon.svg">', self.html)
        for name in ('logo.svg', 'icon.svg'):
            with open(os.path.join(REPO_ROOT, 'ganttbit', 'static', name), 'rb') as f:
                served = f.read()
            with open(os.path.join(REPO_ROOT, 'docs', name), 'rb') as f:
                self.assertEqual(served, f.read())
            self.assertTrue(served.startswith(b'<svg xmlns="http://www.w3.org/2000/svg" viewBox='))
            self.assertLess(len(served), 4096)   # a drawing, not a trace of a bitmap

    def test_attachments_render_with_size_and_a_remove_button(self):
        card = next(p for p in self.projects if p['id'] == 'project-1-navigation-menu')
        detail = view.render_detail_row(card, 'live', settings=self.settings)
        self.assertIn('Attachments (2)', detail)
        self.assertIn('href="/api/project/project-1-navigation-menu/attachments/kickoff-notes.md"',
                      detail)
        self.assertIn('data-action="attachment-delete"', detail)
        self.assertIn('data-name="menu-mockup.png"', detail)
        empty = view.render_detail_row({'id': 'x'}, 'live', settings=self.settings)
        self.assertIn('No file attached.', empty)
        self.assertEqual(markup.human_size(1536), '1.5 KB')

    def test_markdown_is_escaped_before_it_is_transformed(self):
        """The one property that makes rendering free text safe."""
        rendered = markup.render_markdown('<script>alert(1)</script> **bold**')
        self.assertIn('&lt;script&gt;', rendered)
        self.assertNotIn('<script>', rendered)
        self.assertIn('<strong>bold</strong>', rendered)

    def test_markdown_renders_the_subset_and_nothing_else(self):
        rendered = markup.render_markdown(
            '# Heading\n\n'
            'Some **bold**, *italic* and `a*b` code.\n'
            'A second line.\n\n'
            '- one\n'
            '- two\n\n'
            'See [docs](https://x.test/a) and https://y.test/b')
        self.assertIn('<h4>Heading</h4>', rendered)
        self.assertIn('<strong>bold</strong>', rendered)
        self.assertIn('<em>italic</em>', rendered)
        self.assertIn('<code>a*b</code>', rendered)          # `*` inside code stays
        self.assertIn('A second line.', rendered.split('<br>')[1])
        self.assertIn('<ul><li>one</li><li>two</li></ul>', rendered)
        self.assertIn('<a href="https://x.test/a" target="_blank"', rendered)
        self.assertIn('>https://y.test/b</a>', rendered)     # a bare URL is a link
        self.assertEqual(markup.render_markdown('   '), '')

    def test_a_dangerous_link_never_survives_the_renderer(self):
        self.assertNotIn('javascript:',
                         markup.render_markdown('[x](javascript:alert(1))'))

    def test_markup_helpers(self):
        self.assertEqual(markup.ensure_list('a,b'), ['a,b'])        # never splits
        self.assertEqual(markup.safe_url('javascript:x'), '')
        self.assertEqual(markup.safe_url('https://x.test'), 'https://x.test')
        # A browser drops the control character and reads the scheme behind it.
        self.assertEqual(markup.safe_url('\x01javascript:alert(1)'), '')


class TokenTest(VaultTestCase):
    """The gate that stands between the write API and whatever network it is on."""

    def test_loopback_needs_no_token_but_a_public_bind_mints_one(self):
        local = settings_module.configure(vault=self.vault, host='127.0.0.1')
        self.assertEqual(local.token, '')
        public = settings_module.configure(vault=self.vault, host='0.0.0.0')
        self.assertTrue(len(public.token) >= 16)
        chosen = settings_module.configure(vault=self.vault, host='0.0.0.0', token='sesame')
        self.assertEqual(chosen.token, 'sesame')

    def test_loopback_addresses_are_recognised(self):
        for host, expected in (('127.0.0.1', True), ('localhost', True), ('::1', True),
                               ('0.0.0.0', False), ('192.168.1.5', False), ('', False)):
            self.assertIs(settings_module.is_loopback(host), expected, host)


class GatedServerTest(VaultTestCase):
    TOKEN = 'test-token-value'

    def setUp(self):
        super().setUp()
        self.settings = settings_module.configure(
            vault=self.vault, host='127.0.0.1', port=0, token=self.TOKEN)
        self.repo = ProjectRepository(settings=self.settings)
        self.httpd = create_server(self.settings, self.repo)
        self.base = 'http://127.0.0.1:%d' % self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        super().tearDown()

    def fetch(self, path, cookie=None, method='GET', body=None, redirect=True):
        opener = urllib.request.build_opener()
        if not redirect:
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *args, **kwargs):
                    return None
            opener = urllib.request.build_opener(NoRedirect)
        request = urllib.request.Request(self.base + path, data=body, method=method)
        if cookie:
            request.add_header('Cookie', cookie)
        try:
            with opener.open(request, timeout=5) as response:
                return response.status, response.read(), dict(response.headers)
        except urllib.error.HTTPError as error:
            return error.code, error.read(), dict(error.headers)

    def test_without_a_token_everything_is_refused(self):
        for path, method in (('/', 'GET'), ('/api/health', 'GET'),
                             ('/static/app.css', 'GET'),
                             ('/api/project/project-8-banner-defaults/raw', 'GET')):
            status, _, _ = self.fetch(path, method=method)
            self.assertEqual(status, 401, path)

    def test_writes_are_refused_too(self):
        status, _, _ = self.fetch('/api/project/project-8-banner-defaults/attachments/x.txt',
                                  method='PUT', body=b'data')
        self.assertEqual(status, 401)
        self.assertEqual(self.repo.list_attachments('project-8-banner-defaults'), [])

    def test_the_token_in_the_url_hands_back_a_cookie_and_a_clean_redirect(self):
        status, _, headers = self.fetch(f'/?k={self.TOKEN}&from=all', redirect=False)
        self.assertEqual(status, 302)
        self.assertEqual(headers['Location'], '/?from=all')
        self.assertIn(f'{_TOKEN_COOKIE}={self.TOKEN}', headers['Set-Cookie'])
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        self.assertIn('SameSite=Lax', headers['Set-Cookie'])
        self.assertNotIn('Secure', headers['Set-Cookie'])   # plain HTTP here

    def test_behind_an_https_proxy_the_cookie_is_marked_secure(self):
        request = urllib.request.Request(self.base + f'/?k={self.TOKEN}')
        request.add_header('X-Forwarded-Proto', 'https')

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None

        try:
            urllib.request.build_opener(NoRedirect).open(request, timeout=5)
            self.fail('expected a redirect')
        except urllib.error.HTTPError as error:
            self.assertIn('Secure', dict(error.headers)['Set-Cookie'])

    def test_the_cookie_opens_the_door(self):
        status, body, _ = self.fetch('/', cookie=f'{_TOKEN_COOKIE}={self.TOKEN}')
        self.assertEqual(status, 200)
        self.assertIn(b'GanttBit', body)

    def test_a_wrong_token_is_refused_in_url_and_cookie(self):
        self.assertEqual(self.fetch('/?k=nope', redirect=False)[0], 401)
        self.assertEqual(self.fetch('/', cookie=f'{_TOKEN_COOKIE}=nope')[0], 401)

    def test_api_refusals_speak_json(self):
        status, body, _ = self.fetch('/api/health')
        self.assertEqual(status, 401)
        self.assertEqual(json.loads(body)['success'], False)


class ServerTest(VaultTestCase):
    def setUp(self):
        super().setUp()
        self.settings = settings_module.configure(vault=self.vault, host='127.0.0.1', port=0)
        self.repo = ProjectRepository(settings=self.settings)
        self.httpd = create_server(self.settings, self.repo)
        self.base = 'http://127.0.0.1:%d' % self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        super().tearDown()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as response:
            return response.status, response.read().decode('utf-8'), dict(response.headers)

    def post(self, path, payload):
        request = urllib.request.Request(
            self.base + path, data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_dashboard_renders(self):
        status, body, headers = self.get('/')
        self.assertEqual(status, 200)
        self.assertIn('GanttBit', body)
        self.assertIn('project-1-navigation-menu', body)
        self.assertIn("default-src 'self'", headers['Content-Security-Policy'])

    def test_the_chart_opens_on_today_unless_the_url_says_otherwise(self):
        default = self.get('/')[1]
        self.assertIn('<option value="today" selected>', default)
        self.assertIn('<option value="all" selected>', self.get('/?from=all')[1])
        self.assertIn('<option value="year" selected>', self.get('/?from=year')[1])
        # a date lands in the picker beside the select
        chosen = self.get('/?from=2026-03-02')[1]
        self.assertIn('<option value="date" selected>', chosen)
        self.assertIn('id="window-date" aria-label="Show from this date" value="2026-03-02"',
                      chosen)

    def test_health_and_schema_endpoints(self):
        self.assertEqual(json.loads(self.get('/api/health')[1])['status'], 'ok')
        payload = json.loads(self.get('/api/schema')[1])
        self.assertTrue(payload['success'])
        self.assertEqual([section['key'] for section in payload['sections']][0], 'general')

    def test_raw_endpoint_returns_data_body_and_text(self):
        payload = json.loads(self.get('/api/project/project-1-navigation-menu/raw')[1])
        self.assertEqual(payload['data']['id'], 'project-1-navigation-menu')
        self.assertIn('Phase 1', payload['body'])
        self.assertTrue(payload['raw_text'].startswith('# Navigation menu'))

    def test_the_hierarchy_page_and_its_snapshot(self):
        status, body, _ = self.get('/hierarchy')
        self.assertEqual(status, 200)
        self.assertIn('Structure', body)
        self.assertIn('id="vault-markdown"', body)
        # The live list is the tree; only a closing group announces itself.
        self.assertIn('>DONE ', body)
        self.assertIn('>DROPPED ', body)

        status, snapshot, headers = self.get('/api/vault/markdown')
        self.assertEqual(status, 200)
        self.assertIn('attachment; filename="vault-', headers['Content-Disposition'])
        self.assertTrue(snapshot.startswith('# Navigation menu'))

    def test_settings_names_the_version_and_what_shipped_in_it(self):
        body = self.get('/')[1]
        self.assertIn(f'<span class="settings-about__version">{__version__}</span>', body)
        # the notes are the CHANGELOG section of the running version, rendered
        # rather than linked to: whatever it says this release, it is in the page
        self.assertIn('settings-about__notes', body)
        notes = settings_module.release_notes(__version__)
        self.assertTrue(notes)
        self.assertIn(markup.render_markdown(notes), body)

    def test_the_releases_link_leaves_but_the_application_never_does(self):
        body, headers = self.get('/')[1:]
        self.assertIn(f'href="{settings_module.RELEASES_URL}"', body)
        self.assertIn('rel="noopener noreferrer"', body)
        # a link the browser follows on a click, never a request this page makes:
        # the policy still allows nothing but this origin to be reached.
        policy = headers['Content-Security-Policy']
        self.assertIn("default-src 'self'", policy)
        self.assertNotIn('connect-src', policy)
        self.assertNotIn('github.com', policy)

    def test_static_assets_are_served_and_traversal_is_blocked(self):
        self.assertIn('GanttBit', self.get('/static/app.css')[1])
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get('/static/../../settings.toml')
        self.assertEqual(caught.exception.code, 404)

    def test_post_update_round_trip(self):
        status, payload = self.post('/api/project/project-8-banner-defaults/update',
                                    {'status': 'blocked', 'blocked_reason': 'vendor'})
        self.assertEqual((status, payload['success']), (200, True))
        self.assertEqual(self.repo.load('project-8-banner-defaults')[0]['status'], 'blocked')

    def test_post_invalid_payload_is_rejected_with_a_message(self):
        status, payload = self.post('/api/project/project-8-banner-defaults/update',
                                    {'status': 'nope'})
        self.assertEqual(status, 400)
        self.assertIn('Allowed', payload['error'])

    def test_unknown_endpoint(self):
        self.assertEqual(self.post('/api/nope', {})[0], 404)

    def send(self, method, path, body=None, content_type='application/octet-stream'):
        request = urllib.request.Request(
            self.base + path, data=body, method=method,
            headers={'Content-Type': content_type} if body is not None else {})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.read(), dict(response.headers)
        except urllib.error.HTTPError as error:
            return error.code, error.read(), dict(error.headers)

    def test_attachment_round_trip_over_http(self):
        url = '/api/project/project-8-banner-defaults/attachments/palette%20v2.png'
        status, body, _ = self.send('PUT', url, b'\x89PNG fake', 'image/png')
        self.assertEqual(status, 200, body)

        status, body, headers = self.send('GET', url)
        self.assertEqual((status, body), (200, b'\x89PNG fake'))
        self.assertEqual(headers['Content-Type'], 'image/png')
        self.assertTrue(headers['Content-Disposition'].startswith('inline;'))
        self.assertIn("filename*=UTF-8''palette%20v2.png", headers['Content-Disposition'])

        self.assertEqual(self.send('PUT', url, b'again', 'image/png')[0], 409)
        self.assertEqual(self.send('DELETE', url)[0], 200)
        self.assertEqual(self.send('GET', url)[0], 404)
        self.assertEqual(self.send('DELETE', url)[0], 404)

    def test_active_content_is_served_as_a_download(self):
        for name in ('page.html', 'logo.svg'):
            url = f'/api/project/project-8-banner-defaults/attachments/{name}'
            self.assertEqual(self.send('PUT', url, b'<svg onload=alert(1)>')[0], 200)
            _, _, headers = self.send('GET', url)
            self.assertTrue(headers['Content-Disposition'].startswith('attachment;'), name)
            self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')

    def test_attachment_upload_limits_and_traversal(self):
        big = b'x' * (self.settings.max_upload_bytes + 1)
        status, body, _ = self.send('PUT', '/api/project/project-8-banner-defaults/attachments/big.bin', big)
        self.assertEqual(status, 413)
        status, _, _ = self.send('PUT', '/api/project/project-8-banner-defaults/attachments/..%2F..%2Fcard.md', b'x')
        self.assertIn(status, (400, 404))
        self.assertFalse(os.path.exists(os.path.join(self.vault, 'card.md')))
        status, _, _ = self.send('PUT', '/api/project/ghost/attachments/a.txt', b'x')
        self.assertEqual(status, 404)


if __name__ == '__main__':
    unittest.main(verbosity=2)
