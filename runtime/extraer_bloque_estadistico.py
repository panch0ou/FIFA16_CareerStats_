"""Identify candidate statistical groups in a verified DATA snapshot."""
import struct

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
            if offset + 48 > len(data):
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
        current = current + 1 if following - previous == 48 else 1
        longest = max(longest, current)
    return longest


