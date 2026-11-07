"""Find likely FIFA 16 installations and profiles without scanning drives."""
from itertools import chain
import os
from pathlib import Path
import winreg

import layout


def registry_paths():
    """Read known publisher keys and exact-name uninstall entries in both views."""
    publisher_keys = (
        r'SOFTWARE\EA Sports\FIFA 16',
        r'SOFTWARE\Electronic Arts\FIFA 16',
        r'SOFTWARE\EA Games\FIFA 16',
    )
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            access = winreg.KEY_READ | view
            for name in publisher_keys:
                try:
                    with winreg.OpenKey(hive, name, 0, access) as key:
                        for field in ('Install Dir', 'InstallLocation', 'InstallPath'):
                            try:
                                value, _ = winreg.QueryValueEx(key, field)
                            except OSError:
                                continue
                            if isinstance(value, str) and value:
                                yield Path(os.path.expandvars(value.strip('"')))
                except OSError:
                    continue
            try:
                with winreg.OpenKey(hive, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
                                   0, access) as uninstall:
                    for i in range(winreg.QueryInfoKey(uninstall)[0]):
                        try:
                            with winreg.OpenKey(uninstall, winreg.EnumKey(uninstall, i), 0, access) as key:
                                name, _ = winreg.QueryValueEx(key, 'DisplayName')
                                if str(name).strip().casefold() not in ('fifa 16', 'ea sports fifa 16'):
                                    continue
                                path, _ = winreg.QueryValueEx(key, 'InstallLocation')
                                if isinstance(path, str) and path:
                                    yield Path(os.path.expandvars(path.strip('"')))
                        except OSError:
                            continue
            except OSError:
                continue


def unique_folders(paths, marker):
    result = []
    for candidate in paths:
        if not candidate:
            continue
        try:
            path = layout.directory(candidate)
            if (path/marker).is_file() and path not in result:
                result.append(path)
        except (OSError, ValueError):
            continue
    return result


def games(saved=None):
    base_dirs = [Path(os.environ[name]) for name in ('ProgramW6432', 'ProgramFiles',
                 'ProgramFiles(x86)') if os.environ.get(name)]
    system_drive = Path(os.environ.get('SystemDrive', 'C:') + '\\')
    standard = [system_drive/'Games/FIFA 16', system_drive/'EA Games/FIFA 16',
                system_drive/'Origin Games/FIFA 16', layout.ROOT/'FIFA 16', layout.ROOT.parent]
    publisher = ('EA Games', 'Origin Games', 'Electronic Arts', 'EA SPORTS', 'EA')
    common = (base/brand/'FIFA 16' for base in base_dirs for brand in publisher)
    return unique_folders(chain([saved], registry_paths(), standard, common), 'fifa16.exe')


def profiles(saved=None, game=None):
    guesses = [saved]
    try:
        guesses.append(layout.documents_profile())
    except (OSError, RuntimeError):
        pass
    for name in ('OneDrive', 'OneDriveConsumer', 'OneDriveCommercial', 'USERPROFILE'):
        if os.environ.get(name):
            guesses.append(Path(os.environ[name])/'Documents/FIFA 16')
    if game:
        guesses.extend(game.parent/relative for relative in ('Documents/FIFA 16', 'Profile'))
    result = []
    for candidate in guesses:
        if not candidate:
            continue
        try:
            path = layout.directory(candidate)
            if layout.target(path, '0/FIFA16').is_dir() and path not in result:
                result.append(path)
        except (OSError, ValueError):
            continue
    return result
