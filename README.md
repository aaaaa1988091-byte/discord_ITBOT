# discord_ITBOT

## 指令
- `/farm`：農地
- `/farmui`：功能頁（轉化爐/穀倉/好友/合成區/農機具/寶典）

## 已完成重點
- 5×5 農地 + Select 動態選單
- 素材掉落與等級倍率（1.1^level）
- 合成區（⛈️、🪧、💉）
- 農機具佈置/拆除與範圍效果（3×3 / 1×1）
- 穀倉互動、賣出二次確認
- 每作物獨立熟練度
- 好友拜訪加速
- 本地 JSON 即時保存

## 啟動
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
DISCORD_TOKEN=xxx python bot.py
```

## 測試
```bash
python -m unittest test_game_logic.py
```
