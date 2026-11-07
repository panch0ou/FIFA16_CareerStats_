"""Formats the two APT views from one immutable Career head."""
from collections import defaultdict
from contextlib import closing, nullcontext
import json
import re
import sqlite3

import carreras

BUCKETS = 512
CAPACITY = 32768
BASELINE = HISTORICAL_DB = None
HISTORICAL_BEFORE = 2015
# Transfermarkt -> FIFA. Identical names may be different clubs.
HISTORICAL_CLUBS = {}
STAT_KEYS = ('apps', 'goals', 'assists', 'clean_sheets')
RECORD_KEYS = (
    ('all_time', 'most_appearances'), ('all_time', 'most_goals'),
    ('all_time', 'most_assists'), ('single_season', 'most_goals'),
    ('single_season', 'most_assists'),
)


def historical():
    history = defaultdict(list)
    with closing(sqlite3.connect(HISTORICAL_DB.as_uri()+'?mode=ro', uri=True)) as db:
        for pid, club, year, season, apps, goals, assists, name, competition in db.execute(
                'SELECT s.fifa_id,s.club_id,s.season_start,p.source_season,'
                's.appearances,s.goals,s.assists,s.club_name,s.league_name '
                'FROM staged_league_stats s LEFT JOIN ampliacion_procedencia p '
                'USING(fifa_id,season_start,club_id,league_id) '
                'WHERE s.season_start<? AND s.fifa_id>0 ORDER BY s.fifa_id,s.season_start,s.rowid', (HISTORICAL_BEFORE,)):
            row = (season or season_label(year), apps, goals, assists, None, f'{name} / {competition}')
            history[pid].append((HISTORICAL_CLUBS.get(str(club)), tuple(map(safe, row)),
                                 (year, 0 if str(row[0]).isdigit() else 1)))
    return history


def season_label(year):
    return f'{year % 100:02d}/{(year+1) % 100:02d}'


def chronological_key(record):
    club, row = record[:2]
    label = row[0].strip()
    if len(record) > 2:
        period = record[2]
    elif re.fullmatch(r'\d{4}', label):
        period = (int(label), 0)
    elif re.fullmatch(r'\d{2}/\d{2}', label):
        # The display covers the historical baseline and FIFA 16's Career years.
        # Keep 99/00 before 00/01 instead of sorting the abbreviated year text.
        year = int(label[:2])
        period = (1900 + year if year >= 50 else 2000 + year, 1)
    elif re.fullmatch(r'\d{4}/\d{2,4}', label):
        period = (int(label[:4]), 1)
    else:
        period = (10000, 0)
    return (*period, row[5].casefold(), -1 if club is None else club, row)


def safe(value):
    text = '-' if value is None else str(value)
    if any(ch in text for ch in '|^~\r\n\0'):
        raise ValueError(f'Value contains an unsupported screen delimiter: {text!r}')
    return text


def totals(rows):
    result = []
    for index in range(1, 5):
        values = [int(row[index]) for row in rows if row[index].isdigit()]
        result.append(str(sum(values)) if values else '-')
    return tuple(result)


def player_line(pid, past, current, club_id, active):
    records = sorted([*past, *current], key=chronological_key)
    rows = [record[1] for record in records]
    if len(rows) > 512:
        raise ValueError(f'Player {pid} exceeds the 512-row screen limit')
    local = totals([record[1] for record in records if club_id is not None and record[0] == club_id])
    career = totals(rows)
    if current:
        status = 'PRE-2015 + PARTIAL CAREER' if past else 'PARTIAL CAREER STATS'
    else:
        status = 'PRE-2015 HISTORY' if active else 'PRE-2015 / CAREER UNVERIFIED'
    return '|'.join((str(pid), '^'.join('~'.join(row) for row in rows),
                     '       '.join(local[:3]), local[3], '       '.join(career[:3]),
                     f'CS {career[3]}', status))


def club_packet(baseline, club):
    item = baseline['clubs'].get(str(club))
    records = []
    for group, field in RECORD_KEYS:
        rec = item[group][field] if item else None
        if not rec or rec['value'] is None:
            records.append('-')
            continue
        suffix = f" ({rec['season']})" if group == 'single_season' else ''
        records.append(safe(f"{rec['player_name']} - {rec['value']}{suffix}"))
    return '|'.join((str(club), *records, 'ALL COMPETITIONS', ''))


class Source:
    def __init__(self):
        self.baseline = json.loads(BASELINE.read_text(encoding='utf-8'))
        self.past = historical()
        self.historical_buckets = [[] for _ in range(BUCKETS)]
        for pid, rows in self.past.items():
            self.historical_buckets[pid % BUCKETS].append(player_line(pid, rows, [], None, False))

    def snapshot(self, head, db=None):
        if head is None:
            return self.historical_buckets, 'WAIT', {'head': None}
        data = carreras.history(head, db)
        with (carreras.connect() if db is None else nullcontext(db)) as db:
            root = db.execute('SELECT season,metadata FROM snapshots WHERE sha=?',
                              (data['ancestry'][-1],)).fetchone()
            club = db.execute('SELECT club FROM snapshots WHERE sha=?', (head,)).fetchone()[0]
        root_year = json.loads(root['metadata'])['calendar']['setupdate'] // 10000 - root['season'] + 1
        by_id = defaultdict(list)
        for r in data['official_player_rows']:
            context = r['club_id']
            name = self.baseline['clubs'].get(str(context), {}).get('club_name', f'CLUB {context}')
            counts = ((None,)*len(STAT_KEYS) if r['assist_evidence'] == 'ambiguous_club_attribution'
                      else tuple(r[k] for k in STAT_KEYS))
            row = (season_label(root_year + r['season'] - 1), *counts,
                   f"{name} / {r['competition']}")
            by_id[r['player_id']].append((context, tuple(map(safe, row)),
                                         (root_year + r['season'] - 1, 1)))
        buckets = [[] for _ in range(BUCKETS)]
        for pid in sorted(self.past.keys() | by_id.keys()):
            buckets[pid % BUCKETS].append(player_line(pid, self.past.get(pid, ()), by_id.get(pid, ()), club, True))
        return buckets, club_packet(self.baseline, club), {
            'head': head, 'career_id': data['career_id'], 'club': club,
            'career_rows': len(data['official_player_rows']),
        }
