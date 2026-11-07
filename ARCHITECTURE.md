# Architecture

| Area | Responsibility |
| --- | --- |
| `runtime/desktop.py`, `runtime/discovery.py` | Windowed launcher, folder discovery, manual selection and backend dispatch |
| `runtime/launch.py`, `layout.py`, `lanzador.py` | Configured paths, pinned validation, runtime preparation and supervision |
| `runtime/archivos.py` | Journaled temporary cache installation and hash-checked recovery |
| `runtime/observar_cargas.py`, `native/observer.rs`, `runtime/bridge.py` | Existing observer and Player ID bridge, scoped to the verified game process |
| `runtime/guardados.py`, `estado_activo.py`, `carreras.py` | Save events, identity, CRC-checked read-only extraction and snapshot ancestry |
| `runtime/career_schema.py`, `runtime/transferengine` | Required metadata projection and bounded DATA decoding |
| `runtime/datos.py`, `transporte.py`, `monitor.py` | Historical and tracked data formatting, bounded screen publication and worker lifecycle |
| `runtime/screen_assets.py`, `tools/build_payload.py`, `tools/apt_patcher` | Extract game templates, generate and repack screens, compile portable helpers |
| `tools/package_release.py`, `Diagnostics.cmd` | Build the portable and source archives and run developer diagnostics |
| `tools/stage_data.py`, `contributions`, `tests` | Candidate builds, CSV templates and disposable validation |

## Runtime sequence

1. Detect game and profile folders. Check the executable and native BIN, required save metadata, both screen templates, bundled inputs and helpers, and absence of conflicting cache files. Prepare the screens locally when needed and validate history and known snapshots against screen capacity.
2. Record a recovery journal and create two cache files under `cache0/data/ui/game/screens/career`. Start FIFA from its installation folder.
3. Wait for the pinned native instructions. The monitor applies the original two-operand Player ID bridge and loads one local observer into the running game. The observer records bounded native load and save evidence and retains its executable path, module base and import checks.
4. Read the immutable history using SQLite read-only mode. Resolve the active snapshot using native flow evidence and save hashes. Write only to recognized APT memory reservations and the separate local registry and logs.
5. Wait for FIFA and the monitor to exit and remove the exact temporary resources. If the supervisor is interrupted, use the journal after FIFA closes. The launcher serializes sessions with a Windows mutex.

The packaged generators reproduce both reference APT/BIGF pairs without a compiler. The validator reads a loose copy of a required screen if present, otherwise it reads the matching BIG4 entry. It accepts raw BIGF or the supported chunkzip representation and normalizes alignment padding and entry offsets. The fingerprint still covers the actual APT, constants, fixed wrapper fields and opaque trailer. Unrelated archive entries have no bearing on compatibility.

The portable observer is validated by its exports and bundled hash. At attachment the validated process path is passed in a bounded UTF-16 buffer. The observer checks its own process path, module base, and ReadFile import. The launcher checks the pinned executable and BIN, absence of known conflicting proxy files, process path, and in-memory signatures before patching. No DLL is placed in the game folder.

The player release is a windowed PyInstaller folder bundle. The backend, monitor and observer use the same executable with internal roles and dedicated logs. Portable release state is scoped to the Windows user under `%LOCALAPPDATA%\FIFA16CareerStats`. Package data and runtime are read from beside the executable.

## Compatibility profiles

`profiles/fifa16-2015-16.json` describes the supported native files, 2015/16 start and cutoff, history and screen hashes, two source screens, known league tuples and reviewed historical club crosswalk. Player mappings are stored in the history database. This is a single profile. A selectable profile system would also need separate runtime state, independently validated native offsets and CRC rules, and a new APT contract where applicable.

## Save metadata contract

Career Stats does not open `data/db/fifa_ng_db.db`. It reads the loose `data/db/fifa_ng_db-meta.xml` to map names, four-character field codes, bit widths and numeric offsets for the relevant tables in Career DATA. A required field must have the expected type and agree with its descriptor in the actual save. Extra tables, columns and roster rows are permitted within the binary reader's bounds. The reader still checks the bounds and CRCs of the save, including tables whose values Career Stats does not interpret.

| Save table | Fields used |
| --- | --- |
| `career_users` | `clubteamid`, `seasoncount`. Optional `leagueid` and `primarycompobjid` for league classification. |
| `career_calendar` | `currdate`, `setupdate`. Optional `enddate` for the season record. |
| `teamplayerlinks` | `teamid`, `playerid` for the current roster |
| `players` | Optional `playerid` and `preferredposition1` for goalkeeper position |
| `leagues` | Optional `leagueid`, `leaguename`, `countryid`, `level` for league classification |

The monitor and observer use native events and fixed code locations. They do not depend on the contents of the roster database, ANT catalog or competition engine DLL as direct inputs. The player bridge reads two reference instructions from the native BIN. Player history joins by FIFA player ID and club records by FIFA team ID. Save statistics use roster IDs and the existing 48-byte statistics layout. No catalog-wide player, club, or competition mapping is required.

The APT transport uses 512 buckets of 32 KiB, an epoch marker and a separate club reservation. Delimiters are reserved and some APT literals have Latin-1 limits. The monitor bounds its memory scans and validates the reservations before writing. The registry stores immutable save snapshots and evidence. See [DATA.md](DATA.md) for the historical schema and coverage policy.
