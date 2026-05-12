import asyncio
import json
import os
import random
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands

from game_logic import CropInstance, PlayerState, consume_stamina, mature

# 遊戲內 1 日 = 現實 1 分鐘
DAY_SECONDS = 60
WATER_COOLDOWN_DAYS = 3
WATER_SPEEDUP_DAYS = 1

CROPS = [
    {"emoji": "🥕", "name": "胡蘿蔔", "level": 1, "grow_days": 10, "required_nutrients": 10},
    {"emoji": "🍆", "name": "茄子", "level": 2, "grow_days": 20, "required_nutrients": 20},
    {"emoji": "🍉", "name": "西瓜", "level": 3, "grow_days": 45, "required_nutrients": 30},
]
CROP_MAP = {c["name"]: c for c in CROPS}
GAME: dict[int, PlayerState] = {}
DATA_DIR = "player_data"
UI_VERSION: dict[int, int] = {}


def get_state(uid: int) -> PlayerState:
    if uid not in GAME:
        load_player(uid)
    if uid not in GAME:
        s = PlayerState()
        s.init_default_layout()
        s.gold = 100
        s.scroll = 0
        s.poop = 0
        s.bag_expand = 0
        s.moon_shard = 0
        s.seeds = {}
        s.friends = []
        s.visit_cooldowns = {}
        s.crop_mastery = {}
        GAME[uid] = s
    return GAME[uid]


def next_ui_version(uid: int) -> int:
    UI_VERSION[uid] = UI_VERSION.get(uid, 0) + 1
    return UI_VERSION[uid]


def is_ui_active(uid: int, version: int) -> bool:
    return UI_VERSION.get(uid, 0) == version


def state_to_dict(s: PlayerState) -> dict:
    return {
        "gold": s.gold, "stamina": s.stamina, "stamina_max": s.stamina_max, "fullness": s.fullness,
        "moon_shard": s.moon_shard, "scroll": s.scroll, "poop": s.poop, "bag_expand": s.bag_expand,
        "proficiency_level": s.proficiency_level, "proficiency_exp": s.proficiency_exp, "seeds": s.seeds,
        "friends": s.friends, "visit_cooldowns": s.visit_cooldowns, "player_name": s.player_name,
    }


def save_all_players() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    for uid, s in GAME.items():
        with open(os.path.join(DATA_DIR, f"{uid}.json"), "w", encoding="utf-8") as f:
            json.dump(state_to_dict(s), f, ensure_ascii=False, indent=2)


def load_player(uid: int) -> None:
    path = os.path.join(DATA_DIR, f"{uid}.json")
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    s = PlayerState()
    s.init_default_layout()
    for k, v in d.items():
        setattr(s, k, v)
    GAME[uid] = s


def crop_emoji(cell) -> str:
    if not cell.unlocked:
        return "⬛"
    if cell.crop is None:
        return "🟫"
    crop = CROP_MAP[cell.crop.crop_name]
    return crop["emoji"]


def render_status(s: PlayerState) -> str:
    seed_text = "、".join(f"{CROP_MAP[n]['emoji']}{n}x{q}" for n, q in s.seeds.items() if q > 0) or "無"
    return f"💰{s.gold} ⚡{s.stamina}/{s.stamina_max} 🍖{s.fullness}/100 | 種籽：{seed_text}"


def market_unit_price(state: PlayerState, crop_name: str, level: int) -> tuple[int, int]:
    pct = 0
    last_name, streak = state.same_crop_sale_streak
    if last_name == crop_name and streak >= 10:
        pct -= 10
    if state.scarcity_bonus_left.get(crop_name, 0) > 0:
        pct += 10
    base = level * 10
    return int(base * (100 + pct) / 100), pct


class FarmMainView(discord.ui.View):
    def __init__(self, uid: int, version: int):
        super().__init__(timeout=120)
        self.uid = uid
        self.version = version
        s = get_state(uid)
        for idx, cell in enumerate(s.farm):
            style = discord.ButtonStyle.success if (cell.crop and mature(cell.crop)) else discord.ButtonStyle.secondary
            btn = discord.ui.Button(label=crop_emoji(cell), row=idx // 5, style=style)

            async def cb(interaction: discord.Interaction, x=idx):
                if not is_ui_active(uid, self.version):
                    await interaction.response.send_message("此 UI 已被新畫面取代。", ephemeral=True)
                    return
                await interaction.response.edit_message(
                    content=f"{render_status(get_state(uid))}\n地塊 #{x+1} 操作",
                    view=CellMenuView(uid, x, self.version),
                    embed=None,
                )

            btn.callback = cb
            self.add_item(btn)

class CellActionSelect(discord.ui.Select):
    def __init__(self, uid: int, idx: int, version: int):
        self.uid, self.idx = uid, idx
        self.version = version
        s = get_state(uid)
        cell = s.farm[idx]
        options: list[discord.SelectOption] = []

        if not cell.unlocked:
            if s.scroll >= 1:
                options.append(discord.SelectOption(label="解鎖(🧾x1)", value="unlock"))
            options.append(discord.SelectOption(label="返回農地←", value="back"))
        elif cell.crop is None:
            for name, qty in s.seeds.items():
                if qty <= 0:
                    continue
                crop = CROP_MAP[name]
                options.append(discord.SelectOption(label=f"種植{name}{crop['emoji']}(養分{crop['required_nutrients']})", value=f"plant:{name}"))
            if s.stamina >= 10 and s.gold >= 40 and s.poop >= cell.level * 5:
                options.append(discord.SelectOption(label=f"升級(40金+💩{cell.level*5})", value="upgrade"))
            options.append(discord.SelectOption(label="返回農地←", value="back"))
        else:
            options.append(discord.SelectOption(label="澆水(+10%生長速度1日)", value="water"))
            options.append(discord.SelectOption(label="直接吃掉(10%飽食恢復)", value="eat_crop"))
            if mature(cell.crop) and s.stamina >= 10:
                options.append(discord.SelectOption(label="收割", value="harvest"))
            options.append(discord.SelectOption(label="更多資訊", value="info"))
            options.append(discord.SelectOption(label="返回農地←", value="back"))

        super().__init__(placeholder=f"地塊 #{idx+1} 選單", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if not is_ui_active(self.uid, self.version):
            await interaction.response.send_message("此 UI 已被新畫面取代。", ephemeral=True)
            return
        s = get_state(self.uid)
        cell = s.farm[self.idx]
        action = self.values[0]

        if action == "back":
            await interaction.response.edit_message(content=render_status(s), view=FarmMainView(self.uid, self.version), embed=None)
            return
        if action == "unlock":
            s.scroll -= 1
            cell.unlocked = True
            await interaction.response.edit_message(content=f"{render_status(s)}\n地塊已解鎖", view=FarmMainView(self.uid, self.version), embed=None)
            return
        if action.startswith("plant:"):
            crop_name = action.split(":", 1)[1]
            if cell.crop is not None or s.seeds.get(crop_name, 0) <= 0 or not consume_stamina(s, 10):
                await interaction.response.edit_message(content=f"{render_status(s)}\n無法種植", view=CellMenuView(self.uid, self.idx, self.version), embed=None)
                return
            crop = CROP_MAP[crop_name]
            now = datetime.now(timezone.utc)
            cell.crop = CropInstance(crop_name, now, now + timedelta(seconds=crop["grow_days"] * DAY_SECONDS))
            s.seeds[crop_name] -= 1
            await interaction.response.edit_message(content=f"{render_status(s)}\n已種植 {crop['emoji']}{crop_name}", view=FarmMainView(self.uid, self.version), embed=None)
            return
        if action == "upgrade":
            if not consume_stamina(s, 10):
                await interaction.response.send_message("體力不足", ephemeral=True)
                return
            s.gold -= 40
            s.poop -= cell.level * 5
            cell.level += 1
            await interaction.response.edit_message(content=f"{render_status(s)}\n地塊升級 Lv.{cell.level}", view=CellMenuView(self.uid, self.idx, self.version), embed=None)
            return
        if action == "water":
            now = datetime.now(timezone.utc)
            cooldown_until = getattr(cell, "water_cooldown_until", None)
            if cooldown_until and now < cooldown_until:
                left = int((cooldown_until - now).total_seconds() / DAY_SECONDS)
                await interaction.response.edit_message(content=f"澆水冷卻中，剩餘 {left} 日", view=CellMenuView(self.uid, self.idx, self.version), embed=None)
                return
            speed = timedelta(seconds=WATER_SPEEDUP_DAYS * DAY_SECONDS)
            if cell.crop and cell.crop.grow_until > now:
                cell.crop.grow_until = max(now, cell.crop.grow_until - speed)
            cell.water_cooldown_until = now + timedelta(seconds=WATER_COOLDOWN_DAYS * DAY_SECONDS)
            await interaction.response.edit_message(content=f"澆水完成，冷卻 {WATER_COOLDOWN_DAYS} 日", view=CellMenuView(self.uid, self.idx, self.version), embed=None)
            return
        if action == "eat_crop":
            crop = CROP_MAP[cell.crop.crop_name]
            s.fullness = min(100, s.fullness + max(1, int(crop["level"] * 2 * 0.1)))
            cell.crop = None
            await interaction.response.edit_message(content=f"{render_status(s)}\n已直接吃掉作物", view=FarmMainView(self.uid, self.version), embed=None)
            return
        if action == "harvest":
            if not cell.crop or not mature(cell.crop) or not consume_stamina(s, 10):
                await interaction.response.edit_message(content=f"{render_status(s)}\n目前無法收割", view=CellMenuView(self.uid, self.idx, self.version), embed=None)
                return
            crop = CROP_MAP[cell.crop.crop_name]
            mastery = s.crop_mastery.setdefault(crop["name"], {"level": 1, "exp": 0})
            prof_level = max(1, min(4, mastery["level"]))
            harvest_qty = 1 + prof_level
            if cell.nutrients < crop["required_nutrients"]:
                cell.crop = None
                s.poop += 1
                await interaction.response.edit_message(content=f"{render_status(s)}\n養分不足枯萎，獲得💩x1", view=FarmMainView(self.uid, self.version), embed=None)
                return
            cell.nutrients -= crop["required_nutrients"]
            # 收成先進穀倉；若無法存放才直接換金
            stored = False
            remaining_qty = harvest_qty
            for slot in s.barn:
                cap = 20 + slot.level * 10
                if slot.unlocked and slot.crop_name == crop["name"] and slot.amount < cap and remaining_qty > 0:
                    can_add = min(remaining_qty, cap - slot.amount)
                    slot.amount += can_add
                    remaining_qty -= can_add
                    stored = True
            if not stored:
                for slot in s.barn:
                    if slot.unlocked and slot.crop_name is None and remaining_qty > 0:
                        slot.crop_name = crop["name"]
                        cap = 20 + slot.level * 10
                        slot.amount = min(remaining_qty, cap)
                        remaining_qty -= slot.amount
                        stored = True
            if remaining_qty > 0:
                s.gold += crop["level"] * 10 * remaining_qty
            mastery["exp"] += 1
            need = 20 + crop["level"] * 10
            if mastery["level"] < 4 and mastery["exp"] >= need:
                mastery["exp"] = 0
                mastery["level"] += 1
            cell.crop = None
            result = "已存入穀倉" if remaining_qty == 0 else f"部分換金 x{remaining_qty}"
            await interaction.response.edit_message(content=f"{render_status(s)}\n收割 {crop['emoji']}{crop['name']} x{harvest_qty}（{result}）", view=FarmMainView(self.uid, self.version), embed=None)
            return
        if action == "info":
            crop = CROP_MAP[cell.crop.crop_name]
            rem = max(0, int((cell.crop.grow_until - datetime.now(timezone.utc)).total_seconds() / DAY_SECONDS))
            e = discord.Embed(title=f"地塊 #{self.idx+1}")
            e.add_field(name="作物", value=f"{crop['emoji']}{crop['name']} Lv.{crop['level']}")
            e.add_field(name="養分需求", value=str(crop["required_nutrients"]))
            e.add_field(name="剩餘天數", value=str(rem))
            await interaction.response.edit_message(content=render_status(s), view=CellMenuView(self.uid, self.idx, self.version), embed=e)


class CellMenuView(discord.ui.View):
    def __init__(self, uid: int, idx: int, version: int):
        super().__init__(timeout=90)
        self.add_item(CellActionSelect(uid, idx, version))


class BarnMainView(discord.ui.View):
    def __init__(self, uid: int, origin: str = "farmui"):
        super().__init__(timeout=120)
        self.uid = uid
        self.origin = origin
        s = get_state(uid)
        for idx, slot in enumerate(s.barn):
            label = "⬛" if not slot.unlocked else ("🟫" if not slot.crop_name else CROP_MAP.get(slot.crop_name, {"emoji": "🟫"})["emoji"])
            btn = discord.ui.Button(label=label, row=idx // 5, style=discord.ButtonStyle.secondary)

            async def cb(interaction: discord.Interaction, x=idx):
                slot_data = get_state(self.uid).barn[x]
                cap = 20 + slot_data.level * 10
                used = slot_data.amount
                await interaction.response.edit_message(
                    content=f"穀倉欄位 #{x+1} 操作（容量 {used}/{cap}，Lv.{slot_data.level}）",
                    view=BarnSlotMenuView(self.uid, x),
                    embed=None,
                )

            btn.callback = cb
            self.add_item(btn)

    @discord.ui.button(label="返回主選單←", row=2, style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, _):
        s = get_state(self.uid)
        if self.origin == "farm":
            await interaction.response.edit_message(content=render_status(s), view=FarmMainView(self.uid, UI_VERSION.get(self.uid, 0)), embed=None)
        else:
            await interaction.response.edit_message(content=render_status(s), view=FarmUIView(self.uid), embed=None)


class BarnSlotSelect(discord.ui.Select):
    def __init__(self, uid: int, idx: int):
        self.uid, self.idx = uid, idx
        s = get_state(uid)
        slot = s.barn[idx]
        options: list[discord.SelectOption] = []
        if not slot.unlocked:
            if s.gold >= 40 and s.bag_expand >= 1:
                options.append(discord.SelectOption(label="解鎖欄位(40金+👜x1)", value="unlock"))
        else:
            if slot.level < 4 and s.gold >= 40 and s.bag_expand >= slot.level * 5 and s.stamina >= 10:
                options.append(discord.SelectOption(label=f"升級欄位(40金+👜x{slot.level*5})", value="upgrade"))
            if slot.crop_name and slot.amount > 0:
                crop = CROP_MAP[slot.crop_name]
                options.append(discord.SelectOption(label=f"吃掉1個 {crop['emoji']}{slot.crop_name}", value="eat"))
                unit, pct = market_unit_price(s, slot.crop_name, crop["level"])
                options.append(discord.SelectOption(label=f"全部賣出 {crop['emoji']}{slot.crop_name}x{slot.amount}（{pct:+d}%）", value="sell_all"))
        options.append(discord.SelectOption(label="返回穀倉←", value="back"))
        super().__init__(placeholder=f"穀倉欄位 #{idx+1} 選單", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        s = get_state(self.uid)
        slot = s.barn[self.idx]
        action = self.values[0]
        if action == "back":
            await interaction.response.edit_message(content="穀倉 2x5", view=BarnMainView(self.uid), embed=None)
            return
        if action == "unlock":
            s.gold -= 40
            s.bag_expand -= 1
            slot.unlocked = True
            await interaction.response.edit_message(content=f"{render_status(s)}\n穀倉欄位已解鎖", view=BarnMainView(self.uid), embed=None)
            return
        if action == "upgrade":
            cost = slot.level * 5
            if not consume_stamina(s, 10):
                await interaction.response.send_message("體力不足", ephemeral=True)
                return
            s.gold -= 40
            s.bag_expand -= cost
            slot.level += 1
            await interaction.response.edit_message(content=f"{render_status(s)}\n欄位升級至 Lv.{slot.level}", view=BarnSlotMenuView(self.uid, self.idx), embed=None)
            return
        if action == "eat":
            crop = CROP_MAP[slot.crop_name]
            slot.amount -= 1
            s.fullness = min(100, s.fullness + crop["level"] * 2)
            if slot.amount == 0:
                slot.crop_name = None
            await interaction.response.edit_message(content=f"{render_status(s)}\n已吃掉1個作物", view=BarnSlotMenuView(self.uid, self.idx), embed=None)
            return
        if action == "sell_all":
            crop = CROP_MAP[slot.crop_name]
            unit, pct = market_unit_price(s, slot.crop_name, crop["level"])
            total = unit * slot.amount
            await interaction.response.edit_message(
                content=f"確認賣出 {crop['emoji']}{slot.crop_name} x{slot.amount}\n單價：{unit}（{pct:+d}%） 總價：{total}",
                view=SellConfirmView(self.uid, self.idx, unit, pct),
                embed=None,
            )


class BarnSlotMenuView(discord.ui.View):
    def __init__(self, uid: int, idx: int):
        super().__init__(timeout=90)
        self.add_item(BarnSlotSelect(uid, idx))


class SellConfirmView(discord.ui.View):
    def __init__(self, uid: int, idx: int, unit_price: int, pct: int):
        super().__init__(timeout=60)
        self.uid = uid
        self.idx = idx
        self.unit_price = unit_price
        self.pct = pct

    @discord.ui.button(label="確認賣出", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _):
        s = get_state(self.uid)
        slot = s.barn[self.idx]
        if not slot.crop_name or slot.amount <= 0:
            await interaction.response.edit_message(content="作物已不存在，請重試。", view=BarnMainView(self.uid), embed=None)
            return
        crop_name = slot.crop_name
        qty = slot.amount
        total = self.unit_price * qty
        s.gold += total
        # 市場過剩/稀缺狀態更新
        last_name, streak = s.same_crop_sale_streak
        if last_name == crop_name:
            s.same_crop_sale_streak = (crop_name, streak + qty)
        else:
            s.same_crop_sale_streak = (crop_name, qty)
        if s.scarcity_bonus_left.get(crop_name, 0) > 0:
            s.scarcity_bonus_left[crop_name] -= 1
        s.last_sold_tick[crop_name] = s.ticks
        slot.crop_name = None
        slot.amount = 0
        await interaction.response.edit_message(
            content=f"{render_status(s)}\n賣出完成：{total} 金幣（單價 {self.unit_price} / {self.pct:+d}%）",
            view=BarnMainView(self.uid),
            embed=None,
        )

    @discord.ui.button(label="取消", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(content="已取消賣出。", view=BarnMainView(self.uid), embed=None)


class Bot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        asyncio.create_task(self.tick())

    async def tick(self):
        while not self.is_closed():
            for s in GAME.values():
                s.ticks += 1
                if s.stamina < s.stamina_max:
                    s.stamina = min(s.stamina_max, s.stamina + (5 if s.fullness > 0 else 1))
                if s.stamina < s.stamina_max and s.fullness > 0:
                    s.fullness = max(0, s.fullness - 5)
                for c in CROPS:
                    name = c["name"]
                    last = s.last_sold_tick.get(name, -999999)
                    if s.ticks - last >= 60 and s.scarcity_bonus_left.get(name, 0) == 0:
                        s.scarcity_bonus_left[name] = 2
            save_all_players()
            await asyncio.sleep(10)


bot = Bot()


@bot.tree.command(name="farm", description="顯示完整農場 UI")
async def farm(interaction: discord.Interaction):
    s = get_state(interaction.user.id)
    s.player_name = interaction.user.name
    version = next_ui_version(interaction.user.id)
    await interaction.response.send_message(f"{render_status(s)}\n（農地指令）", view=FarmMainView(interaction.user.id, version), ephemeral=True)


class FarmUIView(discord.ui.View):
    def __init__(self, uid: int):
        super().__init__(timeout=120)
        self.uid = uid

    @discord.ui.button(label="🛍️ 轉化爐(20金)", style=discord.ButtonStyle.primary)
    async def furnace(self, interaction: discord.Interaction, _):
        s = get_state(self.uid)
        if s.gold < 20:
            await interaction.response.edit_message(content=f"{render_status(s)}\n金幣不足 20。", view=FarmUIView(self.uid))
            return
        s.gold -= 20
        c = random.choice(CROPS)
        s.seeds[c["name"]] = s.seeds.get(c["name"], 0) + 1
        await interaction.response.edit_message(content=f"{render_status(s)}\n轉化爐獲得 {c['emoji']}{c['name']} 種籽 x1", view=FarmUIView(self.uid))

    @discord.ui.button(label="🎒 背包", style=discord.ButtonStyle.secondary)
    async def bag(self, interaction: discord.Interaction, _):
        s = get_state(self.uid)
        await interaction.response.edit_message(content=render_status(s), view=FarmUIView(self.uid))

    @discord.ui.button(label="🌾 穀倉", style=discord.ButtonStyle.success)
    async def barn(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(content="穀倉 2x5", view=BarnMainView(self.uid, origin="farmui"))

    @discord.ui.button(label="👥 好友", style=discord.ButtonStyle.primary)
    async def friends(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(content="好友選單", view=FriendsView(self.uid))

    @discord.ui.button(label="📖 農夫寶典", style=discord.ButtonStyle.secondary)
    async def codex(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(content="農夫寶典", view=FarmerCodexView(self.uid))


class FarmerCodexSelect(discord.ui.Select):
    def __init__(self, uid: int):
        self.uid = uid
        s = get_state(uid)
        options = []
        rank = {1: "業餘", 2: "學徒", 3: "農夫", 4: "神農"}
        for name, m in s.crop_mastery.items():
            options.append(
                discord.SelectOption(
                    label=f"{name}｜{rank.get(m['level'],'業餘')}({m['level']})",
                    value=name,
                    description=f"增益：收成量 = 1 + {m['level']}",
                )
            )
        if not options:
            options.append(discord.SelectOption(label="尚無熟練度資料", value="none"))
        options.append(discord.SelectOption(label="返回←", value="back"))
        super().__init__(placeholder="查看作物熟練度", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        s = get_state(self.uid)
        v = self.values[0]
        if v == "back":
            await interaction.response.edit_message(content=render_status(s), view=FarmUIView(self.uid))
            return
        if v == "none":
            await interaction.response.edit_message(content="尚未收割任何作物。", view=FarmerCodexView(self.uid))
            return
        m = s.crop_mastery[v]
        level_name = {1: "業餘", 2: "學徒", 3: "農夫", 4: "神農"}.get(m["level"], "業餘")
        e = discord.Embed(title=f"農夫寶典｜{v} 熟練度")
        e.add_field(name="熟練等級", value=f"{level_name}({m['level']})", inline=False)
        e.add_field(name="經驗獲取", value="成功收割 +1", inline=False)
        e.add_field(name="升級需求", value="20 + (作物等級 × 10)", inline=False)
        e.add_field(name="當前經驗", value=str(m["exp"]), inline=False)
        e.add_field(name="當前增益", value=f"成品收成量 = 1 + {m['level']}", inline=False)
        await interaction.response.edit_message(content="農夫寶典", embed=e, view=FarmerCodexView(self.uid))


class FarmerCodexView(discord.ui.View):
    def __init__(self, uid: int):
        super().__init__(timeout=120)
        self.add_item(FarmerCodexSelect(uid))


class FriendsSelect(discord.ui.Select):
    def __init__(self, uid: int):
        self.uid = uid
        s = get_state(uid)
        options = []
        for fid in s.friends:
            fs = get_state(fid)
            name = fs.player_name or f"user-{fid}"
            options.append(discord.SelectOption(label=f"{name} (點擊拜訪對方)", value=f"visit:{fid}"))
        options.append(discord.SelectOption(label="新增好友", value="add"))
        options.append(discord.SelectOption(label="返回←", value="back"))
        super().__init__(placeholder="好友功能", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        s = get_state(self.uid)
        action = self.values[0]
        if action == "back":
            await interaction.response.edit_message(content=render_status(s), view=FarmUIView(self.uid))
            return
        if action == "add":
            await interaction.response.edit_message(content="新增好友", view=AddFriendView(self.uid))
            return
        if action.startswith("visit:"):
            fid = int(action.split(":")[1])
            target = get_state(fid)
            now = datetime.now(timezone.utc)
            key = str(fid)
            cool_until = s.visit_cooldowns.get(key)
            if cool_until and now < datetime.fromisoformat(cool_until):
                await interaction.response.edit_message(content="拜訪冷卻中（30日）", view=FriendsView(self.uid))
                return
            # 拜訪加速 +30% 且不可疊加
            for cell in target.farm:
                if cell.crop and cell.crop.grow_until > now:
                    remaining = cell.crop.grow_until - now
                    cell.crop.grow_until = now + remaining * 0.7
            s.visit_cooldowns[key] = (now + timedelta(seconds=30 * DAY_SECONDS)).isoformat()
            await interaction.response.edit_message(content=f"拜訪 {target.player_name} 的農地", view=VisitFarmView(self.uid, fid))


class FriendsView(discord.ui.View):
    def __init__(self, uid: int):
        super().__init__(timeout=120)
        self.add_item(FriendsSelect(uid))


class AddFriendSelect(discord.ui.Select):
    def __init__(self, uid: int):
        self.uid = uid
        s = get_state(uid)
        options = []
        for pid in list(GAME.keys()):
            if pid == uid or pid in s.friends:
                continue
            ps = get_state(pid)
            options.append(discord.SelectOption(label=ps.player_name or f"user-{pid}", value=str(pid)))
        if not options:
            options = [discord.SelectOption(label="目前無可新增玩家", value="none")]
        options.append(discord.SelectOption(label="返回←", value="back"))
        super().__init__(placeholder="選擇要新增的好友", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        s = get_state(self.uid)
        v = self.values[0]
        if v == "back":
            await interaction.response.edit_message(content="好友選單", view=FriendsView(self.uid))
            return
        if v == "none":
            await interaction.response.edit_message(content="目前無可新增玩家", view=AddFriendView(self.uid))
            return
        pid = int(v)
        if pid not in s.friends:
            s.friends.append(pid)
        await interaction.response.edit_message(content="新增好友完成", view=FriendsView(self.uid))


class AddFriendView(discord.ui.View):
    def __init__(self, uid: int):
        super().__init__(timeout=120)
        self.add_item(AddFriendSelect(uid))


class VisitCellSelect(discord.ui.Select):
    def __init__(self, visitor_id: int, owner_id: int, idx: int):
        self.visitor_id, self.owner_id, self.idx = visitor_id, owner_id, idx
        super().__init__(
            placeholder=f"拜訪地塊 #{idx+1}",
            options=[
                discord.SelectOption(label="查看基本資訊", value="info"),
                discord.SelectOption(label="返回←", value="back"),
            ],
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        owner = get_state(self.owner_id)
        cell = owner.farm[self.idx]
        if self.values[0] == "back":
            await interaction.response.edit_message(content=f"拜訪 {owner.player_name} 的農地", view=VisitFarmView(self.visitor_id, self.owner_id))
            return
        e = discord.Embed(title=f"拜訪資訊 地塊#{self.idx+1}")
        e.add_field(name="等級", value=str(cell.level))
        e.add_field(name="養分", value=f"{cell.nutrients}/{cell.level*30}")
        await interaction.response.edit_message(content=f"拜訪 {owner.player_name}", embed=e, view=VisitCellView(self.visitor_id, self.owner_id, self.idx))


class VisitCellView(discord.ui.View):
    def __init__(self, visitor_id: int, owner_id: int, idx: int):
        super().__init__(timeout=90)
        self.add_item(VisitCellSelect(visitor_id, owner_id, idx))


class VisitFarmView(discord.ui.View):
    def __init__(self, visitor_id: int, owner_id: int):
        super().__init__(timeout=120)
        self.visitor_id = visitor_id
        owner = get_state(owner_id)
        for idx, cell in enumerate(owner.farm):
            style = discord.ButtonStyle.success if (cell.crop and mature(cell.crop)) else discord.ButtonStyle.secondary
            btn = discord.ui.Button(label=crop_emoji(cell), row=idx // 5, style=style)
            async def cb(interaction: discord.Interaction, x=idx):
                await interaction.response.edit_message(content=f"拜訪地塊 #{x+1}", view=VisitCellView(visitor_id, owner_id, x))
            btn.callback = cb
            self.add_item(btn)


@bot.tree.command(name="farmui", description="顯示背包/轉化爐/穀倉 UI")
async def farmui(interaction: discord.Interaction):
    s = get_state(interaction.user.id)
    s.player_name = interaction.user.name
    next_ui_version(interaction.user.id)
    await interaction.response.send_message(f"{render_status(s)}\n（功能指令）", view=FarmUIView(interaction.user.id), ephemeral=True)


if __name__ == "__main__":
    import os

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("請設定 DISCORD_TOKEN")
    bot.run(token)
