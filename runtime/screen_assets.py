"""Prepare the two screens from verified resources in the user's game archive."""
from contextlib import contextmanager
import ctypes
import hashlib
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import zlib

import layout
import monitor
from archivos import target

HELPER_NAMES = ('player_history_dynamic.exe', 'player_history_external_cache.exe',
                'fifa16-career-apt-probe.exe')

@contextmanager
def external_dll_search():
    """Keep bundled Python DLL search paths out of external game/helper processes."""
    if not layout.FROZEN:
        yield
        return
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
    if not kernel.SetDllDirectoryW(None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield
    finally:
        if not kernel.SetDllDirectoryW(sys._MEIPASS):
            raise ctypes.WinError(ctypes.get_last_error())


def run_helper(command):
    with external_dll_search():
        result = subprocess.run(command, capture_output=True, text=True,
                                errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError(f'Screen helper failed: {result.stderr or result.stdout}')


SOURCE_ENTRIES = {
    'SquadRanking': 'data/ui/game/screens/career/squadranking.big',
    'ManagerModeSeasonObjectives': 'data/ui/game/screens/career/managermode/managermodeseasonobjectives.big',
}


class ScreenCompatibilityError(ValueError):
    pass


def extract_screens(archive, expected):
    """Read the requested entries from a supported BIG4 archive."""
    result = {}
    wanted = {SOURCE_ENTRIES[stem].encode(): stem for stem in expected}
    with archive.open('rb') as stream:
        size = archive.stat().st_size
        header = stream.read(16)
        if len(header) != 16 or header[:4] != b'BIG4':
            raise ValueError('Expected a FIFA 16 BIG4 front-end archive.')
        count, toc_end = struct.unpack_from('>II', header, 8)
        if not 16 < toc_end <= min(size, 8 * 1024 * 1024) or count > 100_000:
            raise ValueError('Invalid BIG4 directory.')
        toc = stream.read(toc_end-16)
        index = 0
        for _ in range(count):
            offset, length = struct.unpack_from('>II', toc, index)
            end = toc.index(b'\0', index+8)
            name = toc[index+8:end].lower()
            index = end + 1
            if name not in wanted:
                continue
            stem = wanted[name]
            if stem in result or offset < toc_end or offset+length > size or not 48 < length < 65_536:
                raise ValueError(f'Unexpected BIG4 entry: {stem}')
            stream.seek(offset)
            packed = stream.read(length)
            result[stem] = verify_template(unpack_entry(packed, stem), stem, expected[stem])
    if result.keys() != expected.keys():
        raise ValueError('The front-end archive is missing a required screen.')
    return result


def unpack_entry(packed, stem):
    if packed[:4] == b'BIGF':
        return packed
    if (len(packed) <= 48 or packed[:12] != b'chunkzip\0\0\0\x02'
            or struct.unpack_from('>I', packed, 20)[0] != 1
            or struct.unpack_from('>II', packed, 40) != (len(packed)-48, 1)):
        raise ValueError(f'Unexpected chunkzip format: {stem}')
    size = struct.unpack_from('>I', packed, 12)[0]
    if not 0 < size < 65_536:
        raise ValueError(f'Unexpected screen size: {stem}')
    decoder = zlib.decompressobj(-15)
    data = decoder.decompress(packed[48:], size+1)
    if not decoder.eof or decoder.unused_data or len(data) != size:
        raise ValueError(f'Invalid compressed screen: {stem}')
    return data


def verify_template(data, stem, expected):
    if len(data) < 80 or len(data) >= 65_536:
        raise ValueError(f'Unexpected screen size: {stem}')
    a, n = struct.unpack_from('>II', data, 16)
    c, m = struct.unpack_from('>II', data, 38)
    if not 64 == a < a+n <= c < c+m <= len(data)-16:
        raise ValueError(f'Invalid screen template bounds: {stem}')
    # Normalize alignment and entry offsets. Keep the APT bytecode, constants,
    # fixed wrapper fields and opaque trailer in the verified fingerprint.
    canonical, _ = pack_bytes(data, data[a:a+n], data[c:c+m])
    if hashlib.sha256(canonical).hexdigest() != expected:
        raise ValueError(f'The {stem} template differs in content required by Career Stats.')
    return canonical


def game_screens(game, expected):
    result = {}
    try:
        for stem, relative in SOURCE_ENTRIES.items():
            path = target(game, relative)
            if path.exists():
                with path.open('rb') as stream:
                    data = stream.read(65_536)
                result[stem] = verify_template(unpack_entry(data, stem), stem, expected[stem])
        missing = {stem: sha for stem, sha in expected.items() if stem not in result}
        if missing:
            result.update(extract_screens(target(game, 'data_front_end_extra.big'), missing))
    except (OSError, ValueError, struct.error, zlib.error) as exc:
        raise ScreenCompatibilityError(f'Incompatible Career Mode screen resources: {exc}') from exc
    return result


def extract_templates(sources, folder):
    for stem, data in sources.items():
        apt_offset, apt_size = struct.unpack_from('>II', data, 16)
        const_offset, const_size = struct.unpack_from('>II', data, 38)
        (folder / f'{stem}.apt').write_bytes(data[apt_offset:apt_offset+apt_size])
        (folder / f'{stem}.const').write_bytes(data[const_offset:const_offset+const_size])


def u32be(data, offset):
    return struct.unpack_from(">I", data, offset)[0]


def align(value, step):
    return (value + step - 1) // step * step


def pack_bytes(source, apt, const):
    if source[:4] != b"BIGF" or u32be(source, 8) != 3:
        raise ValueError("unexpected nested archive")
    old_apt_offset, old_apt_size = u32be(source, 0x10), u32be(source, 0x14)
    old_const_offset, old_const_size = u32be(source, 0x26), u32be(source, 0x2A)
    if (old_apt_offset != 0x40 or source[old_apt_offset:old_apt_offset+8] != b"Apt Data"
            or source[old_const_offset:old_const_offset+4] != b"Apt1"
            or u32be(source, 0x1A) != old_const_offset
            or u32be(source, 0x1E) != 0
            or source[0x18:0x1A] != b"0\0"
            or source[0x22:0x26] != b"sg2\0"
            or source[0x2E:0x30] != b"1\0"):
        raise ValueError("BIGF layout differs from the verified three-entry layout")
    if old_const_offset < old_apt_offset + old_apt_size:
        raise ValueError("overlapping original entries")
    if apt[:8] != b"Apt Data" or const[:4] != b"Apt1":
        raise ValueError("patched APT/const magic mismatch")
    new_const_offset = align(0x40 + len(apt), 64)
    result = bytearray(source[:0x40])
    result.extend(apt)
    result.extend(b"\0" * (new_const_offset - len(result)))
    result.extend(const)
    result.extend(b"\0" * (align(len(result), 4) - len(result)))
    result.extend(source[-16:])  # opaque trailer retained; its purpose is not yet verified
    struct.pack_into(">I", result, 0x14, len(apt))
    struct.pack_into(">I", result, 0x1A, new_const_offset)
    struct.pack_into(">I", result, 0x26, new_const_offset)
    struct.pack_into(">I", result, 0x2A, len(const))
    struct.pack_into("<I", result, 0x04, len(result)-16)
    if (result[0x40:0x40+len(apt)] != apt or result[new_const_offset:new_const_offset+len(const)] != const):
        raise ValueError("repack self-check failed")
    return bytes(result), new_const_offset




def render(game, out, records, bins):
    spec = layout.read(layout.PROFILE_FILE)
    originals = game_screens(game, spec['screen_sources'])
    with tempfile.TemporaryDirectory(dir=layout.LOCAL) as scratch:
        folder = Path(scratch)
        extract_templates(originals, folder)
        empty = folder/'runtime.json'
        empty.write_text('{"players":{},"runtime_only":true}', encoding='utf-8')
        base = folder/'NativeSelector'
        run_helper([bins/'player_history_dynamic.exe', folder/'SquadRanking', base, empty])
        run_helper([bins/'player_history_external_cache.exe', base,
                        out/'PlayerHistory12D_Ampliado', '32768', empty, '512'])
        baseline = layout.read(records)
        generator_data = folder/'club-generator.json'
        monitor.publish(generator_data, baseline | {'schema': 2, 'competition_scope': 'all_competitions'})
        run_helper([bins/'fifa16-career-apt-probe.exe', folder/'ManagerModeSeasonObjectives',
                        generator_data, out/'ClubHistory12D', 'history12d'])
    for stem, original in zip(layout.RESOURCES, SOURCE_ENTRIES):
        apt, const = out/f'{stem}.apt', out/f'{stem}.const'
        data, _ = pack_bytes(originals[original], apt.read_bytes(), const.read_bytes())
        (out/f'{stem}.bigf').write_bytes(data)
