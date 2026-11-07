"""Windowed entry point and GUI for the portable Career Stats distribution."""
from concurrent.futures import ThreadPoolExecutor
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, ttk
import traceback
import uuid

import discovery
from career_schema import CareerSchemaError
import launch
import layout
import monitor
from lanzador import single_launcher
from screen_assets import ScreenCompatibilityError
from version import DISPLAY_VERSION


def log_path(action):
    folder = layout.LOCAL/'logs'
    folder.mkdir(parents=True, exist_ok=True)
    return folder/f'{action}-{uuid.uuid4().hex[:10]}.log'


def backend_command(log, action, *args):
    if layout.FROZEN:
        return [sys.executable, '--backend', str(log), action, *map(str, args)]
    return [str(launch.python_console()), '-B', str(Path(__file__).resolve()),
            '--backend', str(log), action, *map(str, args)]


def saved_folders():
    try:
        saved = layout.read(layout.SETTINGS)
        return saved if isinstance(saved, dict) else {}
    except (OSError, ValueError):
        return {}


def game_status(path):
    if path is None:
        return 'FIFA 16 was not found. Choose Locate FIFA 16.', False
    try:
        path = layout.directory(path)
        launch.check_game(path)
    except (OSError, ValueError, RuntimeError) as exc:
        with log_path('compatibility').open('w', encoding='utf-8') as log:
            traceback.print_exc(file=log)
        if isinstance(exc, CareerSchemaError):
            return str(exc), False
        if isinstance(exc, ScreenCompatibilityError):
            return 'The required Career Mode screens are incompatible. Open View Logs for details.', False
        return 'Incompatible game executable or native components. Open View Logs for details.', False
    return 'Technically compatible · 2015/16 profile', True


def choose_initial(games, saved):
    if saved and Path(saved) in games:
        first = Path(saved)
        return first, game_status(first)
    first_status = None
    for path in games:
        status = game_status(path)
        if first_status is None:
            first_status = status
        if status[1]:
            return path, status
    return (games[0], first_status) if games else (None, game_status(None))


def inspect_setup(game, profile):
    saved = saved_folders()
    games = discovery.games(saved.get('game'))
    if game is None:
        game, (game_text, game_ok) = choose_initial(games, saved.get('game'))
    else:
        game_text, game_ok = game_status(game)
        if game not in games:
            games.insert(0, game)
    profiles = discovery.profiles(saved.get('profile'), game)
    if profile is None and profiles:
        profile = profiles[0]
    if profile and profile not in profiles:
        profiles.insert(0, profile)
    profile_text = 'Profile not found. Open FIFA 16 normally once, then close it and try again.'
    profile_ok = False
    if profile:
        try:
            profile = layout.directory(profile)
            launch.check_profile(profile)
            profile_text, profile_ok = 'Detected', True
        except (OSError, ValueError, RuntimeError):
            profile_text = 'FIFA has not initialized this folder. Choose its profile or open FIFA once.'
    try:
        launch.check_components()
        history_text, components_ok = 'Ready', True
    except (OSError, ValueError, KeyError, RuntimeError):
        with log_path('components').open('w', encoding='utf-8') as log:
            traceback.print_exc(file=log)
        history_text, components_ok = 'Missing or damaged files. Extract the entire ZIP again.', False

    pending = layout.JOURNAL.is_file()
    status = 'Choose a compatible game and an initialized profile.'
    ready = False
    if pending:
        status = 'Previous session needs recovery. Close FIFA 16 and choose Recover.'
    elif game_ok and profile_ok and components_ok:
        try:
            game, profile = layout.validated_locations(game, profile)
            with single_launcher():
                launch.closed()
                if layout.JOURNAL.exists():
                    raise RuntimeError('Previous session needs recovery.')
                layout.check_files(profile, dict.fromkeys(layout.CACHE_PATHS))
                new_settings = {'game': str(game), 'profile': str(profile)}
                if new_settings != saved:
                    monitor.publish(layout.SETTINGS, new_settings)
            status, ready = 'Ready to launch.', True
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            with log_path('setup').open('w', encoding='utf-8') as log:
                traceback.print_exc(file=log)
            if str(exc).startswith('Unexpected existing file:'):
                status = 'A screen file is already present in the FIFA profile. Open View Logs.'
            else:
                status = 'Check that FIFA 16 is closed and that both folders are accessible. Open View Logs for details.'
    return dict(game=game, games=games, game_text=game_text, profile=profile, profiles=profiles,
                profile_text=profile_text, history_text=history_text, pending=pending,
                status=status, ready=ready)


class Launcher:
    def __init__(self, window):
        self.window = window
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.selection = (None, None)
        self.game, self.profile = tk.StringVar(), tk.StringVar()
        self.game_text, self.profile_text = tk.StringVar(), tk.StringVar()
        self.history_text, self.status = tk.StringVar(), tk.StringVar(value='Looking for FIFA 16…')
        window.title('FIFA 16 Career Stats')
        window.minsize(560, 365)
        window.columnconfigure(0, weight=1)
        panel = ttk.Frame(window, padding=(24, 20))
        panel.grid(sticky='nsew')
        panel.columnconfigure(0, weight=1)
        ttk.Label(panel, text='FIFA 16 Career Stats', font=('Segoe UI', 20, 'bold')).grid(sticky='w')
        ttk.Label(panel, text=f'{DISPLAY_VERSION} · 2015/16 Career Mode',
                  font=('Segoe UI', 10)).grid(sticky='w', pady=(0, 14))
        self.game_combo, self.find_game = self.folder_row(
            panel, 2, 'Game installation', self.game, self.game_text, 'Locate FIFA 16', 0)
        self.profile_combo, self.find_profile = self.folder_row(
            panel, 5, 'FIFA profile', self.profile, self.profile_text, 'Locate Profile', 1)
        ttk.Separator(panel).grid(row=8, columnspan=2, sticky='ew', pady=(9, 10))
        ttk.Label(panel, textvariable=self.history_text, wraplength=500).grid(row=9, columnspan=2, sticky='w')
        ttk.Label(panel, textvariable=self.status, wraplength=500).grid(row=10, columnspan=2, sticky='w', pady=(8, 12))
        buttons = ttk.Frame(panel)
        buttons.grid(row=11, columnspan=2, sticky='ew')
        self.launch_button = ttk.Button(buttons, text='Launch FIFA 16', command=lambda: self.run('play-selected', *self.selection))
        self.launch_button.pack(side='left', ipadx=14, ipady=4)
        ttk.Button(buttons, text='View Logs', command=self.view_logs).pack(side='right')
        self.recover_button = ttk.Button(buttons, text='Recover', command=lambda: self.run('recover-selected'))
        self.recover_button.pack(side='right', padx=8)
        window.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh()

    def folder_row(self, parent, row, title, value, detail, label, index):
        ttk.Label(parent, text=title, font=('Segoe UI', 10, 'bold')).grid(row=row, sticky='w')
        combo = ttk.Combobox(parent, textvariable=value, state='readonly', width=54)
        combo.grid(row=row+1, sticky='ew', pady=2, padx=(0, 8))
        combo.bind('<<ComboboxSelected>>', lambda _: self.select(index, Path(value.get())))
        button = ttk.Button(parent, text=label, command=lambda: self.locate(index))
        button.grid(row=row+1, column=1, sticky='ew')
        ttk.Label(parent, textvariable=detail, wraplength=500).grid(row=row+2, columnspan=2, sticky='w', pady=(0, 8))
        return combo, button

    def select(self, index, path):
        pair = list(self.selection)
        pair[index] = path
        self.selection = tuple(pair)
        self.refresh()

    def locate(self, index):
        path = filedialog.askdirectory(parent=self.window, mustexist=True,
                                       title=('Locate FIFA 16', 'Locate FIFA 16 Profile')[index],
                                       initialdir=str(self.selection[index] or Path.home()))
        if path:
            self.select(index, Path(path))

    def view_logs(self):
        folder = layout.LOCAL/'logs'
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def disable(self):
        for control in (self.game_combo, self.profile_combo, self.find_game, self.find_profile,
                        self.launch_button, self.recover_button):
            control.configure(state='disabled')

    def refresh(self, notice=None):
        self.disable()
        self.status.set('Checking setup…')
        future = self.executor.submit(inspect_setup, *self.selection)

        def finish():
            if not future.done():
                self.window.after(100, finish)
                return
            try:
                result = future.result()
            except Exception:
                with log_path('launcher').open('w', encoding='utf-8') as log:
                    traceback.print_exc(file=log)
                self.status.set('Setup could not be checked. Open View Logs for details.')
                self.find_game.configure(state='normal')
                self.find_profile.configure(state='normal')
                return
            self.selection = result['game'], result['profile']
            self.game.set(str(result['game'] or ''))
            self.profile.set(str(result['profile'] or ''))
            self.game_combo.configure(values=tuple(map(str, result['games'])), state='readonly')
            self.profile_combo.configure(values=tuple(map(str, result['profiles'])), state='readonly')
            self.game_text.set(result['game_text'])
            self.profile_text.set(result['profile_text'])
            self.history_text.set('Historical coverage · Pre-2015/16 records for matching player and club IDs'
                                  if result['history_text'] == 'Ready' else result['history_text'])
            self.status.set(notice or result['status'])
            self.find_game.configure(text='Change Game Folder' if result['game'] else 'Locate FIFA 16',
                                     state='normal')
            self.find_profile.configure(text='Change Profile Folder' if result['profile'] else 'Locate Profile',
                                        state='normal')
            self.launch_button.configure(state='normal' if result['ready'] else 'disabled')
            self.recover_button.configure(state='normal' if result['pending'] else 'disabled')
        self.window.after(80, finish)

    def run(self, action, *paths):
        self.disable()
        log = log_path(action)
        try:
            process = subprocess.Popen(backend_command(log, action, *paths), cwd=layout.ROOT,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError:
            with log.open('w', encoding='utf-8') as stream:
                traceback.print_exc(file=stream)
            self.refresh('Career Stats could not start. Open View Logs for details.')
            return
        self.status.set('Preparing Career Stats and starting FIFA…' if paths else 'Recovering the previous session…')

        def poll():
            code = process.poll()
            content = log.read_text(encoding='utf-8', errors='replace') if log.is_file() else ''
            if code is None:
                if 'The monitor stopped.' in content:
                    self.status.set('The monitor stopped. Close FIFA normally and open View Logs.')
                elif 'FIFA 16 started.' in content:
                    self.status.set('FIFA 16 is running. Close the game normally to finish the session.')
                self.window.after(500, poll)
                return
            message = ('Career Stats could not finish. Open View Logs for details.' if code else
                       'FIFA 16 closed. Temporary screens were removed.' if paths else 'Recovery completed.')
            self.refresh(message)
        self.window.after(500, poll)

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.window.destroy()


def main():
    if sys.argv[1:2] == ['--backend']:
        log = Path(sys.argv[2])
        sys.argv[1:3] = []
        with log.open('a', encoding='utf-8', buffering=1) as stream:
            sys.stdout = sys.stderr = stream
            try:
                launch.run()
            except Exception:
                traceback.print_exc(file=stream)
                sys.exit(1)
        return
    layout.LOCAL.mkdir(parents=True, exist_ok=True)
    window = tk.Tk()
    Launcher(window)
    window.mainloop()


if __name__ == '__main__':
    backend = sys.argv[1:2] == ['--backend']
    try:
        main()
    except Exception:
        with log_path('startup').open('w', encoding='utf-8') as stream:
            traceback.print_exc(file=stream)
        if not backend:
            ctypes.windll.user32.MessageBoxW(None, 'Career Stats could not start. See the Career Stats logs.',
                                           'FIFA 16 Career Stats', 0x10)
        sys.exit(1)
