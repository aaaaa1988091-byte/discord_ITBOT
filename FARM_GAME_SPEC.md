# Discord 農業模擬遊戲完整設計規範

## 1. 核心規範
- 唯一指令：`/farm`
- 所有訊息皆為 **Ephemeral**（僅本人可見）
- 全按鈕操作，不使用文字輸入
- UI 切換透過 **Edit Message** 原地更新 View

## 2. 初始資源
- 金幣：`100`
- 體力：`100 / 100`
- 飽食度：`100 / 100`（上限固定，無法提升）

## 3. 體力系統
### 3.1 動作消耗（每次 -10 體力）
- 播種
- 收割
- 施肥
- 土地升級
- 穀倉升級

### 3.2 恢復機制（每 10 秒檢測一次）
- 飽食度 > 0：體力 `+5 / 10s`
- 飽食度 = 0：體力 `+1 / 10s`

## 4. 飽食度系統
- 上限固定：`100`
- 消耗條件：當前體力 < 最大體力時，每秒 `-5`
- 體力滿時：飽食度不消耗
- 恢復方式：吃下作物後，飽食度 `+ (作物等級 × 2)`

## 5. 農田系統
- 版面：`5 × 5` 按鈕矩陣（共 25 格）
- 初始狀態：僅中心第 13 格為已解鎖（🟫），其餘為灰地（⬛）

### 5.1 土地按鈕交互
| 狀態 | 點擊選單 |
|---|---|
| 未解鎖灰地 ⬛ | `解鎖（消耗 🧾 ×1）` |
| 已解鎖空地 🟫 | `種植`、`施肥`、`升級` |
| 種植中（未成熟） | `澆水（縮短 10% 生長時間）`、`進一步資訊` |
| 種植中（已成熟） | `澆水`、`收割`、`進一步資訊` |

> 「進一步資訊」需於訊息下方顯示 Embed，內容至少包含：養分、剩餘生長時間。

### 5.2 土地養分
- 養分上限：`土地等級 × 30`
- 施肥一次：`+20 養分`（消耗 `💩 ×1`，體力 `-10`）
- 收割消耗養分：`作物等級 × 10`
- 收割後剩餘養分保留於該地塊
- 養分不足時收割：作物枯萎消失，且 `100%` 掉落 `💩 ×1`

### 5.3 土地升級
- 消耗：`40 金幣 +（當前土地等級 × 5）💩`
- 效果：養分上限 `+30`

## 6. 穀倉系統
- 版面：`2 × 5` 按鈕矩陣（共 10 格）
- 初始解鎖：`4` 格
- 儲存限制：每格僅存單一種類作物
- 可儲存種類數：= 已解鎖欄位數
- 每格存放上限：`20 +（欄位等級 × 10）`
- 欄位等級上限：`Lv.4`

### 6.1 穀倉按鈕交互
| 狀態 | 按鈕顯示 | 點擊選單 |
|---|---|---|
| 未解鎖 | ⬛ | `解鎖欄位（消耗 👜 + 40 金幣）` |
| 已解鎖（空） | 🟫（無 emoji） | `升級欄位` |
| 已解鎖（有作物） | 作物 emoji | `吃掉`、`全部賣出（顯示價格與增減%）`、`升級欄位` |

### 6.2 欄位升級
- 消耗：`40 金幣 +（當前欄位等級 × 5）👜`

## 7. 農田與穀倉共用類別
- `田地（5×5）` 與 `穀倉（2×5）` 使用同一套按鈕格類別
- 差異僅在尺寸與行為策略

## 8. 轉化爐
- 消耗：`20 金幣 / 次`
- 產出：隨機獲得 `Lv.1 ～ Lv.6` 作物一個
- 注意：種籽與作物是同一物件

## 9. 作物系統
- 等級範圍：`Lv.1 ～ Lv.6`
- 每級包含多種不同作物
- 用途：
  1. 種植（消耗體力 `-10`）
  2. 吃食（恢復飽食度 `= 等級 × 2`）
  3. 出售至市場

## 10. 市場經濟
- 基礎售價：`作物等級 × 10` 金幣
- 過剩懲罰（`-10%`）：連續賣出同作物 10 次且未交易其他作物
- 稀缺加成（`+10%`）：長久未賣出時觸發，僅限前 2 次賣出
- 出售需二次確認，並顯示價格與增減百分比

## 11. 熟練度系統
- 等級：`業餘(1) → 學徒(2) → 農夫(3) → 神農(4)`
- 經驗獲取：成功收割 `+1`
- 升級需求：`20 +（作物等級 × 10）` 經驗
- 效果：成品收成量 `= 1 + 當前熟練等級`

## 12. 素材資料庫
| 素材 | Emoji | 掉落機率 | 功能 |
|---|---|---|---|
| 神秘月亮寶石碎片 | 🌚 | 等級 × 1% | 體力上限 +2 |
| 破石法符 | 🧾 | 等級 × 0.5% | 解鎖農田灰地 |
| 肥料 | 💩 | 等級 × 10% | 施肥 +20 養分 / 土地升級素材 |
| 四次元空間拓展 | 👜 | 等級 × 0.2% | 解鎖/升級穀倉欄位素材 |

## 13. 主介面導覽按鈕
- 🛍️ 轉化爐
- 🎒 背包
- 🌾 進入穀倉

---

## 作物資料（預設清單）

```json
[
  {"emoji":"🌾","name":"小麥","level":1,"grow_days":7,"required_nutrients":10},
  {"emoji":"🥕","name":"胡蘿蔔","level":1,"grow_days":10,"required_nutrients":10},
  {"emoji":"🥔","name":"馬鈴薯","level":1,"grow_days":12,"required_nutrients":10},
  {"emoji":"🌽","name":"玉米","level":2,"grow_days":20,"required_nutrients":20},
  {"emoji":"🍅","name":"番茄","level":2,"grow_days":25,"required_nutrients":20},
  {"emoji":"🥦","name":"花椰菜","level":2,"grow_days":14,"required_nutrients":20},
  {"emoji":"🧅","name":"洋蔥","level":1,"grow_days":18,"required_nutrients":10},
  {"emoji":"🧄","name":"大蒜","level":2,"grow_days":30,"required_nutrients":20},
  {"emoji":"🥬","name":"高麗菜","level":1,"grow_days":11,"required_nutrients":10},
  {"emoji":"🌶️","name":"辣椒","level":3,"grow_days":28,"required_nutrients":30},
  {"emoji":"🫑","name":"甜椒","level":2,"grow_days":22,"required_nutrients":20},
  {"emoji":"🍆","name":"茄子","level":2,"grow_days":20,"required_nutrients":20},
  {"emoji":"🥒","name":"黃瓜","level":2,"grow_days":15,"required_nutrients":20},
  {"emoji":"🎃","name":"南瓜","level":3,"grow_days":40,"required_nutrients":30},
  {"emoji":"🍉","name":"西瓜","level":3,"grow_days":45,"required_nutrients":30},
  {"emoji":"🍓","name":"草莓","level":3,"grow_days":30,"required_nutrients":30},
  {"emoji":"🫐","name":"藍莓","level":4,"grow_days":60,"required_nutrients":40},
  {"emoji":"🍇","name":"葡萄","level":4,"grow_days":90,"required_nutrients":40},
  {"emoji":"🍈","name":"哈密瓜","level":4,"grow_days":55,"required_nutrients":40},
  {"emoji":"🌻","name":"向日葵","level":3,"grow_days":35,"required_nutrients":30},
  {"emoji":"🫘","name":"黃豆","level":2,"grow_days":16,"required_nutrients":20},
  {"emoji":"🥝","name":"奇異果","level":4,"grow_days":75,"required_nutrients":40},
  {"emoji":"🍋","name":"檸檬","level":4,"grow_days":120,"required_nutrients":40},
  {"emoji":"🍑","name":"水蜜桃","level":5,"grow_days":100,"required_nutrients":50},
  {"emoji":"🍒","name":"櫻桃","level":5,"grow_days":90,"required_nutrients":50},
  {"emoji":"🥭","name":"芒果","level":5,"grow_days":110,"required_nutrients":50},
  {"emoji":"🍍","name":"鳳梨","level":5,"grow_days":150,"required_nutrients":50},
  {"emoji":"🥥","name":"椰子","level":6,"grow_days":365,"required_nutrients":60},
  {"emoji":"🍄","name":"松露","level":6,"grow_days":180,"required_nutrients":60},
  {"emoji":"🌹","name":"番紅花","level":6,"grow_days":210,"required_nutrients":60}
]
```
