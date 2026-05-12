import asyncio
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


def get_state(uid: int) -> PlayerState:
    if uid not in GAME:
        s = PlayerState()
        s.init_default_layout()
        s.gold = 100
        s.scroll = 0
        s.poop = 0
        s.bag_expand = 0
        s.moon_shard = 0
        s.seeds = {}
        GAME[uid] = s
    return GAME[uid]


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


class FarmMainView(discord.ui.View):
    def __init__(self, uid: int):
        super().__init__(timeout=120)
        self.uid = uid
        s = get_state(uid)
        for idx, cell in enumerate(s.farm):
            style = discord.ButtonStyle.success if (cell.crop and mature(cell.crop)) else discord.ButtonStyle.secondary
            btn = discord.ui.Button(label=crop_emoji(cell), row=idx // 5, style=style)

            async def cb(interaction: discord.Interaction, x=idx):
                await interaction.response.edit_message(
                    content=f"{render_status(get_state(uid))}\n地塊 #{x+1} 操作",
                    view=CellMenuView(uid, x),
                    embed=None,
                )

            btn.callback = cb
            self.add_item(btn)

class CellActionSelect(discord.ui.Select):
    def __init__(self, uid: int, idx: int):
        self.uid, self.idx = uid, idx
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
        s = get_state(self.uid)
        cell = s.farm[self.idx]
        action = self.values[0]

        if action == "back":
            await interaction.response.edit_message(content=render_status(s), view=FarmMainView(self.uid), embed=None)
            return
        if action == "unlock":
            s.scroll -= 1
            cell.unlocked = True
            await interaction.response.edit_message(content=f"{render_status(s)}\n地塊已解鎖", view=FarmMainView(self.uid), embed=None)
            return
        if action.startswith("plant:"):
            crop_name = action.split(":", 1)[1]
            if cell.crop is not None or s.seeds.get(crop_name, 0) <= 0 or not consume_stamina(s, 10):
                await interaction.response.edit_message(content=f"{render_status(s)}\n無法種植", view=CellMenuView(self.uid, self.idx), embed=None)
                return
            crop = CROP_MAP[crop_name]
            now = datetime.now(timezone.utc)
            cell.crop = CropInstance(crop_name, now, now + timedelta(seconds=crop["grow_days"] * DAY_SECONDS))
            s.seeds[crop_name] -= 1
            await interaction.response.edit_message(content=f"{render_status(s)}\n已種植 {crop['emoji']}{crop_name}", view=FarmMainView(self.uid), embed=None)
            return
        if action == "upgrade":
            if not consume_stamina(s, 10):
                await interaction.response.send_message("體力不足", ephemeral=True)
                return
            s.gold -= 40
            s.poop -= cell.level * 5
            cell.level += 1
            await interaction.response.edit_message(content=f"{render_status(s)}\n地塊升級 Lv.{cell.level}", view=CellMenuView(self.uid, self.idx), embed=None)
            return
        if action == "water":
            now = datetime.now(timezone.utc)
            cooldown_until = getattr(cell, "water_cooldown_until", None)
            if cooldown_until and now < cooldown_until:
                left = int((cooldown_until - now).total_seconds() / DAY_SECONDS)
                await interaction.response.edit_message(content=f"澆水冷卻中，剩餘 {left} 日", view=CellMenuView(self.uid, self.idx), embed=None)
                return
            speed = timedelta(seconds=WATER_SPEEDUP_DAYS * DAY_SECONDS)
            if cell.crop and cell.crop.grow_until > now:
                cell.crop.grow_until = max(now, cell.crop.grow_until - speed)
            cell.water_cooldown_until = now + timedelta(seconds=WATER_COOLDOWN_DAYS * DAY_SECONDS)
            await interaction.response.edit_message(content=f"澆水完成，冷卻 {WATER_COOLDOWN_DAYS} 日", view=CellMenuView(self.uid, self.idx), embed=None)
            return
        if action == "eat_crop":
            crop = CROP_MAP[cell.crop.crop_name]
            s.fullness = min(100, s.fullness + max(1, int(crop["level"] * 2 * 0.1)))
            cell.crop = None
            await interaction.response.edit_message(content=f"{render_status(s)}\n已直接吃掉作物", view=FarmMainView(self.uid), embed=None)
            return
        if action == "harvest":
            if not cell.crop or not mature(cell.crop) or not consume_stamina(s, 10):
                await interaction.response.edit_message(content=f"{render_status(s)}\n目前無法收割", view=CellMenuView(self.uid, self.idx), embed=None)
                return
            crop = CROP_MAP[cell.crop.crop_name]
            if cell.nutrients < crop["required_nutrients"]:
                cell.crop = None
                s.poop += 1
                await interaction.response.edit_message(content=f"{render_status(s)}\n養分不足枯萎，獲得💩x1", view=FarmMainView(self.uid), embed=None)
                return
            cell.nutrients -= crop["required_nutrients"]
            s.gold += crop["level"] * 10
            cell.crop = None
            await interaction.response.edit_message(content=f"{render_status(s)}\n收割 {crop['emoji']}{crop['name']} 完成", view=FarmMainView(self.uid), embed=None)
            return
        if action == "info":
            crop = CROP_MAP[cell.crop.crop_name]
            rem = max(0, int((cell.crop.grow_until - datetime.now(timezone.utc)).total_seconds() / DAY_SECONDS))
            e = discord.Embed(title=f"地塊 #{self.idx+1}")
            e.add_field(name="作物", value=f"{crop['emoji']}{crop['name']} Lv.{crop['level']}")
            e.add_field(name="養分需求", value=str(crop["required_nutrients"]))
            e.add_field(name="剩餘天數", value=str(rem))
            await interaction.response.edit_message(content=render_status(s), view=CellMenuView(self.uid, self.idx), embed=e)


class CellMenuView(discord.ui.View):
    def __init__(self, uid: int, idx: int):
        super().__init__(timeout=90)
        self.add_item(CellActionSelect(uid, idx))


class BarnMainView(discord.ui.View):
    def __init__(self, uid: int):
        super().__init__(timeout=120)
        self.uid = uid
        s = get_state(uid)
        for idx, slot in enumerate(s.barn):
            label = "⬛" if not slot.unlocked else "🟫"
            self.add_item(discord.ui.Button(label=label, row=idx // 5, style=discord.ButtonStyle.secondary, disabled=True))

    @discord.ui.button(label="返回主選單←", row=2, style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, _):
        s = get_state(self.uid)
        await interaction.response.edit_message(content=render_status(s), view=FarmMainView(self.uid), embed=None)


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
                if s.stamina < s.stamina_max:
                    s.stamina = min(s.stamina_max, s.stamina + (5 if s.fullness > 0 else 1))
                if s.stamina < s.stamina_max and s.fullness > 0:
                    s.fullness = max(0, s.fullness - 5)
            await asyncio.sleep(10)


bot = Bot()


@bot.tree.command(name="farm", description="顯示完整農場 UI")
async def farm(interaction: discord.Interaction):
    s = get_state(interaction.user.id)
    await interaction.response.send_message(f"{render_status(s)}\n（農地指令）", view=FarmMainView(interaction.user.id), ephemeral=True)


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
        await interaction.response.edit_message(content="穀倉 2x5", view=BarnMainView(self.uid))


@bot.tree.command(name="farmui", description="顯示背包/轉化爐/穀倉 UI")
async def farmui(interaction: discord.Interaction):
    s = get_state(interaction.user.id)
    await interaction.response.send_message(f"{render_status(s)}\n（功能指令）", view=FarmUIView(interaction.user.id), ephemeral=True)


if __name__ == "__main__":
    import os

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("請設定 DISCORD_TOKEN")
    bot.run(token)
