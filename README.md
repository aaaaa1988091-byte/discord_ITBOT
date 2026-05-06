# Discord 五子棋 Bot

這是一個使用 `discord.js` 製作的 Discord Activities 風格互動 Bot，提供 `/gomoku` 指令開啟五子棋對局。

## 功能

- `/gomoku opponent:@user` 建立對局
- 15x15 棋盤
- 按鈕操作游標移動、落子、投降
- 自動判斷連五勝利

## 安裝

```bash
npm install
cp .env.example .env
```

填入 `.env`：

- `DISCORD_TOKEN`: Bot token
- `CLIENT_ID`: Discord application client id

## 啟動

```bash
npm start
```

Bot 上線後會自動註冊全域 slash command。
