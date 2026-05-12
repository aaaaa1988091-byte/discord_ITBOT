# discord_ITBOT

Discord 農業模擬遊戲（持續補齊版）。

## 目前功能
- `/farm`（ephemeral）
- 主選單：🛍️ 轉化爐 / 🎒 背包 / 🌾 農田 / 🏚️ 穀倉
- 農田：5x5、中心解鎖、種植/澆水/施肥/升級/收割/資訊
- 穀倉：2x5、解鎖、升級、吃掉、全部賣出
- 市場：基礎價格 + 稀缺加成(+10%) + 過剩懲罰(-10%)
- 熟練度：收割經驗與等級影響收成量
- 素材掉落：🌚/🧾/💩/👜

## 啟動
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
DISCORD_TOKEN=xxx python bot.py
```
