# Discord 五子棋通話活動 Bot

你說得對：這版是**通話活動（Voice Activity）**，不是聊天訊息內嵌棋盤。

Bot 會提供 `/gomoku` 指令，在語音頻道建立一個五子棋 Activity 邀請連結。

## 需求

1. 你有一個可供嵌入語音活動的五子棋 Activity Application ID
2. Bot 有該語音頻道的：
   - View Channel
   - Create Invite

## 安裝

```bash
npm install
cp .env.example .env
```

## 環境變數

- `DISCORD_TOKEN`: Bot token
- `CLIENT_ID`: Discord application client id
- `GOMOKU_ACTIVITY_APP_ID`: 五子棋活動的 Application ID

## 使用

1. 啟動 bot

```bash
npm start
```

2. 在伺服器輸入：

- `/gomoku`：使用你目前所在語音頻道
- `/gomoku voice_channel:#你的語音頻道`：指定語音頻道

Bot 會回傳活動邀請連結（`https://discord.gg/...`），點擊即可開啟通話活動。
