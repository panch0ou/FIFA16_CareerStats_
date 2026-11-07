"""Identify candidate statistical groups in a verified DATA snapshot."""
import struct

ROW_SIZE = 48
ASSISTS_OFFSET = 13


def find_groups(data: bytes, roster_ids: set[int], tail_start: int) -> dict[int, list[tuple[int, int]]]:
    groups: dict[int, list[tuple[int, int]]] = {}
    for player_id in roster_ids:
        if not 0 <= player_id <= 0xffffffff:
            continue  # A vacant roster link cannot match the 32-bit player ID in a statistics row.
        needle = struct.pack("<I", player_id)
        cursor = tail_start
        while True:
            offset = data.find(needle, cursor)
            if offset < 0:
                break
            cursor = offset + 1
            if offset + ROW_SIZE > len(data):
                continue
            group_id, minutes, rating_sum = struct.unpack_from("<HHH", data, offset+4)
            appearances = data[offset+10]
            if group_id > 0 and 0 < appearances <= 100 and 0 <= minutes <= 9000 and 0 <= rating_sum <= 10000:
                groups.setdefault(group_id, []).append((offset, player_id))
    return groups


def longest_stride_run(entries: list[tuple[int, int]]) -> int:
    offsets = sorted({offset for offset, _ in entries})
    longest = current = 1
    for previous, following in zip(offsets, offsets[1:]):
        current = current + 1 if following - previous == ROW_SIZE else 1
        longest = max(longest, current)
    return longest


def aligned_groups(groups):
    """Confirm an intact cadence or a fragmented group on the same proven alignment."""
    candidates = {}
    for group, entries in groups.items():
        phases = {offset % ROW_SIZE for offset, _ in entries}
        if (len(entries) < 8 or len(phases) != 1
                or len({offset for offset, _ in entries}) != len(entries)
                or len({player for _, player in entries}) != len(entries)):
            continue
        run = longest_stride_run(entries)
        if run >= 4:
            candidates[group] = (next(iter(phases)), run)
    anchors = {phase for phase, run in candidates.values() if run >= 8}
    return {group for group, (phase, run) in candidates.items()
            if run >= 8 or anchors == {phase}}


def verified_assists(rows):
    """Read the confirmed assists byte only from internally consistent rows."""
    groups = {}
    counts = {}
    for row in rows:
        try:
            raw = bytes.fromhex(row['raw48'])
        except (TypeError, ValueError):
            continue
        if len(raw) != ROW_SIZE or row['source_offset'] < 0:
            continue
        player, group, minutes, rating = struct.unpack_from('<IHHH', raw)
        if ((player, group, minutes) != (row['player'], row['group_raw'], row['minutes'])
                or raw[10] != row['apps'] or raw[11] != row['goals']
                or raw[ASSISTS_OFFSET] != row['assists_raw']
                or not (group and 0 < raw[10] <= 100 and minutes <= 9000 and rating <= 10000)):
            continue
        groups.setdefault(group, []).append((row['source_offset'], player))
        counts[group, player] = raw[ASSISTS_OFFSET]
    accepted = aligned_groups(groups)
    return {key: value for key, value in counts.items() if key[0] in accepted}


