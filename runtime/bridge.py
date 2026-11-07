"""Verify and patch the existing in-memory player ID bridge."""
import ctypes as c
import json
import struct
from pathlib import Path
from memory import read_process, pe_bytes

HERE = GAME = None

def native(action, pid):
    k = c.WinDLL('kernel32', use_last_error=True)
    nt = c.WinDLL('ntdll')
    k.OpenProcess.argtypes = [c.c_uint32, c.c_int, c.c_uint32]
    k.OpenProcess.restype = c.c_void_p
    k.CloseHandle.argtypes = [c.c_void_p]
    k.QueryFullProcessImageNameW.argtypes = [c.c_void_p, c.c_uint32, c.c_wchar_p, c.POINTER(c.c_uint32)]
    k.GetProcessTimes.argtypes = [c.c_void_p] + [c.c_void_p] * 4
    k.VirtualProtectEx.argtypes = [c.c_void_p, c.c_void_p, c.c_size_t, c.c_uint32, c.POINTER(c.c_uint32)]
    k.WriteProcessMemory.argtypes = [c.c_void_p, c.c_void_p, c.c_void_p, c.c_size_t, c.POINTER(c.c_size_t)]
    k.FlushInstructionCache.argtypes = [c.c_void_p, c.c_void_p, c.c_size_t]
    for f in (nt.NtSuspendProcess, nt.NtResumeProcess):
        f.argtypes = [c.c_void_p]
        f.restype = c.c_long
    h = k.OpenProcess(0x1838, False, pid)
    if not h:
        raise c.WinError(c.get_last_error())
    suspended = False
    try:
        name = c.create_unicode_buffer(32768)
        size = c.c_uint32(len(name))
        if not k.QueryFullProcessImageNameW(h, 0, name, c.byref(size)):
            raise c.WinError(c.get_last_error())
        if Path(name.value).resolve() != (GAME / 'fifa16.exe').resolve():
            raise RuntimeError('The process does not belong to the configured game')
        times = [c.c_uint64() for _ in range(4)]
        if not k.GetProcessTimes(h, *[c.byref(x) for x in times]):
            raise c.WinError(c.get_last_error())
        creation = times[0].value
        base = 0x140000000
        if read_process(pid, base, 2) != b'MZ':
            raise RuntimeError('Unexpected game module base')
        if read_process(pid, 0x14219d030, 10) != b'PLAYER_ID\0':
            raise RuntimeError('PLAYER_ID signature does not match in memory')
        entries = [
            (0x145adfdab, bytes.fromhex('458b4c2414'), bytes.fromhex('458b4c24fc')),
            (0x145adfe08, bytes.fromhex('4c8d05b1c656fd'), b'\x4c\x8d\x05' + struct.pack('<i', 0x14219d030 - (0x145adfe08 + 7)))
        ]
        for va, old, new in entries:
            if pe_bytes(GAME / 'fifa16.bin', va-base, len(old)) != old:
                raise RuntimeError('Unexpected reference BIN')
        journal = HERE / f'native_{pid}.json'
        if journal.exists():
            state = json.loads(journal.read_text())
            if state['creation'] != creation:
                raise RuntimeError('The process ID was reused. The prior journal cannot be applied')
        elif action == 'unpatch':
            raise RuntimeError('Missing memory patch journal for this process')
        else:
            state = {'pid': pid, 'creation': creation, 'exe': name.value,
                     'patches': [{'va': hex(a), 'original': o.hex(), 'experimental': n.hex()} for a,o,n in entries]}
        expected = [new if action == 'unpatch' else old for _,old,new in entries]
        desired = [old if action == 'unpatch' else new for _,old,new in entries]
        current = [read_process(pid,a,len(o)) for a,o,_ in entries]
        if current == desired:
            print('Memory already matches the requested state')
            return
        if current != expected:
            raise RuntimeError('Unexpected bytes in game memory. The patch was refused')
        if nt.NtSuspendProcess(h) < 0:
            raise RuntimeError('Could not suspend FIFA')
        suspended = True
        if [read_process(pid,a,len(o)) for a,o,_ in entries] != expected:
            raise RuntimeError('Game code changed before the patch could be applied')
        if action == 'patch':
            state['state'] = 'applying'
            journal.write_text(json.dumps(state, indent=2))

        def write(va, data):
            old_protection = c.c_uint32()
            if not k.VirtualProtectEx(h, va, len(data), 0x40, c.byref(old_protection)):
                raise c.WinError(c.get_last_error())
            try:
                buffer = c.create_string_buffer(data)
                count = c.c_size_t()
                if not k.WriteProcessMemory(h, va, buffer, len(data), c.byref(count)) or count.value != len(data):
                    raise c.WinError(c.get_last_error())
                if not k.FlushInstructionCache(h, va, len(data)):
                    raise c.WinError(c.get_last_error())
            finally:
                ignored = c.c_uint32()
                if not k.VirtualProtectEx(h, va, len(data), old_protection.value, c.byref(ignored)):
                    raise c.WinError(c.get_last_error())
            if read_process(pid, va, len(data)) != data:
                raise RuntimeError('Game memory does not match after the write')

        changed = []
        try:
            for i, (va,_,_) in enumerate(entries):
                changed.append(i)
                write(va, desired[i])
        except Exception:
            for i in reversed(changed):
                write(entries[i][0], expected[i])
            raise
        state['state'] = 'restored' if action == 'unpatch' else 'active'
        journal.write_text(json.dumps(state, indent=2))
        print(f'Player ID bridge {action} verified in memory for process {pid}')
    finally:
        if suspended and nt.NtResumeProcess(h) < 0:
            raise RuntimeError('Could not resume FIFA')
        k.CloseHandle(h)


