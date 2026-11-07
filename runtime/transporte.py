"""Bounded replacements of string reservations in the two verified APT images."""
import ctypes as ct
import struct
import time

from memory import MBI
from datos import BUCKETS, CAPACITY


class Reservation:
    def __init__(self, apt, prefix, capacity, guard):
        self.guard = guard.encode()
        self.capacity = capacity
        marker = prefix.encode()
        self.original = marker.ljust(capacity-len(self.guard), b' ') + self.guard
        self.offset = apt.find(marker)
        if (self.offset < 0 or apt.find(marker, self.offset+len(marker)) != -1
                or apt[self.offset:self.offset+capacity] != self.original):
            raise ValueError(f'Ambiguous APT reservation: {prefix}')

    def encode(self, value):
        raw = value.encode('utf-8')
        if len(raw) > self.capacity - len(self.guard):
            raise ValueError(f'APT reservation is too small at offset {self.offset:#x}')
        return raw.ljust(self.capacity-len(self.guard), b' ') + self.guard


class Screen:
    def __init__(self, apt, player):
        self.apt = apt
        self.player = player
        if player:
            self.slots = [Reservation(apt, f'12D_BUCKET_{i:03}_WAIT\n', CAPACITY, f'END_BUCKET_{i:03}')
                          for i in range(BUCKETS)]
            self.anchor = Reservation(apt, '12D_EPOCH_WAIT', 128, 'END_12D_EPOCH')
            self.slots.append(self.anchor)
        else:
            self.anchor = Reservation(apt, '12D_CLUB_WAIT', 2048, 'END_12D_CLUB')
            self.slots = [self.anchor]
        self.needle = self.anchor.guard
        self.needle_offset = self.anchor.offset + self.anchor.capacity - len(self.needle)
        self.location = None
        self.previous = None

    def payload(self, buckets, club, generation):
        if not self.player:
            if club == 'WAIT':
                return [self.anchor.original]
            fields = club.split('|')
            return [self.anchor.encode(f'{int(fields[0]):06d} {fields[6]}')]
        values = [slot.encode(f'12D_BUCKET_{i:03}_READY\n'+'\n'.join(lines)+'\n')
                  for i, (slot, lines) in enumerate(zip(self.slots[:-1], buckets, strict=True))]
        return values + [self.anchor.encode(f'12D_EPOCH_{generation}')]

    def valid(self, read, base):
        header = read(base, 64)
        return (len(header) == 64 and header[:24] == self.apt[:24]
                and struct.unpack_from('<Q', header, 24)[0] == base+16
                and struct.unpack_from('<Q', header, 56)[0] == base+struct.unpack_from('<Q', self.apt, 56)[0]
                and all(read(base+s.offset+s.capacity-len(s.guard), len(s.guard)) == s.guard for s in self.slots))


class Writer:
    def __init__(self, process, screens):
        self.p = process
        self.screens = screens
        self.next_scan = 0
        self.scan_address = 0
        self.scan_matches = {}
        self.nt = ct.WinDLL('ntdll')
        for method in (self.nt.NtSuspendProcess, self.nt.NtResumeProcess):
            method.argtypes = [ct.c_void_p]
            method.restype = ct.c_long
        p = process
        p.k.VirtualQueryEx.argtypes = [ct.c_void_p, ct.c_void_p, ct.POINTER(MBI), ct.c_size_t]
        p.k.VirtualQueryEx.restype = ct.c_size_t

    def read(self, addr, size):
        try:
            return self.p.read(addr, size)
        except OSError:
            return b''

    def scan(self, missing):
        # Continue on the next tick instead of dropping the monitor if a
        # modded game has a large heap. Accept an address only after a full pass.
        if self.scan_matches.keys() != set(missing):
            self.scan_matches = {screen: set() for screen in missing}
            self.scan_address = 0
        address = self.scan_address
        deadline = time.monotonic() + .20
        block_size = 4 * 1024 * 1024
        while address < 0x7fffffffffff:
            if time.monotonic() >= deadline:
                self.scan_address = address
                return False
            info = MBI()
            if not self.p.k.VirtualQueryEx(self.p.h, address, ct.byref(info), ct.sizeof(info)):
                break
            base = info.base or 0
            end = base + info.size
            if end <= address:
                break
            if info.state == 0x1000 and info.type == 0x20000 and info.protect == 4:
                data = self.read(address, min(block_size, end-address))
                for screen in missing:
                    index = data.find(screen.needle)
                    while index >= 0:
                        at = address + index - screen.needle_offset
                        if at > 0 and screen.valid(self.read, at):
                            self.scan_matches[screen].add(at)
                        index = data.find(screen.needle, index+1)
                if end-address > block_size:
                    address += block_size-64
                    continue
            address = end
        for screen, matches in self.scan_matches.items():
            matches = {at for at in matches if screen.valid(self.read, at)}
            if len(matches) == 1:
                screen.location = matches.pop()
        self.scan_address = 0
        self.scan_matches.clear()
        return True

    def write(self, address, data):
        size = ct.c_size_t()
        p = self.p
        return (p.k.WriteProcessMemory(p.h, address, ct.c_char_p(data), len(data), ct.byref(size))
                and size.value == len(data) and self.read(address, len(data)) == data)

    def update(self, payloads):
        missing = []
        for screen in self.screens:
            if screen.location and not screen.valid(self.read, screen.location):
                screen.location = None
            if not screen.location:
                missing.append(screen)
        if missing and time.monotonic() >= self.next_scan:
            if self.scan(missing):
                self.next_scan = time.monotonic()+2
        updated = []
        for screen, values in zip(self.screens, payloads):
            base = screen.location
            if not base:
                continue
            if self.read(base+screen.anchor.offset, screen.anchor.capacity) == values[-1]:
                continue
            old = [self.read(base+s.offset, s.capacity) for s in screen.slots]
            if old == values:
                continue
            if not all(raw == s.original or (screen.previous and raw == screen.previous[i])
                       for i, (s, raw) in enumerate(zip(screen.slots, old))):
                screen.location = None
                continue
            changes = [i for i, raw in enumerate(old) if raw != values[i]]
            if self.nt.NtSuspendProcess(self.p.h) < 0:
                if not self.p.alive():
                    return updated
                raise RuntimeError('Could not suspend FIFA FIFA para publicar las cadenas')
            done = []
            try:
                if not screen.valid(self.read, base) or any(
                    self.read(base+screen.slots[i].offset, screen.slots[i].capacity) != old[i] for i in changes
                ):
                    continue
                for i in changes:
                    done.append(i)
                    if not self.write(base+screen.slots[i].offset, values[i]):
                        raise RuntimeError('Screen publication failed')
            except Exception:
                for i in reversed(done):
                    if not self.write(base+screen.slots[i].offset, old[i]):
                        raise RuntimeError('Could not restore an APT reservation')
                raise
            finally:
                self.nt.NtResumeProcess(self.p.h)
            screen.previous = values
            updated.append(('PLAYER HISTORY' if screen.player else 'CLUB HISTORY', hex(base)))
        return updated
