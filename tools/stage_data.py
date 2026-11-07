"""Apply reviewed CSV changes to a new local candidate for the 2015/16 profile."""
import argparse
from contextlib import closing
import csv
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'runtime'))
import datos
import layout
from archivos import digest, target
from build_payload import generate
from launch import check_game
from transporte import Screen

FIELDS = {
    'mappings': 'fifa_id transfermarkt_id evidence_url',
    'player_history': ('action fifa_id transfermarkt_id season_start source_season club_id club_name '
                       'competition_id competition_name appearances goals assists source_url confidence'),
    'club_records': ('action fifa_club_id club_name period metric fifa_player_id player_name '
                     'value season_start source_url scope confidence'),
}
CONFIDENCE = {'verified', 'partial', 'provisional'}


def csv_rows(folder, name):
    path = folder/f'{name}.csv'
    if not path.exists():
        return
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != FIELDS[name].split():
            raise ValueError(f'Unexpected columns in {path.name}. Use the provided template.')
        for row in reader:
            if None in row or None in row.values():
                raise ValueError(f'{path.name}:{reader.line_num} has an invalid column count.')
            yield {key: value.strip() for key, value in row.items()}


def number(value, minimum=0, maximum=2**31-1):
    if not re.fullmatch('[0-9]{1,10}', value) or not minimum <= int(value) <= maximum:
        raise ValueError(f'Expected a whole number from {minimum} to {maximum}: {value!r}')
    return int(value)


def counter(value):
    return number(value) if value else None


def source_url(value):
    parsed = urlparse(value)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise ValueError('A source URL is required.')
    return value


def label(value):
    if not value:
        raise ValueError('A display label is required.')
    return datos.safe(value)


def source_season(value, year):
    next_year = year + 1
    if value not in {str(year), datos.season_label(year), f'{year}/{next_year % 100:02d}',
                     f'{year}/{next_year}'}:
        raise ValueError(f'Source season {value!r} does not match start year {year}.')
    return value


def action(value, exists):
    if value != ('replace' if exists else 'add'):
        raise ValueError('Use add for a new key and replace for an existing key.')


def apply_history(db, folder, cutoff):
    for row in csv_rows(folder, 'mappings'):
        fifa = number(row['fifa_id'], 1)
        tm = number(row['transfermarkt_id'], 1)
        evidence = source_url(row['evidence_url'])
        db.execute('INSERT INTO mapping VALUES (?,?,?,?)',
                   (fifa, tm, f'Community review: {evidence}', 'reviewed'))
    seen = set()
    for row in csv_rows(folder, 'player_history'):
        fifa = number(row['fifa_id'], 1)
        tm = number(row['transfermarkt_id'], 1)
        if db.execute('SELECT transfermarkt_id FROM mapping WHERE fifa_id=?', (fifa,)).fetchone() != (tm,):
            raise ValueError(f'The reviewed FIFA to Transfermarkt mapping does not match player {fifa}.')
        year = number(row['season_start'], 1800, cutoff-1)
        club, competition = row['club_id'], row['competition_id']
        if not club or not competition:
            raise ValueError('Historical club and competition IDs are required.')
        key = (fifa, year, club, competition)
        if key in seen:
            raise ValueError(f'Duplicate historical key in the CSV: {key}')
        seen.add(key)
        exists = db.execute('SELECT 1 FROM staged_league_stats WHERE '
                            'fifa_id=? AND season_start=? AND club_id=? AND league_id=?', key).fetchone()
        action(row['action'], exists)
        stats = tuple(counter(row[k]) for k in ('appearances', 'goals', 'assists'))
        if all(value is None for value in stats):
            raise ValueError('Supply at least one known counter.')
        url, confidence = source_url(row['source_url']), row['confidence']
        if confidence not in CONFIDENCE:
            raise ValueError('Use verified, partial or provisional confidence.')
        db.execute('INSERT INTO staged_league_stats VALUES (?,?,?,?,?,?,?,?,?,?,?) '
                   'ON CONFLICT(fifa_id,season_start,club_id,league_id) DO UPDATE SET '
                   'club_name=excluded.club_name, league_name=excluded.league_name, '
                   'appearances=excluded.appearances, goals=excluded.goals, assists=excluded.assists, '
                   'source_url=excluded.source_url',
                   (fifa, tm, year, club, label(row['club_name']), competition,
                    label(row['competition_name']), *stats, url))
        db.execute('INSERT INTO ampliacion_procedencia VALUES (?,?,?,?,?,?,?) '
                   'ON CONFLICT(fifa_id,season_start,club_id,league_id) DO UPDATE SET '
                   'source_season=excluded.source_season, source=excluded.source, '
                   'confidence=excluded.confidence',
                   (*key, source_season(row['source_season'], year), url, confidence))


def apply_clubs(baseline, folder, cutoff):
    seen = set()
    for row in csv_rows(folder, 'club_records'):
        club_id = number(row['fifa_club_id'], 1, 2**32-1)
        name = label(row['club_name'])
        period, metric = row['period'], row['metric']
        key = (club_id, period, metric)
        if (period, metric) not in datos.RECORD_KEYS or key in seen:
            raise ValueError(f'Invalid or duplicate club record key: {key}')
        seen.add(key)
        empty = dict(player_id=None, player_name=None, value=None, season=None, source=None)
        club = baseline['clubs'].setdefault(str(club_id), dict(
            club_id=club_id, club_name=name, all_time={}, single_season={}))
        if club['club_name'] != name:
            raise ValueError(f'Club name differs from the baseline for ID {club_id}.')
        for group, field in datos.RECORD_KEYS:
            club[group].setdefault(field, empty.copy())
        action(row['action'], club[period][metric]['value'] is not None)
        season = row['season_start']
        if bool(season) != (period == 'single_season'):
            raise ValueError('Provide a season start year only for a single-season record.')
        if season:
            season = number(season, 1800, cutoff-1)
            season = f'{season}/{(season+1)%100:02d}'
        name = label(row['player_name'])
        name.replace('ş', 's').replace('Ş', 'S').encode('latin-1')
        confidence = row['confidence']
        if confidence not in CONFIDENCE:
            raise ValueError('Use verified, partial or provisional confidence.')
        club[period][metric] = dict(
            player_id=number(row['fifa_player_id'], 1) if row['fifa_player_id'] else None,
            player_name=name, value=number(row['value']), season=season or None,
            source=dict(kind='community_review', reference=source_url(row['source_url']),
                        scope=label(row['scope']), confidence=confidence))


def stage(folder, output, build_screens):
    output = output.absolute()
    # Candidate outputs stay separate from the active profile and runtime inputs.
    candidates = layout.LOCAL/'candidates'
    output = target(candidates, output.relative_to(candidates))
    if output.parent != candidates or output.exists():
        raise ValueError('Choose a new direct subfolder under .local/candidates.')
    spec = layout.read(layout.PROFILE_FILE)
    cutoff = spec['historical_before']
    base_db = layout.INPUTS/'historial_ampliado.sqlite'
    layout.check_files(layout.INPUTS, {base_db.name: spec['history_sha256'],
                                      'club_records.json': spec['club_records_sha256']})
    candidates.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=candidates) as scratch:
        staged = Path(scratch)/'candidate'
        staged.mkdir()
        with (closing(sqlite3.connect(base_db.as_uri()+'?mode=ro', uri=True)) as base,
              closing(sqlite3.connect(staged/base_db.name)) as candidate):
            base.backup(candidate)
            with candidate:
                apply_history(candidate, folder, cutoff)
            unmatched = candidate.execute(
                'SELECT 1 FROM staged_league_stats s LEFT JOIN mapping m '
                'USING(fifa_id, transfermarkt_id) WHERE m.fifa_id IS NULL LIMIT 1').fetchone()
            if unmatched:
                raise ValueError('A historical row has no matching player identity.')
            if candidate.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                raise ValueError('Candidate SQLite failed its integrity check.')
        records = staged/'club_records.json'
        baseline = layout.read(layout.INPUTS/'club_records.json')
        apply_clubs(baseline, folder, cutoff)
        records.write_text(json.dumps(baseline, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        datos.HISTORICAL_DB, datos.BASELINE, datos.HISTORICAL_BEFORE = staged/base_db.name, records, cutoff
        datos.HISTORICAL_CLUBS = spec['historical_clubs']
        source = datos.Source()
        apt = (layout.PAYLOAD/'PlayerHistory12D_Ampliado.apt').read_bytes()
        Screen(apt, player=True).payload(*source.snapshot(None)[:2], 1)
        spec.update(history_sha256=digest(staged/base_db.name), club_records_sha256=digest(records))
        if build_screens:
            game, _ = layout.locations()
            check_game(game)
            with tempfile.TemporaryDirectory(dir=scratch) as build_dir:
                generated = Path(build_dir)
                generate(game, generated, records)
                for name in spec['screens']:
                    shutil.copyfile(generated/name, staged/name)
                spec['screens'] = {name: digest(staged/name) for name in spec['screens']}
            club_screen = Screen((staged/'ClubHistory12D.apt').read_bytes(), player=False)
            for club in baseline['clubs']:
                club_screen.payload([], datos.club_packet(baseline, int(club)), 1)
            (staged/layout.PROFILE_FILE.name).write_text(json.dumps(spec, indent=2)+'\n', encoding='utf-8')
        staged.rename(output)
    print(f'Candidate saved to {output}. Runtime files are unchanged.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv_folder', type=Path)
    parser.add_argument('candidate_name', help='New directory name under .local/candidates')
    parser.add_argument('--build-screens', action='store_true', help='Regenerate screens and candidate profile')
    args = parser.parse_args()
    if not args.csv_folder.is_dir():
        parser.error('CSV folder does not exist.')
    try:
        stage(args.csv_folder, layout.LOCAL/'candidates'/args.candidate_name, args.build_screens)
    except (OSError, ValueError, KeyError, RuntimeError, sqlite3.Error, subprocess.SubprocessError) as exc:
        parser.exit(1, f'ERROR: {exc}\n')


if __name__ == '__main__':
    main()

