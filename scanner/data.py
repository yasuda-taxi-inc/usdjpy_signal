"""Twelve Data から5分足を取得（標準ライブラリのみ）。"""
from __future__ import annotations

import csv
import json
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

from .engine import M5, Bar

JST = ZoneInfo("Asia/Tokyo")


def _ts(s: str) -> datetime:
    return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=JST)


def fetch_bars(api_key: str, symbol: str = "USD/JPY", n: int = 288) -> list[Bar]:
    q = urllib.parse.urlencode({
        "symbol": symbol, "interval": "5min", "outputsize": n,
        "timezone": "Asia/Tokyo", "order": "ASC", "apikey": api_key,
    })
    req = urllib.request.Request(f"https://api.twelvedata.com/time_series?{q}",
                                 headers={"User-Agent": "usdjpy-signal-alert/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    if data.get("status") == "error" or "values" not in data:
        raise RuntimeError(f"Twelve Data error: {data.get('code')} {data.get('message')}")
    bars = [Bar(_ts(v["datetime"]), float(v["open"]), float(v["high"]),
                float(v["low"]), float(v["close"])) for v in data["values"]]
    bars.sort(key=lambda b: b.t)
    return bars


def drop_unclosed(bars: list[Bar], now: datetime) -> list[Bar]:
    """開始時刻+5分 が now を過ぎていない（形成中の）足を除く。"""
    return [b for b in bars if b.t + M5 <= now]


def load_bars_csv(path: str) -> list[Bar]:
    """Twelve Data等のCSV（datetime,open,high,low,close。区切りは , か ;）。時刻はJST扱い。"""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        head = fh.readline()
        fh.seek(0)
        rd = csv.DictReader(fh, delimiter=";" if ";" in head else ",")
        bars = [Bar(_ts(r["datetime"]), float(r["open"]), float(r["high"]),
                    float(r["low"]), float(r["close"])) for r in rd]
    bars.sort(key=lambda b: b.t)
    return bars
