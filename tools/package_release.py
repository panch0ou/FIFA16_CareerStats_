"""Build separate portable Windows and complete source archives."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'runtime'))
import layout
from build_payload import compile_helpers, rust_environment
from version import DISPLAY_VERSION, VERSION

BUILD = ROOT/'.local/build'
OUTPUT = ROOT/f'Release_v{VERSION}'
USER_ZIP = OUTPUT/'FIFA16_CareerStats_User_Release.zip'
SOURCE_ZIP = OUTPUT/'FIFA16_CareerStats_Source_Code.zip'
DATA_NAMES = ('historial_ampliado.sqlite', 'club_records.json')


def history_inputs():
    spec = layout.read(layout.PROFILE_FILE)
    layout.check_files(layout.INPUTS, dict(zip(DATA_NAMES,
                       (spec['history_sha256'], spec['club_records_sha256']), strict=True)))
    return [(layout.INPUTS/name, f'Data/{name}') for name in DATA_NAMES]


def notice_files(portable):
    notices = portable/'Notices'
    notices.mkdir()
    shutil.copyfile(Path(sys.base_prefix)/'LICENSE.txt', notices/'Python.txt')
    for library in ('tcl8.6', 'tk8.6'):
        path = Path(sys.base_prefix)/'tcl'/library/'license.terms'
        if path.is_file():
            shutil.copyfile(path, notices/f'{library}.txt')
    packaging = importlib.metadata.distribution('pyinstaller')
    for path in packaging.files or []:
        if path.name.upper().startswith(('LICENSE', 'COPYING')):
            shutil.copyfile(packaging.locate_file(path), notices/f'PyInstaller-{path.name}')
    env = rust_environment()
    cargo = ROOT/'tools/apt_patcher/Cargo.toml'
    meta = json.loads(subprocess.check_output(['cargo', 'metadata', '--locked', '--format-version=1',
                                              '--manifest-path', str(cargo)], env=env))
    for crate in meta['packages']:
        if not crate['source']:
            continue
        folder = Path(crate['manifest_path']).parent
        for path in folder.iterdir():
            if path.is_file() and path.name.upper().startswith(('LICENSE', 'COPYING', 'NOTICE', 'UNLICENSE')):
                shutil.copyfile(path, notices/f"{crate['name']}-{crate['version']}-{path.name}")
    rust_root = Path(subprocess.check_output(['rustc', '--print', 'sysroot'], env=env, text=True).strip())
    rust_docs = rust_root/'share/doc/rust'
    copyright = rust_docs/'COPYRIGHT-library.html'
    if copyright.is_file():
        rust_notices = notices/'Rust'
        rust_notices.mkdir()
        shutil.copyfile(copyright, rust_notices/copyright.name)
        shutil.copytree(rust_docs/'licenses', rust_notices/'licenses')


def build_user():
    import PyInstaller.__main__

    helpers = BUILD/'helpers'
    compile_helpers(helpers)
    version_file = BUILD/'windows-version.txt'
    windows_version = tuple(map(int, VERSION.split('.'))) + (0,)
    version_file.write_text(
        f"""VSVersionInfo(
    ffi=FixedFileInfo(filevers={windows_version!r}, prodvers={windows_version!r},
                      mask=0x3f, flags=2, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
    kids=[StringFileInfo([StringTable('040904B0', [
        StringStruct('FileDescription', 'FIFA 16 Career Stats'),
        StringStruct('FileVersion', {VERSION!r}),
        StringStruct('ProductName', 'FIFA 16 Career Stats'),
        StringStruct('ProductVersion', {DISPLAY_VERSION!r}),
        StringStruct('OriginalFilename', 'CareerStats.exe'),
    ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
""", encoding='utf-8')
    PyInstaller.__main__.run([
        '--noconfirm', '--onedir', '--windowed', '--noupx', '--name', 'CareerStats',
        '--version-file', str(version_file),
        '--contents-directory', 'Runtime', '--paths', str(ROOT/'runtime'),
        '--distpath', str(BUILD/'dist'), '--workpath', str(BUILD/'pyinstaller'),
        '--specpath', str(BUILD), str(ROOT/'runtime/desktop.py'),
    ])
    portable = BUILD/'dist/CareerStats'
    data = portable/'Data'
    data.mkdir()
    for source, relative in history_inputs():
        shutil.copyfile(source, portable/relative)
    shutil.copyfile(layout.PROFILE_FILE, data/layout.PROFILE_FILE.name)
    shutil.copyfile(helpers/'runtime-manifest.json', data/'runtime-manifest.json')
    bundled = portable/'Runtime/Helpers'
    bundled.mkdir()
    for name in layout.read(data/'runtime-manifest.json')['files']:
        shutil.copyfile(helpers/name, bundled/name)
    notice_files(portable)
    return portable


def write_zip(path, files):
    temp = path.with_suffix('.tmp')
    with ZipFile(temp, 'w', compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for file, relative in sorted(files, key=lambda pair: pair[1]):
            if file.is_symlink() or not file.is_file():
                raise ValueError(f'Expected a regular package file: {relative}')
            archive.write(file, relative)
        if len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError('Duplicate archive names.')
    with ZipFile(temp) as archive:
        if archive.testzip() is not None:
            raise ValueError(f'ZIP integrity check failed: {path.name}')
    temp.replace(path)
    print(path)


def source_files():
    top = ('README.md', 'INSTALLATION.md', 'FEATURES.md', 'DATA.md', 'CONTRIBUTING.md',
           'ARCHITECTURE.md', 'KNOWN_LIMITATIONS.md', 'LICENSE_REVIEW.md', 'RELEASE_REPORT.md',
           'SOCCERGAMING_DRAFT.md', 'CHANGELOG.md', 'DEVELOPMENT.md', 'Diagnostics.cmd', '.gitignore')
    yield from ((ROOT/name, name) for name in top)
    for name, extensions in {
        'runtime': {'.py'}, 'native': {'.rs'}, 'profiles': {'.json'},
        'contributions': {'.csv'}, 'tools': {'.py', '.rs', '.toml', '.lock', '.txt'},
        'tests': {'.py'}, 'packaging': {'.txt'},
    }.items():
        for file in (ROOT/name).rglob('*'):
            relative = file.relative_to(ROOT)
            if file.is_file() and file.suffix in extensions and 'target' not in relative.parts:
                yield file, relative.as_posix()
    yield from history_inputs()


def package(portable):
    OUTPUT.mkdir(exist_ok=True)
    fixed_docs = [(ROOT/'packaging/README.txt', 'README.txt')]
    fixed_docs.extend((ROOT/name, f'Notices/{name}')
                      for name in ('DATA.md', 'FEATURES.md', 'LICENSE_REVIEW.md', 'CHANGELOG.md'))
    write_zip(USER_ZIP, [(file, file.relative_to(portable).as_posix())
                         for file in portable.rglob('*') if file.is_file()] + fixed_docs)
    write_zip(SOURCE_ZIP, list(source_files()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-build', action='store_true', help='Package a previously verified staging build')
    parser.add_argument('--build-only', action='store_true', help='Build staging files without writing archives')
    args = parser.parse_args()
    portable = BUILD/'dist/CareerStats' if args.reuse_build else build_user()
    if not args.build_only:
        package(portable)
