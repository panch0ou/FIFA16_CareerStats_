from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import subprocess
import unittest
from unittest.mock import Mock, patch

import archivos
import carreras
import launch
import layout
from archivos import digest


@contextmanager
def workspace():
    local = layout.ROOT/'.local'
    local.mkdir(exist_ok=True)
    with TemporaryDirectory(dir=local) as folder:
        root = Path(folder)
        game, profile = root/'game', root/'profile'
        game.mkdir()
        (profile/'0/FIFA16/slot').mkdir(parents=True)
        (profile/'0/FIFA16/slot/DATA').write_bytes(b'Synthetic read-only save fixture')
        payload = root/'payload'
        payload.mkdir()
        entries = []
        for index, relative in enumerate(layout.RESOURCES.values()):
            source = payload/f'{index}.big'
            source.write_bytes(b'Synthetic screen '+bytes([index]))
            entries.append((relative.as_posix(), source, None, digest(source)))
        yield root, game, profile, entries


class ReleaseLifecycle(unittest.TestCase):
    def test_wrong_game_path_and_modified_executable_fail_before_writes(self):
        with workspace() as (root, game, profile, _):
            with self.assertRaises(ValueError):
                layout.validated_locations(root/'wrong-game', profile)
            (game/'fifa16.exe').write_bytes(b'Unsupported')
            with self.assertRaisesRegex(RuntimeError, 'SHA-256 does not match'):
                launch.check_game(game)
            self.assertFalse((profile/'cache0').exists())

    def test_pending_session_recovers_without_requiring_payload(self):
        with workspace() as (root, _, profile, entries):
            journal = root/'journal.json'
            archivos.apply(profile, entries, journal)
            (profile/entries[1][0]).unlink()
            for _, source, _, _ in entries:
                source.unlink()
            with patch.object(layout, 'JOURNAL', journal), patch.object(launch, 'closed'):
                launch.recover(profile)
            self.assertFalse(journal.exists())
            self.assertFalse(any((profile/name).exists() for name in layout.CACHE_PATHS))
            self.assertEqual((profile/'0/FIFA16/slot/DATA').read_bytes(),
                             b'Synthetic read-only save fixture')

    def test_recovery_refuses_to_remove_an_unknown_screen(self):
        with workspace() as (root, _, profile, entries):
            journal = root/'journal.json'
            archivos.apply(profile, entries, journal)
            replaced = profile/entries[0][0]
            replaced.write_bytes(b'Another mod')
            with (patch.object(layout, 'JOURNAL', journal), patch.object(launch, 'closed'),
                  self.assertRaisesRegex(RuntimeError, 'Unrecognized or modified file')):
                launch.recover(profile)
            self.assertTrue(journal.exists())
            self.assertEqual(replaced.read_bytes(), b'Another mod')
            self.assertTrue((profile/entries[1][0]).is_file())

    def test_first_play_creates_registry_and_removes_screens_on_exit(self):
        with workspace() as (root, game, profile, entries):
            journal, db = root/'journal.json', root/'career.sqlite'
            log_dir = root/'logs'
            log_dir.mkdir()
            process = Mock(pid=123, returncode=0)
            process.poll.return_value = 0
            with (patch.object(layout, 'JOURNAL', journal), patch.object(carreras, 'DB', db),
                  patch.object(launch, 'preflight'), patch.object(launch, 'closed'),
                  patch.object(launch, 'configure_runtime'),
                  patch.object(launch, 'new_log_dir', return_value=log_dir),
                  patch.object(launch, 'validate_views', return_value=entries),
                  patch.object(launch.subprocess, 'Popen', return_value=process) as start,
                  patch.object(launch.lanzador, 'supervise') as supervise):
                launch.play(game, profile)
            start.assert_called_once_with([str(game/'fifa16.exe')], cwd=game)
            supervise.assert_called_once()
            self.assertEqual(json.loads((log_dir/'launch.json').read_text())['pid'], 123)
            self.assertFalse(journal.exists())
            self.assertFalse(any((profile/name).exists() for name in layout.CACHE_PATHS))
            with patch.object(carreras, 'DB', db), carreras.connect() as connection:
                self.assertEqual(connection.execute('SELECT count(*) FROM snapshots').fetchone()[0], 0)

    def test_hidden_supervisor_uses_worker_command_once(self):
        process = Mock(pid=123, returncode=0)
        process.poll.side_effect = [None, 0]
        worker = Mock()
        worker.wait.return_value = 0
        with (workspace() as (root, _, _, _),
              patch.object(launch.lanzador, 'native_ready', return_value=True),
              patch.object(launch.subprocess, 'Popen', return_value=worker) as start):
            launch.lanzador.supervise(process, ['python.exe', 'worker.py'], root/'worker.log')
        self.assertEqual(start.call_args.args[0], ['python.exe', 'worker.py', '123'])
        self.assertEqual(start.call_args.kwargs['creationflags'], subprocess.CREATE_NO_WINDOW)


if __name__ == '__main__':
    unittest.main()

