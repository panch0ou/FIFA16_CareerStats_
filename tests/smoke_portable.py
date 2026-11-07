"""Exercise an extracted Windows release without starting FIFA."""
import argparse
from hashlib import file_digest
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


def run(zip_path, game):
    work = ROOT/'.local'
    work.mkdir(exist_ok=True)
    with TemporaryDirectory(dir=work, prefix='portable-test-') as folder:
        temp = Path(folder)
        portable = temp/'Extracted Career Stats ñ'
        with ZipFile(zip_path) as archive:
            archive.extractall(portable)
        exe = portable/'CareerStats.exe'
        image = exe.read_bytes()
        pe = struct.unpack_from('<I', image, 0x3C)[0]
        assert struct.unpack_from('<H', image, pe+4)[0] == 0x8664
        assert struct.unpack_from('<H', image, pe+24+68)[0] == 2  # Windows GUI
        assert any((portable/'Runtime').glob('python3??.dll'))
        profile = temp/'Disposable FIFA profile'
        (profile/'0/FIFA16/slot').mkdir(parents=True)
        save = profile/'0/FIFA16/slot/DATA'
        save.write_bytes(b'Disposable save sentinel')
        saved_hash = digest(save)
        env = {key: value for key, value in os.environ.items()
               if not key.upper().startswith(('PYTHON', 'RUST', 'CARGO', 'TCL_', 'TK_'))}
        env['PATH'] = str(Path(os.environ['SystemRoot'])/'System32')
        env['LOCALAPPDATA'] = str(temp/'State')
        env['TEMP'] = env['TMP'] = str(temp)
        state = temp/'State/FIFA16CareerStats'

        def backend(action, *arguments, expected=0):
            log = temp/f'{action}.log'
            log.unlink(missing_ok=True)
            proc = subprocess.run([exe, '--backend', log, action, *map(str, arguments)],
                                  env=env, cwd=temp, timeout=60)
            output = log.read_text(encoding='utf-8')
            assert proc.returncode == expected, output
            return output

        assert not state.exists()
        assert 'installed and removed in a disposable folder' in backend('prepare-selected', game, profile)
        assert not (profile/'cache0').exists()
        assert not (state/'career.sqlite').exists()
        settings = json.loads((state/'settings.json').read_text(encoding='utf-8'))
        assert settings == {'game': str(game), 'profile': str(profile)}
        renamed = portable.with_name('Moved Career Stats')
        portable.rename(renamed)
        exe = renamed/exe.name
        assert 'both history screens passed' in backend('check')

        invalid = temp/'Incompatible Game'
        invalid.mkdir()
        (invalid/'fifa16.exe').write_bytes(b'Incompatible executable sentinel')
        assert 'SHA-256 does not match' in backend('prepare-selected', invalid, profile, expected=1)
        assert not (profile/'cache0').exists()
        assert json.loads((state/'settings.json').read_text(encoding='utf-8')) == settings

        from_files = (
            ('PlayerHistory12D_Ampliado.bigf', 'cache0/data/ui/game/screens/career/SquadRanking.big'),
            ('ClubHistory12D.bigf', 'cache0/data/ui/game/screens/career/managermode/ManagerModeSeasonObjectives.big'),
        )
        journal = state/'temporary-screens.json'
        operations = []
        for name, rel in from_files:
            path = profile/rel
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(state/'payload'/name, path)
            operations.append(dict(relative=rel, before=None, after=digest(path), backup=None))
        journal.write_text(json.dumps({'root': str(profile), 'files': operations}), encoding='utf-8')
        (profile/from_files[1][1]).unlink()  # Simulate a session interrupted midway through cleanup.
        assert 'Temporary Career Stats screens removed' in backend('recover-selected')
        assert not journal.exists()
        assert all(not (profile/rel).exists() for _, rel in from_files)
        assert digest(save) == saved_hash
        print('Portable setup, screen generation, relocation, mismatch and interrupted recovery passed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('zip', type=Path)
    parser.add_argument('game', type=Path, help='Matching disposable copy of the required game files')
    args = parser.parse_args()
    run(args.zip.resolve(strict=True), args.game.resolve(strict=True))
