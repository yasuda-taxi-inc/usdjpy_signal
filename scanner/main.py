from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

from .data import JST, drop_unclosed, fetch_bars, load_bars_csv
from .engine import M5, Params, Signal, replay
from .notify import format_signal, send
from .parser import ParseError, load_scenarios


def _since(v: str | None):
    if not v:
        return None
    d = datetime.fromisoformat(v.strip())
    return d.replace(tzinfo=JST) if d.tzinfo is None else d.astimezone(JST)


def print_check(scenarios) -> None:
    for sc in scenarios:
        print(f"■ {sc.name}  [{'売り' if sc.side == 'short' else '買い'}]")
        for i, st in enumerate(sc.steps, 1):
            print(f"   {i}. {st.describe()}")
        print(f"   → エントリー目安 {sc.entry} / 損切り {sc.sl} / 利確1 {sc.tp1} / 利確2 {sc.tp2}\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="signals.csv")
    ap.add_argument("--check", action="store_true", help="CSVの解釈結果を表示して終了")
    ap.add_argument("--bars-csv", help="ローカルの5分足CSVで全期間リプレイ（検証用。通知なし）")
    ap.add_argument("--test-notify", action="store_true", help="テスト通知を1通送って終了（市場休場中の経路確認用）")
    ap.add_argument("--dry-run", action="store_true", help="通知・状態保存をしない")
    ap.add_argument("--since", help="この時刻以降の足だけで判定（ISO。無印はJST）")
    ap.add_argument("--state", default=os.environ.get("STATE_PATH", "state/notified.json"))
    a = ap.parse_args(argv)
    env = os.environ.get

    try:
        scenarios = load_scenarios(a.csv)
    except ParseError as e:
        print(f"CSVエラー: {e}", file=sys.stderr)
        return 1
    if a.check:
        print_check(scenarios)
        return 0

    if a.test_notify:
        sc = scenarios[0]
        msg = "【テスト通知】\n" + format_signal(Signal(sc, datetime.now(JST), sc.entry))
        print(msg)
        if send(msg):
            return 0
        print("どの通知先にも送信できませんでした", file=sys.stderr)
        return 1

    p = Params(tol=float(env("TOL") or 0.03), max_dev=float(env("MAX_ENTRY_DEVIATION") or 0.08),
               cooldown_bars=int(env("COOLDOWN_BARS") or 12))
    since = _since(a.since or env("SIGNAL_SINCE"))

    if a.bars_csv:
        for s in replay(scenarios, load_bars_csv(a.bars_csv), p, since):
            print(format_signal(s), "\n")
        return 0

    now = datetime.now(JST)
    bars = drop_unclosed(fetch_bars(env("TWELVE_DATA_API_KEY", ""), env("SYMBOL") or "USD/JPY",
                                    int(env("LOOKBACK_BARS") or 288)), now)
    if not bars or now - (bars[-1].t + M5) > timedelta(minutes=30):
        print("最新の確定足が古い（市場休場の可能性）。何もせず終了")
        return 0

    max_age = timedelta(minutes=int(env("NOTIFY_MAX_AGE_MIN") or 30))
    try:
        with open(a.state, encoding="utf-8") as fh:
            notified = json.load(fh)
    except FileNotFoundError:
        notified = {}
    changed = False
    for s in replay(scenarios, bars, p, since):
        key = f"{s.scenario.name}|{s.t.isoformat()}"
        if key in notified or now - (s.t + M5) > max_age:
            continue
        msg = format_signal(s)
        print(msg, "\n")
        if a.dry_run:
            continue
        if send(msg):
            notified[key] = now.isoformat()
            changed = True
    cutoff = now - timedelta(days=3)
    pruned = {k: v for k, v in notified.items() if datetime.fromisoformat(v) > cutoff}
    if (changed or pruned != notified) and not a.dry_run:
        os.makedirs(os.path.dirname(a.state) or ".", exist_ok=True)
        with open(a.state, "w", encoding="utf-8") as fh:
            json.dump(pruned, fh, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
