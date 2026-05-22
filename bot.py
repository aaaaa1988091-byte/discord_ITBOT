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
DIFFICULTY_FACTOR = 0.6  # 降低難度 20%


def easier(v: int, min_value: int = 1) -> int:
    return max(min_value, int(round(v * DIFFICULTY_FACTOR)))

CROPS = [
    {"emoji": "🥕", "name": "胡蘿蔔", "level": 1, "grow_days": 10, "required_nutrients": 10},
    {"emoji": "🌾", "name": "小麥", "level": 1, "grow_days": 7, "required_nutrients": 10},
    {"emoji": "🥔", "name": "馬鈴薯", "level": 1, "grow_days": 12, "required_nutrients": 10},
    {"emoji": "🧅", "name": "洋蔥", "level": 1, "grow_days": 18, "required_nutrients": 10},
    {"emoji": "🥬", "name": "高麗菜", "level": 1, "grow_days": 11, "required_nutrients": 10},
    {"emoji": "🍆", "name": "茄子", "level": 2, "grow_days": 20, "required_nutrients": 20},
    {"emoji": "🌽", "name": "玉米", "level": 2, "grow_days": 20, "required_nutrients": 20},
    {"emoji": "🍅", "name": "番茄", "level": 2, "grow_days": 25, "required_nutrients": 20},
    {"emoji": "🥦", "name": "花椰菜", "level": 2, "grow_days": 14, "required_nutrients": 20},
    {"emoji": "🧄", "name": "大蒜", "level": 2, "grow_days": 30, "required_nutrients": 20},
    {"emoji": "🫑", "name": "甜椒", "level": 2, "grow_days": 22, "required_nutrients": 20},
    {"emoji": "🥒", "name": "黃瓜", "level": 2, "grow_days": 15, "required_nutrients": 20},
    {"emoji": "🫘", "name": "黃豆", "level": 2, "grow_days": 16, "required_nutrients": 20},
    {"emoji": "🍉", "name": "西瓜", "level": 3, "grow_days": 45, "required_nutrients": 30},
    {"emoji": "🌶️", "name": "辣椒", "level": 3, "grow_days": 28, "required_nutrients": 30},
    {"emoji": "🎃", "name": "南瓜", "level": 3, "grow_days": 40, "required_nutrients": 30},
    {"emoji": "🍓", "name": "草莓", "level": 3, "grow_days": 30, "required_nutrients": 30},
    {"emoji": "🌻", "name": "向日葵", "level": 3, "grow_days": 35, "required_nutrients": 30},
    {"emoji": "🫐", "name": "藍莓", "level": 4, "grow_days": 60, "required_nutrients": 40},
    {"emoji": "🍇", "name": "葡萄", "level": 4, "grow_days": 90, "required_nutrients": 40},
    {"emoji": "🍈", "name": "哈密瓜", "level": 4, "grow_days": 55, "required_nutrients": 40},
    {"emoji": "🥝", "name": "奇異果", "level": 4, "grow_days": 75, "required_nutrients": 40},
    {"emoji": "🍋", "name": "檸檬", "level": 4, "grow_days": 120, "required_nutrients": 40},
    {"emoji": "🍑", "name": "水蜜桃", "level": 5, "grow_days": 100, "required_nutrients": 50},
    {"emoji": "🍒", "name": "櫻桃", "level": 5, "grow_days": 90, "required_nutrients": 50},
    {"emoji": "🥭", "name": "芒果", "level": 5, "grow_days": 110, "required_nutrients": 50},
    {"emoji": "🍍", "name": "鳳梨", "level": 5, "grow_days": 150, "required_nutrients": 50},
    {"emoji": "🥥", "name": "椰子", "level": 6, "grow_days": 365, "required_nutrients": 60},
    {"emoji": "🍄", "name": "松露", "level": 6, "grow_days": 180, "required_nutrients": 60},
    {"emoji": "🌹", "name": "番紅花", "level": 6, "grow_days": 210, "required_nutrients": 60},
]
CROP_MAP = {c["name"]: c for c in CROPS}
LEVEL_WEIGHT = {1: 10, 2: 12, 3: 18, 4: 22, 5: 20, 6: 18}  # 高等級大幅提高抽取權重
LEVEL_TAG = {1: "普通", 2: "良好", 3: "稀有", 4: "史詩", 5: "傳說", 6: "神話"}

# 素材基礎掉落率修正
MATERIAL_BASE = {
    "scroll": 0.20,
    "poop": 0.40,
    "moai": 0.05,
    "meteor": 0.03,
    "typhoon_eye": 0.03,
    "umbrella": 0.08,
    "lobster": 0.02,
    "deadwood": 0.10,
    "roach": 0.10,
    "cig_butt": 0.38
}

# 素材中文與 Emoji 對應表
MATERIAL_MAP = {
    "scroll": {"emoji": "🧾", "name": "破石法符"},
    "poop": {"emoji": "💩", "name": "大便"},
    "moai": {"emoji": "🗿", "name": "古老的摩艾石像"},
    "meteor": {"emoji": "☄️", "name": "隕石碎片"},
    "typhoon_eye": {"emoji": "🌀", "name": "幼年的颱風眼"},
    "umbrella": {"emoji": "☔", "name": "偷菜賊忘記帶走的雨傘"},
    "lobster": {"emoji": "🦞", "name": "上岸覓食的龍蝦"},
    "deadwood": {"emoji": "🪾", "name": "枯木"},
    "roach": {"emoji": "🪳", "name": "蟑螂"},
    "cig_butt": {"emoji": "🚬", "name": "勞改犯亂丟的菸蒂"},
    "bag_expand": {"emoji": "👜", "name": "擴充道具"}
}

GAME: dict[int, PlayerState] = {}
DATA_DIR = "player_data"
UI_VERSION: dict[int, int] = {}
SELECT_PAGE_SIZE = 24


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
        s.materials = {"scroll":0,"poop":0,"bag_expand":0,"moai":0,"meteor":0,"typhoon_eye":0,"umbrella":0,"lobster":0,"deadwood":0,"roach":0,"cig_butt":0}
        s.machines = {}
        s.hormone = 0
        s.lobster_cfg = {}
        s.ticks = 0
        s.same_crop_sale_streak = [None, 0]
        s.scarcity_bonus_left = {}
        s.last_sold_tick = {}
        GAME[uid] = s
    ensure_state_defaults(GAME[uid])
    return GAME[uid]


def ensure_state_defaults(s: PlayerState) -> None:
    if not hasattr(s, "materials") or s.materials is None:
        s.materials = {"scroll": 0, "poop": 0, "bag_expand": 0, "moai": 0, "meteor": 0, "typhoon_eye": 0, "umbrella": 0, "lobster": 0, "deadwood": 0, "roach": 0, "cig_butt": 0}
    else:
        for k in ("scroll", "poop", "bag_expand", "moai", "meteor", "typhoon_eye", "umbrella", "lobster", "deadwood", "roach", "cig_butt"):
            s.materials.setdefault(k, 0)
    if not hasattr(s, "machines") or s.machines is None:
        s.machines = {}
    if not hasattr(s, "hormone"):
        s.hormone = 0
    if not hasattr(s, "lobster_cfg") or s.lobster_cfg is None:
        s.lobster_cfg = {}
    if not hasattr(s, "crop_mastery") or s.crop_mastery is None:
        s.crop_mastery = {}
    if not hasattr(s, "ticks"):
        s.ticks = 0
    if not hasattr(s, "same_crop_sale_streak"):
        s.same_crop_sale_streak = [None, 0]
    if not hasattr(s, "scarcity_bonus_left"):
        s.scarcity_bonus_left = {}
    if not hasattr(s, "last_sold_tick"):
        s.last_sold_tick = {}


def next_ui_version(uid: int) -> int:
    UI_VERSION[uid] = UI_VERSION.get(uid, 0) + 1
    return UI_VERSION[uid]


def is_ui_active(uid: int, version: int) -> bool:
    return UI_VERSION.get(uid, 0) == version


def farm_to_dict(farm) -> list:
    out = []
    for cell in farm:
        c_dict = {
            "unlocked": cell.unlocked,
            "level": cell.level,
            "nutrients": cell.nutrients,
            "machine": getattr(cell, "machine", None),
            "wet_until": cell.wet_until.isoformat() if getattr(cell, "wet_until", None) else None,
            "water_cooldown_until": cell.water_cooldown_until.isoformat() if getattr(cell, "water_cooldown_until", None) else None,
            "visited_boosted": getattr(cell, "visited_boosted", False),
            "hormone_boosted": getattr(cell, "hormone_boosted", False),
            "nutrient_shortage_since": cell.nutrient_shortage_since.isoformat() if getattr(cell, "nutrient_shortage_since", None) else None,
            "crop": None
        }
        if getattr(cell, "crop", None):
            pt = getattr(cell.crop, "plant_time", None)
            gu = getattr(cell.crop, "grow_until", None)
            c_dict["crop"] = {
                "crop_name": getattr(cell.crop, "crop_name", None),
                "plant_time": pt.isoformat() if pt else None,
                "grow_until": gu.isoformat() if gu else None
            }
        out.append(c_dict)
    return out


def barn_to_dict(barn) -> list:
    out = []
    for slot in barn:
        out.append({
            "unlocked": slot.unlocked,
            "level": slot.level,
            "crop_name": slot.crop_name,
            "amount": slot.amount
        })
    return out


def dict_to_farm(farm_list, farm_obj) -> None:
    for i, d in enumerate(farm_list):
        if i >= len(farm_obj):
            break
        cell = farm_obj[i]
        cell.unlocked = d.get("unlocked", cell.unlocked)
        cell.level = d.get("level", cell.level)
        cell.nutrients = d.get("nutrients", cell.nutrients)
        cell.machine = d.get("machine", None)
        
        wet = d.get("wet_until")
        cell.wet_until = datetime.fromisoformat(wet) if wet else None
        
        wcooldown = d.get("water_cooldown_until")
        cell.water_cooldown_until = datetime.fromisoformat(wcooldown) if wcooldown else None
        
        cell.visited_boosted = d.get("visited_boosted", False)
        cell.hormone_boosted = d.get("hormone_boosted", False)
        ns = d.get("nutrient_shortage_since")
        cell.nutrient_shortage_since = datetime.fromisoformat(ns) if ns else None
        
        crop_d = d.get("crop")
        if crop_d:
            p_time = datetime.fromisoformat(crop_d["plant_time"]) if crop_d.get("plant_time") else datetime.now(timezone.utc)
            g_until = datetime.fromisoformat(crop_d["grow_until"]) if crop_d.get("grow_until") else datetime.now(timezone.utc)
            cell.crop = CropInstance(crop_d["crop_name"], p_time, g_until)
        else:
            cell.crop = None


def dict_to_barn(barn_list, barn_obj) -> None:
    for i, d in enumerate(barn_list):
        if i >= len(barn_obj):
            break
        slot = barn_obj[i]
        slot.unlocked = d.get("unlocked", slot.unlocked)
        slot.level = d.get("level", slot.level)
        slot.crop_name = d.get("crop_name", None)
        slot.amount = d.get("amount", 0)


def state_to_dict(s: PlayerState) -> dict:
    return {
        "gold": s.gold, "stamina": s.stamina, "stamina_max": s.stamina_max, "fullness": s.fullness,
        "moon_shard": s.moon_shard, "scroll": s.scroll, "poop": s.poop, "bag_expand": s.bag_expand,
        "proficiency_level": s.proficiency_level, "proficiency_exp": s.proficiency_exp, "seeds": s.seeds,
        "friends": s.friends, "visit_cooldowns": s.visit_cooldowns, "player_name": s.player_name, "crop_mastery": s.crop_mastery,
        "materials": getattr(s, "materials", {}), "machines": getattr(s, "machines", {}), "hormone": getattr(s, "hormone", 0), "lobster_cfg": getattr(s, "lobster_cfg", {}),
        "ticks": getattr(s, "ticks", 0),
        "same_crop_sale_streak": getattr(s, "same_crop_sale_streak", [None, 0]),
        "scarcity_bonus_left": getattr(s, "scarcity_bonus_left", {}),
        "last_sold_tick": getattr(s, "last_sold_tick", {}),
        "farm": farm_to_dict(s.farm),
        "barn": barn_to_dict(s.barn)
    }


def save_all_players() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    for uid, s in GAME.items():
        with open(os.path.join(DATA_DIR, f"{uid}.json"), "w", encoding="utf-8") as f:
            json.dump(state_to_dict(s), f, ensure_ascii=False, indent=2)


def save_player(uid: int) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    s = GAME.get(uid)
    if not s:
        return
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
    
    farm_list = d.pop("farm", None)
    barn_list = d.pop("barn", None)
    
    for k, v in d.items():
        setattr(s, k, v)
        
    if farm_list:
        dict_to_farm(farm_list, s.farm)
    if barn_list:
        dict_to_barn(barn_list, s.barn)
        
    ensure_state_defaults(s)
    GAME[uid] = s


def crop_emoji(cell) -> str:
    if not cell.unlocked:
        return "⬛"
    if getattr(cell, "machine", None) == "typhoon":
        return "⛈️"
    if getattr(cell, "machine", None) == "billboard":
        return "🪧"
    if getattr(cell, "machine", None) == "lobster":
        return "🦞"
    if cell.crop is None:
        return "🟫"
    if cell.crop.crop_name == "__WITHERED__":
        return "🪾"
    crop = CROP_MAP[cell.crop.crop_name]
    return crop["emoji"]


def render_status(s: PlayerState) -> str:
    seed_text = "、".join(f"{CROP_MAP[n]['emoji']}{n}x{q}" for n, q in s.seeds.items() if q > 0) or "無"
    return f"💰{s.gold} ⚡{s.stamina}/{s.stamina_max} 🍖{s.fullness}/100 | 種籽：{seed_text} | 素材：🧾破石法符x{s.materials.get('scroll',0)} 💩大便x{s.materials.get('poop',0)}"


def bag_detail_text(s: PlayerState) -> str:
    mats = [(k, v) for k, v in s.materials.items() if v > 0]
    mats_text = "、".join([f"{MATERIAL_MAP.get(k, {'emoji': '', 'name': k})['emoji']}{MATERIAL_MAP.get(k, {'emoji': '', 'name': k})['name']}x{v}" for k, v in mats]) if mats else "（目前無素材）"
    seeds = [(k, v) for k, v in s.seeds.items() if v > 0]
    seeds_text = "、".join([f"{CROP_MAP[k]['emoji']}{k}x{v}" for k, v in seeds]) if seeds else "（目前無種籽）"
    return f"🎒背包詳情\n素材：{mats_text}\n種籽：{seeds_text}\n農機具：⛈️{s.machines.get('typhoon',0)} 🪧{s.machines.get('billboard',0)} 🦞{s.materials.get('lobster',0)}\n💉生長激素：{getattr(s,'hormone',0)}"


def cell_status_text(cell, idx: int) -> str:
    return f"地塊 #{idx+1}｜Lv.{cell.level}｜養分 {cell.nutrients}/{cell.level*30}"


def cell_is_nutrient_shortage(cell) -> bool:
    if not getattr(cell, "crop", None):
        return False
    crop_name = getattr(cell.crop, "crop_name", None)
    if crop_name in (None, "__WITHERED__") or crop_name not in CROP_MAP:
        return False
    req = easier(CROP_MAP[crop_name]["required_nutrients"])
    return cell.nutrients < req


def market_unit_price(state: PlayerState, crop_name: str, level: int) -> tuple[int, int]:
    pct = 0
    last_name, streak = state.same_crop_sale_streak
    if last_name == crop_name and streak >= 10:
        pct -= 10
    if state.scarcity_bonus_left.get(crop_name, 0) > 0:
        pct += 10
    base = int(level * 10 * (1 + level * 0.8))
    return int(base * (100 + pct) / 100), pct


def furnace_draw_crop() -> dict:
    weights = [LEVEL_WEIGHT.get(c["level"], 1) for c in CROPS]
    return random.choices(CROPS, weights=weights, k=1)[0]


def furnace_seed_amount(crop_level: int) -> int:
    if crop_level >= 5 and random.random() < 0.35:
        return 2
    if crop_level >= 3 and random.random() < 0.15:
        return 2
    return 1


def neighbors_3x3(idx: int) -> list[int]:
    r, c = divmod(idx, 5)
    out = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            nr, nc = r + dr, c + dc
            if 0 <= nr < 5 and 0 <= nc < 5:
                out.append(nr * 5 + nc)
    return out


class FarmMainView(discord.ui.View):
    def __init__(self, uid: int, version: int):
        super().__init__(timeout=120)
        self.uid = uid
        self.version = version
        s = get_state(uid)
        for idx, cell in enumerate(s.farm):
            wet = getattr(cell, "wet_until", None)
            is_wet = wet and datetime.now(timezone.utc) < wet
            if not cell.unlocked:
                style = discord.ButtonStyle.secondary
            elif cell.crop and getattr(cell.crop, "crop_name", None) == "__WITHERED__":
                style = discord.ButtonStyle.danger
            elif cell_is_nutrient_shortage(cell):
                style = discord.ButtonStyle.danger
            elif cell.crop and mature(cell.crop):
                style = discord.ButtonStyle.success
            elif is_wet:
                style = discord.ButtonStyle.primary
            else:
                style = discord.ButtonStyle.secondary
            btn = discord.ui.Button(label=crop_emoji(cell), row=idx // 5, style=style)

            async def cb(interaction: discord.Interaction, x=idx):
                if not is_ui_active(uid, self.version):
                    await interaction.response.send_message("此 UI 已被新畫面取代。", ephemeral=True)
                    return
                await interaction.response.edit_message(
                    content=f"{render_status(get_state(uid))}\n{cell_status_text(get_state(uid).farm[x], x)}",
                    view=CellMenuView(uid, x, self.version),
                    embed=None,
                )

            btn.callback = cb
            self.add_item(btn)


class CellActionSelect(discord.ui.Select):
    def __init__(self, uid: int, idx: int, version: int, page: int = 0):
        self.uid, self.idx = uid, idx
        self.version = version
        s = get_state(uid)
        cell = s.farm[idx]
        options: list[discord.SelectOption] = []

        if not cell.unlocked:
            if s.materials.get("scroll", 0) >= 1:
                options.append(discord.SelectOption(label=f"解鎖({MATERIAL_MAP['scroll']['emoji']}{MATERIAL_MAP['scroll']['name']}x1)", value="unlock"))
            options.append(discord.SelectOption(label="返回農地←", value="back"))
        elif cell.crop is None and getattr(cell, "machine", None) not in ("typhoon", "billboard"):
            for name, qty in sorted(s.seeds.items(), key=lambda kv: (CROP_MAP[kv[0]]["level"], kv[0])):
                if qty <= 0:
                    continue
                crop = CROP_MAP[name]
                options.append(discord.SelectOption(label=f"種植{name}{crop['emoji']}(養分{easier(crop['required_nutrients'])})", value=f"plant:{name}"))
            up_gold = easier(40)
            up_poop = easier(cell.level * 5)
            if s.stamina >= 10 and s.gold >= up_gold and s.materials.get("poop", 0) >= up_poop:
                options.append(discord.SelectOption(label=f"升級({up_gold}金+{MATERIAL_MAP['poop']['emoji']}{MATERIAL_MAP['poop']['name']}x{up_poop})", value="upgrade"))
            if s.stamina >= 10 and s.materials.get("poop", 0) >= 1:
                options.append(discord.SelectOption(label=f"施肥(+20養分，{MATERIAL_MAP['poop']['emoji']}{MATERIAL_MAP['poop']['name']}x1)", value="fertilize"))
            if s.machines.get("typhoon", 0) > 0:
                options.append(discord.SelectOption(label="佈置 ⛈️颱風眼催發器", value="place:typhoon"))
            if s.machines.get("billboard", 0) > 0:
                options.append(discord.SelectOption(label="佈置 🪧電影廣告招牌", value="place:billboard"))
            if s.materials.get("lobster", 0) > 0:
                options.append(discord.SelectOption(label=f"佈置 {MATERIAL_MAP['lobster']['emoji']}{MATERIAL_MAP['lobster']['name']}", value="place:lobster"))
            options.append(discord.SelectOption(label="返回農地←", value="back"))
        else:
            if cell.crop and cell.crop.crop_name == "__WITHERED__":
                options.append(discord.SelectOption(label="清理枯萎作物（3日後可回收）", value="clear_wither"))
                options.append(discord.SelectOption(label="返回農地←", value="back"))
                super().__init__(placeholder=f"地塊 #{idx+1} 選單", options=options, min_values=1, max_values=1)
                return
            options.append(discord.SelectOption(label="澆水(+10%生長速度1日)", value="water"))
            if s.hormone >= 1 and not getattr(cell, "hormone_boosted", False):
                options.append(discord.SelectOption(label="使用生長激素(💉生長+30%)", value="use_hormone"))
            options.append(discord.SelectOption(label="直接吃掉(10%飽食恢復)", value="eat_crop"))
            if s.stamina >= 10 and s.materials.get("poop", 0) >= 1:
                options.append(discord.SelectOption(label=f"施肥(+20養分，{MATERIAL_MAP['poop']['emoji']}{MATERIAL_MAP['poop']['name']}x1)", value="fertilize"))
            if mature(cell.crop) and s.stamina >= 10:
                options.append(discord.SelectOption(label="收割", value="harvest"))
            options.append(discord.SelectOption(label="更多資訊", value="info"))
            options.append(discord.SelectOption(label="返回農地←", value="back"))
        if getattr(cell, "machine", None) == "lobster":
            options.append(discord.SelectOption(label="設定🦞單一種籽", value="cfg_lobster"))
        if getattr(cell, "machine", None) in ("typhoon", "billboard", "lobster"):
            options.append(discord.SelectOption(label="拆除農機具", value="remove_machine"))

        total_pages = max(1, (len(options) + SELECT_PAGE_SIZE - 1) // SELECT_PAGE_SIZE)
        page = max(0, min(page, total_pages - 1))
        paged = options[page * SELECT_PAGE_SIZE:(page + 1) * SELECT_PAGE_SIZE]
        if total_pages > 1 and page < total_pages - 1:
            paged.append(discord.SelectOption(label="下一頁→", value=f"page:{page+1}"))
        if total_pages > 1 and page > 0:
            paged.append(discord.SelectOption(label="←上一頁", value=f"page:{page-1}"))
        super().__init__(placeholder=f"地塊 #{idx+1} 選單（第{page+1}/{total_pages}頁）", options=paged, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if not is_ui_active(self.uid, self.version):
            await interaction.response.send_message("此 UI 已被新畫面取代。", ephemeral=True)
            return
        s = get_state(self.uid)
        cell = s.farm[self.idx]
        action = self.values[0]
        if action.startswith("page:"):
            page = int(action.split(":")[1])
            await interaction.response.edit_message(content=render_status(s), view=CellMenuView(self.uid, self.idx, self.version, page=page), embed=None)
            return

        if action == "back":
            await interaction.response.edit_message(content=render_status(s), view=FarmMainView(self.uid, self.version), embed=None)
            return
        if action == "clear_wither":
            action = "harvest"
        if action == "unlock":
            s.materials["scroll"] = max(0, s.materials.get("scroll", 0) - 1)
            cell.unlocked = True
            save_player(self.uid)
            await interaction.response.edit_message(content=f"{render_status(s)}\n地塊已解鎖", view=FarmMainView(self.uid, self.version), embed=None)
            return
        if action.startswith("plant:"):
            crop_name = action.split(":", 1)[1]
            if cell.crop is not None or s.seeds.get(crop_name, 0) <= 0 or not consume_stamina(s, 10):
                await interaction.response.edit_message(content=f"{render_status(s)}\n無法種植", view=CellMenuView(self.uid, self.idx, self.version), embed=None)
                return
            crop = CROP_MAP[crop_name]
            now = datetime.now(timezone.utc)
            cell.crop = CropInstance(crop_name, now, now + timedelta(seconds=easier(crop["grow_days"]) * DAY_SECONDS))
            s.seeds[crop_name] -= 1
            cell.visited_boosted = False
            cell.hormone_boosted = False
            save_player(self.uid)
            await interaction.response.edit_message(content=f"{render_status(s)}\n已種植 {crop['emoji']}{crop_name}", view=FarmMainView(self.uid, self.version), embed=None)
            return
        if action.startswith("place:"):
            tool = action.split(":", 1)[1]
            if tool == "typhoon":
                if s.machines.get("typhoon", 0) <= 0:
                    return await interaction.response.edit_message(content=f"{render_status(s)}\n沒有可佈置的⛈️", view=CellMenuView(self.uid, self.idx, self.version), embed=None)
                cell.machine = "typhoon"
                s.machines["typhoon"] -= 1
            elif tool == "billboard":
                if s.machines.get("billboard", 0) <= 0:
                    return await interaction.response.edit_message(content=f"{render_status(s)}\n沒有可佈置的🪧", view=CellMenuView(self.uid, self.idx, self.version), embed=None)
                cell.machine = "billboard"
                s.machines["billboard"] -= 1
            elif tool == "lobster":
                if s.materials.get("lobster", 0) <= 0:
                    return await interaction.response.edit_message(content=f"{render_status(s)}\n沒有可佈置的🦞", view=CellMenuView(self.uid, self.idx, self.version), embed=None)
                cell.machine = "lobster"
                s.materials["lobster"] -= 1
            save_player(self.uid)
            return await interaction.response.edit_message(content=f"{render_status(s)}\n已佈置 {crop_emoji(cell)} 於地塊#{self.idx+1}", view=FarmMainView(self.uid, self.version), embed=None)
        if action == "cfg_lobster":
            return await interaction.response.edit_message(content=f"設定龍蝦地塊#{self.idx+1}單一種籽", view=LobsterConfigView(self.uid, self.idx, return_to_cell=True, cell_version=self.version))
        if action == "upgrade":
            if not consume_stamina(s, 10):
                await interaction.response.send_message("體力不足", ephemeral=True)
                return
            s.gold -= easier(40)
            s.materials["poop"] = max(0, s.materials.get("poop", 0) - easier(cell.level * 5))
            cell.level += 1
            save_player(self.uid)
            await interaction.response.edit_message(content=f"{render_status(s)}\n地塊升級 Lv.{cell.level}", view=CellMenuView(self.uid, self.idx, self.version), embed=None)
            return
        if action == "fertilize":
            if s.materials.get("poop", 0) < 1 or not consume_stamina(s, 10):
                await interaction.response.edit_message(
                    content=f"{render_status(s)}\n{cell_status_text(cell, self.idx)}\n施肥失敗：需要體力10與{MATERIAL_MAP['poop']['emoji']}{MATERIAL_MAP['poop']['name']}x1",
                    view=CellMenuView(self.uid, self.idx, self.version),
                    embed=None,
                )
                return
            s.materials["poop"] = max(0, s.materials.get("poop", 0) - 1)
            before = cell.nutrients
            cell.nutrients = min(cell.level * 30, cell.nutrients + 20)
            gain = cell.nutrients - before
            save_player(self.uid)
            await interaction.response.edit_message(
                content=f"{render_status(s)}\n{cell_status_text(cell, self.idx)}\n施肥成功：+{gain} 養分",
                view=CellMenuView(self.uid, self.idx, self.version),
                embed=None,
            )
            return
        if action == "water":
            now = datetime.now(timezone.utc)
            cooldown_until = getattr(cell, "water_cooldown_until", None)
            if cooldown_until and now < cooldown_until:
                left = int((cooldown_until - now).total_seconds() / DAY_SECONDS)
                await interaction.response.edit_message(content=f"澆水冷卻中，剩餘 {left} 日", view=CellMenuView(self.uid, self.idx, self.version), embed=None)
                return
            speed = timedelta(seconds=WATER_SPEEDUP_DAYS * DAY_SECONDS)
            if cell.crop and getattr(cell.crop, "grow_until", None) and cell.crop.grow_until > now:
                cell.crop.grow_until = max(now, cell.crop.grow_until - speed)
            cell.water_cooldown_until = now + timedelta(seconds=WATER_COOLDOWN_DAYS * DAY_SECONDS)
            cell.wet_until = cell.water_cooldown_until
            save_player(self.uid)
            await interaction.response.edit_message(content=f"澆水完成，冷卻 {WATER_COOLDOWN_DAYS} 日", view=CellMenuView(self.uid, self.idx, self.version), embed=None)
            return
        if action == "use_hormone":
            if s.hormone < 1:
                await interaction.response.edit_message(content=f"{render_status(s)}\n生長激素不足。", view=CellMenuView(self.uid, self.idx, self.version), embed=None)
                return
            if not cell.crop or getattr(cell.crop, "crop_name", None) == "__WITHERED__":
                await interaction.response.edit_message(content=f"{render_status(s)}\n此地塊沒有生長中的作物。", view=CellMenuView(self.uid, self.idx, self.version), embed=None)
                return
            if getattr(cell, "hormone_boosted", False):
                await interaction.response.edit_message(content=f"{render_status(s)}\n此作物已使用過生長激素。", view=CellMenuView(self.uid, self.idx, self.version), embed=None)
                return
            s.hormone -= 1
            cell.hormone_boosted = True
            now = datetime.now(timezone.utc)
            if getattr(cell.crop, "grow_until", None) and cell.crop.grow_until > now:
                remaining = cell.crop.grow_until - now
                cell.crop.grow_until = now + remaining * 0.7
            save_player(self.uid)
            await interaction.response.edit_message(content=f"{render_status(s)}\n已成功對作物使用生長激素，生長加速 30%！", view=CellMenuView(self.uid, self.idx, self.version), embed=None)
            return
        if action == "remove_machine":
            m = getattr(cell, "machine", None)
            if m == "typhoon":
                s.machines["typhoon"] = s.machines.get("typhoon", 0) + 1
            elif m == "billboard":
                s.machines["billboard"] = s.machines.get("billboard", 0) + 1
            elif m == "lobster":
                s.materials["lobster"] = s.materials.get("lobster", 0) + 1
            cell.machine = None
            save_player(self.uid)
            await interaction.response.edit_message(content=f"{render_status(s)}\n已拆除農機具", view=FarmMainView(self.uid, self.version), embed=None)
            return
        if action == "eat_crop":
            if getattr(cell.crop, "crop_name", None) == "__WITHERED__":
                await interaction.response.edit_message(content=f"{render_status(s)}\n枯萎作物不可食用", view=CellMenuView(self.uid, self.idx, self.version), embed=None)
                return
            crop = CROP_MAP[cell.crop.crop_name]
            s.fullness = min(100, s.fullness + max(1, int(crop["level"] * 2 * 0.1)))
            cell.crop = None
            save_player(self.uid)
            await interaction.response.edit_message(content=f"{render_status(s)}\n已直接吃掉作物", view=FarmMainView(self.uid, self.version), embed=None)
            return
        if action == "harvest":
            if cell.crop and getattr(cell.crop, "crop_name", None) == "__WITHERED__":
                cell.crop = None
                s.materials["poop"] = s.materials.get("poop", 0) + 1
                cell.nutrient_shortage_since = None
                msg_parts = [f"{MATERIAL_MAP['poop']['emoji']}{MATERIAL_MAP['poop']['name']}"]
                if random.random() < 0.5:
                    s.materials["deadwood"] = s.materials.get("deadwood", 0) + 1
                    msg_parts.append(f"{MATERIAL_MAP['deadwood']['emoji']}{MATERIAL_MAP['deadwood']['name']}")
                if random.random() < 0.5:
                    s.materials["roach"] = s.materials.get("roach", 0) + 1
                    msg_parts.append(f"{MATERIAL_MAP['roach']['emoji']}{MATERIAL_MAP['roach']['name']}")
                save_player(self.uid)
                await interaction.response.edit_message(content=f"{render_status(s)}\n已清理枯萎作物，獲得：" + "、".join(msg_parts), view=FarmMainView(self.uid, self.version), embed=None)
                return
            if not cell.crop or not mature(cell.crop) or not consume_stamina(s, 10):
                await interaction.response.edit_message(content=f"{render_status(s)}\n目前無法收割", view=CellMenuView(self.uid, self.idx, self.version), embed=None)
                return
            crop = CROP_MAP[cell.crop.crop_name]
            mastery = s.crop_mastery.setdefault(crop["name"], {"level": 1, "exp": 0})
            prof_level = max(1, min(4, mastery["level"]))
            harvest_qty = 1 + prof_level
            req_nutrients = easier(crop["required_nutrients"])
            if cell.nutrients < req_nutrients:
                now = datetime.now(timezone.utc)
                cell.crop = CropInstance("__WITHERED__", now, now + timedelta(seconds=3 * DAY_SECONDS))
                save_player(self.uid)
                await interaction.response.edit_message(content=f"{render_status(s)}\n養分不足，作物進入🪾枯萎狀態（3日後可清理回收）", view=FarmMainView(self.uid, self.version), embed=None)
                return
            cell.nutrients -= req_nutrients
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
                fallback_unit = int(crop["level"] * 10 * (1 + crop["level"] * 0.8))
                s.gold += fallback_unit * remaining_qty
            mult = 1.1 ** max(1, crop["level"])
            for k, b in MATERIAL_BASE.items():
                if random.random() < min(0.95, b * mult):
                    s.materials[k] = s.materials.get(k, 0) + 1
            if random.random() < 0.5:
                s.materials["deadwood"] = s.materials.get("deadwood", 0) + 1
            if random.random() < 0.5:
                s.materials["roach"] = s.materials.get("roach", 0) + 1
            mastery["exp"] += 1
            need = easier(20 + crop["level"] * 10)
            if mastery["level"] < 4 and mastery["exp"] >= need:
                mastery["exp"] = 0
                mastery["level"] += 1
            cell.crop = None
            save_player(self.uid)
            result = "已存入穀倉" if remaining_qty == 0 else f"部分換金 x{remaining_qty}"
            await interaction.response.edit_message(content=f"{render_status(s)}\n收割 {crop['emoji']}{crop['name']} x{harvest_qty}（{result}）", view=FarmMainView(self.uid, self.version), embed=None)
            return
        if action == "info":
            crop = CROP_MAP[cell.crop.crop_name]
            rem = max(0, int((getattr(cell.crop, "grow_until", datetime.now(timezone.utc)) - datetime.now(timezone.utc)).total_seconds() / DAY_SECONDS))
            e = discord.Embed(title=f"地塊 #{self.idx+1}")
            e.add_field(name="作物", value=f"{crop['emoji']}{crop['name']} Lv.{crop['level']}")
            e.add_field(name="養分需求", value=str(crop["required_nutrients"]))
            e.add_field(name="剩餘天數", value=str(rem))
            await interaction.response.edit_message(content=render_status(s), view=CellMenuView(self.uid, self.idx, self.version), embed=e)


class CellMenuView(discord.ui.View):
    def __init__(self, uid: int, idx: int, version: int, page: int = 0):
        super().__init__(timeout=90)
        self.add_item(CellActionSelect(uid, idx, version, page=page))


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
            unlock_gold = easier(40)
            if s.gold >= unlock_gold and s.materials.get("bag_expand", 0) >= 1:
                options.append(discord.SelectOption(label=f"解鎖欄位({unlock_gold}金+{MATERIAL_MAP['bag_expand']['emoji']}{MATERIAL_MAP['bag_expand']['name']}x1)", value="unlock"))
        else:
            up_gold = easier(40)
            up_bag = easier(slot.level * 5)
            if slot.level < 4 and s.gold >= up_gold and s.materials.get("bag_expand", 0) >= up_bag and s.stamina >= 10:
                options.append(discord.SelectOption(label=f"升級欄位({up_gold}金+{MATERIAL_MAP['bag_expand']['emoji']}{MATERIAL_MAP['bag_expand']['name']}x{up_bag})", value="upgrade"))
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
            s.gold -= easier(40)
            s.materials["bag_expand"] = max(0, s.materials.get("bag_expand", 0) - 1)
            slot.unlocked = True
            save_player(self.uid)
            await interaction.response.edit_message(content=f"{render_status(s)}\n穀倉欄位已解鎖", view=BarnMainView(self.uid), embed=None)
            return
        if action == "upgrade":
            cost = easier(slot.level * 5)
            if not consume_stamina(s, 10):
                await interaction.response.send_message("體力不足", ephemeral=True)
                return
            s.gold -= easier(40)
            s.materials["bag_expand"] = max(0, s.materials.get("bag_expand", 0) - cost)
            slot.level += 1
            save_player(self.uid)
            await interaction.response.edit_message(content=f"{render_status(s)}\n欄位升級至 Lv.{slot.level}", view=BarnSlotMenuView(self.uid, self.idx), embed=None)
            return
        if action == "eat":
            crop = CROP_MAP[slot.crop_name]
            slot.amount -= 1
            s.fullness = min(100, s.fullness + crop["level"] * 2)
            if slot.amount == 0:
                slot.crop_name = None
            save_player(self.uid)
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
        save_player(self.uid)
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
                for i, cell in enumerate(s.farm):
                    now = datetime.now(timezone.utc)
                    if getattr(cell, "crop", None):
                        crop_name = getattr(cell.crop, "crop_name", None)
                        if crop_name not in (None, "__WITHERED__") and crop_name in CROP_MAP:
                            if cell_is_nutrient_shortage(cell):
                                shortage_since = getattr(cell, "nutrient_shortage_since", None)
                                if shortage_since is None:
                                    cell.nutrient_shortage_since = now
                                elif now - shortage_since >= timedelta(seconds=3 * DAY_SECONDS):
                                    cell.crop = CropInstance("__WITHERED__", now, now)
                                    cell.nutrient_shortage_since = None
                            else:
                                cell.nutrient_shortage_since = None
                        else:
                            cell.nutrient_shortage_since = None
                    else:
                        cell.nutrient_shortage_since = None
                    machine = getattr(cell, "machine", None)
                    if machine == "typhoon":
                        for ni in neighbors_3x3(i):
                            target_cell = s.farm[ni]
                            cooldown_until = getattr(target_cell, "water_cooldown_until", None)
                            if not cooldown_until or now >= cooldown_until:
                                speed = timedelta(seconds=WATER_SPEEDUP_DAYS * DAY_SECONDS)
                                if getattr(target_cell, "crop", None) and getattr(target_cell.crop, "grow_until", None) and target_cell.crop.grow_until > now:
                                    target_cell.crop.grow_until = max(now, target_cell.crop.grow_until - speed)
                                target_cell.water_cooldown_until = now + timedelta(seconds=WATER_COOLDOWN_DAYS * DAY_SECONDS)
                                target_cell.wet_until = target_cell.water_cooldown_until
                    elif machine == "billboard":
                        for ni in neighbors_3x3(i):
                            c2 = s.farm[ni]
                            c2.nutrients = min(c2.level * 30, c2.nutrients + 20)
                    elif machine == "lobster":
                        if cell.crop and mature(cell.crop):
                            cname = getattr(cell.crop, "crop_name", None)
                            cell.crop = None
                            s.seeds[cname] = max(0, s.seeds.get(cname, 0) - 1)
                        if cell.crop is None:
                            cfg = getattr(s, "lobster_cfg", {}).get(str(i))
                            if cfg and s.seeds.get(cfg, 0) > 0:
                                crop = CROP_MAP[cfg]
                                now = datetime.now(timezone.utc)
                                cell.crop = CropInstance(cfg, now, now + timedelta(seconds=easier(crop["grow_days"]) * DAY_SECONDS))
                                s.seeds[cfg] -= 1
                                cell.visited_boosted = False
                                cell.hormone_boosted = False
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

    @discord.ui.button(label="🛍️ 轉化爐", style=discord.ButtonStyle.primary)
    async def furnace(self, interaction: discord.Interaction, _):
        s = get_state(self.uid)
        furnace_cost = easier(20)
        if s.gold < furnace_cost:
            await interaction.response.edit_message(content=f"{render_status(s)}\n金幣不足 {furnace_cost}。", view=FarmUIView(self.uid))
            return
        s.gold -= furnace_cost
        c = furnace_draw_crop()
        amount = furnace_seed_amount(c["level"])
        s.seeds[c["name"]] = s.seeds.get(c["name"], 0) + amount
        save_player(self.uid)
        await interaction.response.edit_message(
            content=f"{render_status(s)}\n轉化爐花費 {furnace_cost} 金幣，獲得 {c['emoji']}{c['name']} 種籽 x{amount}（{LEVEL_TAG.get(c['level'],'普通')}）",
            view=FarmUIView(self.uid),
        )

    @discord.ui.button(label="🎒 背包", style=discord.ButtonStyle.secondary)
    async def bag(self, interaction: discord.Interaction, _):
        s = get_state(self.uid)
        await interaction.response.edit_message(content=bag_detail_text(s), view=FarmUIView(self.uid))

    @discord.ui.button(label="🌾 穀倉", style=discord.ButtonStyle.success)
    async def barn(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(content="穀倉 2x5", view=BarnMainView(self.uid, origin="farmui"))

    @discord.ui.button(label="🧪 合成區", style=discord.ButtonStyle.secondary)
    async def craft(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(content="合成區", view=CraftView(self.uid))

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
        crop_level = CROP_MAP.get(v, {"level": 1})["level"]
        need_exp = easier(20 + crop_level * 10)
        e = discord.Embed(title=f"農夫寶典｜{v} 熟練度")
        e.add_field(name="熟練等級", value=f"{level_name}({m['level']})", inline=False)
        e.add_field(name="經驗獲取", value="成功收割 +1", inline=False)
        e.add_field(name="升級需求", value=f"目前需求 {need_exp}（基礎公式：20 + 作物等級×10，含難度調整）", inline=False)
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
            
            # 統一拜訪加成演算法，且不可疊加
            for cell in target.farm:
                if cell.crop and getattr(cell.crop, "grow_until", None) and cell.crop.grow_until > now and not getattr(cell, "visited_boosted", False):
                    remaining = cell.crop.grow_until - now
                    cell.crop.grow_until = now + remaining * 0.7
                    cell.visited_boosted = True
                    
            s.visit_cooldowns[key] = (now + timedelta(seconds=30 * DAY_SECONDS)).isoformat()
            save_player(self.uid)
            save_player(fid)
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
            save_player(self.uid)
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


class CraftSelect(discord.ui.Select):
    def __init__(self, uid: int):
        self.uid = uid
        s = get_state(uid)
        m = s.materials
        opts = []
        if m.get("typhoon_eye", 0) >= 1 and m.get("umbrella", 0) >= 1:
            opts.append(discord.SelectOption(label=f"合成 ⛈️颱風眼催發器 ({MATERIAL_MAP['typhoon_eye']['emoji']}x1 + {MATERIAL_MAP['umbrella']['emoji']}x1)", value="mk_typhoon"))
        if m.get("moai", 0) >= 1 and m.get("meteor", 0) >= 1 and m.get("deadwood", 0) >= 1:
            opts.append(discord.SelectOption(label=f"合成 🪧電影廣告招牌 ({MATERIAL_MAP['moai']['emoji']}x1 + {MATERIAL_MAP['meteor']['emoji']}x1 + {MATERIAL_MAP['deadwood']['emoji']}x1)", value="mk_billboard"))
        if m.get("roach", 0) >= 3:
            opts.append(discord.SelectOption(label=f"合成 💉生長激素 ({MATERIAL_MAP['roach']['emoji']}x3)", value="mk_hormone"))
        if not opts:
            opts = [discord.SelectOption(label="目前無可合成", value="none")]
        opts.append(discord.SelectOption(label="返回←", value="back"))
        super().__init__(placeholder="合成菜單", options=opts)

    async def callback(self, interaction):
        s = get_state(self.uid)
        m = s.materials
        v = self.values[0]
        if v == "back":
            return await interaction.response.edit_message(content=render_status(s), view=FarmUIView(self.uid))
        if v == "none":
            return await interaction.response.edit_message(content="目前無可合成", view=CraftView(self.uid))
        if v == "mk_typhoon":
            m["typhoon_eye"] -= 1
            m["umbrella"] -= 1
            s.machines["typhoon"] = s.machines.get("typhoon", 0) + 1
        if v == "mk_billboard":
            m["moai"] -= 1
            m["meteor"] -= 1
            m["deadwood"] -= 1
            s.machines["billboard"] = s.machines.get("billboard", 0) + 1
        if v == "mk_hormone":
            m["roach"] -= 3
            s.hormone = getattr(s, "hormone", 0) + 1
        save_player(self.uid)
        await interaction.response.edit_message(content=f"{render_status(s)}\n合成成功", view=CraftView(self.uid))


class CraftView(discord.ui.View):
    def __init__(self, uid: int):
        super().__init__(timeout=120)
        self.add_item(CraftSelect(uid))


class ToolsView(discord.ui.View):
    def __init__(self, uid: int, page: int = 0):
        super().__init__(timeout=120)
        self.uid = uid
        self.add_item(ToolsSelect(uid, page=page))


class ToolsSelect(discord.ui.Select):
    def __init__(self, uid: int, page: int = 0):
        self.uid = uid
        s = get_state(uid)
        opts = []
        for i, c in enumerate(s.farm):
            if not c.unlocked:
                continue
            if getattr(c, "machine", None) in ("typhoon", "billboard", "lobster"):
                continue
            opts.append(discord.SelectOption(label=f"佈置到地塊#{i+1}", value=f"cell:{i}"))
        for i, c in enumerate(s.farm):
            if getattr(c, "machine", None) == "lobster":
                opts.append(discord.SelectOption(label=f"設定🦞地塊#{i+1}單一種籽", value=f"cfg:{i}"))
        if s.machines.get("typhoon", 0) > 0:
            opts.append(discord.SelectOption(label="選擇佈置 ⛈️颱風眼催發器", value="pick:typhoon"))
        if s.machines.get("billboard", 0) > 0:
            opts.append(discord.SelectOption(label="選擇佈置 🪧電影廣告招牌", value="pick:billboard"))
        if s.materials.get("lobster", 0) > 0:
            opts.append(discord.SelectOption(label=f"選擇佈置 {MATERIAL_MAP['lobster']['emoji']}{MATERIAL_MAP['lobster']['name']}", value="pick:lobster"))
        opts.append(discord.SelectOption(label="返回←", value="back"))
        total_pages = max(1, (len(opts) + SELECT_PAGE_SIZE - 1) // SELECT_PAGE_SIZE)
        page = max(0, min(page, total_pages - 1))
        paged = opts[page * SELECT_PAGE_SIZE:(page + 1) * SELECT_PAGE_SIZE]
        if total_pages > 1 and page < total_pages - 1:
            paged.append(discord.SelectOption(label="下一頁→", value=f"page:{page+1}"))
        if total_pages > 1 and page > 0:
            paged.append(discord.SelectOption(label="←上一頁", value=f"page:{page-1}"))
        super().__init__(placeholder=f"農機具管理（第{page+1}/{total_pages}頁）", options=paged, min_values=1, max_values=1)

    async def callback(self, interaction):
        s = get_state(self.uid)
        v = self.values[0]
        if v.startswith("page:"):
            page = int(v.split(":")[1])
            return await interaction.response.edit_message(content="農機具配置", view=ToolsView(self.uid, page=page))
        if v == "back":
            return await interaction.response.edit_message(content=render_status(s), view=FarmUIView(self.uid))
        if v.startswith("pick:"):
            s.tool_pick = v.split(":")[1]
            save_player(self.uid)
            return await interaction.response.edit_message(content=f"已選擇 {s.tool_pick}，再選地塊佈置", view=ToolsView(self.uid))
        if v.startswith("cell:"):
            idx = int(v.split(":")[1])
            c = s.farm[idx]
            pick = getattr(s, "tool_pick", None)
            if not pick:
                return await interaction.response.edit_message(content="請先選擇要佈置的農機具", view=ToolsView(self.uid))
            c.machine = pick
            if pick == "typhoon":
                s.machines["typhoon"] = max(0, s.machines.get("typhoon", 0) - 1)
            elif pick == "billboard":
                s.machines["billboard"] = max(0, s.machines.get("billboard", 0) - 1)
            elif pick == "lobster":
                s.materials["lobster"] = max(0, s.materials.get("lobster", 0) - 1)
            s.tool_pick = None
            save_player(self.uid)
            return await interaction.response.edit_message(content=f"已佈置 {pick} 到地塊#{idx+1}", view=FarmUIView(self.uid))
        if v.startswith("cfg:"):
            idx = int(v.split(":")[1])
            return await interaction.response.edit_message(content=f"設定龍蝦地塊#{idx+1}自動種植種籽", view=LobsterConfigView(self.uid, idx))


class LobsterSeedSelect(discord.ui.Select):
    def __init__(self, uid: int, idx: int, page: int = 0, return_to_cell: bool = False, cell_version: int = 0):
        self.uid = uid
        self.idx = idx
        self.return_to_cell = return_to_cell
        self.cell_version = cell_version
        s = get_state(uid)
        opts = []
        for name, qty in sorted(s.seeds.items(), key=lambda kv: (CROP_MAP[kv[0]]["level"], kv[0])):
            if qty > 0:
                crop = CROP_MAP[name]
                opts.append(discord.SelectOption(label=f"{crop['emoji']}{name} x{qty}", value=name))
        if not opts:
            opts = [discord.SelectOption(label="目前無可設定種籽", value="none")]
        opts.append(discord.SelectOption(label="清除設定", value="clear"))
        opts.append(discord.SelectOption(label="返回←", value="back"))
        total_pages = max(1, (len(opts) + SELECT_PAGE_SIZE - 1) // SELECT_PAGE_SIZE)
        page = max(0, min(page, total_pages - 1))
        paged = opts[page * SELECT_PAGE_SIZE:(page + 1) * SELECT_PAGE_SIZE]
        if total_pages > 1 and page < total_pages - 1:
            paged.append(discord.SelectOption(label="下一頁→", value=f"page:{page+1}"))
        if total_pages > 1 and page > 0:
            paged.append(discord.SelectOption(label="←上一頁", value=f"page:{page-1}"))
        super().__init__(placeholder=f"龍蝦地塊#{idx+1}單一種籽（第{page+1}/{total_pages}頁）", options=paged, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        s = get_state(self.uid)
        v = self.values[0]
        if v.startswith("page:"):
            page = int(v.split(":")[1])
            return await interaction.response.edit_message(content="設定龍蝦種籽", view=LobsterConfigView(self.uid, self.idx, page=page, return_to_cell=self.return_to_cell, cell_version=self.cell_version))
        if v == "back":
            if self.return_to_cell:
                return await interaction.response.edit_message(content=render_status(s), view=CellMenuView(self.uid, self.idx, self.cell_version))
            return await interaction.response.edit_message(content="農機具配置", view=ToolsView(self.uid))
        if v == "none":
            return await interaction.response.edit_message(content="目前無可設定種籽", view=LobsterConfigView(self.uid, self.idx, return_to_cell=self.return_to_cell, cell_version=self.cell_version))
        if v == "clear":
            s.lobster_cfg.pop(str(self.idx), None)
            save_player(self.uid)
            return await interaction.response.edit_message(content=f"已清除地塊#{self.idx+1}龍蝦種籽設定", view=LobsterConfigView(self.uid, self.idx, return_to_cell=self.return_to_cell, cell_version=self.cell_version))
        s.lobster_cfg[str(self.idx)] = v
        save_player(self.uid)
        crop = CROP_MAP[v]
        return await interaction.response.edit_message(content=f"地塊#{self.idx+1}龍蝦已設定：{crop['emoji']}{v}", view=LobsterConfigView(self.uid, self.idx, return_to_cell=self.return_to_cell, cell_version=self.cell_version))


class LobsterConfigView(discord.ui.View):
    def __init__(self, uid: int, idx: int, page: int = 0, return_to_cell: bool = False, cell_version: int = 0):
        super().__init__(timeout=120)
        self.add_item(LobsterSeedSelect(uid, idx, page=page, return_to_cell=return_to_cell, cell_version=cell_version))


if __name__ == "__main__":
    import os

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("請設定 DISCORD_TOKEN")
    bot.run(token)
