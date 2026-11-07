from contextlib import closing
from pathlib import Path
import json
import shutil
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import career_import
import carreras
import career_schema
import datos
import guardados as g
import layout
from test_automation import capture, flow
from test_compatibility import CLUB, PLAYER, make_save, write_metadata


class ImportCareer(unittest.TestCase):
    def setUp(self):
        layout.LOCAL.mkdir(exist_ok=True)
        tmp = TemporaryDirectory(dir=layout.LOCAL)
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.active = self.root/'FIFA 16'
        self.archive = self.root/'External saves'
        self.archive.mkdir()
        self.db = self.root/'career.sqlite'
        schema = self.root/'fifa-meta.xml'
        write_metadata(schema)
        patcher = patch.multiple(carreras, DB=self.db, ACTIVE=self.active, SCHEMA=career_schema.load(schema),
                                  LEAGUES={(13, 773, 'England Premier League (1)', 14, 1): 'Fixture league'})
        patcher.start()
        self.addCleanup(patcher.stop)

    def fixture(self, name, day, *, goals=2, season=1, club=CLUB, assists=2):
        path = self.archive/name
        path.write_bytes(make_save(day, club=club, season=season, goals=goals,
                                   assist_groups={773: [assists]+[0]*7}))
        return path

    def preview(self, *paths, parent=None):
        return career_import.preview_import([carreras.inspect_external(p) for p in paths], parent)

    def count(self, table):
        with carreras.connect() as db:
            return db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]

    def player_rows(self, head):
        return [r for r in carreras.history(head)['official_player_rows'] if r['player_id'] == PLAYER]

    def test_single_advanced_save_and_cancel_is_read_only(self):
        save = self.fixture('January checkpoint.sav', 20180103, season=3)
        before = save.read_bytes()
        plan = self.preview(save)
        self.assertEqual(plan.seasons, ((3, 8, 8, 8, 8, 0),))
        self.assertTrue(any('earlier seasons' in w for w in plan.warnings))
        self.assertFalse(self.db.exists())
        result = career_import.commit_import(plan)
        self.assertEqual(self.player_rows(result.head)[0]['assists'], 2)
        self.assertEqual(save.read_bytes(), before)

    def test_accumulated_values_and_seasons_are_not_added(self):
        a = self.fixture('Week 10', 20151001, goals=3, assists=1)
        b = self.fixture('Week 20', 20160101, goals=7, assists=4)
        c = self.fixture('Season 2', 20160710, season=2, goals=1, assists=0)
        result = career_import.commit_import(self.preview(a, b, c))
        self.assertEqual(result.added, 3)
        self.assertEqual({r['season']: (r['goals'], r['assists']) for r in self.player_rows(result.head)},
                         {1: (7, 4), 2: (1, 0)})
        self.assertEqual(self.count('careers'), 1)
        with closing(career_import.open_preview()) as db:
            self.assertEqual(len(career_import.registered_saves(db)), 3)

    def test_decrease_warns_and_latest_wins(self):
        a = self.fixture('Earlier', 20151001, goals=7)
        b = self.fixture('Later', 20151101, goals=3)
        plan = self.preview(a, b)
        self.assertTrue(any('values decrease' in w for w in plan.warnings))
        self.assertEqual(self.player_rows(career_import.commit_import(plan).head)[0]['goals'], 3)
        with self.assertRaisesRegex(ValueError, 'moves backwards'):
            self.preview(b, a)

    def test_idempotent_hash_and_explicit_continuation(self):
        a = self.fixture('Original', 20151001)
        alias = self.archive/'Renamed'
        shutil.copyfile(a, alias)
        first = career_import.commit_import(self.preview(a, alias))
        second = career_import.commit_import(self.preview(alias))
        self.assertEqual((first.added, first.reused, second.added, second.reused), (1, 1, 0, 1))
        self.assertEqual(first.head, second.head)
        b = self.fixture('Later', 20151101)
        later = career_import.commit_import(self.preview(b, parent=first.head))
        self.assertEqual(self.count('careers'), 1)
        self.assertEqual(carreras.history(later.head)['ancestry'], [later.head, first.head])
        self.assertEqual(self.count('snapshots'), 2)

    def test_earlier_saves_can_be_added_before_a_selected_registered_root(self):
        later = self.fixture('Original root', 20160710, season=2)
        first = career_import.commit_import(self.preview(later))
        next_save = self.fixture('Continuation', 20160711, season=2)
        tip = career_import.commit_import(self.preview(next_save, parent=first.head))
        early = self.fixture('Season 1', 20151101, goals=7)
        plan = self.preview(early, later)
        self.assertTrue(any('before the first' in w for w in plan.warnings))
        with self.assertRaisesRegex(ValueError, 'capacity'):
            def invalid(_, __):
                raise ValueError('capacity exceeded')
            career_import.commit_import(plan, invalid)
        self.assertEqual(carreras.history(tip.head)['ancestry'], [tip.head, first.head])
        affected = []
        career_import.commit_import(plan, lambda sha, _: affected.append(sha))
        self.assertIn(tip.head, affected)
        self.assertEqual(self.count('careers'), 1)
        self.assertEqual({r['season']: r['goals'] for r in self.player_rows(tip.head)}, {1: 7, 2: 2})

    def test_separate_careers_and_branches_are_not_reassigned(self):
        a = self.fixture('A', 20151001)
        b = self.fixture('B', 20151002)
        first = career_import.commit_import(self.preview(a))
        second = career_import.commit_import(self.preview(b))
        with self.assertRaisesRegex(ValueError, 'different Careers'):
            self.preview(a, b)
        with self.assertRaisesRegex(ValueError, 'different Careers'):
            self.preview(b, parent=first.head)
        self.assertEqual(self.count('careers'), 2)
        self.assertNotEqual(first.head, second.head)
        branch_a = self.fixture('Branch A', 20151101, goals=1)
        branch_b = self.fixture('Branch B', 20151101, goals=2)
        career_import.commit_import(self.preview(branch_a, parent=first.head))
        career_import.commit_import(self.preview(branch_b, parent=first.head))
        with self.assertRaisesRegex(ValueError, 'different branch'):
            self.preview(branch_a, branch_b)

    def test_incompatible_changed_and_capacity_failure_are_atomic(self):
        bad = self.archive/'Incomplete'
        bad.write_bytes(b'not a save')
        [(path, value, message)] = career_import.read_candidates([bad])
        self.assertIsNone(value)
        self.assertIn('not a FIFA 16 Career', message)
        a = self.fixture('A', 20151001)
        b = self.fixture('B', 20151101)
        plan = self.preview(a, b)
        original = b.read_bytes()
        b.write_bytes(make_save(20151102))
        with self.assertRaisesRegex(ValueError, 'changed after preview'):
            career_import.commit_import(plan)
        self.assertFalse(self.db.exists())
        b.write_bytes(original)

        def reject(_, db):
            self.assertEqual(db.execute('SELECT count(*) FROM snapshots').fetchone()[0], 2)
            raise ValueError('Screen capacity exceeded')

        with self.assertRaisesRegex(ValueError, 'capacity'):
            career_import.commit_import(plan, reject)
        self.assertEqual(self.count('snapshots'), 0)
        self.assertEqual(self.count('careers'), 0)

    def test_imported_career_continues_through_native_load_and_save(self):
        imported = self.fixture('Archive', 20160710, season=2)
        start = career_import.commit_import(self.preview(imported))
        slot = self.active/'0/FIFA16/slot/DATA'
        slot.parent.mkdir(parents=True)
        shutil.copyfile(imported, slot)
        key = str(slot.relative_to(self.active))
        session = g.AutomaticSession(SimpleNamespace(pid=1, creation=1),
                                     {'career_inventory_before': {key: start.head}})
        events = [capture(1, start.head), flow(2, g.LOAD)]
        session.update(events, True)
        slot.write_bytes(make_save(20160711, season=2, goals=4, assist_groups={773: [3]+[0]*7}))
        events += [flow(3, g.USER_SAVE)]
        with patch.object(g.time, 'monotonic') as clock:
            clock.return_value = 1
            session.update(events, True)
            clock.return_value = 2
            session.update(events, True)
        self.assertEqual(carreras.history(session.head)['ancestry'][1], start.head)
        row = self.player_rows(session.head)[0]
        self.assertEqual((row['goals'], row['assists']), (4, 3))
        self.assertEqual(self.count('careers'), 1)

    def test_overlapping_club_rows_are_not_summed_in_player_history(self):
        a = self.fixture('Team 1', 20151001, goals=3)
        b = self.fixture('Team 2', 20151101, club=CLUB+1, goals=7)
        plan = self.preview(a, b)
        self.assertTrue(any('overlap across clubs' in w for w in plan.warnings))
        result = career_import.commit_import(plan)
        inputs = layout.INPUTS
        with patch.multiple(datos, HISTORICAL_DB=inputs/'historial_ampliado.sqlite',
                            BASELINE=inputs/'club_records.json'):
            buckets, _, _ = datos.Source().snapshot(result.head)
        row = next(r for r in buckets[PLAYER % datos.BUCKETS] if r.startswith(f'{PLAYER}|'))
        self.assertEqual(row.count('15/16~-~-~-~-~'), 2)
        self.assertEqual(row.split('|')[4], '-       -       -')

    def test_departed_player_retains_earlier_snapshot(self):
        before = self.fixture('Before transfer', 20151001, goals=3, assists=1)
        after = self.archive/'After transfer'
        after.write_bytes(make_save(20151101, transferred=True, goals=7,
                                    assist_groups={773: [4]+[0]*7}))
        result = career_import.commit_import(self.preview(before, after))
        row, = self.player_rows(result.head)
        self.assertEqual((row['goals'], row['assists']), (3, 1))

    def test_all_identified_competitions_match_normal_tracking_and_continue(self):
        catalog = {group: {'code': code, 'label': label, 'category': category}
                   for group, code, label, category in (
                       (773, 'C13', 'Fixture league', 'league'),
                       (951, 'C201', 'Fixture cup', 'domestic_cup'),
                       (955, 'C224', 'Fixture continental', 'continental'))}
        paths = []
        for name, date, season, goals, assists in (
                ('Early', 20151001, 1, 3, 1), ('Late', 20160501, 1, 7, 4),
                ('Next season', 20161001, 2, 2, 0)):
            path = self.archive/name
            path.write_bytes(make_save(date, season=season, goals=goals, clean_sheets=2,
                assist_groups={group: [assists]+[0]*7 for group in (773, 951, 955, 999)},
                competition_progress=[(951, 'C201', CLUB, season), (955, 'C224', CLUB, season)]))
            paths.append(path)

        def normalized(head):
            return sorted((r['season'], r['club_id'], r['group_raw'], r['player_id'],
                           r['competition'], r['apps'], r['goals'], r['assists'], r['clean_sheets'])
                          for r in carreras.history(head)['official_player_rows'])

        with patch.object(carreras, 'COMPETITIONS', catalog):
            single = self.preview(paths[0])
            self.assertEqual(single.seasons, ((1, 24, 24, 24, 24, 0),))
            self.assertTrue(any('999' in w for w in single.warnings))
            result = career_import.commit_import(self.preview(*paths))
            imported = normalized(result.head)
            self.assertEqual(len(imported), 48)
            self.assertEqual({r['season']: {v['group_raw'] for v in self.player_rows(result.head)
                                          if v['season'] == r['season']}
                              for r in self.player_rows(result.head)}, {1: {773, 951, 955}, 2: {773, 951, 955}})
            self.assertEqual({(r['season'], r['goals'], r['assists'])
                              for r in self.player_rows(result.head)}, {(1, 7, 4), (2, 2, 0)})
            self.assertEqual(career_import.commit_import(self.preview(*paths)).added, 0)
            self.assertEqual(normalized(result.head), imported)
            self.active.mkdir(parents=True)
            slot = self.active/'0/FIFA16/slot/DATA'
            slot.parent.mkdir(parents=True)
            with patch.object(carreras, 'DB', self.root/'normal.sqlite'):
                parent = None
                for path in paths:
                    shutil.copyfile(path, slot)
                    tracked = carreras.bind(slot, 'Fixture native load/save', parent=parent,
                                            label=None if parent else 'Tracked Career', known_league=True)
                    parent = tracked['sha']
                self.assertEqual(normalized(parent), imported)

            shutil.copyfile(paths[-1], slot)
            key = str(slot.relative_to(self.active))
            session = g.AutomaticSession(SimpleNamespace(pid=1, creation=1),
                                         {'career_inventory_before': {key: result.head}})
            events = [capture(1, result.head), flow(2, g.LOAD)]
            session.update(events, True)
            slot.write_bytes(make_save(20161101, season=2, goals=5,
                                      assist_groups={k: [3]+[0]*7 for k in catalog}))
            events.append(flow(3, g.USER_SAVE))
            with patch.object(g.time, 'monotonic') as clock:
                clock.return_value = 1
                session.update(events, True)
                clock.return_value = 2
                session.update(events, True)
            self.assertEqual({(r['season'], r['goals'], r['assists'])
                              for r in self.player_rows(session.head)}, {(1, 7, 4), (2, 5, 3)})
            self.assertEqual(len(normalized(session.head)), 48)
            carreras.verify_field(session.head, 951, PLAYER, 'clean_sheets', 0, 'Fixture exact check')
            self.assertEqual(next(r for r in self.player_rows(session.head)
                                  if r['season'] == 2 and r['group_raw'] == 951)['clean_sheets'], 0)
            carreras.verify_field(result.head, 951, PLAYER, 'clean_sheets', 2, 'Fixture positive check')
            carreras.certify_field(result.head, 951, PLAYER, 'clean_sheets', 'Fixture decoder evidence')
            self.assertEqual({r['season']: r['clean_sheets'] for r in self.player_rows(session.head)
                              if r['group_raw'] == 951}, {1: 2, 2: 0})

    def test_old_registries_recover_cup_rows_and_conflicting_native_ids_are_withheld(self):
        cup = {951: {'code': 'C201', 'label': 'Fixture cup', 'category': 'domestic_cup'}}
        path = self.archive/'Old import'
        path.write_bytes(make_save(20151001, assist_groups={773: [1]*8, 951: [2]*8}))
        result = career_import.commit_import(self.preview(path))
        with carreras.connect() as db:
            stored = db.execute('SELECT metadata FROM snapshots WHERE sha=?', (result.head,)).fetchone()
            metadata = json.loads(stored[0])
            del metadata['native_competitions']
            del metadata['competition_progress']
            db.execute('UPDATE snapshots SET metadata=? WHERE sha=?', (json.dumps(metadata), result.head))
        with patch.object(carreras, 'COMPETITIONS', cup):
            self.assertEqual({r['group_raw'] for r in self.player_rows(result.head)}, {773, 951})
            conflicting = self.archive/'Different object'
            conflicting.write_bytes(make_save(20151002, assist_groups={951: [2]*8},
                                               competition_progress=[(951, 'C999', CLUB, 1)]))
            value = carreras.inspect_external(conflicting)
            self.assertEqual(value['native_competitions'], {})
            plan = self.preview(conflicting, parent=result.head)
            self.assertTrue(any('951' in w for w in plan.warnings))


if __name__ == '__main__':
    unittest.main()
