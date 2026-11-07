# Contributing

Open a local change with a focused explanation, evidence and expected output. Include the profile ID, the affected IDs and seasons, and whether the change adds or corrects a row. Use a disposable profile for testing and redact diagnostics before sharing.

## Historical data

Copy the header-only templates in [contributions](contributions) into a working folder. Use UTF-8. One submission can include any combination of the three files.

| File | What to enter |
| --- | --- |
| `mappings.csv` | A new one-to-one FIFA and Transfermarkt ID pair, with an evidence URL. Provide independent identity evidence such as date of birth and matching clubs in the same season. |
| `player_history.csv` | One player/season/club/competition row. Use `add` for a new key and `replace` for a correction to an existing key. Use the external club and competition IDs. Leave unknown numeric fields empty and use 0 only for a reported zero. Retain the source season label and cite the source. |
| `club_records.csv` | One FIFA team ID and record category. Use `all_time` or `single_season`, with `most_appearances`, `most_goals` or `most_assists` as supported by the panel. Supply `season_start` for single-season rows. A historical player may lack a FIFA ID. Add the actual scope, source URL and confidence. |

Use `verified`, `partial` or `provisional` to describe evidence coverage. Include provenance and permission information with the submission. Example key: an existing FIFA player and external ID in the baseline, start year `2014`, display label `14/15`, one verified external club ID and one verified competition ID. Use your cited counters for that key.

For a wrong identity mapping, submit both IDs, the affected rows and independent evidence. The tool refuses a second mapping for an existing FIFA or Transfermarkt ID. A maintainer must remove or reconstruct affected history and provenance together in a new candidate before accepting an identity correction. For new club equivalences, verify country, identity and period as well as the display name before changing `historical_clubs`.

## Stage and validate

With the Source Code archive and a successful [developer build](DEVELOPMENT.md), run:

```powershell
python -B tools/stage_data.py path\to\reviewed-csv my-candidate
python -B tools/stage_data.py path\to\reviewed-csv my-full-candidate --build-screens
```

The tool copies the approved SQLite into a new directory under `.local/candidates`. It checks the cutoff, IDs, mappings, duplicate keys, counts, sources, database integrity and player screen capacity. With `--build-screens` it also rebuilds both screens and writes a candidate compatibility manifest. Review the SQLite and records diff before promotion. Use a separate project copy and disposable profile to test the candidate, including known saved branches, capacity, both panels and recovery. Keep the manifest and history inputs together. See [ARCHITECTURE.md](ARCHITECTURE.md) for resource generation.

## Code and compatibility

```powershell
$env:PYTHONPATH = (Resolve-Path runtime).Path
python -B -m unittest discover -s tests -v
.\Diagnostics.cmd check
.\Diagnostics.cmd simulate
```

Fork the project to experiment with new profiles. Record the executable and native BIN fingerprints, starting season, historical cutoff, ID crosswalks, competition mappings and screen contract. Document the fields read from DATA and validate those fields against the actual save. Ordinary roster edits do not need a new fingerprint.

An additional profile requires controlled isolated tests of both screens, save/load/reload, cleanup and interrupted recovery. Keep the executable, memory and CRC checks enabled. For a pull request, include the profile and reproducible test results with personal paths and saves removed. FIP and modern profiles are future work.
