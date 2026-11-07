"""Paths and the pinned 2015/16 compatibility profile."""
import ctypes
import json
import os
from pathlib import Path
import sys

from archivos import fingerprint, target

FROZEN = getattr(sys, 'frozen', False)
ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parents[1]
LOCAL = Path(os.environ['LOCALAPPDATA']) / 'FIFA16CareerStats' if FROZEN else ROOT / '.local'
SETTINGS = LOCAL / 'settings.json'
DATA = ROOT / 'Data'
INPUTS = DATA if FROZEN or (DATA/'historial_ampliado.sqlite').is_file() else LOCAL / 'inputs'
PAYLOAD = LOCAL / 'payload'
HELPERS = ROOT / 'Runtime/Helpers' if FROZEN else LOCAL / 'helpers'
OBSERVER = HELPERS / 'observer_v5.dll'
RUNTIME_MANIFEST = DATA / 'runtime-manifest.json' if FROZEN else HELPERS / 'runtime-manifest.json'
JOURNAL = LOCAL / 'temporary-screens.json'
PROFILE_FILE = (DATA if FROZEN else ROOT / 'profiles') / 'fifa16-2015-16.json'
SCREEN = Path('cache0/data/ui/game/screens/career')
RESOURCES = {
    'PlayerHistory12D_Ampliado': SCREEN / 'SquadRanking.big',
    'ClubHistory12D': SCREEN / 'managermode/ManagerModeSeasonObjectives.big',
}
CACHE_PATHS = {path.as_posix() for path in RESOURCES.values()}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def directory(path):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError(f'Use an absolute folder path: {path}')
    path = Path(path.anchor, *path.parts[1:])
    if '..' in path.parts or not path.is_dir():
        raise ValueError(f'Folder does not exist or is invalid: {path}')
    target(Path(path.anchor), path.relative_to(path.anchor))
    return path.resolve(strict=True)


def documents_profile():
    name = ctypes.create_unicode_buffer(260)
    if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, name) != 0:
        raise RuntimeError('Windows could not locate Documents. Specify the FIFA profile folder.')
    return Path(name.value) / 'FIFA 16'


def locations():
    if not SETTINGS.is_file():
        raise ValueError(r'Run Diagnostics.cmd configure --game "X:\Path\To\FIFA 16" first.')
    settings = read(SETTINGS)
    return validated_locations(settings['game'], settings['profile'])


def validated_locations(game, user_profile):
    game, user_profile = directory(game), directory(user_profile)
    if (game.is_relative_to(user_profile) or user_profile.is_relative_to(game)
            or LOCAL.is_relative_to(user_profile) or LOCAL.is_relative_to(game)
            or game.is_relative_to(LOCAL) or user_profile.is_relative_to(LOCAL)):
        raise ValueError('Use separate game, FIFA profile and Career Stats folders.')
    return game, user_profile


def check_files(root, expected):
    for relative, sha in expected.items():
        path = target(root, relative)
        actual = fingerprint(path)
        if actual != sha:
            reason = ('Unexpected existing file' if sha is None else
                      'File missing' if actual is None else 'SHA-256 does not match')
            raise RuntimeError(f'{reason}: {path}')

