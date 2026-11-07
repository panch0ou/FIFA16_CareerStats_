"""Supervise the game and its monitoring worker."""
from contextlib import contextmanager
import ctypes
import struct
import subprocess
import time

import observar_cargas as observer

@contextmanager
def single_launcher():
    """Serialize sessions even when the package is extracted twice."""
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateMutexW(None, True, r'Global\FIFA16CareerStats')
    last_error = ctypes.get_last_error()
    if not handle:
        raise ctypes.WinError(last_error)
    try:
        if last_error == 183:
            raise RuntimeError('Another Career Stats launcher is already active.')
        yield
    finally:
        kernel.CloseHandle(handle)


def native_ready(pid):
    process = observer.Process(pid, readonly=True)
    try:
        if process.read(0x145adfdab, 5).hex() != '458b4c2414':
            return False
        if process.read(0x145adfe08, 7).hex() != '4c8d05b1c656fd':
            return False
        return all(process.read(at, 5) == b'\xe8'+struct.pack('<i', 0x144511560-at-5)
                   for at in (observer.SAVE_CALL, *observer.LIFECYCLE_CALLS))
    finally:
        process.close()


def supervise(game, worker, diagnostic):
    monitor_process = None
    error = None
    try:
        deadline = time.monotonic()+50
        while game.poll() is None:
            try:
                if native_ready(game.pid):
                    with diagnostic.open('ab') as log:
                        monitor_process = subprocess.Popen(
                            [*worker, str(game.pid)], stdout=log, stderr=subprocess.STDOUT,
                            creationflags=subprocess.CREATE_NO_WINDOW)
                    break
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError('The expected FIFA memory signatures did not appear')
            time.sleep(.25)
    except (KeyboardInterrupt, RuntimeError, OSError, ValueError) as exc:
        error = f'Career Stats could not start: {exc or "startup interrupted"}'
        print(error+'. Close FIFA from its menu.', flush=True)
    while game.poll() is None:
        try:
            if monitor_process is not None and monitor_process.poll() is not None:
                try:
                    game.wait(timeout=2)
                    break
                except subprocess.TimeoutExpired:
                    pass
                error = 'The monitor stopped. Close FIFA from its menu to remove the temporary screens.'
                print(error, flush=True)
                monitor_process = None
            time.sleep(.3)
        except KeyboardInterrupt:
            print('Close FIFA normally to remove the temporary screens.', flush=True)
    if monitor_process is not None:
        try:
            if monitor_process.wait(timeout=15) != 0:
                error = 'The monitor reported an error. Check the session logs.'
        except subprocess.TimeoutExpired:
            monitor_process.terminate()
            monitor_process.wait(timeout=5)
            error = 'The monitor had to be stopped after FIFA exited.'
    if game.returncode != 0 and not error:
        error = f'FIFA exited with code {game.returncode}. Cleanup will now run.'
    if monitor_process is None and not error:
        error = 'FIFA closed before the Career Stats monitor could start.'
    if error:
        if diagnostic and diagnostic.is_file():
            error += f' Log: {diagnostic}'
        raise RuntimeError(error)


