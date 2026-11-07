"""Check the release inputs, launch FIFA, supervise, and recover the two screens."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import sqlite3
import traceback
import struct
import subprocess
import sys
import tempfile
import uuid

import bridge
import career_schema
import carreras
import datos
import lanzador
import layout
import monitor
import observar_cargas as observer
from archivos import apply, restore, target
from guardados import AutomaticSession
from screen_assets import HELPER_NAMES, external_dll_search, game_screens, render
from transporte import Screen


def profile():
    return layout.read(layout.PROFILE_FILE)


def python_console():
    # Use the console interpreter with output redirected when started from the GUI.
    return Path(sys.executable).with_name('python.exe')


def closed():
    result = subprocess.run(
        [str(Path(os.environ['SystemRoot'])/'System32/tasklist.exe'),
         '/FI', 'IMAGENAME eq fifa16.exe', '/FO', 'CSV', '/NH'],
        check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if any(line.lower().startswith(b'"fifa16.exe",') for line in result.stdout.splitlines()):
        raise RuntimeError('Close FIFA 16 before using Career Stats.')


def check_game(game):
    spec = profile()
    layout.check_files(game, spec['game'])
    career_schema.load(target(game, career_schema.METADATA))
    game_screens(game, spec['screen_sources'])


def check_profile(user_profile):
    path = target(user_profile, '0/FIFA16')
    if not path.is_dir():
        raise RuntimeError(f'FIFA profile is not initialized: {path}. Open FIFA normally first.')


def configure_runtime(game, user_profile, log_dir=None):
    spec = profile()
    carreras.ACTIVE = user_profile
    carreras.SCHEMA = career_schema.load(target(game, career_schema.METADATA))
    carreras.DB = layout.LOCAL / 'career.sqlite'
    carreras.LEAGUES = {(r['league'], r['primary'], r['native'], r['country'], r['level']): r['label']
                        for r in spec['compatible_leagues']}
    datos.BASELINE = layout.INPUTS / 'club_records.json'
    datos.HISTORICAL_DB = layout.INPUTS / 'historial_ampliado.sqlite'
    datos.HISTORICAL_BEFORE = spec['historical_before']
    datos.HISTORICAL_CLUBS = spec['historical_clubs']
    observer.TARGET_EXE = game / 'fifa16.exe'
    observer.DLL = layout.OBSERVER
    bridge.GAME = game
    if log_dir is not None:
        observer.HERE = carreras.HERE = monitor.HERE = bridge.HERE = log_dir
        monitor.STATE = log_dir / 'status.json'
        monitor.RESOURCE_DIR = layout.PAYLOAD


def check_components():
    spec = profile()
    carreras.require_reader()
    layout.check_files(layout.INPUTS, {'historial_ampliado.sqlite': spec['history_sha256'],
                                      'club_records.json': spec['club_records_sha256']})
    files = layout.read(layout.RUNTIME_MANIFEST)['files']
    if files.keys() != {*HELPER_NAMES, layout.OBSERVER.name}:
        raise ValueError('The runtime manifest does not list the expected helpers.')
    layout.check_files(layout.HELPERS, files)


def check_payload():
    check_components()
    layout.check_files(layout.PAYLOAD, profile()['screens'])


def ensure_screens(game):
    expected = profile()['screens']
    try:
        layout.check_files(layout.PAYLOAD, expected)
        return
    except RuntimeError:
        pass
    with tempfile.TemporaryDirectory(dir=layout.LOCAL) as folder:
        staging = Path(folder)
        render(game, staging, layout.INPUTS/'club_records.json', layout.HELPERS)
        layout.check_files(staging, expected)
        layout.PAYLOAD.mkdir(exist_ok=True)
        for name in expected:
            (staging/name).replace(target(layout.LOCAL, 'payload/'+name))


def cache_entries():
    entries = []
    expected = profile()['screens']
    for index, (stem, relative) in enumerate(layout.RESOURCES.items()):
        archive = layout.PAYLOAD / f'{stem}.bigf'
        apt = (layout.PAYLOAD / f'{stem}.apt').read_bytes()
        data = archive.read_bytes()
        if (data[:4] != b'BIGF' or struct.unpack_from('>II', data, 16) != (64, len(apt))
                or data[64:64+len(apt)] != apt):
            raise ValueError(f'The BIGF and APT disagree: {stem}')
        Screen(apt, player=index == 0)
        entries.append((relative.as_posix(), archive, None, expected[archive.name]))
    return entries


def preflight(game, user_profile):
    closed()
    if layout.JOURNAL.exists():
        raise RuntimeError('A session needs recovery. Use Recover in the launcher or Diagnostics.cmd recover.')
    check_game(game)
    check_profile(user_profile)
    layout.check_files(user_profile, dict.fromkeys(layout.CACHE_PATHS))
    check_payload()


def recover(user_profile):
    closed()
    if not layout.JOURNAL.exists():
        print('No interrupted session needs recovery.')
        return
    if any(item['before'] is not None for item in layout.read(layout.JOURNAL)['files']):
        raise RuntimeError('Unexpected recovery journal. Keep it for diagnosis.')
    restore(user_profile, layout.JOURNAL, layout.CACHE_PATHS)
    print('Temporary Career Stats screens removed.')


def validate_views():
    entries = cache_entries()
    source = datos.Source()
    screens = [Screen((layout.PAYLOAD/f'{stem}.apt').read_bytes(), player=i == 0)
               for i, stem in enumerate(layout.RESOURCES)]
    heads = []
    if carreras.DB.exists():
        with carreras.connect() as db:
            heads = [row[0] for row in db.execute('SELECT sha FROM snapshots')]
    for head in [None, *heads]:
        buckets, club, _ = source.snapshot(head)
        for screen in screens:
            screen.payload(buckets, club, 1)
    return entries


def new_log_dir():
    folder = layout.LOCAL / 'logs' / f'{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}'
    folder.mkdir(parents=True)
    return folder


def worker_command(action, log_dir):
    if layout.FROZEN:
        return [sys.executable, '--backend', str(log_dir/f'{action}.log'), action, str(log_dir)]
    return [str(python_console()), '-B', str(Path(__file__).resolve()), action, str(log_dir)]


def play(game, user_profile):
    preflight(game, user_profile)
    log_dir = new_log_dir()
    configure_runtime(game, user_profile, log_dir)
    entries = validate_views()
    with carreras.connect():
        pass
    closed()
    process = None
    try:
        apply(user_profile, entries, layout.JOURNAL)
        with external_dll_search():
            process = subprocess.Popen([str(game/'fifa16.exe')], cwd=game)
        monitor.publish(log_dir/'launch.json', {
            'game': str(game), 'profile': str(user_profile), 'pid': process.pid,
        })
        print(f'FIFA 16 started. Session diagnostics are in {log_dir}', flush=True)
        lanzador.supervise(process, worker=worker_command('_monitor', log_dir),
                           diagnostic=log_dir/f'monitor_{process.pid}.log')
    finally:
        if layout.JOURNAL.exists() and (process is None or process.poll() is not None):
            recover(user_profile)


def internal_worker(action, log_dir, pid):
    log_dir = target(layout.LOCAL, log_dir.relative_to(layout.LOCAL))
    if log_dir.parent != layout.LOCAL/'logs':
        raise ValueError('Invalid session directory.')
    session = layout.read(log_dir/'launch.json')
    game, user_profile = layout.locations()
    if (not layout.JOURNAL.exists() or session != {
            'game': str(game), 'profile': str(user_profile), 'pid': pid}):
        raise RuntimeError('The worker has no matching active launcher session.')
    configure_runtime(game, user_profile, log_dir)
    check_game(game)
    check_payload()
    if action == '_observer':
        observer.run(pid, 'watch', quiet=True)
    else:
        monitor.attach(pid, AutomaticSession, [*worker_command('_observer', log_dir), str(pid)])


def confirm(user_profile):
    check_profile(user_profile)
    with carreras.connect():
        pass
    slots = []
    for relative, sha in monitor.identity.career_inventory(user_profile).items():
        if monitor.identity.lookup(sha):
            continue
        path = carreras.safe_source(user_profile/relative)
        try:
            info = carreras.inspect(path)
        except (OSError, ValueError) as exc:
            print(f'Skipping {relative}: {exc}')
            continue
        if info['sha'] == sha:
            slots.append((path, info))
            print(f'{len(slots)}. {info["save_label"]} [{sha[:12]}]')
    if not slots:
        print('There are no eligible unregistered Career Mode saves.')
        return
    choice = input('Choose a save, or press Enter to cancel: ').strip()
    if not choice:
        return
    if not choice.isdecimal() or not 1 <= int(choice) <= len(slots):
        raise ValueError('Invalid selection.')
    path, info = slots[int(choice)-1]
    parent = input('Enter NEW for an independent Career, the full SHA-256 of its known parent, '
                   'or Enter to cancel: ').strip()
    if parent:
        result = carreras.bind(path, 'Save origin confirmed by the user',
                               label=(info['save_label'] or 'Career') if parent == 'NEW' else None,
                               parent=None if parent == 'NEW' else parent,
                               expected_sha=info['sha'], known_league=True)
        print(f'Registered {result["sha"]}.')


def simulate(entries):
    with tempfile.TemporaryDirectory(dir=layout.LOCAL) as folder:
        root = Path(folder)
        journal = root/'journal.json'
        apply(root, entries, journal)
        layout.check_files(root, {rel: sha for rel, _, _, sha in entries})
        restore(root, journal, layout.CACHE_PATHS)
        layout.check_files(root, dict.fromkeys(layout.CACHE_PATHS))
        assert not journal.exists()
    print('Both screens were installed and removed in a disposable folder.')


def main():
    parser = argparse.ArgumentParser(description='FIFA 16 Career Stats diagnostics')
    commands = parser.add_subparsers(dest='action', required=True)
    setup = commands.add_parser('configure', help='Choose the game and FIFA profile folders')
    setup.add_argument('--game', type=Path, required=True)
    setup.add_argument('--profile', type=Path)
    commands.add_parser('build', help='Compile the observer and generate the screens locally')
    for action in ('check', 'simulate', 'play', 'recover', 'confirm'):
        commands.add_parser(action)
    for action in ('play-selected', 'prepare-selected'):
        selection = commands.add_parser(action)
        selection.add_argument('game', type=Path)
        selection.add_argument('profile', type=Path)
    commands.add_parser('recover-selected')
    for action in ('_monitor', '_observer'):
        worker = commands.add_parser(action)
        worker.add_argument('log_dir', type=Path)
        worker.add_argument('pid', type=int)
    args = parser.parse_args()
    if args.action.startswith('_'):
        internal_worker(args.action, args.log_dir, args.pid)
        return
    if os.name != 'nt' or struct.calcsize('P') != 8 or sys.version_info < (3, 11):
        raise RuntimeError('Use 64-bit Python 3.11 or later on Windows.')
    layout.LOCAL.mkdir(parents=True, exist_ok=True)
    with lanzador.single_launcher():
        if args.action == 'configure':
            if layout.JOURNAL.exists():
                raise RuntimeError('Recover the previous session before changing folders.')
            game, user_profile = layout.validated_locations(args.game, args.profile or layout.documents_profile())
            check_game(game)
            check_profile(user_profile)
            monitor.publish(layout.SETTINGS, {'game': str(game), 'profile': str(user_profile)})
            print('Folders saved. Add the historical inputs, then run Diagnostics.cmd build.')
            return
        if args.action == 'recover-selected':
            pending = layout.read(layout.JOURNAL)
            saved = layout.read(layout.SETTINGS)
            user_profile = layout.directory(saved['profile'])
            if pending['root'] != str(user_profile):
                raise RuntimeError('Recovery folder differs from the last used profile.')
            recover(user_profile)
            return
        if args.action in ('play-selected', 'prepare-selected'):
            closed()
            if layout.JOURNAL.exists():
                raise RuntimeError('Recover the previous session before starting FIFA.')
            game, user_profile = layout.validated_locations(args.game, args.profile)
            check_game(game)
            check_profile(user_profile)
            check_components()
            layout.check_files(user_profile, dict.fromkeys(layout.CACHE_PATHS))
            ensure_screens(game)
            monitor.publish(layout.SETTINGS, {'game': str(game), 'profile': str(user_profile)})
            if args.action == 'play-selected':
                play(game, user_profile)
            else:
                preflight(game, user_profile)
                configure_runtime(game, user_profile)
                simulate(validate_views())
            return
        game, user_profile = layout.locations()
        if args.action == 'recover':
            recover(user_profile)
        elif args.action == 'build':
            closed()
            if layout.JOURNAL.exists():
                raise RuntimeError('Recover the previous session before building.')
            check_game(game)
            sys.path.insert(0, str(layout.ROOT/'tools'))
            from build_payload import build
            build(game)
        elif args.action == 'play':
            play(game, user_profile)
        else:
            preflight(game, user_profile)
            configure_runtime(game, user_profile)
            if args.action == 'confirm':
                confirm(user_profile)
            else:
                entries = validate_views()
                if args.action == 'simulate':
                    simulate(entries)
                else:
                    print('Game, profile, observer and both history screens passed local checks.')


def run():
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, sqlite3.Error, subprocess.SubprocessError) as exc:
        if layout.FROZEN or sys.argv[1:2] in (['_monitor'], ['_observer']):
            traceback.print_exc()
        print(f'ERROR: {exc}', file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == '__main__':
    run()

