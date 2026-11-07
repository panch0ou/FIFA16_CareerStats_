"""Compile the portable helpers and prepare developer assets."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import layout
import monitor
import observar_cargas
from archivos import digest, target
from screen_assets import HELPER_NAMES, render

TOOLS = Path(__file__).resolve().parent

def rust_environment():
    env = os.environ.copy()
    if 'RUSTFLAGS' not in env:
        toolchain = subprocess.check_output(['rustc', '-vV'], env=env, text=True)
        if 'host: x86_64-pc-windows-gnu' in toolchain.splitlines():
            sysroot = subprocess.check_output(['rustc', '--print', 'sysroot'], env=env, text=True).strip()
            linker = Path(sysroot)/'lib/rustlib/x86_64-pc-windows-gnu/bin/rust-lld.exe'
            if linker.is_file():
                env['PATH'] = str(linker.parent) + os.pathsep + env['PATH']
                env['RUSTFLAGS'] = '-C linker=rust-lld.exe'
    return env


def compile_helpers(out):
    if not all(shutil.which(command) for command in ('rustc', 'cargo')):
        raise RuntimeError('Install stable x64 Rust with Cargo and add both commands to PATH.')
    env = rust_environment()
    # Rust panic locations can include paths to the checkout and Cargo cache.
    # Keep those locations useful without embedding the builder's folders.
    encoded = env.get('CARGO_ENCODED_RUSTFLAGS')
    flags = encoded.split('\x1f') if encoded else env.get('RUSTFLAGS', '').split()
    cargo_home = Path(env.get('CARGO_HOME', Path.home()/'.cargo')).resolve()
    flags.extend((f'--remap-path-prefix={cargo_home}=cargo-cache',
                  f'--remap-path-prefix={layout.ROOT}=career-stats'))
    env['CARGO_ENCODED_RUSTFLAGS'] = '\x1f'.join(flags)
    target_dir = layout.LOCAL/'build/cargo-target'
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run(['cargo', 'build', '--locked', '--release', '--manifest-path',
                    str(TOOLS/'apt_patcher/Cargo.toml'), '--target-dir', str(target_dir)],
                   env=env, check=True)
    for name in HELPER_NAMES:
        shutil.copyfile(target_dir/'release'/name, out/name)
    source = layout.ROOT/'native/observer.rs'
    dll = out/'observer_v5.dll'
    subprocess.run(['rustc', '--crate-type', 'cdylib', '--crate-name', 'observer', '-O',
                    *flags, str(source), '-o', str(dll)],
                   env=env, check=True)
    symbols = observar_cargas.exports(dll)
    required = {'Install', 'Uninstall', 'Notify', 'OBS_RECORDS', 'OBS_COUNT', 'OBS_DROPPED',
                'OBS_BANK', 'OBS_BANK_RECORD', 'OBS_BANK_SEQ', 'OBS_BANK_LEN',
                'FLOWS', 'FLOW_COUNT', 'FLOW_DROPPED'}
    if not required <= symbols.keys():
        raise RuntimeError('The rebuilt observer is missing required exports.')
    monitor.publish(out/'runtime-manifest.json', {
        'files': {name: digest(out/name) for name in (*HELPER_NAMES, dll.name)},
    })


def generate(game, out, records):
    compile_helpers(layout.HELPERS)
    render(game, out, records, layout.HELPERS)


def build(game):
    from carreras import require_reader
    require_reader()
    spec = layout.read(layout.PROFILE_FILE)
    layout.check_files(layout.INPUTS, {'historial_ampliado.sqlite': spec['history_sha256'],
                                      'club_records.json': spec['club_records_sha256']})
    with tempfile.TemporaryDirectory(dir=layout.LOCAL) as tmp:
        staging = Path(tmp)
        generate(game, staging, layout.INPUTS/'club_records.json')
        layout.check_files(staging, spec['screens'])
        layout.PAYLOAD.mkdir(exist_ok=True)
        for name in spec['screens']:
            dest = target(layout.LOCAL, 'payload/'+name)
            (staging/name).replace(dest)
    print('Local screens and observer built.')
