"""Resolve native competition objects and English names without changing game files."""
import csv
from io import StringIO
from struct import unpack_from

from archivos import target
from transferengine.saveio import SaveSnapshot

COMPDATA = 'dlc/dlc_FootballCompEng/dlc/FootballCompEng/data/compdata/'
OFFICIAL_TYPES = {'LEAGUE', 'PLAYOFF', 'CUP', 'SUPERCUP', 'INTERCUP', 'INTERQUAL'}


def read_bounded(game, relative, limit):
    with target(game, relative).open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Competition metadata exceeds the supported size.')
    return data


def localized_names(game, wanted):
    data = read_bounded(game, 'data/loc/eng_us.db', 8 * 1024 * 1024)
    snapshot = SaveSnapshot.from_bytes(data, target(game, 'data/loc/eng_us-meta.xml'), container=False)
    snapshot.require_valid()
    table = snapshot.table('LanguageStrings')
    key_field = table.get_field('stringid')
    text_field = table.get_field('sourcetext')
    if (key_field.type, text_field.type) != (13, 14):
        raise ValueError('Unsupported competition name encoding.')
    pool = table.record_start + table.capacity * table.record_size

    def decode(row, field, prefix):
        start = table.record_start + row * table.record_size + field.bit // 8
        pointer = unpack_from('<I', data, start)[0]
        cursor = pool + pointer
        if not pool <= cursor < table.end - 4 - prefix:
            raise ValueError('Invalid competition name pointer.')
        length = int.from_bytes(data[cursor:cursor + prefix], 'big')
        if length > field.depth // 8:
            raise ValueError('Invalid competition name length.')
        result = bytearray()
        node = 0
        for byte in data[cursor + prefix:min(table.end - 4, cursor + prefix + length * 32)]:
            for bit in range(7, -1, -1):
                at = pool + node * 4 + 2 * ((byte >> bit) & 1)
                if not pool <= at < min(pool + pointer, table.end - 5):
                    raise ValueError('Invalid competition name tree.')
                branch = unpack_from('<H', data, at)[0]
                if branch & 0xff == 0:
                    result.append(branch >> 8)
                    node = 0
                    if len(result) == length:
                        return result.decode('utf-8')
                else:
                    node = branch
        if length:
            raise ValueError('Incomplete competition name.')
        return ''

    names = {}
    for row in table.active_rows(data):
        key = decode(row, key_field, 1)
        if key in wanted:
            text = decode(row, text_field, 2).strip()
            if text and not any(c in text for c in '|^~\r\n\0'):
                if key in names and names[key] != text:
                    raise ValueError('Ambiguous competition name.')
                names[key] = text
    return names


def load(game):
    """Missing or unsupported evidence leaves competition IDs unclassified."""
    try:
        objects = {}
        content = read_bounded(game, COMPDATA + 'compobj.txt', 1024 * 1024)
        for row in csv.reader(StringIO(content.decode('utf-8-sig'))):
            if len(row) != 5:
                raise ValueError('Invalid competition object.')
            group, kind, code, label, parent = row
            group, kind, parent = int(group), int(kind), int(parent)
            if group in objects:
                raise ValueError('Ambiguous competition object.')
            objects[group] = (kind, code, label, parent)
        types = {}
        content = read_bounded(game, COMPDATA + 'settings.txt', 1024 * 1024)
        for row in csv.reader(StringIO(content.decode('utf-8-sig'))):
            if len(row) != 3:
                raise ValueError('Invalid competition settings.')
            group, field, value = row
            if field == 'comp_type':
                group = int(group)
                if group in types:
                    raise ValueError('Ambiguous competition type.')
                types[group] = value
        names = localized_names(game, {o[2] for o in objects.values() if o[0] == 3})
    except (OSError, ValueError):
        return {}
    result = {}
    for group, (kind, code, name, parent) in objects.items():
        comp_type = types.get(group)
        if kind != 3 or comp_type not in OFFICIAL_TYPES or name not in names:
            continue
        if comp_type in ('LEAGUE', 'PLAYOFF'):
            category = 'league'
        elif comp_type in ('INTERCUP', 'INTERQUAL') or objects.get(parent, (None,))[0] in (0, 1):
            category = 'continental'
        elif objects.get(parent, (None,))[0] == 2:
            category = 'domestic_cup'
        else:
            continue
        result[group] = {'code': code, 'label': names[name], 'category': category,
                         'evidence': 'Native competition object, type and English localization'}
    return result
