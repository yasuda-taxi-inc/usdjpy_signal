"""signals.csv（自然文シナリオ）→ 機械判定できる Scenario に変換する。

対応している言い回しは RULES に列挙したものだけ。
解釈できない文や、読み取れない数値が残る文は ParseError にして、黙って誤解釈しない。
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field

NUM = r"\d+(?:\.\d+)?"
T = r"[～〜~]"
TF = r"(?:(?P<tf>M5|M15)\s*で)?"


class ParseError(ValueError):
    pass


@dataclass
class Step:
    kind: str
    tf: str = "M5"
    level: float | None = None
    lo: float | None = None
    hi: float | None = None

    def describe(self) -> str:
        k = self.kind
        if k == "BREAK_DOWN":
            return f"{self.tf}終値が {self.level} を下回る"
        if k == "BREAK_UP":
            return f"{self.tf}終値が {self.level} を上回る"
        if k == "RECLAIM":
            return f"{self.tf}終値が {self.level} を上回る（回復）"
        if k == "ZONE_TOUCH":
            return f"価格が {self.lo}～{self.hi} のゾーンに到達"
        if k == "RETEST_FAIL":
            return f"{self.lo}～{self.hi} に到達後、M5終値がゾーン外へ押し戻される（戻り失敗）"
        if k == "ZONE_SUPPORT":
            return f"安値が {self.hi} 以下まで下げ、M5終値が {self.lo} 以上を維持（支持化）"
        if k == "ZONE_RESIST":
            return f"高値が {self.lo} 以上まで上げ、M5終値が {self.hi} 以下（抵抗化）"
        if k == "HOLD_LOW":
            return f"安値が {self.level}＋許容幅 まで下げるが、M5終値は {self.level} 以上（安値更新に失敗／押し維持）"
        if k == "HOLD_HIGH":
            return f"高値が {self.level}－許容幅 まで上げるが、M5終値は {self.level} 以下（高値更新に失敗）"
        if k == "BEAR_CONFIRM":
            return f"{self.tf}の陰線が確定（反落確認）"
        if k == "BULL_CONFIRM":
            return f"{self.tf}の陽線が確定（反発確認）"
        return k


@dataclass
class Scenario:
    name: str
    side: str  # "short" | "long"
    entry: float
    tp1: float
    tp2: float
    sl: float
    steps: list[Step] = field(default_factory=list)
    text: str = ""


RULES = [
    ("RETEST_FAIL", rf"(?P<lo>{NUM})\s*{T}\s*(?P<hi>{NUM})\s*(?:へ|に)?の?\s*(?:戻り|押し)失敗"),
    ("ZONE_TOUCH", rf"(?P<lo>{NUM})\s*{T}\s*(?P<hi>{NUM})\s*(?:へ|に)?の?\s*(?:戻り|押し)(?!失敗)"),
    ("ZONE_SUPPORT", rf"(?P<lo>{NUM})\s*{T}\s*(?P<hi>{NUM})\s*を?\s*支持化"),
    ("ZONE_RESIST", rf"(?P<lo>{NUM})\s*{T}\s*(?P<hi>{NUM})\s*を?\s*抵抗化"),
    ("HOLD_LOW", rf"(?P<lv>{NUM})\s*(?:付近|前後)で安値更新に失敗"),
    ("HOLD_HIGH", rf"(?P<lv>{NUM})\s*(?:付近|前後)で高値更新に失敗"),
    ("BREAK_DOWN", rf"{TF}(?P<lv>{NUM})\s*を?\s*(?:割れ|下抜け|下回)"),
    ("BREAK_UP", rf"{TF}(?P<lv>{NUM})\s*を?\s*(?:超え|上抜け|上回)"),
    ("RECLAIM", rf"{TF}(?P<lv>{NUM})\s*を?\s*回復"),
    ("BEAR_CONFIRM", rf"{TF}反落確認"),
    ("BULL_CONFIRM", rf"{TF}反発確認"),
    ("PULLBACK_HOLD", r"押し(?:を)?維持"),
]
ENTRY_RX = re.compile(rf"(?P<px>{NUM})\s*(?:付近|近辺|前後)?\s*で\s*(?P<side>売り|買い)")


def _clause_steps(clause: str) -> list[Step]:
    found = []
    for kind, rx in RULES:
        for m in re.finditer(rx, clause):
            found.append((m.start(), m.end(), kind, m.groupdict()))
    found.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    picked, end = [], -1
    for s, e, kind, gd in found:
        if s >= end:
            picked.append((s, e, kind, gd))
            end = e
    if not picked:
        raise ParseError(f"解釈できない条件文です: 「{clause}」")
    leftover = clause
    for s, e, _, _ in reversed(picked):
        leftover = leftover[:s] + " " + leftover[e:]
    if re.search(NUM, leftover):
        raise ParseError(f"数値が条件として解釈されていません: 「{clause}」")
    steps = []
    for _, _, kind, gd in picked:
        f = lambda k: float(gd[k]) if gd.get(k) else None  # noqa: E731
        steps.append(Step(kind=kind, tf=(gd.get("tf") or "M5").upper(),
                          level=f("lv"), lo=f("lo"), hi=f("hi")))
    return steps


def parse_entry_text(text: str) -> tuple[str, float, list[Step]]:
    ms = list(ENTRY_RX.finditer(text))
    if not ms:
        raise ParseError(f"「◯◯付近で売り／買い」の形でエントリー価格が読み取れません: 「{text}」")
    last = ms[-1]
    side = "short" if last["side"] == "売り" else "long"
    entry = float(last["px"])
    body = text[: last.start()]
    steps: list[Step] = []
    for clause in re.split(r"[、。,，]", body):
        clause = re.sub(r"その後(は)?", "", clause).strip()
        if not clause:
            continue
        for st in _clause_steps(clause):
            if st.kind == "PULLBACK_HOLD":
                prev = [s for s in steps if s.kind == "RECLAIM"]
                if not prev:
                    raise ParseError(f"「押し維持」の基準価格（◯◯回復）が見つかりません: 「{clause}」")
                st = Step(kind="HOLD_LOW" if side == "long" else "HOLD_HIGH", level=prev[-1].level)
            steps.append(st)
    if not steps:
        raise ParseError(f"発生条件が1つも読み取れません: 「{text}」")
    return side, entry, steps


def _num(v: str, label: str, name: str) -> float:
    m = re.search(NUM, v or "")
    if not m:
        raise ParseError(f"[{name}] {label} の数値が読み取れません: 「{v}」")
    return float(m.group())


def _col(header: list[str], *keys: str) -> str:
    for h in header:
        if any(k in h for k in keys):
            return h
    raise ParseError(f"CSVに「{'/'.join(keys)}」を含む列がありません。列: {header}")


def load_scenarios(path: str) -> list[Scenario]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh)
        header = [h.strip() for h in (rd.fieldnames or [])]
        rd.fieldnames = header
        c_name = _col(header, "シナリオ")
        c_entry = _col(header, "エントリー")
        c_tp1 = _col(header, "第一利確", "利確1", "TP1")
        c_tp2 = _col(header, "第二利確", "利確2", "TP2")
        c_sl = _col(header, "損切")
        out = []
        for row in rd:
            name = (row[c_name] or "").strip()
            if not name:
                continue
            text = row[c_entry].strip()
            side, entry, steps = parse_entry_text(text)
            sc = Scenario(name=name, side=side, entry=entry, steps=steps, text=text,
                          tp1=_num(row[c_tp1], "第一利確", name),
                          tp2=_num(row[c_tp2], "第二利確", name),
                          sl=_num(row[c_sl], "損切り", name))
            ok = (sc.sl > sc.entry > sc.tp1 > sc.tp2) if side == "short" else (sc.sl < sc.entry < sc.tp1 < sc.tp2)
            if not ok:
                raise ParseError(f"[{name}] 売買方向と 損切り/エントリー/利確 の価格順が矛盾しています")
            out.append(sc)
    if not out:
        raise ParseError("シナリオが1行もありません")
    return out
