import asyncio
import random
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands

from game_logic import CropInstance, PlayerState, consume_stamina, mature

CROPS = [
    {"emoji": "🌾", "name": "小麥", "level": 1, "grow_days": 7},
    {"emoji": "🥕", "name": "胡蘿蔔", "level": 1, "grow_days": 10},
    {"emoji": "🥔", "name": "馬鈴薯", "level": 1, "grow_days": 12},
    {"emoji": "🌽", "name": "玉米", "level": 2, "grow_days": 20},
    {"emoji": "🍅", "name": "番茄", "level": 2, "grow_days": 25},
]
CROP_MAP = {c["name"]: c for c in CROPS}
GAME: dict[int, PlayerState] = {}


def get_state(uid: int) -> PlayerState:
    if uid not in GAME:
        s = PlayerState()
        s.init_default_layout()
        # 修正初始物品：僅保留 100 金幣，材料皆為 0
        s.gold = 100
        s.scroll = 0
        s.poop = 0
        s.bag_expand = 0
        s.moon_shard = 0
        GAME[uid] = s
    return GAME[uid]


def crop_emoji(cell) -> str:
    if not cell.unlocked:
        return "⬛"
    if cell.crop is None:
        return "🟫"
    crop = CROP_MAP[cell.crop.crop_name]
    return f"{crop['emoji']}✅" if mature(cell.crop) else f"{crop['emoji']}🌱"


class FarmActionSelect(discord.ui.Select):
    def __init__(self, uid: int, idx: int):
        self.uid = uid
        self.idx = idx
        s = get_state(uid)
        cell = s.farm[idx]
        options: list[discord.SelectOption] = []

        if not cell.unlocked:
            if s.scroll >= 1:
                options.append(discord.SelectOption(label="解鎖（消耗 🧾×1）", value="unlock"))
        else:
            if cell.crop is None:
                if s.stamina >= 10:
                    options.append(discord.SelectOption(label="種植", value="plant"))
                if s.stamina >= 10 and s.poop >= 1:
                    options.append(discord.SelectOption(label="施肥", value="fertilize"))
                if s.stamina >= 10 and s.gold >= 40 and s.poop >= cell.level * 5:
                    options.append(discord.SelectOption(label="升級", value="upgrade"))
            else:
                options.append(discord.SelectOption(label="進一步資訊", value="info"))
                options.append(discord.SelectOption(label="澆水（-10%）", value="water"))
                if mature(cell.crop) and s.stamina >= 10:
                    options.append(discord.SelectOption(label="收割", value="harvest"))

        if not options:
            options = [discord.SelectOption(label="目前無可執行操作", value="noop")]

        super().__init__(placeholder=f"地塊 #{idx+1} 可執行操作", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        s = get_state(self.uid)
        cell = s.farm[self.idx]
        action = self.values[0]

        if action == "noop":
            await interaction.response.edit_message(content="目前條件不足，無可執行操作。", view=FarmView(self.uid))
            return
        if action == "unlock":
            s.scroll -= 1
            cell.unlocked = True
            await interaction.response.edit_message(content=f"解鎖地塊 #{self.idx+1}", view=FarmView(self.uid), embed=None)
            return
        if action == "plant":
            pick = random.choice(CROPS)
            now = datetime.now(timezone.utc)
            cell.crop = CropInstance(pick["name"], now, now + timedelta(seconds=max(10, pick["grow_days"])))
            consume_stamina(s, 10)
            await interaction.response.edit_message(content=f"種下 {pick['emoji']}{pick['name']}", view=FarmView(self.uid), embed=None)
            return
        if action == "fertilize":
            s.poop -= 1
            consume_stamina(s, 10)
            cell.nutrients = min(cell.level * 30, cell.nutrients + 20)
            await interaction.response.edit_message(content=f"施肥完成，養分 {cell.nutrients}/{cell.level*30}", view=FarmView(self.uid), embed=None)
            return
        if action == "upgrade":
            s.gold -= 40
            s.poop -= cell.level * 5
            consume_stamina(s, 10)
            cell.level += 1
            await interaction.response.edit_message(content=f"地塊升級到 Lv.{cell.level}", view=FarmView(self.uid), embed=None)
            return
        if action == "water":
            rem = cell.crop.grow_until - datetime.now(timezone.utc)
            cell.crop.grow_until -= rem * 0.1
            await interaction.response.edit_message(content="澆水成功（-10%）", view=FarmView(self.uid), embed=None)
            return
        if action == "harvest":
            crop = CROP_MAP[cell.crop.crop_name]
            need = crop["level"] * 10
            consume_stamina(s, 10)
            if cell.nutrients < need:
                cell.crop = None
                s.poop += 1
                await interaction.response.edit_message(content="養分不足，作物枯萎並掉落 💩×1", view=FarmView(self.uid), embed=None)
                return
            cell.nutrients -= need
            s.gold += crop["level"] * 10
            cell.crop = None
            await interaction.response.edit_message(content=f"收割 {crop['emoji']}{crop['name']}，已換得金幣", view=FarmView(self.uid), embed=None)
            return
        if action == "info":
            e = discord.Embed(title=f"地塊 #{self.idx+1}")
            e.add_field(name="等級", value=str(cell.level))
            e.add_field(name="養分", value=f"{cell.nutrients}/{cell.level*30}")
            if cell.crop:
                rem = max(0, int((cell.crop.grow_until - datetime.now(timezone.utc)).total_seconds()))
                e.add_field(name="作物", value=cell.crop.crop_name)
                e.add_field(name="剩餘秒數", value=str(rem))
            await interaction.response.edit_message(content="地塊資訊", view=FarmView(self.uid), embed=e)


class CellActionView(discord.ui.View):
    def __init__(self, uid: int, idx: int):
        super().__init__(timeout=90)
        self.add_item(FarmActionSelect(uid, idx))


class FarmView(discord.ui.View):
    def __init__(self, uid: int):
        super().__init__(timeout=120)
        self.uid = uid
        s = get_state(uid)
        for idx, cell in enumerate(s.farm):
            btn = discord.ui.Button(label=crop_emoji(cell), row=idx // 5, style=discord.ButtonStyle.secondary)

            async def cb(interaction: discord.Interaction, x=idx):
                await interaction.response.edit_message(content=f"選擇地塊 #{x+1} 操作", view=CellActionView(uid, x), embed=None)

            btn.callback = cb
            self.add_item(btn)


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


@bot.tree.command(name="farm", description="顯示 5x5 農田")
async def farm(interaction: discord.Interaction):
    s = get_state(interaction.user.id)
    msg = f"💰{s.gold} ⚡{s.stamina}/{s.stamina_max} 🍖{s.fullness}/100 | 點擊地塊後用下拉選單操作"
    await interaction.response.send_message(msg, view=FarmView(interaction.user.id), ephemeral=True)


if __name__ == "__main__":
    import os

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("請設定 DISCORD_TOKEN")
    bot.run(token)
