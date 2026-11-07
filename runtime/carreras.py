"""Read-only save extraction and a separate Career Mode registry."""
from contextlib import contextmanager
import datetime as dt
import json
import sqlite3
import struct
import sys
import uuid
from pathlib import Path

from archivos import target
import career_schema
from extraer_bloque_estadistico import find_groups, longest_stride_run

try:
    from transferengine.saveio import SaveSnapshot
except ModuleNotFoundError as exc:
    if exc.name != 'transferengine':
        raise
    SaveSnapshot = None

HERE = DB = ACTIVE = SCHEMA = None
LEAGUES = {}
DDL="""
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS careers(id TEXT PRIMARY KEY,label TEXT NOT NULL,evidence TEXT NOT NULL,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS snapshots(sha TEXT PRIMARY KEY,career TEXT NOT NULL REFERENCES careers(id),
 parent TEXT REFERENCES snapshots(sha),source TEXT NOT NULL,club INTEGER NOT NULL,season INTEGER NOT NULL,
 date INTEGER NOT NULL,save_label TEXT NOT NULL,evidence TEXT NOT NULL,metadata TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS player_observations(sha TEXT NOT NULL REFERENCES snapshots(sha),
 group_raw INTEGER NOT NULL,player INTEGER NOT NULL,apps INTEGER NOT NULL,goals INTEGER NOT NULL,
 assists_raw INTEGER NOT NULL,clean_raw INTEGER NOT NULL,gk INTEGER,minutes INTEGER NOT NULL,
 source_offset INTEGER NOT NULL,raw48 TEXT NOT NULL,
 PRIMARY KEY(sha,group_raw,player));
CREATE TABLE IF NOT EXISTS competition_rules(career TEXT NOT NULL REFERENCES careers(id),
 club INTEGER NOT NULL,group_raw INTEGER NOT NULL,label TEXT NOT NULL,category TEXT NOT NULL,
 evidence TEXT NOT NULL,PRIMARY KEY(career,club,group_raw));
CREATE TABLE IF NOT EXISTS field_checks(sha TEXT NOT NULL,group_raw INTEGER NOT NULL,player INTEGER NOT NULL,
 field TEXT NOT NULL,value INTEGER NOT NULL,evidence TEXT NOT NULL,
 PRIMARY KEY(sha,group_raw,player,field),
 FOREIGN KEY(sha,group_raw,player) REFERENCES player_observations(sha,group_raw,player));
CREATE TABLE IF NOT EXISTS observations(sha TEXT NOT NULL REFERENCES snapshots(sha),path TEXT NOT NULL,
 PRIMARY KEY(sha,path));
CREATE TABLE IF NOT EXISTS decoder_certifications(career TEXT NOT NULL REFERENCES careers(id),club INTEGER NOT NULL,
 group_raw INTEGER NOT NULL,field TEXT NOT NULL,proof_sha TEXT NOT NULL,proof_player INTEGER NOT NULL,evidence TEXT NOT NULL,
 PRIMARY KEY(career,club,group_raw,field),
 FOREIGN KEY(proof_sha,group_raw,proof_player,field) REFERENCES field_checks(sha,group_raw,player,field));
"""

@contextmanager
def connect():
    db=sqlite3.connect(DB)
    db.row_factory=sqlite3.Row
    db.executescript(DDL)
    try:
        with db:yield db
    finally:db.close()

def require_reader():
    if SaveSnapshot is None:
        raise RuntimeError('The TransferEngine reader is pending source clearance. See LICENSE_REVIEW.md.')


def safe_source(path):
    path = Path(path)
    area = ACTIVE/'0/FIFA16'
    if path != area and (path.parent.parent != area or path.name != 'DATA'):
        raise ValueError('Only DATA in the configured FIFA 16 profile may be read')
    return target(ACTIVE, path.relative_to(ACTIVE))

def rows(s,name,fields):
    t=s.table(name,required=False)
    if t is None:return []
    fields=[field for field in fields if field in t.aliases]
    return [{f:t.value(s.data,r,f) for f in fields} for r in t.active_rows(s.data)]

def validate_snapshot(snapshot):
    snapshot.require_valid()
    career_schema.verify_snapshot(snapshot)
    return 'crc_valid'


def inspect(path):
    path=safe_source(path);st=path.stat()
    s=SaveSnapshot.read(path,SCHEMA);integrity=validate_snapshot(s)
    if (path.stat().st_size,path.stat().st_mtime_ns)!=(st.st_size,st.st_mtime_ns):raise ValueError('The DATA changed while it was being read')
    user_fields = (*career_schema.REQUIRED['career_users'], *career_schema.OPTIONAL['career_users'])
    users=rows(s,'career_users',user_fields)
    calendar_fields = (*career_schema.REQUIRED['career_calendar'], *career_schema.OPTIONAL['career_calendar'])
    calendars=rows(s,'career_calendar',calendar_fields)
    if len(users)!=1 or len(calendars)!=1:raise ValueError('Ambiguous Career Mode user or calendar')
    u,c=users[0],calendars[0];club=u['clubteamid']
    links=s.table('teamplayerlinks');roster={links.value(s.data,r,'playerid') for r in links.active_rows(s.data) if links.value(s.data,r,'teamid')==club}
    player_fields = career_schema.OPTIONAL['players']
    positions = {row['playerid']: row['preferredposition1'] for row in rows(s,'players',player_fields)
                 if len(row) == len(player_fields)}
    candidates=find_groups(s.data,roster,s.databases[-1][2]);records=[];groups={}
    for group,entries in candidates.items():
        run=longest_stride_run(entries)
        previously_corroborated=(club==144 and group in (776,1759))
        if run<8 and not(previously_corroborated and len(entries)>=8 and run>=4):continue
        if len({player for _,player in entries})!=len(entries):raise ValueError(f'Ambiguous statistical group {group}')
        groups[group]={'count':len(entries),'stride_run':run}
        for off,pid in sorted(entries):
            actual,code,minutes,rating=struct.unpack_from('<IHHH',s.data,off)
            if (actual,code)!=(pid,group):raise ValueError('Inconsistent statistical row')
            records.append({'group_raw':group,'player':pid,'apps':s.data[off+10],'goals':s.data[off+11],
                'assists_raw':s.data[off+13],'clean_raw':s.data[off+19],
                'gk':int(positions[pid]==0) if pid in positions else None,'minutes':minutes,
                'source_offset':off,'raw48':s.data[off:off+48].hex()})
    league_fields = career_schema.OPTIONAL['leagues']
    native_leagues=[(row['leaguename'],row['countryid'],row['level'])
                    for row in rows(s,'leagues',league_fields)
                    if len(row)==len(league_fields) and row['leagueid']==u.get('leagueid')]
    return {'sha':s.sha256,'integrity':integrity,'source':str(path),'club':club,'season':u['seasoncount'],'date':c['currdate'],
        'save_label':s.data[16:80].split(b'\0')[0].decode('utf-8',errors='replace'),
        'user':u,'calendar':c,'roster':sorted(roster),'groups':groups,'records':records,
        'native_league':native_leagues[0] if len(native_leagues)==1 else None,
        'common_header_140_156':s.data[140:156].hex()}

def bind(path,evidence,label=None,parent=None,expected_sha=None,known_league=False):
    if not evidence.strip():raise ValueError('Explicit evidence is required')
    value=inspect(path)
    if expected_sha is not None and value['sha']!=expected_sha:
        raise ValueError('The DATA no longer matches the observed hash')
    with connect() as db:
        existing=db.execute('SELECT * FROM snapshots WHERE sha=?',(value['sha'],)).fetchone()
        if existing:
            if parent:
                p=db.execute('SELECT * FROM snapshots WHERE sha=?',(parent,)).fetchone()
                if not p or p['career']!=existing['career']:raise ValueError('This hash belongs to another Career')
                if parent!=existing['parent'] and parent!=existing['sha']:raise ValueError('An existing snapshot keeps its original parent')
            if label:raise ValueError('This hash already has a Career identity')
            db.execute('INSERT OR IGNORE INTO observations VALUES (?,?)',(value['sha'],value['source']))
            return {'career':existing['career'],'sha':value['sha'],'result':'known_exact_hash_no_duplicate'}
        if parent:
            p=db.execute('SELECT * FROM snapshots WHERE sha=?',(parent,)).fetchone()
            if not p:raise ValueError('Unknown parent hash')
            if value['season']<p['season'] or value['date']<p['date']:
                raise ValueError('Choose the earlier snapshot that was loaded as the parent')
            career=p['career']
        elif label:
            career=str(uuid.uuid4());db.execute('INSERT INTO careers VALUES (?,?,?,?)',(career,label,evidence,dt.datetime.now(dt.timezone.utc).isoformat()))
        else:raise ValueError('Choose a new Career identity or confirm the parent save')
        metadata={k:v for k,v in value.items() if k!='records'}
        db.execute('INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?,?)',(value['sha'],career,parent,value['source'],value['club'],value['season'],value['date'],value['save_label'],evidence,json.dumps(metadata,ensure_ascii=False)))
        primary=value['user'].get('primarycompobjid')
        league=value['user'].get('leagueid')
        if known_league and primary is not None and league is not None:
            labels=db.execute("""
                SELECT DISTINCT r.label FROM competition_rules r JOIN snapshots s
                ON s.career=r.career AND s.club=r.club
                WHERE r.club=? AND r.group_raw=? AND r.category='league'
                AND json_extract(s.metadata,'$.user.primarycompobjid')=?
                AND json_extract(s.metadata,'$.user.leagueid')=?
                """,(value['club'],primary,primary,league)).fetchall()
            if len(labels)==1:
                db.execute('INSERT OR IGNORE INTO competition_rules VALUES (?,?,?,?,?,?)',
                           (career,value['club'],primary,labels[0][0],'league',
                            'Native club, league and primary competition match a verified rule'))
            elif not labels:
                native = value.get('native_league')
                verified = LEAGUES.get((league, primary, *native)) if native else None
                if verified:
                    db.execute('INSERT OR IGNORE INTO competition_rules VALUES (?,?,?,?,?,?)',
                               (career,value['club'],primary,verified,'league',
                                'Native league name and IDs match the compatibility profile'))
        for rec in value['records']:
            db.execute('INSERT INTO player_observations VALUES (?,?,?,?,?,?,?,?,?,?,?)',(value['sha'],*[rec[k] for k in ['group_raw','player','apps','goals','assists_raw','clean_raw','gk','minutes','source_offset','raw48']]))
        db.execute('INSERT INTO observations VALUES (?,?)',(value['sha'],value['source']))
        siblings=db.execute('SELECT count(*) FROM snapshots WHERE parent=?',(parent,)).fetchone()[0] if parent else 0
        return {'career':career,'sha':value['sha'],'parent':parent,'siblings_including_this':siblings,'result':'registered_explicitly','stats':len(value['records'])}

def resolve(path):
    value=inspect(path)
    with connect() as db:
        row=db.execute('SELECT career,parent FROM snapshots WHERE sha=?',(value['sha'],)).fetchone()
    return {'sha':value['sha'],'club':value['club'],'season':value['season'],'date':value['date'],
            'identity':dict(row) if row else None,'status':'known_exact_hash' if row else 'unbound_do_not_merge',
            'active_game_detection':'not_automatic; source snapshot only'}

def history(head):
    with connect() as db:
        chain=[];seen=set();sha=head;career=None;latest={}
        while sha:
            if sha in seen:raise ValueError('Snapshot ancestry contains a cycle')
            seen.add(sha);s=db.execute('SELECT * FROM snapshots WHERE sha=?',(sha,)).fetchone()
            if not s:raise ValueError('Unknown snapshot')
            if career and career!=s['career']:raise ValueError('Snapshot ancestry crosses Career identities')
            career=s['career'];chain.append(sha)
            for r in db.execute('SELECT * FROM player_observations WHERE sha=?',(sha,)):
                key=(s['season'],s['club'],r['group_raw'],r['player'])
                if key in latest:continue
                rule=db.execute('SELECT * FROM competition_rules WHERE career=? AND club=? AND group_raw=?',(career,s['club'],r['group_raw'])).fetchone()
                if not rule or rule['category'] not in ('league','domestic_cup','continental'):continue
                checks={a['field']:a['value'] for a in db.execute('SELECT * FROM field_checks WHERE sha=? AND group_raw=? AND player=?',(sha,r['group_raw'],r['player']))}
                calibrated={a['field']:a['proof_sha'] for a in db.execute('SELECT * FROM decoder_certifications WHERE career=? AND club=? AND group_raw=?',(career,s['club'],r['group_raw']))}
                assists=checks.get('assists',r['assists_raw'] if 'assists' in calibrated else None)
                clean=checks.get('clean_sheets',r['clean_raw'] if 'clean_sheets' in calibrated else None)
                cal=json.loads(s['metadata'])['calendar']
                latest[key]={'career_id':career,'season':s['season'],'club_id':s['club'],'group_raw':r['group_raw'],
                    'club_scope':'roster_club_at_observation; transfer split not established',
                    'season_setup_date':cal['setupdate'],'season_end_date':cal.get('enddate'),
                    'competition':rule['label'],'category':rule['category'],'player_id':r['player'],'apps':r['apps'],'goals':r['goals'],
                    'assists':assists,'clean_sheets':clean if r['gk'] else None,
                    'field_proof_sha256':calibrated,
                    'source_sha256':sha,'scope':'latest_observed_cumulative_not_season_complete'}
            sha=s['parent']
        return {'career_id':career,'head':head,'ancestry':chain,'official_player_rows':list(latest.values()),
                'club_match_records':None,'club_limit':'manager_history includes friendlies; no official club match totals established',
                'historical_pre_2015':'separate unchanged SQLite; not merged here'}

def classify(career,club,group,label,category,evidence):
    if category not in ('league','domestic_cup','continental','friendly','unknown') or not evidence.strip():raise ValueError('Invalid competition classification or evidence')
    with connect() as db:
        old=db.execute('SELECT * FROM competition_rules WHERE career=? AND club=? AND group_raw=?',(career,club,group)).fetchone()
        if old and (old['label'],old['category'])!=(label,category):raise ValueError('A conflicting competition rule already exists')
        db.execute('INSERT OR IGNORE INTO competition_rules VALUES (?,?,?,?,?,?)',(career,club,group,label,category,evidence))

def verify_field(sha,group,player,field,value,evidence):
    if field not in ('assists','clean_sheets') or not evidence.strip():raise ValueError('Invalid field or evidence')
    with connect() as db:
        row=db.execute('SELECT * FROM player_observations WHERE sha=? AND group_raw=? AND player=?',(sha,group,player)).fetchone()
        if not row:raise ValueError('Observation missing')
        if field=='clean_sheets' and row['gk']!=1:raise ValueError('Clean sheets require a verified goalkeeper position')
        raw=row['assists_raw' if field=='assists' else 'clean_raw']
        if value!=raw:raise ValueError('The screen value differs from the decoded value')
        db.execute('INSERT OR IGNORE INTO field_checks VALUES (?,?,?,?,?,?)',(sha,group,player,field,value,evidence))

def certify_field(sha,group,player,field,evidence):
    if not evidence.strip():raise ValueError('Evidence is required')
    with connect() as db:
        s=db.execute('SELECT * FROM snapshots WHERE sha=?',(sha,)).fetchone()
        check=db.execute('SELECT * FROM field_checks WHERE sha=? AND group_raw=? AND player=? AND field=?',(sha,group,player,field)).fetchone()
        if not s or not check or check['value']<=0:raise ValueError('A positive in-game check for the exact row is required')
        rule=db.execute('SELECT * FROM competition_rules WHERE career=? AND club=? AND group_raw=?',(s['career'],s['club'],group)).fetchone()
        if not rule or rule['category'] not in ('league','domestic_cup','continental'):raise ValueError('Official competition is unverified')
        db.execute('INSERT OR IGNORE INTO decoder_certifications VALUES (?,?,?,?,?,?,?)',(s['career'],s['club'],group,field,sha,player,evidence))

def records(head):
    data=history(head);players={}
    for r in data['official_player_rows']:
        key=(r['club_id'],r['player_id']);players.setdefault(key,[]).append(r)
    accumulated=[];seasonal=[]
    for (club,pid),rows_ in players.items():
        totals={field:sum(r[field] for r in rows_) if all(r[field] is not None for r in rows_) else None for field in ('apps','goals','assists','clean_sheets')}
        accumulated.append({'club_id':club,'player_id':pid,'observed_totals':totals})
        for season in sorted({r['season'] for r in rows_}):
            subset=[r for r in rows_ if r['season']==season]
            seasonal.append({'club_id':club,'player_id':pid,'season':season,'observed_totals':{field:sum(r[field] for r in subset) if all(r[field] is not None for r in subset) else None for field in totals}})
    return {'career_id':data['career_id'],'head':head,'coverage':'captured_official_player_rows_only; roster club context; transfer split and complete records not certified',
        'may_publish_as_CLUB_HISTORY_records':False,
        'accumulated_player_candidates':accumulated,'season_player_candidates':seasonal,
        'official_club_match_totals':None,'reason':'No verified official team result producer; do not sum player appearances as team games'}
