"""Chronology is applied to every player's complete list before pagination."""
import random
import unittest

import datos


class PlayerHistoryOrder(unittest.TestCase):
    def record(self, year, calendar=False, competition='League'):
        label = str(year) if calendar else datos.season_label(year)
        return (1, (label, '3', '2', '1', '-', f'Club / {competition}'),
                (year, 0 if calendar else 1))

    def test_calendar_year_precedes_season_and_all_pages_are_sorted(self):
        records = [self.record(year, calendar, competition)
                   for year in range(1998, 2021)
                   for calendar in (True, False) for competition in ('Cup', 'League')]
        expected = [r[1] for r in records]
        random.Random(16).shuffle(records)
        for pid in (1, 144, 512, 1200321):
            line = datos.player_line(pid, records[:40], records[40:], 1, True)
            rows = [tuple(row.split('~')) for row in line.split('|')[1].split('^')]
            self.assertEqual(rows, expected)
            # The APT renderer slices this same ordered list into 16-row pages.
            pages = [rows[i:i+16] for i in range(0, len(rows), 16)]
            self.assertEqual([row for page in pages for row in page], expected)

    def test_historical_only_and_mixed_import_rows_use_the_same_key(self):
        past = [self.record(2014), self.record(2012), self.record(2013, True)]
        current = [self.record(2016), self.record(2015)]
        line = datos.player_line(1, past, current, 1, True)
        self.assertEqual([r.split('~')[0] for r in line.split('|')[1].split('^')],
                         ['12/13', '2013', '14/15', '15/16', '16/17'])
        historical = datos.player_line(1, past, [], None, False)
        self.assertEqual([r.split('~')[0] for r in historical.split('|')[1].split('^')],
                         ['12/13', '2013', '14/15'])
        self.assertEqual(line.split('|')[4], '15       10       5')

    def test_numeric_source_year_disambiguates_abbreviated_centuries(self):
        rows = [self.record(2051), self.record(1951), self.record(2050), self.record(1950)]
        self.assertEqual([r[2][0] for r in sorted(rows, key=datos.chronological_key)],
                         [1950, 1951, 2050, 2051])


if __name__ == '__main__':
    unittest.main()
