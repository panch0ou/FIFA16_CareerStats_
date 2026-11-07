"""Native object identity, official categories and compressed English labels."""
from pathlib import Path
from struct import pack, pack_into
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import competition_catalog as catalog
import layout
from transferengine.checksums import fifa_crc


class NativeCompetitions(unittest.TestCase):
    def setUp(self):
        layout.LOCAL.mkdir(exist_ok=True)
        tmp = TemporaryDirectory(dir=layout.LOCAL)
        self.addCleanup(tmp.cleanup)
        self.game = Path(tmp.name)
        self.comp = self.game/catalog.COMPDATA
        self.comp.mkdir(parents=True)
        (self.comp/'compobj.txt').write_text(
            '0,0,FIFA,FIFA,-1\n1,1,REGION,Region,0\n2,2,NATION,Nation,1\n'
            '991,3,C42,LeagueKey,2\n992,3,C43,CupKey,2\n993,3,C44,EuroKey,1\n'
            '994,3,C45,FriendlyKey,1\n995,3,C46,UnknownKey,2\n', encoding='utf-8')
        (self.comp/'settings.txt').write_text(
            '991,comp_type,LEAGUE\n992,comp_type,CUP\n993,comp_type,INTERCUP\n'
            '994,comp_type,INTERFRIENDLY\n995,comp_type,CUP\n', encoding='utf-8')

    def test_general_objects_use_native_identity_type_and_name(self):
        with patch.object(catalog, 'localized_names', return_value={
                'LeagueKey': 'Test League', 'CupKey': 'Test Cup', 'EuroKey': 'Test Continental',
                'FriendlyKey': 'Friendly'}):
            result = catalog.load(self.game)
        self.assertEqual({k: (r['code'], r['label'], r['category']) for k, r in result.items()}, {
            991: ('C42', 'Test League', 'league'), 992: ('C43', 'Test Cup', 'domestic_cup'),
            993: ('C44', 'Test Continental', 'continental')})

    def test_duplicate_objects_or_missing_evidence_remain_unclassified(self):
        self.assertEqual(catalog.load(self.game), {})
        with (self.comp/'compobj.txt').open('a') as stream:
            stream.write('992,3,C99,OtherKey,2\n')
        with patch.object(catalog, 'localized_names', return_value={'CupKey': 'Test Cup'}):
            self.assertEqual(catalog.load(self.game), {})

    def test_crc_valid_compressed_localization_is_decoded_and_corruption_rejected(self):
        loc = self.game/'data/loc'
        loc.mkdir(parents=True)
        (loc/'eng_us-meta.xml').write_text(
            '<database><table name="LanguageStrings" shortname="LANG"><fields>'
            '<field name="stringid" shortname="KEYS" depth="800"/>'
            '<field name="sourcetext" shortname="TEXT" depth="32000"/>'
            '</fields></table></database>', encoding='utf-8')
        # Two Huffman leaves, A and B. Offsets address the same string pool
        # used by FIFA's type 13 keys and type 14 localized text.
        pool = pack('<HH', ord('A') << 8, ord('B') << 8) + b'\x01\x00\x00\x01\x80'
        descriptors = pack('<II4sI', 13, 0, b'KEYS', 800) + pack('<II4sI', 14, 32, b'TEXT', 32000)
        header = bytearray(36)
        pack_into('<I', header, 4, 9)
        pack_into('<HHH', header, 16, 1, 1, 0)
        header[24] = 2
        pack_into('<I', header, 32, fifa_crc(header[:32]))
        body = descriptors + pack('<II', 4, 6) + b'\x00' + pool
        table = header + body + pack('<I', fifa_crc(body))
        directory = pack('<4sI', b'LANG', 0)
        db = bytearray(b'DB\x00\x08\x00\x00\x00\x00' + bytes(16))
        pack_into('<I', db, 8, 36 + len(table))
        pack_into('<I', db, 16, 1)
        pack_into('<I', db, 20, fifa_crc(db[:20]))
        db += directory + pack('<I', fifa_crc(directory)) + table
        path = loc/'eng_us.db'
        path.write_bytes(db)
        self.assertEqual(catalog.localized_names(self.game, {'A'}), {'A': 'B'})
        db[-1] ^= 1
        path.write_bytes(db)
        with self.assertRaisesRegex(ValueError, 'CRC'):
            catalog.localized_names(self.game, {'A'})
        self.assertEqual(catalog.load(self.game), {})


if __name__ == '__main__':
    unittest.main()
