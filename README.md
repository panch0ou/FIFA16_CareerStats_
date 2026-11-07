# FIFA 16 Career Stats

**v0.1.1 Beta** · [Changelog](CHANGELOG.md)

Career Stats adds **PLAYER HISTORY** and **CLUB HISTORY** to FIFA 16 PC Manager Career. The initial profile follows the 2015/16 timeline. The historical baseline covers 10,142 FIFA player IDs and 13 clubs.

This update publishes Career Mode assists from validated records in identified competitions. It can use the raw rows already in your local Career Stats history.

## Play

1. Download the **User Release** ZIP and extract the entire archive.
2. Open **CareerStats.exe**.
3. If needed, choose your FIFA 16 game or profile folder.
4. Click **Launch FIFA 16**.

The Windows x64 release includes its runtime, history, and compiled helpers. It prepares the two screens from your verified FIFA installation and removes them after the game closes. [Installation and recovery](INSTALLATION.md)

## Compatibility

The [2015/16 profile](profiles/fifa16-2015-16.json) supports one verified FIFA 16 PC executable and native BIN. Edited squads, transfers, players and clubs can pass the technical checks if the required save metadata and two Career Mode screens remain compatible. The launcher does not check the hash of the game roster database.

Historical coverage is separate. The included records end before 2015/16 and use FIFA IDs. New IDs can have no history, and reused IDs can match the wrong record. FIP, modern seasons, other executables and console versions remain unverified or outside this profile. The compatibility update was tested offline. [Known limitations](KNOWN_LIMITATIONS.md)

| Screenshot | Planned capture |
| --- | --- |
| PLAYER HISTORY | A player with historical and saved Career Mode rows |
| CLUB HISTORY | Historical records for a covered club |

## Develop

The **Source Code** ZIP contains the code, historical inputs, build tools, tests and CSV templates. Start with [DEVELOPMENT.md](DEVELOPMENT.md), [ARCHITECTURE.md](ARCHITECTURE.md), and [CONTRIBUTING.md](CONTRIBUTING.md).

The project builds on 12Final and the companion FIFA 16 TransferEngine. See [features](FEATURES.md), [data coverage and sources](DATA.md), and [credits and notices](LICENSE_REVIEW.md). FIFA 16 and its game resources belong to their respective rights holders.
