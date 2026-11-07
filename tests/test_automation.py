from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import lanzador
import guardados as g


def flow(order, name, status='SUCCESS'):
    return {'kind': 'native_flow_complete', 'flow': name, 'order': order,
            'native_status': status, 'arg0': '0' if status == 'SUCCESS' else '16'}


def capture(order, sha):
    return {'kind': 'complete_DATA_crc_valid', 'event': {'order': order}, 'sha256': sha}


class AutomaticSaves(unittest.TestCase):
    def setUp(self):
        self.session = g.AutomaticSession(SimpleNamespace(pid=7, creation=11),
                                          {'career_inventory_before': {'a': 'known'}})
        self.load = [flow(1, g.LIST), capture(2, 'known'), flow(3, g.LOAD)]
        self.registered = {'known': {'career_id': 'uuid'}, 'other': {'career_id': 'other-uuid'}}

    def apply(self, events, inventory, trusted=True):
        with (
            patch.object(g.carreras, 'ACTIVE', Path('disposable-profile')),
            patch.object(g.identity, 'lookup', side_effect=self.registered.get),
            patch.object(g.carreras, 'bind', side_effect=lambda path, ev, **k: {'sha': k['expected_sha']}) as bind,
            patch.object(self.session.inventory, 'refresh', return_value=inventory),
            patch.object(g.time, 'monotonic', return_value=1.) as clock,
        ):
            self.session.update(events, trusted)
            clock.return_value = 2.
            self.session.update(events, trusted)
        return bind

    def test_automatic_save_as_uses_confirmed_load_across_list(self):
        events = self.load + [flow(4, g.LIST), flow(5, g.USER_SAVE),
                              flow(6, 'ProgressSaveFlowComplete')]
        bind = self.apply(events, {'a': 'known', 'b': 'new'})
        self.assertEqual(bind.call_args.kwargs['parent'], 'known')
        self.assertEqual(self.session.head, 'new')
        self.assertEqual(self.session.last_flow['mode'], 'new_slot')

    def test_late_capture_recovers_the_completed_load(self):
        read = {'kind': 'data_read', 'event': {'order': 2, 'requested': 6_000_000}}
        partial = [flow(1, g.LIST), read, flow(3, g.LOAD)]
        self.apply(partial, {'a': 'known'})
        self.assertIsNone(self.session.head)
        events = partial + [capture(2, 'known'), flow(4, g.LIST), flow(5, g.USER_SAVE)]
        bind = self.apply(events, {'a': 'next'})
        self.assertEqual(bind.call_args.kwargs['parent'], 'known')
        self.assertEqual(self.session.head, 'next')

    def test_late_capture_cannot_restore_a_career_after_quit(self):
        partial = [flow(1, g.LIST), flow(3, g.LOAD), flow(4, g.QUIT)]
        self.apply(partial, {'a': 'known'})
        self.apply(partial + [capture(2, 'known')], {'a': 'known'})
        self.assertIsNone(self.session.head)

    def test_overwrite_and_autosave_use_current_head(self):
        for trigger in (g.USER_SAVE, 'ProgressSaveFlowComplete'):
            with self.subTest(trigger=trigger):
                self.setUp()
                bind = self.apply(self.load + [flow(4, trigger)], {'a': 'next'})
                self.assertEqual(bind.call_args.kwargs['parent'], 'known')
                self.assertEqual(self.session.last_flow['mode'], 'overwrite')

    def test_new_career_and_unknown_load_are_distinguished(self):
        first_day = {'season': 1, 'date': 20150701, 'calendar': {'setupdate': 20150701},
                     'records': [], 'save_label': 'New Career'}
        with patch.object(g.carreras, 'inspect', return_value=first_day):
            squads = {'kind': 'data_read', 'event': {'order': 5, 'requested': 2000, 'actual': 2000,
                      'file_end': 2116, 'prefix': b'SaveType_Squads\0'.hex()}}
            events = self.load + [flow(4, g.QUIT), squads, flow(6, g.AUTOLOAD), flow(7, g.USER_SAVE)]
            bind = self.apply(events, {'a': 'known', 'b': 'new'})
            self.assertIsNone(bind.call_args.kwargs['parent'])
            self.assertEqual(self.session.last_flow['result'], 'automatic_root')
            self.setUp()
            events = [flow(1, g.LIST), capture(2, 'unknown'), flow(3, g.LOAD), flow(4, g.USER_SAVE)]
            self.apply(events, {'a': 'known', 'b': 'new'}).assert_not_called()

    def test_preview_and_uncertain_changes_do_not_bind(self):
        for events, after in (
            ([flow(1, g.LIST), capture(2, 'known'), flow(3, g.USER_SAVE)], {'a': 'new'}),
            (self.load + [flow(4, g.QUIT), flow(5, g.USER_SAVE)], {'a': 'new'}),
            (self.load + [flow(4, g.USER_SAVE)], {'a': 'new', 'b': 'other-new'}),
            (self.load + [flow(4, g.USER_SAVE)], {'a': 'other'}),
            (self.load + [{'kind': 'overrun', 'lost_flows_at_least': 1, 'through_order': 4},
                          flow(5, g.USER_SAVE)], {'a': 'new'}),
        ):
            self.setUp()
            self.apply(events, after).assert_not_called()
            self.assertIsNone(self.session.head)

    def test_load_supersedes_save_from_previous_career(self):
        events = self.load + [flow(4, g.USER_SAVE), flow(5, g.QUIT),
                              flow(6, g.LIST), capture(7, 'other'), flow(8, g.LOAD)]
        self.apply(events, {'a': 'new'}).assert_not_called()
        self.assertEqual(self.session.head, 'other')

    def test_failed_or_multiple_manual_notifications_are_not_autosaves(self):
        for notifications in ([flow(4, g.USER_SAVE, 'FAILURE')],
                              [flow(4, g.USER_SAVE), flow(5, g.USER_SAVE)]):
            self.setUp()
            self.apply(self.load + notifications + [flow(6, 'ProgressSaveFlowComplete')],
                       {'a': 'new'}).assert_not_called()
            self.assertIsNone(self.session.head)

    def test_confirmed_independent_root_reuses_only_known_league_name(self):
        data = {'source': 'unittest/DATA', 'club': 1, 'season': 1, 'date': 20150701,
                'save_label': 'Test', 'records': [],
                'user': {'primarycompobjid': 773, 'leagueid': 13}}
        with TemporaryDirectory() as tmp, patch.object(g.carreras, 'DB', Path(tmp)/'registry.sqlite'):
            with patch.object(g.carreras, 'inspect', return_value=data | {'sha': 'old'}):
                old = g.carreras.bind(None, 'test', label='Old')
            g.carreras.classify(old['career'], 1, 773, 'Premier League', 'league', 'test')
            with patch.object(g.carreras, 'inspect', return_value=data | {'sha': 'new'}):
                new = g.carreras.bind(None, 'test', label='New', expected_sha='new', known_league=True)
            self.assertNotEqual(old['career'], new['career'])
            with g.carreras.connect() as db:
                row = db.execute('SELECT label FROM competition_rules WHERE career=?', (new['career'],)).fetchone()
                self.assertEqual(row['label'], 'Premier League')
                self.assertFalse(db.execute('SELECT * FROM decoder_certifications WHERE career=?',
                                            (new['career'],)).fetchall())

    def test_monitor_exit_during_game_shutdown_is_normal(self):
        game = Mock(pid=7, returncode=0)
        game.poll.side_effect = [None, None, 0]
        worker = Mock()
        worker.poll.return_value = worker.wait.return_value = 0
        with (TemporaryDirectory() as tmp,
              patch.object(lanzador, 'native_ready', return_value=True),
              patch.object(lanzador.subprocess, 'Popen', return_value=worker)):
            lanzador.supervise(game, ['python.exe', 'worker.py'], Path(tmp)/'worker.log')
        worker.wait.assert_called_once()


if __name__ == '__main__':
    unittest.main()
