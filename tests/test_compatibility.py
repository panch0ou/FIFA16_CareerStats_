"""Synthetic FIFA tables and CRC-valid saves for compatibility regressions."""
from hashlib import sha256
from pathlib import Path
from struct import pack, pack_into
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import xml.etree.ElementTree as ET

import carreras
import career_schema
import datos
import guardados
import layout
from screen_assets import pack_bytes, verify_template
from test_automation import capture, flow
from transferengine.checksums import container_crc, fifa_crc
from transferengine.saveio import SaveSnapshot, SaveError


# Use real field names with disposable values. Larger IDs use a widened schema.
TABLES = {
    'career_users': ('mPrV', [('clubteamid', 'NTyS', 20), ('seasoncount', 'CXJt', 4),
                             ('leagueid', 'aQrQ', 12), ('primarycompobjid', 'XGBd', 11)]),
    'career_calendar': ('GJUr', [('currdate', 'aLZZ', 25), ('setupdate', 'KNVN', 25),
                                ('enddate', 'ZPUX', 25)]),
    'teamplayerlinks': ('RrqT', [('teamid', 'mCXg', 20), ('playerid', 'ykFq', 22)]),
    'players': ('CZUM', [('playerid', 'ykFq', 22), ('preferredposition1', 'wZQU', 5),
                         ('customattribute', 'zz01', 8)]),
    'leagues': ('onMQ', [('leagueid', 'aQrQ', 12), ('leaguename', 'HEQX', 240),
                         ('countryid', 'WDGJ', 8), ('level', 'paPI', 3)]),
    'teams': ('lyxL', [('teamid', 'mCXg', 20)]),
    'customtable': ('ztbl', [('customvalue', 'zz02', 8)]),
}
CLUB = 800_321
PLAYER = 1_200_321


def write_metadata(path, *, missing=None, bad_field=None, include_leagues=True):
    root = ET.Element('database')
    for table, (code, fields) in TABLES.items():
        if table == 'leagues' and not include_leagues:
            continue
        entry = ET.SubElement(root, 'table', name=table, shortname=code)
        columns = ET.SubElement(entry, 'fields')
        for field, short, bits in fields:
            if (table, field) == missing:
                continue
            field_type = 'STRING' if field == 'leaguename' else 'INTEGER'
            if (table, field) == bad_field:
                field_type = 'BINARY'
            ET.SubElement(columns, 'field', name=field, shortname=short, rangelow='0',
                          type=f'DBOFIELDTYPE_{field_type}',
                          depth=str(7 if field == 'customattribute' else bits))
    ET.ElementTree(root).write(path, encoding='utf-8')


def binary_table(fields, rows):
    descriptors = bytearray()
    offset = 0
    for name, code, width in fields:
        descriptors += pack('<II4sI', 0 if name == 'leaguename' else 3, offset*8,
                            code.encode('ascii'), width)
        offset += (width+7)//8
    header = bytearray(36)
    pack_into('<I', header, 4, offset+1)
    pack_into('<HHH', header, 16, len(rows), len(rows), 0)
    header[24] = len(fields)
    pack_into('<I', header, 32, fifa_crc(header[:32]))
    data = bytearray(descriptors)
    for row in rows:
        for value, (_, _, width) in zip(row, fields, strict=True):
            size = (width+7)//8
            data += (value.encode('ascii').ljust(size, b'\0') if isinstance(value, str)
                     else value.to_bytes(size, 'little'))
        data += b'\0'
    return header + data + pack('<I', fifa_crc(data))


def make_save(date, *, stats=False, missing_binary_field=False, include_leagues=True):
    ids = list(range(PLAYER, PLAYER+8))
    content = {
        'career_users': [(CLUB, 1, 13, 773)],
        'career_calendar': [(date, 20150701, 20160630)],
        'teamplayerlinks': [(CLUB, player) for player in ids] + [(20, 777)],
        'players': [(player, 0 if player == PLAYER else 6, 87) for player in [777, *ids]],
        'leagues': [(13, 'England Premier League (1)', 14, 1)],
        'teams': [(20,), (CLUB,)],
        'customtable': [(42,)],
    }
    directory, blocks = bytearray(), bytearray()
    for name, (code, fields) in TABLES.items():
        if name == 'leagues' and not include_leagues:
            continue
        rows = content[name]
        if name == 'teamplayerlinks' and missing_binary_field:
            fields = fields[:1]
            rows = [row[:1] for row in rows]
        directory += pack('<4sI', code.encode('ascii'), len(blocks))
        blocks += binary_table(fields, rows)
    header = bytearray(b'DB\x00\x08\x00\x00\x00\x00' + bytes(16))
    pack_into('<I', header, 8, 28+len(directory)+len(blocks))
    pack_into('<I', header, 16, len(directory)//8)
    pack_into('<I', header, 20, fifa_crc(header[:20]))
    save = bytearray(160)
    save[16:32] = b'Disposable save\0'
    save[116:132] = b'SaveType_Career\0'
    save += header + directory + pack('<I', fifa_crc(directory)) + blocks
    if stats:
        for player in ids:
            row = bytearray(48)
            pack_into('<IHHH', row, 0, player, 773, 90, 700)
            row[10:12] = b'\x01\x02'
            save += row
    pack_into('<I', save, 132, container_crc(save))
    return bytes(save)


class FlexibleSaveCompatibility(unittest.TestCase):
    def setUp(self):
        layout.LOCAL.mkdir(exist_ok=True)
        temp = TemporaryDirectory(dir=layout.LOCAL)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.xml = self.root/'game-meta.xml'
        self.profile = self.root/'profile'
        self.save = self.profile/'0/FIFA16/synthetic/DATA'
        self.save.parent.mkdir(parents=True)
        write_metadata(self.xml)

    def test_extra_tables_columns_and_larger_ids_decode(self):
        original = make_save(20150701, stats=True)
        self.save.write_bytes(original)
        with patch.multiple(carreras, ACTIVE=self.profile, SCHEMA=career_schema.load(self.xml)):
            data = carreras.inspect(self.save)
        self.assertEqual(data['club'], CLUB)
        self.assertEqual(data['roster'], list(range(PLAYER, PLAYER+8)))
        self.assertEqual(data['records'][0]['gk'], 1)
        self.assertEqual(data['native_league'], ('England Premier League (1)', 14, 1))
        self.assertEqual(self.save.read_bytes(), original)

    def test_required_schema_missing_or_wrong_type_is_explained(self):
        for options in ({'missing': ('teamplayerlinks', 'playerid')},
                        {'bad_field': ('teamplayerlinks', 'playerid')}):
            with self.subTest(options=options):
                write_metadata(self.xml, **options)
                with self.assertRaisesRegex(career_schema.CareerSchemaError, r'teamplayerlinks\.playerid'):
                    career_schema.load(self.xml)

    def test_required_binary_field_and_crc_remain_guarded(self):
        schema = career_schema.load(self.xml)
        with self.assertRaisesRegex(SaveError, r'teamplayerlinks\.playerid'):
            carreras.validate_snapshot(SaveSnapshot.from_bytes(
                make_save(20150701, missing_binary_field=True), schema))
        data = bytearray(make_save(20150701))
        data[-1] ^= 1
        with self.assertRaisesRegex(SaveError, 'CRC'):
            carreras.validate_snapshot(SaveSnapshot.from_bytes(data, schema))

    def test_missing_optional_league_metadata_does_not_block_save(self):
        write_metadata(self.xml, include_leagues=False)
        self.save.write_bytes(make_save(20150701, include_leagues=False))
        with patch.multiple(carreras, ACTIVE=self.profile, SCHEMA=career_schema.load(self.xml)):
            self.assertIsNone(carreras.inspect(self.save)['native_league'])

    def test_missing_position_does_not_block_appearances_and_goals(self):
        write_metadata(self.xml, missing=('players', 'preferredposition1'))
        self.save.write_bytes(make_save(20150701, stats=True))
        with patch.multiple(carreras, ACTIVE=self.profile, SCHEMA=career_schema.load(self.xml)):
            first = carreras.inspect(self.save)['records'][0]
        self.assertIsNone(first['gk'])
        self.assertEqual((first['apps'], first['goals']), (1, 2))

    def test_new_career_and_continuation_with_uncovered_player_and_club(self):
        spec = layout.read(layout.PROFILE_FILE)
        leagues = {(13, 773, 'England Premier League (1)', 14, 1): 'Barclays Premier League'}
        db = self.root/'career.sqlite'
        self.save.write_bytes(make_save(20150701))
        with (patch.multiple(carreras, ACTIVE=self.profile, SCHEMA=career_schema.load(self.xml),
                             DB=db, LEAGUES=leagues),
              patch.multiple(datos, HISTORICAL_DB=layout.INPUTS/'historial_ampliado.sqlite',
                             BASELINE=layout.INPUTS/'club_records.json',
                             HISTORICAL_CLUBS=spec['historical_clubs']),
              patch.object(guardados.time, 'monotonic') as clock):
            with carreras.connect():
                pass
            process = SimpleNamespace(pid=12, creation=34)
            session = guardados.AutomaticSession(process, {'career_inventory_before': {}})
            events = [flow(1, guardados.START), flow(2, guardados.USER_SAVE)]
            clock.return_value = 1
            session.update(events, True)
            clock.return_value = 2
            session.update(events, True)
            self.assertEqual(session.last_flow['result'], 'automatic_root')
            parent = session.head
            self.assertEqual(parent, sha256(self.save.read_bytes()).hexdigest())
            session = guardados.AutomaticSession(process, {
                'career_inventory_before': {str(self.save.relative_to(self.profile)): parent}})
            self.save.write_bytes(make_save(20150702, stats=True))
            before = self.save.read_bytes()
            events = [capture(1, parent), flow(2, guardados.LOAD), flow(3, guardados.USER_SAVE)]
            clock.return_value = 3
            session.update(events, True)
            clock.return_value = 4
            session.update(events, True)
            self.assertEqual(session.last_flow['parent'], parent)
            self.assertEqual(carreras.history(session.head)['ancestry'], [session.head, parent])
            source = datos.Source()
            self.assertNotIn(PLAYER, source.past)
            buckets, club, _ = source.snapshot(session.head)
            record = next(row for row in buckets[PLAYER % datos.BUCKETS]
                          if row.startswith(f'{PLAYER}|'))
            self.assertTrue(record.endswith('|PARTIAL CAREER STATS'))
            self.assertEqual(club.split('|')[1:6], ['-']*5)
            self.assertEqual(self.save.read_bytes(), before)


class ScreenCompatibility(unittest.TestCase):
    def test_padding_is_ignored_but_changed_apt_is_rejected(self):
        header = bytearray(64)
        header[:4] = b'BIGF'
        pack_into('>I', header, 8, 3)
        pack_into('>II', header, 16, 64, 10)
        pack_into('>I', header, 26, 128)
        pack_into('>II', header, 38, 128, 4)
        header[24:26], header[34:38], header[46:48] = b'0\0', b'sg2\0', b'1\0'
        source = header + b'Apt Data!!' + bytes(54) + b'Apt1' + bytes(16)
        canonical, _ = pack_bytes(source, b'Apt Data!!', b'Apt1')
        expected = sha256(canonical).hexdigest()
        changed = bytearray(canonical)
        changed[75] = 0xf0
        self.assertEqual(verify_template(changed, 'test screen', expected), canonical)
        changed[72] = 0x61
        with self.assertRaisesRegex(ValueError, 'differs in content'):
            verify_template(changed, 'test screen', expected)


if __name__ == '__main__':
    unittest.main()
