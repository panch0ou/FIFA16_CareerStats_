"""Read 12C's native events and publish the current 12D snapshot to both screens."""
import json
import struct
import sys
import subprocess
import time

from archivos import digest
from layout import RESOURCES
import bridge
import carreras
import estado_activo as identity
import observar_cargas as observer
from datos import Source
from transporte import Screen, Writer

HERE = STATE = RESOURCE_DIR = None
CONFIRM_COMMAND = 'Diagnostics.cmd confirm'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def publish(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    temp.replace(path)


def attach(pid, session_factory, observer_command):
    family = observer.DLL.stem
    journal_path = carreras.HERE / f'{family}_{pid}.json'
    if journal_path.exists():
        raise RuntimeError('This process already has an observer journal.')
    process = observer.Process(pid)
    child = None
    patched = False
    try:
        for stem, rel in RESOURCES.items():
            if digest(carreras.ACTIVE / rel) != digest(RESOURCE_DIR / (stem+'.bigf')):
                raise RuntimeError('The active screen resource hash does not match')
        bridge.native('patch', pid)
        patched = True
        child = subprocess.Popen(observer_command, stdout=sys.stdout, stderr=sys.stderr,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        source = Source()
        screens = [Screen((RESOURCE_DIR / (stem+'.apt')).read_bytes(), player=i == 0)
                   for i, stem in enumerate(RESOURCES)]
        writer = Writer(process, screens)
        events_path = carreras.HERE / f'cargas_{family}_{pid}.jsonl'
        runlog = HERE / f'session_{pid}.jsonl'
        symbols = observer.exports(observer.DLL)
        session = None
        head = object()
        generation = 0
        last_state = None
        last_publish = 0
        ready = False
        startup_deadline = time.monotonic()+30
        while process.alive():
            if child.poll() is not None:
                if not process.alive():
                    break
                raise RuntimeError(f'The native observer exited with code {child.returncode}')
            events = identity.read_events(events_path)
            beat = next((e['time'] for e in reversed(events) if e['kind'] == 'watcher_heartbeat'), 0)
            healthy = child.poll() is None and time.time()-beat < 3
            if healthy:
                journal = read_json(journal_path)
                healthy = (journal['creation'] == process.creation and
                           process.read(0x1444e777e, 5).hex() == journal['call_new'] and
                           process.read(journal['base']+symbols['OBS_DROPPED'], 8) == bytes(8))
                if healthy and family == 'observer_v5':
                    healthy = (process.read(journal['base']+symbols['FLOW_DROPPED'], 8) == bytes(8)
                               and all(process.read(at, 5) == b'\xe8'+struct.pack('<i', journal['relay']-at-5)
                                       for at in observer.LIFECYCLE_CALLS))
                if healthy:
                    if session is None:
                        session = session_factory(process, journal)
                    session.update(events, healthy)
                    if not ready:
                        ready = True
                        print('Career Stats is ready. You can now load a Career Mode save.', flush=True)
            if not ready and time.monotonic() >= startup_deadline:
                raise RuntimeError('The native observer did not report readiness')
            if not healthy and session is not None and family == 'observer_v5':
                session.update(events, False)
            wanted = session.head if healthy and session else None
            if wanted != head:
                generation += 1
                buckets, club, info = source.snapshot(wanted)
                packets = [s.payload(buckets, club, generation) for s in screens]
                head = wanted
            state = info | {'pid': pid, 'creation': process.creation,
                            'load_order': session.load if session else None,
                            'load_sha': session.load_sha if session else None,
                            'head_order': session.head_order if session else None,
                            'save': session.last_flow if session else None,
                            'observer_available': healthy}
            now = time.time()
            if state != last_state or now-last_publish >= 1:
                publish(STATE, state | {'heartbeat': now})
                last_publish = now
            changes = writer.update(packets)
            if changes or state != last_state:
                message = state | {'publication': changes}
                with runlog.open('a', encoding='utf-8') as f:
                    f.write(json.dumps(message, ensure_ascii=False)+'\n')
                print(json.dumps(message, ensure_ascii=False), flush=True)
                if (session and session.last_flow and session.last_flow.get('result') in ('save_unresolved', 'load_unresolved')
                        and (not last_state or last_state['save'] != session.last_flow)):
                    print('Save identity is unverified. If you can confirm its origin, '
                          f'close FIFA and run {CONFIRM_COMMAND}.', flush=True)
                last_state = state
            time.sleep(.2)
    except (OSError, json.JSONDecodeError):
        if process.alive():
            raise
    finally:
        try:
            if patched and process.alive():
                try:
                    if family == 'observer_v5' and journal_path.exists() and read_json(journal_path)['state']=='observing':
                        observer.run(pid, 'uninstall')
                finally:
                    if process.alive():
                        bridge.native('unpatch', pid)
            if child is not None and not process.alive():
                child.wait(timeout=8)
            if patched and not process.alive() and family == 'observer_v5':
                bridge_journal = HERE / f'native_{pid}.json'
                if bridge_journal.exists():
                    native = read_json(bridge_journal)
                    if native['creation'] == process.creation:
                        publish(bridge_journal, native | {'state': 'process_ended'})
        finally:
            process.close()
            publish(STATE, {'head': None, 'pid': pid, 'observer_available': False, 'heartbeat': time.time()})

