# Features

## PLAYER HISTORY

In Manager Career, open **Squad → Squad Ranking**. The panel uses the game's player selector and portraits. The legacy keyboard layout uses W/E for players and Up/Down for pages. The renderer supports 16 rows per page, up to 512 rows per player. Historical rows show season, club and competition. Each unknown field is shown as a dash. A total sums the numeric observations for that field, and stays a dash when all contributing values are unknown.

**CAREER** combines the pre-2015/16 history and eligible saved Career Mode rows. **Club** uses the active tracked club and includes historical rows where that club's external ID has a verified FIFA match. A row with an unmapped historical club still counts toward CAREER. Some observations have incomplete coverage, so totals are sums of available values.

Players without matching historical IDs can still show eligible Career Mode rows. Newly added IDs with no observations have no history to display. Clubs with no matching historical record show dashes. Reused IDs can match records for the original player or club.

## CLUB HISTORY

Open the Manager Career **Season Objectives** screen. Its five categories are most appearances, goals and assists across the available historical record, plus most goals and assists in a single season. The club is selected by FIFA team ID. Clubs outside the baseline and unsupported values show dashes. The five shipped record values are compiled into the screen and stay fixed throughout a Career. The runtime sends the club context and scope heading. The heading **ALL COMPETITIONS** is a display label. Some records have league-only or other partial scopes detailed in [DATA.md](DATA.md).

## Career Mode tracking

The monitor observes native load and save events. It confirms a loaded Career only after an eligible DATA read and a successful game flow, then looks up the save's exact hash. It can register an identifiable new Career and follow a single confirmed continuation through an overwrite, autosave or Save As. An unverified or ambiguous load stays separate, and incomplete events can make the monitor fall back to historical data.

Tracking uses the selected branch and latest eligible cumulative observation for each season, roster-club context, competition and player. It does not add repeated snapshots together. The developer diagnostics retain manual registration for an eligible unregistered save whose origin can be verified.

Automatic competition rules cover the verified native tuples for the Premier League and Championship. Other groups need their own competition evidence. Once a row belongs to a classified official competition, its assists can be read from the validated 48-byte layout without a per-Career or per-club certification. A validated zero displays as 0. An unverified layout or ambiguous same-season club attribution displays as a dash.

Clean sheets still require evidence and a verified goalkeeper position. Friendlies and unclassified groups are excluded. The project reads saves and stores its own observations in SQLite. Unsaved progress, complete club match totals, transfer-by-transfer splits and statistics from unobserved leagues remain outside the verified scope.

Modified squads can be tracked if their saves retain the required tables, fields, and native event and statistics formats. A save that fails structure or checksum checks is rejected by the tracker. See [ARCHITECTURE.md](ARCHITECTURE.md) for the field contract.
