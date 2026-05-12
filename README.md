# discord_ITBOT

## 已依需求修正
- `/farm` 直接顯示完整 5×5 農田按鈕。
- 點擊地塊後顯示 **Select Menu**（不是額外一排按鈕）。
- Select Menu 為動態可適應：不能做的操作不會出現。
- 初始資源修正：金幣 100，其他素材初始為 0（體力/飽食度 100）。

## 啟動
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
DISCORD_TOKEN=xxx python bot.py
```
