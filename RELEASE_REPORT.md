# v0.1.2 Beta validation

## Import behavior

The launcher discovers Career saves in the active profile and accepts additional folders and files. The user chooses the chronological sequence, reviews the available fields by season and confirms the shared Career identity. A registered checkpoint can anchor an append. Earlier files can be linked before a selected registered root.

The importer reuses the existing registry and save hashes. Preview works in memory. Commit revalidates the files and reconstructed history in one SQLite transaction, including screen capacity checks. FIFA saves remain read-only. On a later run, loading a registered hash gives the native tracker the existing Career and ancestry.

## Test coverage

All 52 automated tests passed. Added regressions exercise mixed calendar years and split-year seasons, chronological ordering across 16-row pages, shared league/cup/continental identification, conflicting object codes, legacy stored cup rows, duplicate prevention and continued native save events after import. Positive and zero clean-sheet checks preserve the existing evidence requirement.

An earlier portable GUI check imported one advanced synthetic save, cancelled a multi-save preview without changing the registry, and then linked an earlier save to the same Career. Registry verification confirmed two checkpoints and the latest cumulative totals of 7 goals and 4 assists.

## Final import corrections

The reader already extracted multiple statistical groups. The old automatic classification only registered the primary league, and PLAYER HISTORY omitted groups without official competition evidence. Both import and normal tracking now resolve the same native objects, types and English names. Saved native evidence remains with each new checkpoint. Older registries can resolve their existing raw observations through the same catalog. The preview reports excluded group IDs.

PLAYER HISTORY now sorts every player's full list using its numeric source year and a calendar-year/season discriminator before pagination. Stable competition and club tie breakers make the result independent of snapshot traversal and row insertion order.

Regression checks on independent copies of two consecutive Fulham saves recovered 67 official player rows for 2015/16 and 94 for 2016/17. Both include FA Cup and Capital One Cup. The later save also includes Community Shield and Euro League. Combined import produced 161 unique rows, all with validated assists, and exactly matched normal registration of the same saves. Reimport added no snapshots. The same rows were recovered after removing new metadata to emulate an older registry.

The complete generated PLAYER HISTORY stream was checked for 10,151 players over 15,038 pages, with up to six pages per player, and both APT payloads passed capacity validation. Original save and game metadata hashes matched before and after the copy-based checks. Unidentified group 1759 remains excluded. These real saves have no clean-sheet certification, so their clean-sheet counts remain unknown.

- An individual advanced save, same-season cumulative updates, different seasons, verified assists and the treatment of missing clean-sheet evidence.
- Duplicate content under different names, manual continuation, earlier checkpoint backfill, and distinct registered Careers and branches.
- Changed and incomplete files, cancellation before commit, and transaction rollback when validation fails.
- Simulated native load and save events after import, preservation of observations for a departed player, and overlapping club contexts excluded from PLAYER HISTORY totals.
- Portable executable metadata, screen generation, relocation, incompatible executable rejection, recovery, and archive contents.

These checks use disposable files, synthetic saves and independent copies of existing saves. Live FIFA rendering and tracking require an in-game acceptance session. Historical baseline hashes, supported native build checks and save CRC validation were preserved.

See [CHANGELOG.md](CHANGELOG.md), [INSTALLATION.md](INSTALLATION.md), and [DEVELOPMENT.md](DEVELOPMENT.md).
