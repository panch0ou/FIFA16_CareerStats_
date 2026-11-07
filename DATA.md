# Historical data

The baseline stops before the 2015/16 Career Mode starting season. The preserved player SQLite has **153,579 rows for 10,142 FIFA player IDs**. It has 11,209 identity mappings, including 1,067 with no eligible rows. The earliest staged season starts in 1992. Coverage is uneven across players, seasons and competitions. There are 13,582 rows with unknown goals and one with unknown assists in this snapshot. Historical clean sheets are unavailable. Unknown counters are stored as SQL NULL.

## Sources and review

- Salimt's Transfermarkt-derived profiles and performance data supply most player rows. The project's earlier sources and manual additions are retained in the baseline. See each row's source URL, where available. [Salimt football-datasets](https://github.com/salimt/football-datasets)
- The archive labeled FIFA Model supported player identity matching. The archive labeled Kaggle2 supplied a partial match-level cross-check and one accepted additional row. The exact Kaggle2 and FIFA Model source releases and terms require confirmation.
- The final audit added 37 reviewed identity mappings and 720 eligible rows using birth dates, name variants, nationality and season/club evidence. Older links often rest on name and birth date. The audit recorded 261 probable candidates that still need review, including 203 with eligible rows, plus unresolved competing IDs. It preserved 2,230 prior source discrepancies rather than averaging competing figures.
- Club records combine club and league publications, historical tables and documented candidates. `club_records.json` retains source, scope and evidence fields for the available records. The 13-club baseline contains 59 populated values and six gaps.

## Club coverage and confidence

The baseline covers Arsenal, Fulham, SC Paderborn 07, Paris FC, FC Crotone, Stevenage FC, Burton Albion, Antalyaspor, Randers FC, Colo-Colo, Rangers de Talca, Deportivo Alavés and Pro Vercelli. Fulham's historical assists figure is a league-only reconstruction. Arsenal's all-time assists entry uses a Premier League figure. Single-season records can be league-only or follow the scope of the cited source. The 11 added clubs have mixed coverage and should be treated as documented candidates where evidence falls short of an exhaustive club record. Assist definitions vary across sources.

## Identity and aggregation

Player IDs are tied to the FIFA 16 catalog, and shared names can represent different players or clubs. The runtime only uses the six checked historical club equivalences listed in the profile for club totals. The broader historical competition IDs are source identifiers. Native Career Mode competition tuples are a separate mapping. See [FEATURES.md](FEATURES.md) for how the display handles missing values and saved Career Mode data.

Edited squads and transfers can use the same historical baseline. IDs added by a mod have no prior record unless the baseline already contains that ID. If a patch reuses an ID for a different player or club, Career Stats can display the original entity's record. It does not infer identity from the name, team, or attributes. The pre-2015/16 cutoff stays fixed.

Both archives carry the preserved player database and club records. Source attribution and coverage notes remain in the data. See [credits and redistribution inventory](LICENSE_REVIEW.md).
