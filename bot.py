import asyncio
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands

CROPS = [
    {"emoji": "🌾", "name": "小麥", "level": 1, "grow_days": 7},
    {"emoji": "🥕", "name": "胡蘿蔔", "level": 1, "grow_days": 10},
    {"emoji": "🥔", "name": "馬鈴薯", "level": 1, "grow_days": 12},
    {"emoji": "🌽", "name": "玉米", "level": 2, "grow_days": 20},
    {"emoji": "🍅", "name": "番茄", "level": 2, "grow_days": 25},
    {"emoji": "🥦", "name": "花椰菜", "level": 2, "grow_days": 14},
    {"emoji": "🧅", "name": "洋蔥", "level": 1, "grow_days": 18},
    {"emoji": "🧄", "name": "大蒜", "level": 2, "grow_days": 30},
    {"emoji": "🥬", "name": "高麗菜", "level": 1, "grow_days": 11},
    {"emoji": "🌶️", "name": "辣椒", "level": 3, "grow_days": 28},
    {"emoji": "🫑", "name": "甜椒", "level": 2, "grow_days": 22},
    {"emoji": "🍆", "name": "茄子", "level": 2, "grow_days": 20},
    {"emoji": "🥒", "name": "黃瓜", "level": 2, "grow_days": 15},
    {"emoji": "🎃", "name": "南瓜", "level": 3, "grow_days": 40},
    {"emoji": "🍉", "name": "西瓜", "level": 3, "grow_days": 45},
    {"emoji": "🍓", "name": "草莓", "level": 3, "grow_days": 30},
    {"emoji": "🫐", "name": "藍莓", "level": 4, "grow_days": 60},
    {"emoji": "🍇", "name": "葡萄", "level": 4, "grow_days": 90},
    {"emoji": "🍈", "name": "哈密瓜", "level": 4, "grow_days": 55},
    {"emoji": "🌻", "name": "向日葵", "level": 3, "grow_days": 35},
    {"emoji": "🫘", "name": "黃豆", "level": 2, "grow_days": 16},
    {"emoji": "🥝", "name": "奇異果", "level": 4, "grow_days": 75},
    {"emoji": "🍋", "name": "檸檬", "level": 4, "grow_days": 120},
    {"emoji": "🍑", "name": "水蜜桃", "level": 5, "grow_days": 100},
    {"emoji": "🍒", "name": "櫻桃", "level": 5, "grow_days": 90},
    {"emoji": "🥭", "name": "芒果", "level": 5, "grow_days": 110},
    {"emoji": "🍍", "name": "鳳梨", "level": 5, "grow_days": 150},
    {"emoji": "🥥", "name": "椰子", "level": 6, "grow_days": 365},
    {"emoji": "🍄", "name": "松露", "level": 6, "grow_days": 180},
    {"emoji": "🌹", "name": "番紅花", "level": 6, "grow_days": 210},
]
CROP_MAP = {c["name"]: c for c in CROPS}


@dataclass
class CropInstance:
    crop_name: str
    planted_at: datetime
    grow_until: datetime


@dataclass
class FarmCell:
    unlocked: bool = False
    level: int = 1
    nutrients: int = 30
    crop: Optional[CropInstance] = None


@dataclass
class BarnSlot:
    unlocked: bool = False
    level: int = 1
    crop_name: Optional[str] = None
    amount: int = 0

    @property
    def cap(self) -> int:
        return 20 + self.level * 10


@dataclass
class PlayerState:
    gold: int = 100
    stamina: int = 100
    stamina_max: int = 100
    fullness: int = 100
    moon_shard: int = 0
    scroll: int = 2
    poop: int = 5
    bag_expand: int = 1
    proficiency_level: int = 1
    proficiency_exp: int = 0
    same_crop_sale_streak: tuple[str, int] = ("", 0)
    scarcity_bonus_left: dict[str, int] = field(default_factory=dict)
    last_sold_tick: dict[str, int] = field(default_factory=dict)
    ticks: int = 0
    farm: list[FarmCell] = field(default_factory=list)
    barn: list[BarnSlot] = field(default_factory=list)

    def __post_init__(self):
        if not self.farm:
            self.farm = [FarmCell() for _ in range(25)]
            self.farm[12].unlocked = True
        if not self.barn:
            self.barn = [BarnSlot(unlocked=i < 4) for i in range(10)]


GAME: dict[int, PlayerState] = {}


def get_state(uid: int) -> PlayerState:
    if uid not in GAME:
        GAME[uid] = PlayerState()
    return GAME[uid]


def get_crop(name: str) -> dict:
    return CROP_MAP[name]


def mature(ci: CropInstance) -> bool:
    return datetime.now(timezone.utc) >= ci.grow_until


def consume_stamina(state: PlayerState, amount: int = 10) -> bool:
    if state.stamina < amount:
        return False
    state.stamina -= amount
    return True


def add_to_barn(state: PlayerState, crop_name: str, amount: int) -> bool:
    # same crop slot first
    for s in state.barn:
        if s.unlocked and s.crop_name == crop_name and s.amount + amount <= s.cap:
            s.amount += amount
            return True
    # empty slot next
    for s in state.barn:
        if s.unlocked and s.crop_name is None and amount <= s.cap:
            s.crop_name = crop_name
            s.amount = amount
            return True
    return False


def sale_price(state: PlayerState, crop_name: str) -> tuple[int, int]:
    crop = get_crop(crop_name)
    base = crop["level"] * 10
    pct = 0
    name, streak = state.same_crop_sale_streak
    if name == crop_name and streak >= 10:
        pct -= 10
    if state.scarcity_bonus_left.get(crop_name, 0) > 0:
        pct += 10
    return int(base * (100 + pct) / 100), pct


class TopMenu(discord.ui.View):
    def __init__(self, uid: int):
        super().__init__(timeout=120)
        self.uid = uid

    @discord.ui.button(label="🛍️ 轉化爐", style=discord.ButtonStyle.primary)
    async def furnace(self, i: discord.Interaction, b: discord.ui.Button):
        state = get_state(self.uid)
        if state.gold < 20:
            await i.response.send_message("金幣不足 20", ephemeral=True)
            return
        state.gold -= 20
        c = random.choice(CROPS)
        if add_to_barn(state, c["name"], 1):
            await i.response.edit_message(content=f"轉化獲得 {c['emoji']} {c['name']}。", view=TopMenu(self.uid))
        else:
            state.gold += 20
            await i.response.send_message("穀倉空間不足。", ephemeral=True)

    @discord.ui.button(label="🎒 背包", style=discord.ButtonStyle.secondary)
    async def bag(self, i: discord.Interaction, b: discord.ui.Button):
        s = get_state(self.uid)
        msg = f"🌚{s.moon_shard} 🧾{s.scroll} 💩{s.poop} 👜{s.bag_expand}"
        await i.response.edit_message(content=msg, view=TopMenu(self.uid))

    @discord.ui.button(label="🌾 農田", style=discord.ButtonStyle.success)
    async def farm(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.edit_message(content="🌾 農田", view=FarmView(self.uid), embed=None)

    @discord.ui.button(label="🏚️ 穀倉", style=discord.ButtonStyle.success)
    async def barn(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.edit_message(content="🏚️ 穀倉", view=BarnView(self.uid), embed=None)


class FarmView(discord.ui.View):
    def __init__(self, uid: int):
        super().__init__(timeout=120)
        self.uid = uid
        s = get_state(uid)
        for idx, c in enumerate(s.farm):
            if not c.unlocked:
                label = "⬛"
            elif c.crop is None:
                label = "🟫"
            elif mature(c.crop):
                label = f"{get_crop(c.crop.crop_name)['emoji']}✅"
            else:
                label = f"{get_crop(c.crop.crop_name)['emoji']}🌱"
            btn = discord.ui.Button(label=label, row=idx // 5, style=discord.ButtonStyle.secondary)

            async def cb(i: discord.Interaction, x=idx):
                await self.click(i, x)

            btn.callback = cb
            self.add_item(btn)

    async def click(self, i: discord.Interaction, idx: int):
        s = get_state(self.uid)
        c = s.farm[idx]
        if not c.unlocked:
            if s.scroll < 1:
                await i.response.send_message("缺少 🧾", ephemeral=True)
                return
            s.scroll -= 1
            c.unlocked = True
            await i.response.edit_message(content=f"解鎖地塊 {idx+1}", view=FarmView(self.uid))
            return
        await i.response.edit_message(content=f"地塊 {idx+1}", view=FarmCellView(self.uid, idx))


class FarmCellView(discord.ui.View):
    def __init__(self, uid: int, idx: int):
        super().__init__(timeout=120)
        self.uid, self.idx = uid, idx

    @discord.ui.button(label="種植", style=discord.ButtonStyle.success)
    async def plant(self, i: discord.Interaction, b: discord.ui.Button):
        s = get_state(self.uid)
        c = s.farm[self.idx]
        if c.crop is not None:
            await i.response.send_message("已有作物", ephemeral=True)
            return
        if s.stamina < 10:
            await i.response.send_message("體力不足", ephemeral=True)
            return
        pick = random.choice(CROPS)
        now = datetime.now(timezone.utc)
        c.crop = CropInstance(pick["name"], now, now + timedelta(seconds=max(10, pick["grow_days"])))
        s.stamina -= 10
        await i.response.edit_message(content=f"種下 {pick['emoji']}{pick['name']}", view=FarmView(self.uid))

    @discord.ui.button(label="施肥", style=discord.ButtonStyle.primary)
    async def fertilize(self, i: discord.Interaction, b: discord.ui.Button):
        s = get_state(self.uid)
        c = s.farm[self.idx]
        if s.poop < 1 or not consume_stamina(s, 10):
            await i.response.send_message("需要 💩 與體力", ephemeral=True)
            return
        s.poop -= 1
        c.nutrients = min(c.level * 30, c.nutrients + 20)
        await i.response.edit_message(content=f"施肥完成，養分 {c.nutrients}/{c.level*30}", view=FarmCellView(self.uid, self.idx))

    @discord.ui.button(label="升級", style=discord.ButtonStyle.primary)
    async def upgrade(self, i: discord.Interaction, b: discord.ui.Button):
        s = get_state(self.uid)
        c = s.farm[self.idx]
        need_poop = c.level * 5
        if s.gold < 40 or s.poop < need_poop or not consume_stamina(s, 10):
            await i.response.send_message("升級資源不足", ephemeral=True)
            return
        s.gold -= 40
        s.poop -= need_poop
        c.level += 1
        c.nutrients = min(c.nutrients, c.level * 30)
        await i.response.edit_message(content=f"地塊升級至 Lv.{c.level}", view=FarmCellView(self.uid, self.idx))

    @discord.ui.button(label="澆水", style=discord.ButtonStyle.secondary)
    async def water(self, i: discord.Interaction, b: discord.ui.Button):
        c = get_state(self.uid).farm[self.idx]
        if c.crop is None:
            await i.response.send_message("目前無作物", ephemeral=True)
            return
        rem = c.crop.grow_until - datetime.now(timezone.utc)
        c.crop.grow_until -= rem * 0.1
        await i.response.edit_message(content="澆水成功（生長時間 -10%）", view=FarmCellView(self.uid, self.idx))

    @discord.ui.button(label="收割", style=discord.ButtonStyle.success)
    async def harvest(self, i: discord.Interaction, b: discord.ui.Button):
        s = get_state(self.uid)
        c = s.farm[self.idx]
        if c.crop is None or not mature(c.crop):
            await i.response.send_message("尚未成熟", ephemeral=True)
            return
        if not consume_stamina(s, 10):
            await i.response.send_message("體力不足", ephemeral=True)
            return
        crop = get_crop(c.crop.crop_name)
        need = crop["level"] * 10
        if c.nutrients < need:
            c.crop = None
            s.poop += 1
            await i.response.edit_message(content="養分不足枯萎，掉落 💩", view=FarmView(self.uid))
            return
        c.nutrients -= need
        qty = 1 + s.proficiency_level
        if not add_to_barn(s, crop["name"], qty):
            await i.response.send_message("穀倉空間不足", ephemeral=True)
            return
        s.proficiency_exp += 1
        need_exp = 20 + crop["level"] * 10
        if s.proficiency_level < 4 and s.proficiency_exp >= need_exp:
            s.proficiency_level += 1
            s.proficiency_exp = 0
        # drops
        if random.random() < crop["level"] * 0.01:
            s.moon_shard += 1
            s.stamina_max += 2
        if random.random() < crop["level"] * 0.005:
            s.scroll += 1
        if random.random() < crop["level"] * 0.10:
            s.poop += 1
        if random.random() < crop["level"] * 0.002:
            s.bag_expand += 1
        c.crop = None
        await i.response.edit_message(content=f"收割 {crop['emoji']}{crop['name']} x{qty}", view=FarmView(self.uid))

    @discord.ui.button(label="資訊", style=discord.ButtonStyle.secondary)
    async def info(self, i: discord.Interaction, b: discord.ui.Button):
        c = get_state(self.uid).farm[self.idx]
        e = discord.Embed(title=f"地塊 {self.idx+1}")
        e.add_field(name="等級", value=str(c.level))
        e.add_field(name="養分", value=f"{c.nutrients}/{c.level*30}")
        if c.crop:
            left = max(0, int((c.crop.grow_until - datetime.now(timezone.utc)).total_seconds()))
            e.add_field(name="作物", value=c.crop.crop_name)
            e.add_field(name="剩餘秒數", value=str(left))
        await i.response.edit_message(embed=e, view=self)

    @discord.ui.button(label="返回", style=discord.ButtonStyle.danger)
    async def back(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.edit_message(content="🌾 農田", view=FarmView(self.uid), embed=None)


class BarnView(discord.ui.View):
    def __init__(self, uid: int):
        super().__init__(timeout=120)
        self.uid = uid
        s = get_state(uid)
        for idx, slot in enumerate(s.barn):
            label = "⬛" if not slot.unlocked else (get_crop(slot.crop_name)["emoji"] if slot.crop_name else "🟫")
            btn = discord.ui.Button(label=label, row=idx // 5, style=discord.ButtonStyle.secondary)

            async def cb(i: discord.Interaction, x=idx):
                await i.response.edit_message(content=f"穀倉欄位 {x+1}", view=BarnSlotView(self.uid, x))

            btn.callback = cb
            self.add_item(btn)


class BarnSlotView(discord.ui.View):
    def __init__(self, uid: int, idx: int):
        super().__init__(timeout=120)
        self.uid, self.idx = uid, idx

    @discord.ui.button(label="解鎖欄位", style=discord.ButtonStyle.success)
    async def unlock(self, i: discord.Interaction, b: discord.ui.Button):
        s = get_state(self.uid)
        slot = s.barn[self.idx]
        if slot.unlocked:
            await i.response.send_message("已解鎖", ephemeral=True)
            return
        if s.gold < 40 or s.bag_expand < 1:
            await i.response.send_message("需要 40 金幣與 👜", ephemeral=True)
            return
        s.gold -= 40
        s.bag_expand -= 1
        slot.unlocked = True
        await i.response.edit_message(content="欄位已解鎖", view=BarnView(self.uid))

    @discord.ui.button(label="升級欄位", style=discord.ButtonStyle.primary)
    async def upgrade(self, i: discord.Interaction, b: discord.ui.Button):
        s = get_state(self.uid)
        slot = s.barn[self.idx]
        if not slot.unlocked or slot.level >= 4:
            await i.response.send_message("不可升級", ephemeral=True)
            return
        cost = slot.level * 5
        if s.gold < 40 or s.bag_expand < cost or s.stamina < 10:
            await i.response.send_message("升級資源不足", ephemeral=True)
            return
        s.gold -= 40
        s.bag_expand -= cost
        s.stamina -= 10
        slot.level += 1
        await i.response.edit_message(content=f"欄位升級到 Lv.{slot.level}", view=BarnSlotView(self.uid, self.idx))

    @discord.ui.button(label="吃掉", style=discord.ButtonStyle.secondary)
    async def eat(self, i: discord.Interaction, b: discord.ui.Button):
        s = get_state(self.uid)
        slot = s.barn[self.idx]
        if slot.amount < 1 or not slot.crop_name:
            await i.response.send_message("沒有作物", ephemeral=True)
            return
        crop = get_crop(slot.crop_name)
        slot.amount -= 1
        s.fullness = min(100, s.fullness + crop["level"] * 2)
        if slot.amount == 0:
            slot.crop_name = None
        await i.response.edit_message(content=f"吃掉 {crop['emoji']}，飽食度 {s.fullness}/100", view=BarnSlotView(self.uid, self.idx))

    @discord.ui.button(label="全部賣出", style=discord.ButtonStyle.danger)
    async def sell(self, i: discord.Interaction, b: discord.ui.Button):
        s = get_state(self.uid)
        slot = s.barn[self.idx]
        if slot.amount < 1 or not slot.crop_name:
            await i.response.send_message("沒有作物可賣", ephemeral=True)
            return
        unit, pct = sale_price(s, slot.crop_name)
        total = unit * slot.amount
        await i.response.edit_message(
            content=f"確認賣出 {slot.crop_name} x{slot.amount}，單價 {unit}，總價 {total}（{pct:+d}%）？",
            view=SellConfirmView(self.uid, self.idx),
        )

    @discord.ui.button(label="返回", style=discord.ButtonStyle.secondary)
    async def back(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.edit_message(content="🏚️ 穀倉", view=BarnView(self.uid))


class SellConfirmView(discord.ui.View):
    def __init__(self, uid: int, idx: int):
        super().__init__(timeout=60)
        self.uid = uid
        self.idx = idx

    @discord.ui.button(label="確認賣出", style=discord.ButtonStyle.danger)
    async def confirm(self, i: discord.Interaction, b: discord.ui.Button):
        s = get_state(self.uid)
        slot = s.barn[self.idx]
        if slot.amount < 1 or not slot.crop_name:
            await i.response.send_message("作物已不存在", ephemeral=True)
            return
        unit, pct = sale_price(s, slot.crop_name)
        total = unit * slot.amount
        sold_name = slot.crop_name
        s.gold += total
        n, streak = s.same_crop_sale_streak
        if n == sold_name:
            s.same_crop_sale_streak = (n, streak + slot.amount)
        else:
            s.same_crop_sale_streak = (sold_name, slot.amount)
        if s.scarcity_bonus_left.get(sold_name, 0) > 0:
            s.scarcity_bonus_left[sold_name] -= 1
        s.last_sold_tick[sold_name] = s.ticks
        slot.crop_name = None
        slot.amount = 0
        await i.response.edit_message(content=f"賣出完成：{total} 金幣（{pct:+d}%）", view=BarnView(self.uid))

    @discord.ui.button(label="取消", style=discord.ButtonStyle.secondary)
    async def cancel(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.edit_message(content="已取消賣出", view=BarnView(self.uid))


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
                    n = c["name"]
                    last = s.last_sold_tick.get(n, -999999)
                    if s.ticks - last >= 60 and s.scarcity_bonus_left.get(n, 0) == 0:
                        s.scarcity_bonus_left[n] = 2
            await asyncio.sleep(10)


bot = Bot()


@bot.tree.command(name="farm", description="農場主介面")
async def farm(i: discord.Interaction):
    s = get_state(i.user.id)
    msg = f"💰{s.gold} ⚡{s.stamina}/{s.stamina_max} 🍖{s.fullness}/100 | 熟練 Lv.{s.proficiency_level} ({s.proficiency_exp})"
    await i.response.send_message(msg, ephemeral=True, view=TopMenu(i.user.id))


if __name__ == "__main__":
    import os

    t = os.getenv("DISCORD_TOKEN")
    if not t:
        raise RuntimeError("請設定 DISCORD_TOKEN")
    bot.run(t)
