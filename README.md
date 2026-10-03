# USD/JPY シグナル通知（Twelve Data + GitHub Actions）

`signals.csv` に書いたシナリオを5分足の確定ごとに判定し、成立したら ntfy / Discord / Telegram / LINE に通知します。

## セットアップ
1. このフォルダをGitHubリポジトリに push（**publicリポジトリ推奨**：privateはActions無料枠が月2,000分で全日5分間隔だと足りません）
2. Settings → Secrets and variables → Actions → Secrets に登録
   - `TWELVE_DATA_API_KEY`
   - 通知先（使うものだけ）: `NTFY_TOPIC`（推測されにくい長めのトピック名。自前サーバ/認証ありなら Variables に `NTFY_SERVER`、Secrets に `NTFY_TOKEN`）/ `DISCORD_WEBHOOK_URL` / `TELEGRAM_BOT_TOKEN`+`TELEGRAM_CHAT_ID` / `LINE_CHANNEL_ACCESS_TOKEN`+`LINE_USER_ID`
3. Actions タブで `signal-scan` を手動実行して動作確認

## 毎日の使い方
- `signals.csv` を差し替えて commit するだけ。**最後にコミットした時刻以降の足だけ**で判定します（前日の値動きで誤発報しない）。
- 時刻を手動指定したい場合は Variables に `SIGNAL_SINCE`（例 `2026-10-03T09:00:00+09:00`）。

## 手元での確認
```
python3 -m scanner.main --check                 # CSVの解釈結果を表示（最初に必ず確認）
python3 -m unittest                             # テスト
python3 -m scanner.main --bars-csv bars.csv     # 過去5分足CSVでリプレイ（datetime,open,high,low,close）
TWELVE_DATA_API_KEY=xxx python3 -m scanner.main --dry-run   # API取得→判定のみ（通知なし）
```

## 調整用の環境変数（任意）
`TOL`(0.03) 「前後」の許容幅 / `MAX_ENTRY_DEVIATION`(0.08) 成立時の終値とエントリー目安の最大乖離 / `COOLDOWN_BARS`(12) / `NOTIFY_MAX_AGE_MIN`(30)

## 対応している条件の言い回し
`M5|M15で◯◯割れ|超え` / `◯◯回復` / `A～Bへの戻り` / `A～Bへの戻り失敗` / `A～Bを支持化|抵抗化` / `◯◯前後で安値更新に失敗` / `押しを維持` / `反落確認|反発確認` / 末尾に `◯◯付近で売り|買い`。
未対応の文はエラーにします（`--check` で確認）。
