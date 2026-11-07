"""Read-only save discovery and transactional Career imports."""
from contextlib import closing
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import json
import sqlite3

import carreras

EVIDENCE = 'Career import: save ancestry explicitly confirmed by the user.'
STATS = ('apps', 'goals', 'assists', 'clean_sheets')


@dataclass(frozen=True)
class Preview:
    files: tuple
    parent: str | None
    head: str
    added: int
    reused: int
    seasons: tuple
    warnings: tuple
    ancestry: tuple
    projection_sha: str


def read_candidates(paths, *, discover=False):
    results = []
    for path in dict.fromkeys(map(Path, paths)):
        try:
            if discover:
                # Avoid reading settings, squad files and arbitrary backups in full.
                if not path.is_file():
                    continue
                with carreras.external_path(path).open('rb') as stream:
                    if stream.read(132)[116:132] != carreras.CAREER_HEADER:
                        continue
            results.append((path, carreras.inspect_external(path), ''))
        except (OSError, ValueError) as exc:
            results.append((path, None, str(exc)))
    return results


def folder_saves(folder):
    return [*folder.iterdir(), *folder.glob('*/DATA'), *folder.glob('0/FIFA16/*/DATA')]


def registered_saves(db):
    return db.execute(
        'SELECT c.label, s.sha, s.parent, s.season, s.date, s.club, s.save_label, s.source '
        'FROM snapshots s JOIN careers c ON c.id=s.career '
        'ORDER BY c.label, c.id, s.season, s.date, s.rowid'
    ).fetchall()


def open_preview():
    """Copy the registry into memory so cancel never writes to it."""
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    try:
        if carreras.DB.is_file():
            with closing(sqlite3.connect(carreras.DB.as_uri()+'?mode=ro', uri=True)) as source:
                source.backup(db)
        db.executescript(carreras.DDL)
    except BaseException:
        db.close()
        raise
    return db


def snapshot(db, sha):
    return db.execute('SELECT * FROM snapshots WHERE sha=?', (sha,)).fetchone() if sha else None


def starting_year(value):
    return value['calendar']['setupdate']//10000 - value['season'] + 1


def apply_import(db, values, parent):
    files = tuple((Path(value['source']), value['sha']) for value in values)
    unique = {}
    for value in values:
        unique.setdefault(value['sha'], value)
    if not unique:
        raise ValueError('Select at least one valid Career save.')

    known = {sha: snapshot(db, sha) for sha in unique}
    anchor = snapshot(db, parent)
    if parent and anchor is None:
        raise ValueError('The selected checkpoint is no longer registered.')
    careers = {row['career'] for row in known.values() if row}
    if anchor:
        careers.add(anchor['career'])
    if len(careers) > 1:
        raise ValueError('The selection contains saves registered to different Careers.')

    first_known = next((row for row in known.values() if row), None)
    prefix = first_known if not parent and not next(iter(known.values())) else None
    if prefix and prefix['parent']:
        raise ValueError('Choose an earlier registered checkpoint as the parent, or select the '
                         'first registered save to add earlier checkpoints before it.')

    warnings = set()
    current = parent
    added = []
    affected = set()
    if prefix:
        warnings.add('Earlier checkpoints will be linked before the first registered save. '
                     'Existing later branches will retain their identities.')

    for sha, value in unique.items():
        earlier = snapshot(db, current)
        if earlier and sha != current:
            previous = json.loads(earlier['metadata'])
            if value['season'] < earlier['season'] or value['date'] < earlier['date']:
                raise ValueError('The selected order moves backwards. Arrange the saves oldest first '
                                 'or choose an earlier parent checkpoint.')
            if value['date'] == earlier['date']:
                warnings.add('Different saves share a Career date. Check their order before linking.')
            if value['club'] != earlier['club']:
                warnings.add('The managed team changes in this sequence. Verify that it is the same Career.')
            if starting_year(value) != starting_year(previous):
                warnings.add('The saves imply different Career starting years. Verify the sequence.')
            if value['club'] == earlier['club'] and value['season'] == earlier['season']:
                old_roster, new_roster = set(previous.get('roster', ())), set(value['roster'])
                if 2*len(old_roster & new_roster) < min(len(old_roster), len(new_roster)):
                    warnings.add('Two saves for the same team and season have very different rosters. '
                                 'Check that they belong to the same Career.')

        old = known[sha]
        if old:
            if prefix and sha == prefix['sha']:
                if starting_year(value) != starting_year(next(iter(unique.values()))):
                    raise ValueError('Earlier saves must match the registered Career starting year.')
                db.execute('UPDATE snapshots SET parent=? WHERE sha=? AND parent IS NULL', (current, sha))
                affected.update(r[0] for r in db.execute('SELECT sha FROM snapshots WHERE career=?',
                                                         (old['career'],)))
            elif current and sha != current and current not in carreras.history(sha, db)['ancestry']:
                raise ValueError('A registered save is on a different branch. Choose its correct '
                                 'parent or leave that save out of this import.')
        else:
            label = (value['save_label'] or 'Imported Career') if not current and not prefix else None
            carreras.bind_snapshot(db, value, EVIDENCE, label=label, parent=current, known_league=True,
                                   prefix_career=prefix['career'] if prefix and not current else None)
            added.append(sha)
            affected.add(sha)
        current = sha

    for path, sha in files:
        db.execute('INSERT OR IGNORE INTO observations VALUES (?,?)', (sha, str(path)))

    data = carreras.history(current, db)
    rows = data['official_player_rows']
    seasons = {}
    for sha in data['ancestry']:
        seasons.setdefault(snapshot(db, sha)['season'], [0, 0, 0, 0, 0])
    observed = {}
    unidentified = set()
    for sha in data['ancestry']:
        checkpoint = snapshot(db, sha)
        rules = carreras.competition_rules(db, checkpoint, json.loads(checkpoint['metadata']))
        for row in db.execute('SELECT * FROM player_observations WHERE sha=?', (sha,)):
            rule = rules.get(row['group_raw'])
            if rule is None or rule['category'] not in ('league', 'domestic_cup', 'continental'):
                unidentified.add(row['group_raw'])
            key = checkpoint['season'], checkpoint['club'], row['group_raw'], row['player']
            counts = row['apps'], row['goals'], row['assists_raw']
            if key in observed and any(latest < earlier for latest, earlier in zip(observed[key], counts)):
                warnings.add('Some cumulative values decrease between checkpoints. The latest selected '
                             'observation wins. Check the order if this was unexpected.')
            observed[key] = counts
    if unidentified:
        warnings.add('Unidentified or non-official statistical groups were excluded: '
                     + ', '.join(map(str, sorted(unidentified))) + '.')
    for row in rows:
        if row['assist_evidence'] == 'ambiguous_club_attribution':
            warnings.add('Some same-season competition rows overlap across clubs. '
                         'Their counts remain unknown because the club split cannot be verified.')
            continue
        counts = seasons[row['season']]
        counts[0] += 1
        for i, field in enumerate(STATS, 1):
            counts[i] += row[field] is not None
    ordered_seasons = sorted(seasons)
    if ordered_seasons[0] > 1 or any(b-a > 1 for a, b in zip(ordered_seasons, ordered_seasons[1:])):
        warnings.add('Some earlier seasons have no selected or recorded checkpoint.')
    if not any(counts[0] for counts in seasons.values()):
        warnings.add('No identified official competition rows can be published yet. '
                     'These saves can still be linked for future tracking.')
    projection = sorted((r['season'], r['club_id'], r['group_raw'], r['player_id'], r['competition'],
                         r['category'], r['source_sha256'], *(r[k] for k in STATS)) for r in rows)
    projection_sha = sha256(json.dumps(projection, ensure_ascii=False).encode('utf-8')).hexdigest()
    preview = Preview(files, parent, current, len(added), len(values)-len(added),
                      tuple((season, *seasons[season]) for season in ordered_seasons),
                      tuple(sorted(warnings)), tuple(data['ancestry']), projection_sha)
    return preview, affected


def preview_import(values, parent):
    with closing(open_preview()) as db:
        return apply_import(db, values, parent)[0]


def commit_import(preview, validate=None):
    values = []
    for path, sha in preview.files:
        value = carreras.inspect_external(path)
        if value['sha'] != sha:
            raise ValueError('A selected save changed after preview. Refresh the save list and try again.')
        values.append(value)
    with carreras.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        result, affected = apply_import(db, values, preview.parent)
        if result != preview:
            raise ValueError('The registry changed after preview. Review the import again.')
        if validate:
            for sha in sorted(affected):
                validate(sha, db)
        return result
