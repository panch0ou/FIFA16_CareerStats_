"""Assist decoding and publication across save contexts."""
import json
from pathlib import Path
from struct import pack_into
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import carreras
import career_schema
import datos
import layout
from extraer_bloque_estadistico import ASSISTS_OFFSET, ROW_SIZE, aligned_groups, verified_assists
from test_compatibility import CLUB, PLAYER, make_save, write_metadata


class CareerAssists(unittest.TestCase):
    def setUp(self):
        layout.LOCAL.mkdir(exist_ok=True)
        temp = TemporaryDirectory(dir=layout.LOCAL)
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        metadata = root/'metadata.xml'
        write_metadata(metadata)
        self.save = root/'profile/0/FIFA16/test-slot/DATA'
        self.save.parent.mkdir(parents=True)
        config = patch.multiple(carreras, ACTIVE=root/'profile', DB=root/'career.sqlite',
                                SCHEMA=career_schema.load(metadata),
                                LEAGUES={(13, 773, 'England Premier League (1)', 14, 1): 'Test League'})
        config.start()
        self.addCleanup(config.stop)

    def save_snapshot(self, date, groups, *, parent=None, club=CLUB, season=1):
        data = make_save(date, assist_groups=groups, club=club, season=season)
        self.save.write_bytes(data)
        result = carreras.bind(self.save, 'Synthetic fixture', parent=parent,
                               label=None if parent else 'Synthetic Career', known_league=True)
        self.assertEqual(self.save.read_bytes(), data)
        return result

    def test_assists_need_no_manual_certification(self):
        snap = self.save_snapshot(20150822, {773: [1, 0, 4, 2, 0, 0, 0, 0],
                                            951: [3, 0, 0, 0, 0, 0, 0, 0],
                                            955: [2, 0, 0, 0, 0, 0, 0, 0]})
        carreras.classify(snap['career'], CLUB, 951, 'Test Cup', 'domestic_cup', 'Fixture evidence')
        rows = {(r['group_raw'], r['player_id']): r
                for r in carreras.history(snap['sha'])['official_player_rows']}
        ozil_shape = rows[773, PLAYER]
        self.assertEqual((ozil_shape['apps'], ozil_shape['goals'], ozil_shape['assists']), (3, 2, 1))
        self.assertEqual(ozil_shape['assist_evidence'], 'verified_48_byte_layout')
        self.assertEqual(rows[773, PLAYER+1]['assists'], 0)
        self.assertEqual(rows[773, PLAYER+2]['assists'], 4)
        self.assertEqual(rows[951, PLAYER]['assists'], 3)
        self.assertNotIn((955, PLAYER), rows)
        self.assertIsNone(ozil_shape['clean_sheets'])
        with carreras.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM decoder_certifications').fetchone()[0], 0)

    def test_successive_snapshots_and_new_season(self):
        first = self.save_snapshot(20150822, {773: [1]+[0]*7})
        second = self.save_snapshot(20150830, {773: [2]+[0]*7}, parent=first['sha'])
        third = self.save_snapshot(20160710, {773: [0]*8}, parent=second['sha'], season=2)
        expected = {1: 2, 2: 0}
        actual = {r['season']: r['assists'] for r in carreras.history(third['sha'])['official_player_rows']
                  if r['player_id'] == PLAYER}
        self.assertEqual(actual, expected)
        self.assertEqual(next(r for r in carreras.history(first['sha'])['official_player_rows']
                              if r['player_id'] == PLAYER)['assists'], 1)

    def test_ambiguous_same_season_transfer_is_not_added_twice(self):
        first = self.save_snapshot(20150822, {773: [1]+[0]*7})
        second = self.save_snapshot(20150910, {773: [2]+[0]*7}, club=CLUB+1, parent=first['sha'])
        rows = [r for r in carreras.history(second['sha'])['official_player_rows'] if r['player_id'] == PLAYER]
        self.assertEqual({r['club_id'] for r in rows}, {CLUB, CLUB+1})
        self.assertTrue(all(r['assists'] is None for r in rows))
        self.assertTrue(all(r['assist_evidence'] == 'ambiguous_club_attribution' for r in rows))
        self.assertEqual(datos.totals([tuple(map(datos.safe, ('15/16', 3, 2, r['assists'], None, 'test')))
                                       for r in rows])[2], '-')
        third = self.save_snapshot(20160710, {773: [3]+[0]*7}, club=CLUB+1, parent=second['sha'], season=2)
        season_two = next(r for r in carreras.history(third['sha'])['official_player_rows']
                          if r['player_id'] == PLAYER and r['season'] == 2)
        self.assertEqual(season_two['assists'], 3)

    def test_unverified_layout_stays_unknown_and_exact_check_can_supply_a_value(self):
        snap = self.save_snapshot(20150822, {773: [1]+[0]*7})
        with carreras.connect() as db:
            db.execute("UPDATE player_observations SET raw48='' WHERE player=?", (PLAYER,))
        before = next(r for r in carreras.history(snap['sha'])['official_player_rows'] if r['player_id'] == PLAYER)
        self.assertIsNone(before['assists'])
        self.assertEqual(before['assist_evidence'], 'unverified_record_layout')
        carreras.verify_field(snap['sha'], 773, PLAYER, 'assists', 1, 'Exact fixture cross-check')
        after = next(r for r in carreras.history(snap['sha'])['official_player_rows'] if r['player_id'] == PLAYER)
        self.assertEqual(after['assists'], 1)
        self.assertEqual(after['assist_evidence'], 'exact_row_check')

    def test_legacy_integrity_exception_does_not_enable_automatic_assists(self):
        snap = self.save_snapshot(20150822, {773: [1]+[0]*7})
        with carreras.connect() as db:
            row = db.execute('SELECT metadata FROM snapshots WHERE sha=?', (snap['sha'],)).fetchone()
            metadata = json.loads(row['metadata'])
            metadata['integrity'] = 'verified_zero_container_crc'
            db.execute('UPDATE snapshots SET metadata=? WHERE sha=?',
                       (json.dumps(metadata), snap['sha']))
        rows = carreras.history(snap['sha'])['official_player_rows']
        self.assertTrue(rows)
        self.assertTrue(all(r['assists'] is None for r in rows))
        self.assertTrue(all(r['assist_evidence'] == 'unverified_save_integrity' for r in rows))


class RecordLayout(unittest.TestCase):
    def test_fragmented_competition_requires_an_independent_same_phase_anchor(self):
        anchor = [(48*i, 10+i) for i in range(8)]
        fragmented = [(48*i, 100+i) for i in (10, 11, 12, 13, 20, 21, 22, 23)]
        self.assertEqual(aligned_groups({42: fragmented}), set())
        self.assertEqual(aligned_groups({42: fragmented, 53: anchor}), {42, 53})
        shifted = [(offset+1, player) for offset, player in fragmented]
        self.assertEqual(aligned_groups({42: shifted, 53: anchor}), {53})

    def test_stored_count_must_match_raw_row_even_on_proven_alignment(self):
        rows = []
        for i in range(10):
            raw = bytearray(ROW_SIZE)
            pack_into('<IHHH', raw, 0, 10+i, 27, 90, 700)
            raw[10:12] = b'\x03\x02'
            raw[ASSISTS_OFFSET] = i
            rows.append(dict(player=10+i, group_raw=27, minutes=90, apps=3, goals=2,
                             assists_raw=i, raw48=raw.hex(), source_offset=i*ROW_SIZE))
        rows[-1]['assists_raw'] = 80
        counts = verified_assists(rows)
        self.assertEqual(counts[27, 10], 0)
        self.assertEqual(counts[27, 18], 8)
        self.assertNotIn((27, 19), counts)


if __name__ == '__main__':
    unittest.main()
