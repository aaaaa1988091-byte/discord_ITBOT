import unittest
from game_logic import PlayerState, add_to_barn, sale_price


class GameLogicTests(unittest.TestCase):
    def test_add_to_barn_uses_empty_slot(self):
        s = PlayerState()
        s.init_default_layout()
        ok = add_to_barn(s, "小麥", 5)
        self.assertTrue(ok)
        self.assertEqual(sum(x.amount for x in s.barn), 5)

    def test_sale_price_penalty_and_bonus(self):
        s = PlayerState()
        s.same_crop_sale_streak = ("小麥", 10)
        s.scarcity_bonus_left["小麥"] = 1
        unit, pct = sale_price(s, crop_level=1, crop_name="小麥")
        self.assertEqual(unit, 10)
        self.assertEqual(pct, 0)


if __name__ == "__main__":
    unittest.main()
