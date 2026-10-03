import unittest
from datetime import datetime, timedelta

from scanner.data import JST
from scanner.engine import Bar, replay
from scanner.parser import ParseError, load_scenarios, parse_entry_text


def mk(start, rows):
    t = datetime.fromisoformat(start).replace(tzinfo=JST)
    return [Bar(t + timedelta(minutes=5 * i), *r) for i, r in enumerate(rows)]


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sc = {s.name: s for s in load_scenarios("signals.csv")}

    def names(self, bars):
        return [s.scenario.name for s in replay(list(self.sc.values()), bars)]

    def test_parse(self):
        self.assertEqual(len(self.sc), 4)
        self.assertEqual([s.kind for s in self.sc["ショート①・本線"].steps], ["ZONE_TOUCH", "BEAR_CONFIRM"])
        self.assertEqual([s.kind for s in self.sc["ショート②・支持割れ"].steps], ["BREAK_DOWN", "RETEST_FAIL"])
        self.assertEqual([s.kind for s in self.sc["ロング①・短期反発"].steps], ["HOLD_LOW", "RECLAIM", "HOLD_LOW"])
        self.assertEqual([s.kind for s in self.sc["ロング②・売り解除"].steps], ["BREAK_UP", "ZONE_SUPPORT"])
        self.assertEqual(self.sc["ロング②・売り解除"].steps[0].tf, "M15")

    def test_parse_error(self):
        with self.assertRaises(ParseError):
            parse_entry_text("月が綺麗なら157.50付近で売り")

    def test_short1(self):
        bars = mk("2026-10-03T10:00", [(157.50, 157.52, 157.48, 157.50), (157.55, 157.61, 157.54, 157.59),
                                       (157.59, 157.60, 157.54, 157.55)])
        self.assertEqual(self.names(bars), ["ショート①・本線"])

    def test_short1_invalidated_by_sl(self):
        bars = mk("2026-10-03T10:00", [(157.50, 157.52, 157.48, 157.50), (157.55, 157.61, 157.54, 157.59),
                                       (157.59, 157.76, 157.58, 157.70), (157.70, 157.71, 157.60, 157.62)])
        self.assertEqual(self.names(bars), [])

    def test_short2(self):
        bars = mk("2026-10-03T10:00", [(157.52, 157.53, 157.48, 157.50), (157.50, 157.51, 157.45, 157.46),
                                       (157.46, 157.47, 157.43, 157.44), (157.44, 157.49, 157.43, 157.48),
                                       (157.48, 157.49, 157.43, 157.44)])
        self.assertEqual(self.names(bars), ["ショート②・支持割れ"])

    def test_long1(self):
        bars = mk("2026-10-03T11:00", [(157.55, 157.56, 157.49, 157.52), (157.52, 157.62, 157.51, 157.61),
                                       (157.65, 157.66, 157.62, 157.62)])
        # 同じ値動きがショート①のゾーン到達+陰線にも該当するため、ロング①が含まれることを確認
        self.assertIn("ロング①・短期反発", self.names(bars))

    def test_long2(self):
        bars = mk("2026-10-03T12:00", [(157.78, 157.80, 157.77, 157.79), (157.79, 157.82, 157.78, 157.81),
                                       (157.81, 157.86, 157.80, 157.85), (157.85, 157.88, 157.83, 157.87),
                                       (157.87, 157.88, 157.81, 157.83)])
        self.assertEqual(self.names(bars), ["ロング②・売り解除"])

    def test_entry_too_far(self):
        # 条件は満たすが終値がエントリー目安(157.84)から離れすぎ → 通知しない
        bars = mk("2026-10-03T12:00", [(157.78, 157.80, 157.77, 157.79), (157.79, 157.82, 157.78, 157.81),
                                       (157.81, 157.86, 157.80, 157.85), (157.85, 157.97, 157.83, 157.95),
                                       (157.95, 157.96, 157.81, 157.94)])
        self.assertEqual(self.names(bars), [])


if __name__ == "__main__":
    unittest.main()
