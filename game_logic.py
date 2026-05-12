"""Core game logic utilities for easier maintenance and testing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


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
    seeds: dict[str, int] = field(default_factory=dict)
    farm: list[FarmCell] = field(default_factory=list)
    barn: list[BarnSlot] = field(default_factory=list)

    def init_default_layout(self) -> None:
        if not self.farm:
            self.farm = [FarmCell() for _ in range(25)]
            self.farm[12].unlocked = True
        if not self.barn:
            self.barn = [BarnSlot(unlocked=i < 4) for i in range(10)]



def mature(ci: CropInstance) -> bool:
    return datetime.now(timezone.utc) >= ci.grow_until


def consume_stamina(state: PlayerState, amount: int = 10) -> bool:
    if state.stamina < amount:
        return False
    state.stamina -= amount
    return True


def add_to_barn(state: PlayerState, crop_name: str, amount: int) -> bool:
    for slot in state.barn:
        if slot.unlocked and slot.crop_name == crop_name and slot.amount + amount <= slot.cap:
            slot.amount += amount
            return True
    for slot in state.barn:
        if slot.unlocked and slot.crop_name is None and amount <= slot.cap:
            slot.crop_name = crop_name
            slot.amount = amount
            return True
    return False


def sale_price(state: PlayerState, crop_level: int, crop_name: str) -> tuple[int, int]:
    base = crop_level * 10
    pct = 0
    name, streak = state.same_crop_sale_streak
    if name == crop_name and streak >= 10:
        pct -= 10
    if state.scarcity_bonus_left.get(crop_name, 0) > 0:
        pct += 10
    return int(base * (100 + pct) / 100), pct
