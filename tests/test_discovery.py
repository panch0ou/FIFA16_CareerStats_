from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest
from unittest.mock import patch

import desktop
import discovery
import launch
import layout


class Discovery(unittest.TestCase):
    def setUp(self):
        layout.LOCAL.mkdir(exist_ok=True)
        self.tmp = TemporaryDirectory(dir=layout.LOCAL)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.game = self.root/'EA Games/FIFA 16'
        self.game.mkdir(parents=True)
        (self.game/'fifa16.exe').write_bytes(b'disposable test file')
        self.profile = self.root/'Redirected Documents/FIFA 16'
        (self.profile/'0/FIFA16').mkdir(parents=True)

    def test_game_candidates_include_saved_registry_and_standard_paths_once(self):
        registry_game = self.root/'Registry Install'
        registry_game.mkdir()
        (registry_game/'fifa16.exe').write_bytes(b'disposable registry file')
        with (patch.dict(os.environ, {'ProgramW6432': str(self.root)}),
              patch.object(discovery, 'registry_paths', return_value=iter((registry_game, self.game)))):
            paths = discovery.games(str(self.game))
        self.assertEqual(paths[:2], [self.game, registry_game])
        self.assertEqual(paths.count(self.game), 1)

    def test_redirected_documents_and_onedrive_profile(self):
        one = self.root/'Cloud/Documents/FIFA 16'
        (one/'0/FIFA16').mkdir(parents=True)
        with (patch.object(layout, 'documents_profile', return_value=self.profile),
              patch.dict(os.environ, {'OneDrive': str(self.root/'Cloud')})):
            self.assertEqual(discovery.profiles()[:2], [self.profile, one])

    def test_choice_prefers_compatible_installation_on_first_run(self):
        invalid = self.root/'Unverified'
        statuses = {invalid: ('Incompatible', False), self.game: ('Compatible', True)}
        with patch.object(desktop, 'game_status', side_effect=statuses.get):
            self.assertEqual(desktop.choose_initial([invalid, self.game], None),
                             (self.game, ('Compatible', True)))
            self.assertEqual(desktop.choose_initial([invalid, self.game], str(invalid)),
                             (invalid, ('Incompatible', False)))

    def test_first_setup_persists_selected_folders_and_recovery_blocks_launch(self):
        state = self.root/'state'
        state.mkdir()
        settings = state/'settings.json'
        journal = state/'journal.json'
        with (patch.multiple(layout, LOCAL=state, SETTINGS=settings, JOURNAL=journal),
              patch.object(desktop.discovery, 'games', return_value=[self.game]),
              patch.object(desktop.discovery, 'profiles', return_value=[self.profile]),
              patch.object(desktop, 'game_status', return_value=('Compatible', True)),
              patch.object(launch, 'check_components'), patch.object(launch, 'closed')):
            self.assertTrue(desktop.inspect_setup(None, None)['ready'])
            self.assertEqual(layout.read(settings),
                             {'game': str(self.game), 'profile': str(self.profile)})
            journal.write_text('{}', encoding='utf-8')
            result = desktop.inspect_setup(None, None)
            self.assertTrue(result['pending'])
            self.assertFalse(result['ready'])

    def test_manually_selected_incompatible_folder_stays_disabled(self):
        invalid = self.root/'Manual folder'
        invalid.mkdir()
        with (patch.object(desktop.discovery, 'games', return_value=[self.game]),
              patch.object(desktop.discovery, 'profiles', return_value=[self.profile]),
              patch.object(desktop, 'game_status', return_value=('Incompatible', False)),
              patch.object(desktop, 'saved_folders', return_value={}),
              patch.object(launch, 'check_components')):
            result = desktop.inspect_setup(invalid, self.profile)
        self.assertEqual(result['game'], invalid)
        self.assertFalse(result['ready'])


if __name__ == '__main__':
    unittest.main()
