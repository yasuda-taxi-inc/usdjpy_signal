"""5分足を古い順に1本ずつ流し、シナリオごとのステートマシンを進める。

* 判定は「確定した足」だけで行う（呼び出し側が未確定足を除外する）。
* 毎回、取得した全足でリプレイするので、実行が欠けても状態を失わない。
* 1本の足で進むステップは最大1つ（同じ足で「到達」と「確認」を済ませない）。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .parser import Scenario, Step

M5 = timedelta(minutes=5)


@dataclass
class Bar:
    t: datetime  # 足の開始時刻
    o: float
    h: float
    l: float
    c: float


@dataclass
class Params:
    tol: float = 0.03          # 「前後」「押し」の許容幅（円）= 3pips
    max_dev: float = 0.08      # 成立時の終値とエントリー目安の最大乖離（円）= 8pips
    cooldown_bars: int = 12    # シグナル後の再判定停止（5分足×12 = 1時間）


@dataclass
class Signal:
    scenario: Scenario
    t: datetime      # シグナルが確定した足の開始時刻
    close: float


def m15_at(bars: list[Bar], i: int) -> Bar | None:
    """bars[i] が15分足の最後の5分足なら、その15分足を返す。"""
    b = bars[i]
    if b.t.minute % 15 != 10 or i < 2:
        return None
    a, m = bars[i - 2], bars[i - 1]
    if b.t - m.t != M5 or m.t - a.t != M5:
        return None
    return Bar(a.t, a.o, max(a.h, m.h, b.h), min(a.l, m.l, b.l), b.c)


class Tracker:
    def __init__(self, sc: Scenario):
        self.sc = sc
        self.k = 0
        self.flag = False
        self.cool_until = -1

    def reset(self) -> None:
        self.k, self.flag = 0, False

    def invalid(self, bar: Bar) -> bool:
        sc = self.sc
        if sc.side == "short":
            return bar.h >= sc.sl or bar.l <= sc.tp1
        return bar.l <= sc.sl or bar.h >= sc.tp1

    def ok(self, st: Step, bar: Bar, m15: Bar | None, p: Params) -> bool:
        side, k = self.sc.side, st.kind
        tfbar = m15 if st.tf == "M15" else bar
        if k in ("BREAK_DOWN", "BREAK_UP", "RECLAIM", "BEAR_CONFIRM", "BULL_CONFIRM") and tfbar is None:
            return False
        if k == "BREAK_DOWN":
            return tfbar.c < st.level
        if k in ("BREAK_UP", "RECLAIM"):
            return tfbar.c > st.level
        if k == "BEAR_CONFIRM":
            return tfbar.c < tfbar.o
        if k == "BULL_CONFIRM":
            return tfbar.c > tfbar.o
        if k == "ZONE_TOUCH":
            return bar.h >= st.lo if side == "short" else bar.l <= st.hi
        if k == "RETEST_FAIL":
            if side == "short":
                self.flag = self.flag or bar.h >= st.lo
                return self.flag and bar.c < st.lo
            self.flag = self.flag or bar.l <= st.hi
            return self.flag and bar.c > st.hi
        if k == "HOLD_LOW":
            return bar.l <= st.level + p.tol and bar.c >= st.level
        if k == "HOLD_HIGH":
            return bar.h >= st.level - p.tol and bar.c <= st.level
        if k == "ZONE_SUPPORT":
            return bar.l <= st.hi and bar.c >= st.lo
        if k == "ZONE_RESIST":
            return bar.h >= st.lo and bar.c <= st.hi
        raise ValueError(k)


def replay(scenarios: list[Scenario], bars: list[Bar], p: Params | None = None,
           since: datetime | None = None) -> list[Signal]:
    p = p or Params()
    trackers = [Tracker(s) for s in scenarios]
    out: list[Signal] = []
    for i, bar in enumerate(bars):
        if since and bar.t < since:
            continue
        m15 = m15_at(bars, i)
        for tr in trackers:
            if i < tr.cool_until:
                continue
            sc = tr.sc
            if tr.k > 0 and tr.invalid(bar):
                tr.reset()  # 損切り水準 or 第一利確に先に到達 → 仕込み前に無効
                continue
            last = tr.k == len(sc.steps) - 1
            if not tr.ok(sc.steps[tr.k], bar, m15, p):
                continue
            if last:
                if abs(bar.c - sc.entry) > p.max_dev:
                    continue  # 条件は満たしたが価格がエントリー目安から離れすぎ
                out.append(Signal(sc, bar.t, bar.c))
                tr.reset()
                tr.cool_until = i + p.cooldown_bars
            else:
                tr.k += 1
                tr.flag = False
    return out
