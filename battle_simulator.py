"""
Tiny Card 战斗回合模拟器
基于《Tiny Card》战斗数值与逻辑计算文档
"""
import sys
import io
import random
import math
from dataclasses import dataclass, field
from typing import Optional

# Windows终端UTF-8支持
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8', errors='replace')

# ============================================================
#  常量定义
# ============================================================

CRIT_MULT_SINGLE = 1.75
CRIT_MULT_AOE = 1.3
ENERGY_PER_TURN = 3

# ============================================================
#  数据类
# ============================================================

@dataclass
class Attributes:
    STR: int = 5
    INT: int = 3
    TEN: int = 2
    LUCK: int = 0

    def crit_rate(self) -> float:
        """暴击率 = 7% + 2*LUCK%"""
        return 0.07 + 0.02 * self.LUCK


@dataclass
class Card:
    name: str
    category: str          # "physical" / "magic" / "defense"
    element: str = ""      # "thunder" / "ice" / "fire" / "nature" / ""
    base_damage: int = 0
    hits: int = 1
    target_mode: str = "single"  # single / dual / aoe / random / execute
    energy_cost: int = 1
    description: str = ""


@dataclass
class Entity:
    name: str
    max_hp: int
    hp: int = 0
    is_player: bool = False
    attrs: Optional[Attributes] = None
    # 状态
    defense: int = 0           # 当前格挡值
    broken: bool = False       # 破防状态
    broken_turns: int = 0
    frozen: bool = False
    frozen_turns: int = 0
    paralyzed: bool = False
    paralyzed_turns: int = 0
    burn_stacks: int = 0
    poison_stacks: int = 0
    magic_disabled: bool = False
    phys_disabled: bool = False
    # 连击追踪
    phys_combo: int = 0

    def __post_init__(self):
        if self.hp == 0:
            self.hp = self.max_hp

    @property
    def alive(self):
        return self.hp > 0

    def take_damage(self, dmg: int, source_name: str = "") -> int:
        """受到伤害，考虑格挡和破防"""
        actual_dmg = dmg
        if self.defense > 0:
            blocked = min(self.defense, actual_dmg)
            self.defense -= blocked
            actual_dmg -= blocked
            if blocked > 0:
                print(f"    格挡吸收 {blocked} 点伤害，剩余格挡 {self.defense}")
        if self.broken and actual_dmg > 0:
            # 破防不需要在这里乘，乘算在外层处理
            pass
        actual_dmg = max(0, actual_dmg)
        self.hp = max(0, self.hp - actual_dmg)
        if actual_dmg > 0:
            print(f"    {self.name} 受到 {actual_dmg} 点伤害 ({source_name})，HP: {self.hp}/{self.max_hp}")
        return actual_dmg

    def tick_status(self):
        """回合结束时的状态结算"""
        # 燃烧
        if self.burn_stacks > 0:
            burn_dmg = max(1, int(self.hp * (0.14 + 0.02 * (self.attrs.INT if self.attrs else 0))))
            self.hp = max(0, self.hp - burn_dmg)
            print(f"    {self.name} 燃烧损失 {burn_dmg} HP (层数:{self.burn_stacks})，HP: {self.hp}/{self.max_hp}")
            self.burn_stacks = max(0, self.burn_stacks - 1)
        # 中毒
        if self.poison_stacks > 0:
            poison_dmg = self.poison_stacks * 2
            self.hp = max(0, self.hp - poison_dmg)
            print(f"    {self.name} 中毒损失 {poison_dmg} HP (层数:{self.poison_stacks})，HP: {self.hp}/{self.max_hp}")
            self.poison_stacks -= 1
        # 冻结倒计时
        if self.frozen:
            self.frozen_turns -= 1
            if self.frozen_turns <= 0:
                self.frozen = False
                print(f"    {self.name} 解除冻结")
        # 麻痹倒计时
        if self.paralyzed:
            self.paralyzed_turns -= 1
            if self.paralyzed_turns <= 0:
                self.paralyzed = False
                print(f"    {self.name} 解除麻痹")
        # 破防倒计时
        if self.broken:
            self.broken_turns -= 1
            if self.broken_turns <= 0:
                self.broken = False
                print(f"    {self.name} 破防状态结束")


# ============================================================
#  卡牌库
# ============================================================

ALL_CARDS = {
    "劈砍": Card("劈砍", "physical", base_damage=7, target_mode="single", description="7点单体伤害"),
    "平砍": Card("平砍", "physical", base_damage=4, target_mode="dual", description="4/4/5多目标"),
    "连斩": Card("连斩", "physical", base_damage=3, hits=2, target_mode="single", description="3点*2"),
    "斩杀": Card("斩杀", "physical", target_mode="execute", description="8%阈值即死"),
    "雷魔法": Card("雷魔法", "magic", element="thunder", base_damage=9, target_mode="random", description="9点随机目标"),
    "冰魔法": Card("冰魔法", "magic", element="ice", base_damage=5, target_mode="single", description="5点单体"),
    "火魔法": Card("火魔法", "magic", element="fire", base_damage=3, hits=2, target_mode="dual", description="3点*2"),
    "自然魔法": Card("自然魔法", "magic", element="nature", base_damage=2, target_mode="aoe", description="2点AOE"),
    "格挡": Card("格挡", "defense", description="防御格挡"),
}


# ============================================================
#  敌人模板
# ============================================================

ENEMY_TEMPLATES = {
    "哥布林":    {"max_hp": 15, "actions": ["attack_3", "block_2"]},
    "小史莱姆":  {"max_hp": 4,  "actions": ["attack_1"]},
    "史莱姆":    {"max_hp": 7,  "actions": ["attack_2"]},
    "大史莱姆":  {"max_hp": 15, "actions": ["attack_3"], "split": True},
    "树妖":      {"max_hp": 18, "actions": ["poison_3", "attack_4"]},
    "骷髅小兵":  {"max_hp": 20, "actions": ["attack_4", "block_1"]},
    "骷髅骑士":  {"max_hp": 30, "actions": ["heavy_14", "block_4", "summon"], "elite": True,
                  "immunity": ["thunder", "nature"]},
    "巨魔":      {"max_hp": 45, "actions": ["multi_attack_3x7", "block_5", "ice_magic", "heavy_10"],
                  "elite": True},
}


# ============================================================
#  战斗引擎
# ============================================================

class BattleEngine:
    def __init__(self, player: Entity, deck: list[str], enemies: list[Entity],
                 magic_history: list[str] = None):
        self.player = player
        self.deck = deck          # 手牌名称列表
        self.enemies = enemies
        self.magic_history = magic_history or []
        self.turn = 0
        self.log = []

    def msg(self, text):
        print(text)
        self.log.append(text)

    # ---------- 伤害计算 ----------
    def calc_phys_damage(self, base: int) -> int:
        """物理伤害 = 基础 + STR加成"""
        return base + self.player.attrs.STR

    def calc_magic_damage(self, base: int) -> int:
        """魔法伤害 = 基础 + INT加成"""
        return base + self.player.attrs.INT

    def calc_block(self) -> int:
        """格挡值 = 7 + 0.5 * TEN"""
        return math.floor(7 + 0.5 * self.player.attrs.TEN)

    def broken_multiplier(self) -> float:
        """破防倍率 = 1.2 + 0.05 * STR"""
        return 1.2 + 0.05 * self.player.attrs.STR

    def check_crit(self) -> bool:
        return random.random() < self.player.attrs.crit_rate()

    # ---------- 魔法反应 ----------
    def check_magic_reaction(self, element: str, target: Entity):
        """检查魔法反应队列"""
        if not element:
            return
        self.magic_history.append(element)

        # 检查各种反应（按优先级）
        # 冻结: 冰+冰+冰
        if len(self.magic_history) >= 3:
            last3 = self.magic_history[-3:]
            if last3 == ["ice", "ice", "ice"]:
                self.msg(f"  >>> 魔法反应: 冻结！{target.name} 停止行动 2 回合")
                target.frozen = True
                target.frozen_turns = 2
                self.magic_history.clear()
                return

        # 燃烧: 火+自然
        if len(self.magic_history) >= 2:
            last2 = self.magic_history[-2:]
            if set(last2) == {"fire", "nature"}:
                burn_dmg_pct = 0.14 + 0.02 * self.player.attrs.INT
                self.msg(f"  >>> 魔法反应: 燃烧！{target.name} 获得燃烧效果 ({int(burn_dmg_pct*100)}%HP/回合)")
                target.burn_stacks += 1
                # 移除参与反应的元素
                self.magic_history.remove("fire")
                self.magic_history.remove("nature")
                return

        # 爆炸: 雷+火
        if len(self.magic_history) >= 2:
            last2 = self.magic_history[-2:]
            if set(last2) == {"fire", "thunder"}:
                coeff = 1.2 + 0.3 * self.player.attrs.INT
                # 前序元素伤害取基础值, 本次触发伤害取最近一次
                prev_dmg = 9 + self.player.attrs.INT  # 雷基础
                curr_dmg = 3 + self.player.attrs.INT  # 火基础
                explosion_dmg = int(0.8 * prev_dmg + coeff * curr_dmg)
                self.msg(f"  >>> 魔法反应: 爆炸！造成 {explosion_dmg} 点额外伤害")
                target.take_damage(explosion_dmg, "爆炸反应")
                self.magic_history.remove("fire")
                self.magic_history.remove("thunder")
                return

        # 麻痹: 雷+雷
        if len(self.magic_history) >= 2:
            last2 = self.magic_history[-2:]
            if last2 == ["thunder", "thunder"]:
                self.msg(f"  >>> 魔法反应: 麻痹！{target.name} 物理命中-45%，魔法反噬")
                target.paralyzed = True
                target.paralyzed_turns = 2
                self.magic_history.remove("thunder")
                self.magic_history.remove("thunder")
                return

        # 中毒: 自然+自然
        if len(self.magic_history) >= 2:
            last2 = self.magic_history[-2:]
            if last2 == ["nature", "nature"]:
                stacks = random.randint(7, 9) + self.player.attrs.INT
                self.msg(f"  >>> 魔法反应: 中毒！{target.name} 获得 {stacks} 层中毒")
                target.poison_stacks += stacks
                self.magic_history.remove("nature")
                self.magic_history.remove("nature")
                return

    # ---------- 连击追踪 ----------
    def track_phys_combo(self, target: Entity):
        """物理连击追踪：3次物理伤害判定后触发破防"""
        target.phys_combo += 1
        if target.phys_combo >= 3:
            target.broken = True
            target.broken_turns = 2
            mult = self.broken_multiplier()
            self.msg(f"  >>> 物理连击: {target.name} 进入破防状态！受到伤害 x{mult:.2f}")
            target.phys_combo = 0

    # ---------- 使用卡牌 ----------
    def play_card(self, card: Card, targets: list[Entity]):
        cost = card.energy_cost
        self.msg(f"\n  >> 使用 [{card.name}] (消耗{cost}能量)")

        if card.category == "defense":
            block_val = self.calc_block()
            self.player.defense += block_val
            self.msg(f"    获得 {block_val} 点格挡，当前格挡: {self.player.defense}")
            return

        for target in targets:
            if not target.alive:
                continue

            # 禁用检查
            if card.category == "physical" and self.player.phys_disabled:
                self.msg(f"    物理牌被禁用！")
                return
            if card.category == "magic" and self.player.magic_disabled:
                self.msg(f"    魔法牌被禁用！")
                return

            # 麻痹反噬(魔法)
            if card.category == "magic" and self.player.paralyzed:
                recoil = card.base_damage + (self.player.attrs.INT if card.category == "magic" else 0)
                self.player.hp = max(0, self.player.hp - recoil)
                self.msg(f"    麻痹反噬！玩家受到 {recoil} 点反噬伤害，HP: {self.player.hp}/{self.player.max_hp}")

            if card.target_mode == "execute":
                # 斩杀
                threshold = target.max_hp * 0.08
                if target.hp <= threshold:
                    self.msg(f"    >>> 斩杀触发！{target.name} HP({target.hp}) <= 8%({threshold:.0f})，即死！")
                    target.hp = 0
                    # 溅射
                    for other in self.enemies:
                        if other.alive and other != target:
                            splash = int(other.max_hp * 0.08 * 0.6)
                            other.hp = max(0, other.hp - splash)
                            self.msg(f"    溅射: {other.name} 受到 {splash} 点伤害")
                else:
                    self.msg(f"    {target.name} HP({target.hp}) > 8%({threshold:.0f})，斩杀未触发")
                continue

            # 计算伤害
            dmg = 0
            for hit_i in range(card.hits):
                if card.category == "physical":
                    raw = self.calc_phys_damage(card.base_damage)
                    dmg_type = "physical"
                else:
                    raw = self.calc_magic_damage(card.base_damage)
                    dmg_type = "magic"

                # 破防加成
                if target.broken and dmg_type == "physical":
                    raw = int(raw * self.broken_multiplier())

                # 暴击
                is_crit = self.check_crit()
                if is_crit:
                    mult = CRIT_MULT_AOE if card.target_mode == "aoe" else CRIT_MULT_SINGLE
                    raw = int(raw * mult)
                    self.msg(f"    暴击！(x{mult})")

                dmg += raw

            target.take_damage(dmg, card.name)

            # 物理连击追踪
            if card.category == "physical":
                self.track_phys_combo(target)

            # 魔法反应
            if card.category == "magic":
                self.check_magic_reaction(card.element, target)

    # ---------- 敌人行动 ----------
    def enemy_action(self, enemy: Entity):
        if not enemy.alive:
            return
        if enemy.frozen:
            self.msg(f"\n  {enemy.name} 被冻结，跳过行动")
            return

        # 麻痹: 命中率-45%
        if enemy.paralyzed and random.random() < 0.45:
            self.msg(f"\n  {enemy.name} 被麻痹，攻击落空！")
            return

        template = ENEMY_TEMPLATES.get(enemy.name, {})
        actions = template.get("actions", ["attack_3"])
        action = random.choice(actions)

        if action == "attack_3":
            self.msg(f"\n  {enemy.name} 攻击 (3点)")
            self.player.take_damage(3, enemy.name)
        elif action == "attack_1":
            self.msg(f"\n  {enemy.name} 攻击 (1点)")
            self.player.take_damage(1, enemy.name)
        elif action == "attack_2":
            self.msg(f"\n  {enemy.name} 攻击 (2点)")
            self.player.take_damage(2, enemy.name)
        elif action == "attack_4":
            self.msg(f"\n  {enemy.name} 攻击 (4点)")
            self.player.take_damage(4, enemy.name)
        elif action == "block_1":
            enemy.defense += 1
            self.msg(f"\n  {enemy.name} 格挡 +1 (总计:{enemy.defense})")
        elif action == "block_2":
            enemy.defense += 2
            self.msg(f"\n  {enemy.name} 格挡 +2 (总计:{enemy.defense})")
        elif action == "block_4":
            enemy.defense += 4
            self.msg(f"\n  {enemy.name} 格挡 +4 (总计:{enemy.defense})")
        elif action == "block_5":
            enemy.defense += 5
            self.msg(f"\n  {enemy.name} 格挡 +5 (总计:{enemy.defense})")
        elif action == "heavy_14":
            self.msg(f"\n  {enemy.name} 重击 (14点)")
            self.player.take_damage(14, enemy.name)
        elif action == "heavy_10":
            self.msg(f"\n  {enemy.name} 重击 (10点)")
            self.player.take_damage(10, enemy.name)
        elif action == "multi_attack_3x7":
            self.msg(f"\n  {enemy.name} 3段攻击 (7/段)")
            for i in range(3):
                self.player.take_damage(7, f"{enemy.name} 第{i+1}段")
        elif action == "poison_3":
            stacks = random.randint(7, 9) + self.player.attrs.INT
            self.player.poison_stacks += stacks
            self.msg(f"\n  {enemy.name} 施加中毒 {stacks} 层")
        elif action == "ice_magic":
            self.msg(f"\n  {enemy.name} 冰魔法 (5点)")
            self.player.take_damage(5, enemy.name)
        elif action == "summon":
            self.msg(f"\n  {enemy.name} 召唤骷髅小兵！")

    # ---------- 选择目标 ----------
    def select_targets(self, card: Card) -> list[Entity]:
        alive = [e for e in self.enemies if e.alive]
        if not alive:
            return []

        if card.target_mode == "aoe":
            return alive
        elif card.target_mode == "random":
            return [random.choice(alive)]
        elif card.target_mode == "dual" and len(alive) >= 2:
            return [alive[0], alive[1]]
        else:
            # 单体: 优先选HP最高的
            return [max(alive, key=lambda e: e.hp)]

    # ---------- 回合 ----------
    def run_turn(self):
        self.turn += 1
        energy = ENERGY_PER_TURN
        self.player.defense = 0  # 格挡每回合重置

        self.msg(f"\n{'='*50}")
        self.msg(f"  第 {self.turn} 回合 | 玩家 HP: {self.player.hp}/{self.player.max_hp} | 能量: {energy}")
        alive_enemies = [e for e in self.enemies if e.alive]
        for e in alive_enemies:
            def_info = f" [格挡:{e.defense}]" if e.defense > 0 else ""
            status = []
            if e.broken: status.append("破防")
            if e.burn_stacks > 0: status.append(f"燃烧x{e.burn_stacks}")
            if e.poison_stacks > 0: status.append(f"中毒x{e.poison_stacks}")
            if e.frozen: status.append("冻结")
            if e.paralyzed: status.append("麻痹")
            s_info = f" ({', '.join(status)})" if status else ""
            self.msg(f"  敌方: {e.name} HP: {e.hp}/{e.max_hp}{def_info}{s_info}")
        self.msg(f"{'='*50}")

        # 玩家回合: 出牌
        if self.player.frozen:
            self.msg(f"\n  玩家被冻结，跳过行动")
        else:
            # 自动出牌策略: 优先高伤害，血量低时用格挡
            hand = list(self.deck)
            random.shuffle(hand)
            for card_name in hand:
                if energy <= 0:
                    break
                card = ALL_CARDS.get(card_name)
                if not card:
                    continue
                if card.energy_cost > energy:
                    continue

                # 低血量时优先格挡
                if self.player.hp < self.player.max_hp * 0.3 and card.category == "defense":
                    self.play_card(card, [])
                    energy -= card.energy_cost
                    continue

                targets = self.select_targets(card)
                if targets:
                    self.play_card(card, targets)
                    energy -= card.energy_cost

        # 状态结算 (回合结束)
        self.msg(f"\n  --- 回合结束状态结算 ---")
        for e in self.enemies:
            if e.alive:
                e.tick_status()
        self.player.tick_status()

        # 敌方回合
        self.msg(f"\n  --- 敌方回合 ---")
        for enemy in alive_enemies:
            if enemy.alive:
                self.enemy_action(enemy)

        # 死亡检查
        dead = [e for e in self.enemies if not e.alive]
        for e in dead:
            self.msg(f"\n  {e.name} 被消灭！")

        return self.player.alive and any(e.alive for e in self.enemies)

    # ---------- 战斗入口 ----------
    def run_battle(self):
        self.msg(f"\n{'#'*60}")
        self.msg(f"  战斗开始！")
        self.msg(f"  玩家: HP={self.player.max_hp} | STR={self.player.attrs.STR} "
                 f"INT={self.player.attrs.INT} TEN={self.player.attrs.TEN} LUCK={self.player.attrs.LUCK}")
        self.msg(f"  卡组: {', '.join(self.deck)}")
        self.msg(f"  敌方: {', '.join(e.name+'('+str(e.max_hp)+'HP)' for e in self.enemies)}")
        self.msg(f"{'#'*60}")

        while True:
            continue_battle = self.run_turn()
            if not continue_battle:
                break
            if self.turn >= 20:
                self.msg("\n  达到最大回合数上限！")
                break

        self.msg(f"\n{'='*60}")
        if not self.player.alive:
            self.msg(f"  战斗失败！玩家阵亡。")
        elif not any(e.alive for e in self.enemies):
            self.msg(f"  战斗胜利！所有敌人被消灭。共 {self.turn} 回合。")
        else:
            self.msg(f"  战斗结束（超时）。")
        self.msg(f"{'='*60}")
        return self.player.alive


# ============================================================
#  交互式设置
# ============================================================

def input_int(prompt, default):
    val = input(f"{prompt} (默认:{default}): ").strip()
    return int(val) if val else default


def choose_deck() -> list[str]:
    print("\n可用卡牌:")
    for i, (name, card) in enumerate(ALL_CARDS.items(), 1):
        print(f"  {i}. {name:6s} [{card.category:8s}] {card.description}")
    print("\n输入卡牌编号（空格分隔，如: 1 3 5 8）")
    raw = input("选择卡组 (默认: 1 3 5 8 即劈砍/连斩/斩杀/格挡): ").strip()
    if not raw:
        return ["劈砍", "连斩", "斩杀", "格挡"]
    indices = [int(x) for x in raw.split()]
    names = list(ALL_CARDS.keys())
    return [names[i-1] for i in indices if 1 <= i <= len(names)]


def choose_enemies() -> list[Entity]:
    print("\n可用敌人:")
    names = list(ENEMY_TEMPLATES.keys())
    for i, name in enumerate(names, 1):
        t = ENEMY_TEMPLATES[name]
        elite = " [精英]" if t.get("elite") else ""
        print(f"  {i}. {name:8s} {t['max_hp']}HP{elite}")
    raw = input("选择敌人编号（空格分隔）(默认: 1 即哥布林): ").strip()
    if not raw:
        return [Entity("哥布林", 15)]
    indices = [int(x) for x in raw.split()]
    return [Entity(names[i-1], ENEMY_TEMPLATES[names[i-1]]["max_hp"]) for i in indices if 1 <= i <= len(names)]


# ============================================================
#  快速演示模式
# ============================================================

def demo():
    """预设演示：玩家 vs 多种敌人"""
    print("\n" + "="*60)
    print("  Tiny Card 战斗模拟器 - 快速演示")
    print("="*60)

    attrs = Attributes(STR=5, INT=3, TEN=2, LUCK=0)
    player = Entity("勇者", max_hp=30 + attrs.STR * 3, is_player=True, attrs=attrs)
    deck = ["劈砍", "连斩", "斩杀", "格挡", "冰魔法", "火魔法"]

    # 演示1: vs 哥布林
    print("\n--- 演示1: vs 哥布林 x2 ---")
    enemies = [Entity("哥布林", 15), Entity("哥布林", 15)]
    engine = BattleEngine(player, deck, enemies)
    engine.run_battle()

    # 重置玩家
    player = Entity("勇者", max_hp=30 + attrs.STR * 3, is_player=True, attrs=attrs)

    # 演示2: vs 骷髅小兵 + 树妖
    print("\n\n--- 演示2: vs 骷髅小兵 + 树妖 ---")
    enemies = [Entity("骷髅小兵", 20), Entity("树妖", 18)]
    deck2 = ["劈砍", "连斩", "自然魔法", "火魔法", "格挡", "雷魔法"]
    engine = BattleEngine(player, deck2, enemies)
    engine.run_battle()

    # 重置玩家
    player = Entity("勇者", max_hp=30 + attrs.STR * 3, is_player=True, attrs=attrs)
    attrs2 = Attributes(STR=5, INT=6, TEN=2, LUCK=0)

    # 演示3: 魔法反应 - vs 大史莱姆
    print("\n\n--- 演示3: 魔法反应构建 (高INT) vs 大史莱姆 ---")
    player = Entity("元素师", max_hp=30 + attrs2.STR * 3, is_player=True, attrs=attrs2)
    enemies = [Entity("大史莱姆", 15)]
    deck3 = ["火魔法", "自然魔法", "雷魔法", "冰魔法", "冰魔法", "格挡"]
    engine = BattleEngine(player, deck3, enemies)
    engine.run_battle()


# ============================================================
#  主菜单
# ============================================================

def main():
    print("""
    ╔══════════════════════════════════════════════╗
    ║      Tiny Card 战斗回合模拟器 v1.0           ║
    ║  基于《Tiny Card》战斗数值与逻辑计算文档     ║
    ╚══════════════════════════════════════════════╝
    """)
    print("  1. 快速演示（预设战斗）")
    print("  2. 自定义战斗")
    print("  3. 公式速查")
    choice = input("\n请选择 (1/2/3): ").strip()

    if choice == "3":
        print("""
    ═══ 公式速查 ═══
    物理伤害 = 基础值 + STR
    魔法伤害 = 基础值 + INT
    格挡值   = 7 + 0.5 * TEN
    暴击率   = 7% + 2*LUCK%
    暴击倍率 = 单体x1.75 / AOE x1.3
    破防倍率 = 1.2 + 0.05 * STR
    燃烧伤害 = (14% + 2%*INT) * 当前HP
    爆炸伤害 = 0.8*前序 + (1.2+0.3*INT)*本次
    中毒层数 = rand(7,9) + INT (每回合层数*2伤害,-1层)
    连击触发 = 3次物理伤害判定后目标破防
    物理连击额外段数 = 每3点STR附带n段(每段75%)
        """)
        return

    if choice == "2":
        print("\n--- 自定义玩家属性 ---")
        STR = input_int("力量(STR)", 5)
        INT = input_int("智力(INT)", 3)
        TEN = input_int("坚韧(TEN)", 2)
        LUCK = input_int("幸运(LUCK)", 0)
        hp = input_int("最大HP", 30 + STR * 3)

        attrs = Attributes(STR=STR, INT=INT, TEN=TEN, LUCK=LUCK)
        player = Entity("玩家", max_hp=hp, is_player=True, attrs=attrs)

        deck = choose_deck()
        enemies = choose_enemies()

        engine = BattleEngine(player, deck, enemies)
        engine.run_battle()
    else:
        demo()

    try:
        input("\n按回车退出...")
    except (EOFError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    main()
