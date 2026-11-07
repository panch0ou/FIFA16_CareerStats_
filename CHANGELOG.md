# Changelog

## v0.1.2 Beta

- Fixed PLAYER HISTORY chronology across all players and pages. Numeric source years order calendar years before the matching split-year season, with stable competition ordering within each period.
- Import and normal tracking now share native competition identification for leagues, domestic cups and international club competitions. Existing stored cup observations can be displayed without importing duplicate snapshots. Missing or conflicting competition evidence is reported in the import preview.
- Added **Import Existing Career** with save discovery, manual selection, ordering, a preview and explicit confirmation.
- Import single saves or chronological checkpoints, append to a registered branch, and add earlier checkpoints before an explicitly selected registered root.
- Imports use one transaction, reuse known hashes and retain the existing Career registry and automatic tracking.
- PLAYER HISTORY withholds overlapping club counts when the source cannot establish a same-season club split.

## v0.1.1 Beta

- PLAYER HISTORY now publishes Career Mode assists from validated 48-byte statistics rows without requiring a manual certification for each Career, club and competition.
- Validated zero counts display as 0. Unverified layouts and ambiguous same-season club attribution still display a dash.
- Existing Career registries can display assists from saved, validated rows. The update needs no save changes or registry migration.
- The executable, native hooks, save CRC checks, competition classification and clean-sheet validation retain their existing safeguards.

## v0.1.0 Beta

- Portable Windows launcher, 2015/16 history, and support for roster edits that retain the required native files, save metadata and screen templates.
