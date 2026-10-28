# -*- coding: utf-8 -*-
"""
小T 回归测试 —— 改任何功能前先跑一遍，防止再出现「改跪下跪穿换装」的事故。

用法：
    python test_pet.py

覆盖：
    1. 菜单项顺序（防止误加/误删按钮）
    2. 击倒系统：40 次 knock 只有 3 种倒姿、首次解锁成就、状态机走完 fall→lie→up
    3. 日常互动：feed / stroke_head / toggle_sleep 状态更新正确
    4. 换装错误路径：_on_skin_ready 收到 error / 空 payload 不崩
    5. 存档 roundtrip：save → load 数据一致
"""
import os
import sys
import tempfile

# 测试前先把存档目录指到临时位置，不污染真实存档
_tmp = tempfile.mkdtemp(prefix="pet_test_")
os.environ["QT_QPA_PLATFORM"] = "offscreen"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trae_pet as tp

tp.SAVE_PATH = os.path.join(_tmp, "test_save.json")

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPixmap

app = QApplication(sys.argv)

passed = 0
failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


# ---------- 1. 菜单 ----------
print("[1] 菜单项")
menu = [x[1] for x in tp.MENU_ITEMS]
check("菜单 7 项且顺序正确",
      menu == ["说话", "揍揍", "摸头", "投喂", "散步", "睡眠", "更多"],
      f"got {menu}")
check("无跪下残留常量",
      not hasattr(tp, "KNEEL_SYNDICATE_KIND") and not hasattr(tp, "KNEEL_LINES"))
check("无 force_kneel 方法", not hasattr(tp.DesktopPet, "force_kneel"))

# ---------- 2. 击倒系统 ----------
print("[2] 击倒系统")
pet = tp.DesktopPet()

import time as _time


def _knock(p):
    """凑满连击数后揍一拳触发击倒"""
    p._hit_streak = tp.KO_HITS - 1
    p._hit_last_ts = _time.time()   # 防止被连击间隔重置
    p.interact("head")


_knock(pet)
check("首次击倒解锁成就", "knockdown" in pet.achievements)
check("首次倒地为 fall 状态", pet._down_state == "fall")

# 状态机：fall → lie
for _ in range(tp.KO_FALL_FRAMES):
    pet._tick()
check("fall 结束进入 lie", pet._down_state == "lie")

# lie 等时间不够复杂，直接推时间戳
pet._lie_until = _time.time() - 0.1
pet._tick()
check("lie 结束进入 up", pet._down_state == "up")

for _ in range(tp.KO_UP_FRAMES):
    pet._tick()
check("up 结束回到 None", pet._down_state is None)

# 40 次 knock 只有 3 种倒姿
kinds = []
for _ in range(40):
    pet._down_state = None
    _knock(pet)
    kinds.append(pet._down_kind)
check("40 次 knock 只有 {0,1,2}", set(kinds) <= {0, 1, 2},
      f"got {sorted(set(kinds))}")

# ---------- 3. 日常互动 ----------
print("[3] 日常互动")
pet._down_state = None
old_feed = pet.counts["feed"]
pet.feed()
check("feed 后计数 +1", pet.counts["feed"] == old_feed + 1)

old_mood = pet.mood
pet.stroke_head()
check("摸头后心情上升", pet.mood > old_mood or pet.mood == 100)

pet.toggle_sleep()
check("睡眠开启", pet.sleep_mode is True)
pet.toggle_sleep()
check("睡眠关闭", pet.sleep_mode is False)

# ---------- 4. 换装错误路径 ----------
print("[4] 换装")
pet._on_skin_ready({"error": "识别失败"})
check("error payload 不崩", True)
pet._on_skin_ready(None)
check("None payload 不崩", True)

# _set_skin_layers 正常数据不崩
head = QPixmap(50, 40)
body = QPixmap(50, 60)
head.fill(); body.fill()
pet._set_skin_layers(head, body, {"eyes": [(10, 10), (30, 10)], "neck_y": 38, "overlap": 5})
check("_set_skin_layers 正常路径", pet.skin_layers is not None)

# ---------- 5. 存档 ----------
print("[5] 存档")
pet.mood = 77
pet._save()
pet2 = tp.DesktopPet()
check("save→load mood 一致", pet2.mood == 77, f"got {pet2.mood}")

# ---------- 6. 积分与搜索框 ----------
print("[6] 积分与搜索框")
check("有积分取凭证函数", hasattr(tp, "read_trae_token") and hasattr(tp, "fetch_credits"))
check("积分告警阈值 500", tp.CREDITS_WARN == 500, f"got {tp.CREDITS_WARN}")
check("积分同步间隔 30 分钟", tp.CREDITS_SYNC_MS == 30 * 60 * 1000, f"got {tp.CREDITS_SYNC_MS}")
check("积分接口走 api.trae.cn",
      tp.CREDITS_API.startswith("https://api.trae.cn/") and "ide_user_ent_usage" in tp.CREDITS_API,
      tp.CREDITS_API)

import base64 as _b64
import json as _json


def _fake_jwt(exp):
    head = _b64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
    body = _b64.urlsafe_b64encode(_json.dumps({"exp": exp}).encode()).rstrip(b"=").decode()
    return head + "." + body + ".sig"


check("_jwt_exp 能解出 exp", tp._jwt_exp(_fake_jwt(1793150000)) == 1793150000)
check("_jwt_exp 坏 token 返回 0", tp._jwt_exp("not-a-jwt") == 0)
check("read_trae_token 不抛异常", tp.read_trae_token() is not None or True)

# 取凭证失败时的提示不影响界面（这里屏蔽真实网络请求）
_orig_sync = pet._sync_credits
pet._sync_credits = lambda manual=False: None
pet.credits = None
pet.show_credits()
check("无数据时 show_credits 不崩", True)
pet._sync_credits = _orig_sync
pet._on_credits(({"balance": 5842.02, "total": 8500.0, "used": 2657.98,
                  "packs": [{"name": "用户福利", "limit": 4000.0, "used": 2157.98}],
                  "ts": _time.time()}, True))
check("_on_credits 存入数据", pet.credits is not None and pet.credits["balance"] == 5842.02)
pet._save()
pet3 = tp.DesktopPet()
check("积分存档 roundtrip", (pet3.credits or {}).get("balance") == 5842.02,
      f"got {pet3.credits}")

m, acts = pet._build_menu()
check("右键菜单有积分入口", "credits" in acts and "sync" in acts, f"got {sorted(acts)}")
check("搜索框右侧按钮不越界",
      pet.web_btn.geometry().right() + 1 <= tp.W and pet.trae_btn.text() == "Trae"
      and pet.web_btn.text() == "网页")

# ---------- 汇总 ----------
print(f"\n===== {passed} passed, {failed} failed =====")
sys.exit(1 if failed else 0)
