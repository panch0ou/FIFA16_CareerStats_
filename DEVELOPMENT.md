# Developer setup

Use the **Source Code** archive on Windows x64. The player archive includes the binaries and requires no development tools.

## Build both archives

Install 64-bit CPython with Tkinter, plus x64 Rust with Cargo. Python 3.12.4 and GNU Rust 1.99.1 were used for the release. The GNU build uses the Rust toolchain's bundled `rust-lld.exe`. The MSVC build requires its C++ linker tools and has not been tested here. [Python for Windows](https://docs.python.org/3/using/windows.html) · [Rust installation](https://rust-lang.org/tools/install/)

```powershell
python -m venv .local\venv
.\.local\venv\Scripts\python.exe -m pip install -r tools\requirements-build.txt
.\.local\venv\Scripts\python.exe -B tools\package_release.py
```

The script builds the three screen helpers and the observer, records their SHA-256 hashes, freezes the windowed application, and writes the User Release and Source Code ZIPs under `Release_v0.1.2`. The launcher and Windows executable version metadata use `runtime/version.py`. The source archive supplies the exact historical files in `Data`. Development worktrees from earlier builds can use the same files in `.local/inputs`. SHA-256 must match the profile.

The player ZIP bundles the Python runtime and Cargo-built helpers. PyInstaller's folder layout starts without extracting a runtime on every launch. Worker roles re-enter the same executable and direct diagnostics to files. [PyInstaller Windows runtime behavior](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html)

## Test from source

```powershell
$env:PYTHONPATH = (Resolve-Path runtime).Path
python -B -m unittest discover -s tests -v
.\Diagnostics.cmd configure --game "D:\Test Games\FIFA 16" --profile "D:\Test Profiles\FIFA 16"
.\Diagnostics.cmd build
.\Diagnostics.cmd check
.\Diagnostics.cmd simulate
python -B runtime\desktop.py
```

Use a disposable copy of the matching game and a separate Windows account or VM for in-game acceptance. Open FIFA once in that account to create its own Documents profile. A simulated folder alone does not redirect FIFA's own save path.

Run the packaged offline smoke test with `python -B tests/smoke_portable.py Release_v0.1.2/FIFA16_CareerStats_User_Release.zip "D:\Test Games\FIFA 16"`. The harness uses a disposable profile and state directory, verifies generation and recovery, and never starts FIFA. The unit suite includes CRC-valid synthetic DATA with widened IDs, extra tables and fields, zero and positive assists, successive saves and seasons, and ambiguous club attribution.

For source-level inspection, see [ARCHITECTURE.md](ARCHITECTURE.md) and [CONTRIBUTING.md](CONTRIBUTING.md). Preserve all game, payload, process, memory and CRC validation when extending the profile.
