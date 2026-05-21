# Discord 五子棋通話活動 Bot

你說得對：這版是**通話活動（Voice Activity）**，不是聊天訊息內嵌棋盤。

Bot 會提供 `/gomoku` 指令，在語音頻道建立五子棋 Activity 邀請連結。

## Application ID 是什麼？

你問的 **Application ID** 指的是 Discord 應用程式 ID。

- `CLIENT_ID`：你的 Discord 應用程式 ID（通常就是 bot 的 app id）
- `GOMOKU_ACTIVITY_APP_ID`：**可選**，只有在你要指定「另一個」Activity 應用程式時才需要

> 一般情況可只填 `CLIENT_ID`，不需要再找第二個 ID。

## 需求

1. Bot 有該語音頻道權限：
   - View Channel
   - Create Invite
2. 伺服器允許啟動 Activities

## 安裝

```bash
npm install
cp .env.example .env
```

## 環境變數

- `DISCORD_TOKEN`: Bot token
- `CLIENT_ID`: Discord application client id（必填）
- `GOMOKU_ACTIVITY_APP_ID`: 指定其他 Activity app id（選填）

## 使用

1. 啟動 bot

```bash
npm start
```

2. 在伺服器輸入：

- `/gomoku`：使用你目前所在語音頻道
- `/gomoku voice_channel:#你的語音頻道`：指定語音頻道

Bot 會回傳活動邀請連結（`https://discord.gg/...`），點擊即可開啟通話活動。
