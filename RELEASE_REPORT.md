# Flexible compatibility release validation

## What changed

- The launcher no longer fingerprints or opens the loose roster database. Transfers, attributes, added IDs and roster counts are separate from the native compatibility checks.
- Save metadata is checked against the fields the tracker needs. Required table or field errors name the missing or incompatible part. Extra metadata is ignored. Optional position and league metadata only affect the corresponding statistics or classification.
- The two required screens are checked by content. A compatible loose replacement or repacked archive can pass. A changed APT, constant table, fixed wrapper or opaque trailer still requires separate verification.
- The exact executable and native BIN checks, known proxy exclusions, process path and memory signatures, read-only save CRC validation and recovery journal remain in place.
- Technical compatibility and pre-2015/16 historical coverage are shown separately. The historical inputs, native observer, tracked save ancestry and bundled runtime remain in the portable release.

## Validation

| Case | Result |
| --- | --- |
| Reference installation | The supported executable and game files passed offline setup from the portable ZIP. |
| Modified game database | A disposable copy with a changed player field and recalculated valid database CRC passed. Its roster database SHA-256 differs from the reference. The same copy had extra XML metadata and a loose screen with changed alignment padding. |
| Added players, teams, roster links, tables and columns | CRC-valid synthetic DATA decoded wider IDs, a custom team and roster, and extra tables and columns. A mismatched unused column did not block decoding. |
| Missing history | An added player with no historical match retained eligible Career Mode goals and appearances. An uncovered club returned blank historical records. |
| Invalid structure and executable | Missing or wrong-type required metadata, an absent required binary field, and bad save CRC failed validation. An unknown executable failed before the launcher wrote anything to the profile. |
| Both screens | The packaged helper regenerated all four pinned APT/BIGF outputs. Setup, relocation, mismatches and interrupted recovery passed using disposable profiles. |
| New Career and continuation | Synthetic native notifications exercised the existing tracker against CRC-valid DATA and a local registry. The new Career and its continuation stayed linked and the tracker left the DATA bytes unchanged. |
| Packaging | Both ZIPs passed integrity and privacy checks. The portable bundle was run from a relocated path with Python and Rust excluded from PATH. All 27 automated tests passed, including from the extracted source archive. |

## In-game evidence

The project owner reported that the preceding portable build worked inside FIFA 16. This compatibility update was tested offline. No FIFA session was started for these checks. Live hooks, screen rendering and real Career tracking on modified installations remain unverified for this update. The original project, personal installation, database and saves were left untouched.

The 2015/16 historical cutoff remains fixed. FIP, modern seasons and other native builds remain outside the verified scope. The ZIPs were prepared locally. Nothing was published.

See [installation](INSTALLATION.md), [developer setup](DEVELOPMENT.md), and the [SoccerGaming draft](SOCCERGAMING_DRAFT.md).
