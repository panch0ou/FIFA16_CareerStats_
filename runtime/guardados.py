"""Asociación de snapshots por transición nativa y guardado confirmado."""
import hashlib
import time

import carreras
import estado_activo as identity

LOAD = 'LoadFlowComplete'
AUTOLOAD = 'AutoLoadFlowComplete'
START = 'StartCareerModeFromMenu'
QUIT = 'QuitCareerMode'
LIST = 'ListFileComplete'
USER_SAVE = 'UserSaveFlowComplete'
SAVE = {USER_SAVE, 'ProgressSaveFlowComplete', 'MultiUserProgressSaveFlowComplete'}


def success(event):
    return event.get('native_status') == 'SUCCESS' and event.get('arg0') == '0'


class Inventory:
    """Stat por casilla en un guardado; hash solo cuando cambia el archivo."""
    def __init__(self, root, baseline):
        self.root = root
        self.cache = {}
        self.hashes = baseline

    def refresh(self):
        cache, hashes = {}, {}
        for path in (self.root/'0/FIFA16').glob('*/DATA'):
            key = str(path.relative_to(self.root))
            if carreras.safe_source(path) != path:
                raise ValueError('Unexpected DATA path')
            st = path.stat()
            if st.st_size < 132:
                continue
            signature = (st.st_size, st.st_mtime_ns, st.st_ino)
            if key in self.cache and self.cache[key][0] == signature:
                digest = self.cache[key][1]
            else:
                with path.open('rb') as stream:
                    header = stream.read(132)
                    digest = None
                    if header[116:132] == b'SaveType_Career\0':
                        stream.seek(0)
                        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                after = path.stat()
                if signature != (after.st_size, after.st_mtime_ns, after.st_ino):
                    raise ValueError('DATA changed while the save was being written')
            cache[key] = (signature, digest)
            if digest:
                hashes[key] = digest
        self.cache, self.hashes = cache, hashes
        return hashes


def candidate(before, after, manual):
    changed = [(slot, sha) for slot, sha in after.items() if before.get(slot) != sha]
    removed = before.keys() - after.keys()
    if len(changed) != 1:
        return None
    slot, sha = changed[0]
    if removed and not (len(removed) == 1 and slot not in before and manual):
        return None
    return slot, sha


def until_load(events, order, floor):
    """Usa el mismo criterio CRC/lista/éxito de 12C, dentro de la Carrera vigente."""
    window = []
    for event in events:
        kind = event['kind']
        if kind == 'overrun':
            native = event.get('through_order')
            if native is None:
                return {}
        else:
            native = event.get('order', event.get('event', {}).get('order', 0))
        if floor < native <= order:
            window.append(event)
    result = identity.reduce_events(window, identity.lookup)
    return result if result.get('flow_order') == order else {}


def noncareer_load(events, order, floor):
    """Settings and squads can be loaded when returning to the main menu."""
    floor = max((e['order'] for e in events if e['kind'] == 'native_flow_complete'
                 and e['flow'] == LIST and floor < e['order'] < order), default=floor)
    reads = [e['event'] for e in events if e['kind'] == 'data_read'
             and floor < e['event']['order'] < order and e['event']['requested'] > 160]
    kinds = {b'SaveType_Settin\0', b'SaveType_Squads\0'}
    for read in reads:
        offset = 116 - (read.get('file_end', -1) - read.get('actual', 0))
        if offset < 0 or bytes.fromhex(read.get('prefix', ''))[offset:offset+16] not in kinds:
            return False
    return bool(reads)


class AutomaticSession:
    def __init__(self, process, journal):
        self.p = process
        self.inventory = Inventory(carreras.ACTIVE, journal['career_inventory_before'])
        self.load = self.load_sha = self.head_order = self.head = None
        self.parent = self.last_flow = None
        self.seen_flow = 0
        self.floor = 0
        self.pending_load = None
        self.pending = None
        self.rebase = False
        self.new_origin = 'pristine'

    def clear(self, order):
        self.rebase = self.rebase or self.pending is not None
        self.parent = self.head = self.load = self.load_sha = self.head_order = None
        self.floor = order
        self.pending_load = None
        self.pending = None
        self.last_flow = None

    def resolve_load(self, events):
        order, floor = self.pending_load
        loaded = until_load(events, order, floor)
        if loaded.get('identity'):
            self.parent = self.head = self.load_sha = loaded['sha256']
            self.head_order = self.load = order
        elif loaded.get('sha256'):
            self.last_flow = {'result': 'load_unresolved', 'sha': loaded['sha256'], 'order': order}
        else:
            return
        self.pending_load = None

    def update(self, events, healthy):
        if not healthy or any(e['kind'] == 'overrun' and
                             ('lost_flows_at_least' in e or e.get('through_order') is None)
                             for e in events):
            self.clear(self.seen_flow)
            self.new_origin = None
            return
        # The observer can finish validating the DATA after logging the native
        # completion. Retry only that load, with its original event boundaries.
        if self.pending_load:
            self.resolve_load(events)
        flows = sorted((e for e in events if e['kind'] == 'native_flow_complete'
                        and e['order'] > self.seen_flow), key=lambda e: e['order'])
        for event in flows:
            order, name = event['order'], event['flow']
            self.seen_flow = order
            if name in (QUIT, START):
                self.clear(order)
                self.new_origin = 'native_start' if name == START else 'pristine'
            elif name == LIST:
                self.head = None
                self.pending_load = None
            elif name == LOAD or (name == AUTOLOAD and success(event)):
                floor = self.floor
                if success(event) and not noncareer_load(events, order, floor):
                    self.new_origin = None
                self.clear(order)
                if success(event):
                    self.pending_load = (order, floor)
                    self.resolve_load(events)
            elif name in SAVE and (success(event) or name == USER_SAVE):
                # The progress notification commonly follows a user save.
                manual = self.pending[1] if self.pending else 0
                if name == USER_SAVE:
                    manual = order if success(event) and manual == 0 else -1
                self.pending = (order, manual, time.monotonic()+.45)
        if self.rebase:
            # A write from the previous mode can have finished while loading the
            # next Career. Its diff must never become the next Career's child.
            try:
                self.inventory.refresh()
            except (OSError, ValueError):
                return
            self.rebase = False
            self.pending = None
        if self.pending and time.monotonic() >= self.pending[2]:
            order, manual, _ = self.pending
            previous = self.inventory.hashes
            try:
                current = self.inventory.refresh()
            except (OSError, ValueError) as exc:
                self.pending = None
                self.pending_load = None
                self.new_origin = None
                self.head = self.parent = None
                self.last_flow = {'result': 'save_unresolved', 'reason': str(exc), 'order': order}
                return
            self.pending = None
            if current == previous:
                if manual > 0 and self.parent:
                    self.head = self.parent
                return
            self.pending_load = None
            self.accept(previous, current, order, manual)

    def accept(self, before, after, order, manual):
        origin = self.new_origin
        removed = before.keys()-after.keys()
        replaces_head = bool(self.parent) and {before[slot] for slot in removed} == {self.parent}
        match = candidate(before, after, manual > 0 or bool(origin) or replaces_head) if manual >= 0 else None
        self.new_origin = None
        new_root = not self.parent and origin and match
        if match is None or (not self.parent and not new_root):
            self.last_flow = {'result': 'save_unresolved', 'order': order,
                              'reason': 'ambiguous save slots or unverified Career origin'}
            if match is not None:
                self.last_flow.update(slot=match[0], sha=match[1])
            self.head = self.parent = None
            return
        slot, sha = match
        if sha == self.parent:
            self.head = sha
            return
        if identity.lookup(sha):
            self.last_flow = {'result': 'save_unresolved', 'order': order, 'sha': sha,
                              'reason': 'this content already has a different place in the save ancestry'}
            self.head = self.parent = None
            return
        path = carreras.ACTIVE / slot
        parent = self.parent
        mode = 'overwrite' if slot in before or before.keys()-after.keys() else 'new_slot'
        evidence = (f'Process {self.p.pid}, created {self.p.creation}, load {self.load}, '
                    f'native boundary {self.floor}, save {manual or order}, {mode}')
        try:
            label = None
            if new_root:
                info = carreras.inspect(path)
                if origin == 'pristine' and not (info['season'] == 1
                        and info['date'] == info['calendar']['setupdate'] and not info['records']):
                    raise ValueError('First DATA lacks evidence of a new Career')
                label = info['save_label'] or 'New Career'
                evidence += f' / new Career ({origin})'
            result = carreras.bind(path, evidence, parent=parent, label=label, expected_sha=sha, known_league=True)
        except (OSError, ValueError) as exc:
            self.last_flow = {'result': 'save_unresolved', 'order': order, 'sha': sha, 'reason': str(exc)}
            self.head = self.parent = None
            return
        self.parent = self.head = sha
        self.head_order = order
        self.last_flow = result | {'result': 'automatic_root' if new_root else 'automatic_save', 'parent': parent, 'slot': slot,
                                   'mode': mode, 'native_save_order': manual or order,
                                   'trigger': USER_SAVE if manual else 'progress'}
