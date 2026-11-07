"""Resuelve cargas nativas terminadas; no asocia guardados desconocidos."""
from contextlib import closing
import hashlib
import json
import sqlite3
import struct
import time
from pathlib import Path
import carreras as c

COMPLETE_DATA = {'complete_DATA_crc_valid'}

def reduce_events(events,lookup):
    facts=[]
    for item in events:
        if item['kind']=='data_read' and item['event']['requested']>=5_000_000:
            facts.append((item['event']['order'],item))
        elif item['kind'] in COMPLETE_DATA:facts.append((item['event']['order'],item))
        elif item['kind']=='native_flow_complete':facts.append((item['order'],item))
        elif item['kind']=='overrun':
            bound=item.get('through_order')
            if bound is None:return {'state':'ambiguous','reason':'unbounded observer overrun','identity':None}
            facts.append((bound,item))
    state={'state':'no_registered_load','identity':None};pending={};unverified=set();loss=False
    for order,event in sorted(facts,key=lambda x:x[0]):
        if event['kind']=='overrun':
            loss=True
            continue
        if event['kind']=='data_read':
            unverified.add(order)
            continue
        if event['kind'] in COMPLETE_DATA:
            unverified.discard(order)
            pending[event['sha256']]=event
            continue
        name=event['flow'];ok=event.get('native_status')=='SUCCESS' and event.get('arg0')=='0'
        if name=='ListFileComplete':
            pending.clear();unverified.clear()
            if ok:loss=False
            state={'state':'load_browser','identity':None,'flow_order':order};continue
        if name in ('LoadFlowComplete','AutoLoadFlowComplete'):
            if name=='AutoLoadFlowComplete' and not ok and not (pending or unverified):continue
            state={'state':'unresolved_load','identity':None,'flow_order':order,'native_status':event.get('native_status')}
            if ok and len(pending)==1 and not unverified and not loss:
                sha=next(iter(pending));identity=lookup(sha)
                state.update({'sha256':sha,'source_order':pending[sha]['event']['order'],'flow':name})
                if identity:
                    state.update({'state':'registered_load_completed','identity':identity,'snapshot_scope':'loaded_saved_snapshot; unsaved progress not represented'})
                else:state['state']='awaiting_registration'
            elif not ok:state['reason']='native load failed or unrecognised result'
            else:state['reason']='no unique complete Career DATA since last completed flow'
            pending.clear();unverified.clear()
    if loss:
        return {'state':'ambiguous','reason':'observer overrun since last successful list','identity':None}
    if pending or unverified:
        return {'state':'awaiting_native_completion','identity':None}
    return state

def lookup(sha):
    with closing(sqlite3.connect(c.DB.as_uri()+'?mode=ro',uri=True)) as db:
        r=db.execute('SELECT career,parent FROM snapshots WHERE sha=?',(sha,)).fetchone()
    return {'career_id':r[0],'parent_sha256':r[1]} if r else None

def career_inventory(base):
    result={}
    for path in (base/'0/FIFA16').glob('*/DATA'):
        path = c.safe_source(path)
        if path.stat().st_size<5_000_000:continue
        with path.open('rb') as f:prefix=f.read(132)
        if prefix[116:132]!=b'SaveType_Career\0':continue
        with path.open('rb') as f:
            result[str(path.relative_to(base))]=hashlib.file_digest(f,'sha256').hexdigest()
    return result

def read_events(path):
    if not path.exists():
        return []
    # The watcher may still be appending its last event.
    return [json.loads(line) for line in path.read_bytes().split(b'\n')[:-1] if line]

