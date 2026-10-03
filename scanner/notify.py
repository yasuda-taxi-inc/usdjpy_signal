"""通知。環境変数が設定されているチャネルすべてに送る（標準ライブラリのみ）。

NTFY_TOPIC（任意で NTFY_SERVER=https://ntfy.sh, NTFY_TOKEN）
DISCORD_WEBHOOK_URL
TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
LINE_CHANNEL_ACCESS_TOKEN + LINE_USER_ID   （LINE Messaging API の push）
"""
from __future__ import annotations

import json
import os
import urllib.request

from .engine import Signal


def format_signal(s: Signal) -> str:
    sc = s.scenario
    pips = lambda px: abs(px - sc.entry) * 100  # noqa: E731
    risk = pips(sc.sl)
    rr = lambda px: pips(px) / risk if risk else 0  # noqa: E731
    return (
        f"🔔 USD/JPY シグナル：{sc.name}\n"
        f"方向：{'売り' if sc.side == 'short' else '買い'}　足確定：{s.t:%m/%d %H:%M}（JST・5分足）\n"
        f"終値：{s.close:.3f}　エントリー目安：{sc.entry:.3f}\n"
        f"損切り：{sc.sl:.3f}（-{risk:.1f}pips）\n"
        f"利確1：{sc.tp1:.3f}（+{pips(sc.tp1):.1f}pips, RR {rr(sc.tp1):.2f}）\n"
        f"利確2：{sc.tp2:.3f}（+{pips(sc.tp2):.1f}pips, RR {rr(sc.tp2):.2f}）\n"
        f"条件：{sc.text}"
    )


def _post(url: str, payload: dict, headers: dict | None = None) -> None:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "usdjpy-signal-alert/1.0", **(headers or {})})
    with urllib.request.urlopen(req, timeout=15) as r:
        r.read()


def send(text: str) -> bool:
    env = os.environ.get
    sent = False
    jobs = []
    if env("NTFY_TOPIC"):
        server = (env("NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
        title = text.splitlines()[0].replace("🔔 ", "")
        hdr = {"Authorization": f"Bearer {env('NTFY_TOKEN')}"} if env("NTFY_TOKEN") else None
        # JSON publish なので日本語・絵文字をヘッダに載せずに済む
        jobs.append(("ntfy", lambda: _post(server, {
            "topic": env("NTFY_TOPIC"), "title": title, "message": "\n".join(text.splitlines()[1:]),
            "priority": 4, "tags": ["chart_with_upwards_trend"]}, hdr)))
    if env("DISCORD_WEBHOOK_URL"):
        jobs.append(("Discord", lambda: _post(env("DISCORD_WEBHOOK_URL"), {"content": text})))
    if env("TELEGRAM_BOT_TOKEN") and env("TELEGRAM_CHAT_ID"):
        jobs.append(("Telegram", lambda: _post(
            f"https://api.telegram.org/bot{env('TELEGRAM_BOT_TOKEN')}/sendMessage",
            {"chat_id": env("TELEGRAM_CHAT_ID"), "text": text})))
    if env("LINE_CHANNEL_ACCESS_TOKEN") and env("LINE_USER_ID"):
        jobs.append(("LINE", lambda: _post(
            "https://api.line.me/v2/bot/message/push",
            {"to": env("LINE_USER_ID"), "messages": [{"type": "text", "text": text}]},
            {"Authorization": f"Bearer {env('LINE_CHANNEL_ACCESS_TOKEN')}"})))
    for name, fn in jobs:
        try:
            fn()
            sent = True
        except Exception as e:  # noqa: BLE001
            print(f"[notify] {name} 送信失敗: {e}")
    if not jobs:
        print("[notify] 通知先が未設定です（標準出力のみ）")
    return sent
