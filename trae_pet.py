# -*- coding: utf-8 -*-
"""
小T · Trae 桌面宠物（养成版）
一只住在桌面上的 AI 小机器人：会眨眼、会溜达、会说话，能摸头、戳肚子、投喂，
有心情/饱食度/等级养成、成就系统、深夜静默和本地存档。

运行：python trae_pet.py   （或双击 start_pet.bat）
依赖：PyQt5  (pip install PyQt5)
"""
import base64
import datetime
import glob
import json
import math
import os
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from PyQt5.QtCore import QPoint, QRectF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import (QColor, QCursor, QFont, QLinearGradient, QPainter,
                         QPainterPath, QPen, QPixmap, QPolygonF, QRadialGradient)
from PyQt5.QtWidgets import (QApplication, QFileDialog, QLineEdit, QMenu,
                             QPushButton, QWidget)

W, H = 300, 330
CX = W // 2


def _asset_base():
    """资源目录：开发时是脚本所在目录，PyInstaller frozen 时是 sys._MEIPASS。"""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def _save_base():
    """可写目录：存档放 exe 同级目录（frozen 后）或脚本目录（开发时）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


SAVE_PATH = os.path.join(_save_base(), "pet_save.json")

LINES = [
    "嗨，我是小T，你的编程搭子！",
    "今天也要写出优雅的代码哦",
    "记得 Ctrl+S，别让灵感丢了",
    "有 BUG 交给我，你先去倒杯水",
    "需求再离谱，也能聊聊看",
    "摸鱼不算偷懒，叫灵感充电",
    "这段代码……还能再优化一下",
    "你的桌面，现在归我巡逻啦",
    "要一起 debug 到深夜吗？",
    "编译通过的感觉，真好呀",
]

ZONE_LINES = {
    "antenna": ["呜……天线要断了啦……", "别揪天线嘛，那是我的信号源……", "好痛……我要没信号了……"],
    "head": ["呜呜呜，头好痛……", "我错了还不行嘛……", "别打头，会变笨的……", "呜……要起包了……"],
    "belly": ["肚子……肚子要扁了……", "呜呜，刚吃的饼干要吐出来了……", "轻点嘛……我肚子疼……"],
    "feet": ["脚脚疼……", "呜……那是我的避震器……", "别踩脚脚，求你了……"],
}

PICK_LINES = ["嘿，抓到我了～", "放我下来啦，谢谢搭乘", "飞高高！"]
HUNGRY_LINES = ["肚子咕咕叫……求投喂数据饼干！", "电量不足，来块数据饼干吧"]

ACHIEVEMENTS = {
    "first_pat": "初次挨揍",
    "pat10": "铁头功（被揍头 10 次）",
    "first_drag": "举高高",
    "drag10": "空中飞人（拎起 10 次）",
    "first_feed": "第一块数据饼干",
    "feed10": "投喂大师（10 次）",
    "night": "深夜陪伴",
    "lv5": "好感度 LV5",
    "jump": "蹦蹦跳跳",
    "dizzy": "被揍晕啦",
    "knockdown": "被打趴下（连挨 10 下）",
}

LEVELS = [0, 20, 50, 100, 180, 300, 500]

# 悬停菜单：底部小圆按钮，鼠标移上来就展开
MENU_ITEMS = [("talk", "说话"), ("pat", "揍揍"), ("stroke", "摸头"), ("feed", "投喂"),
              ("walk", "散步"), ("sleep", "睡眠"), ("more", "更多")]
BTN_R, BTN_GAP, MENU_CY = 12, 6, 315
JUMP_FRAMES = 22

# ---------------- 击倒系统 ----------------
KO_HITS = 10                 # 连续被击中多少次倒地
KO_STREAK_GAP = 3.5          # 超过这么久没挨揍就重置连击
KO_FALL_FRAMES = 14          # 倒下动画帧数
KO_UP_FRAMES = 22            # 爬起动画帧数
KO_LIE_SECONDS = 5.0         # 躺在地上多久后爬起
KO_PAD_X = 180               # 倒地时窗口向右临时扩展：够长身体横躺，头不被裁
KO_PAD_B = 58                # 倒地时窗口向下临时扩展
KO_LEFT_SHIFT = 125          # 左倒＝右倒的镜像，整体右移这么多才不会被窗口左边裁掉
KO_LINES = [
    # 0 向右侧倒
    ["呜……右边的地好硬……", "我、我向右倒下了……", "这一拳……眼前一黑……"],
    # 1 向左侧倒（镜像）
    ["呜哇……往左边倒了……", "左舷中弹！我倒……", "天旋地转……左边着地了……"],
    # 2 脸朝下趴倒
    ["呜……被压成小T饼了……", "脸、脸先着地了……", "扁了扁了……谁来把我铲起来……"],
]
KO_GETUP_LINES = ["呼……我、我还能行……", "下次……下次我一定躲开……", "呜……头还是晕的……"]


# ---- 菜单按钮台词池（每个按钮随机挑一句） ----
STROKE_LINES = ["嘿嘿……好舒服……", "再摸摸嘛～", "唔……被摸头了，好幸福……",
                "头发都要被你摸秃啦"]
WALK_START_LINES = ["出去溜达一圈～", "走走走，巡逻桌面！", "活动活动筋骨～"]
WALK_STOP_LINES = ["那我先歇歇脚", "逛累啦，歇一会儿", "原地待命，听你指挥～"]
SLEEP_LINES = ["那我先睡一会儿……晚安……", "眼皮开始打架了……Zzz", "充电中……请勿打扰……"]
WAKE_LINES = ["睡醒啦！精神满满的～", "唔……这一觉睡得好香……", "充好电了，满血复活！"]

# 眼睛盯鼠标：idle 立绘上两眼中心的 widget 坐标（实测）
EYE_POS = ((121, 178), (173, 178))

# ---------------- Trae 积分监控 ----------------
# 凭证来自浏览器 localStorage 里的 Cloud-IDE-Token（QQ 浏览器/Chrome/Edge 均可）
CREDITS_TOKEN_KEY = "Cloud-IDE-Token"
CREDITS_API = "https://api.trae.cn/trae/api/v2/pay/ide_user_ent_usage"
# 该接口会校验 UA 指纹：必须与浏览器一致，否则一律 401
CREDITS_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/138.0.7204.0 Safari/537.36")
CREDITS_WARN = 500                    # 余额低于这个值主动提醒
CREDITS_SYNC_MS = 30 * 60 * 1000      # 后台自动同步间隔（30 分钟）
CREDITS_LOW_LINES = ["积分快见底啦，省着点用……", "余额不多了哦，要不要去签到领一点？",
                     "钱包要空了，记得补积分呀"]
CREDITS_DOWN_LINES = ["涨啦！积分到账～", "有新积分进来了，收好～", "余额往上走了，开心！"]
CREDITS_UP_LINES = ["积分被吃掉了一些……", "刚才那波消耗不小呀", "积分在减少，注意节奏哦"]
CREDITS_ERR_LINES = ["没拿到积分数据……浏览器可能没登录 trae.cn", "读不到凭证，先在浏览器里登录一下 trae.cn 吧",
                     "同步失败了，等下再试试～"]

# 搜索框右侧「Trae」按钮：唤起本机 Trae IDE
TRAE_SCHEME = "trae-cn://"
TRAE_EXE = r"D:\Program Files\Trae CN\Trae CN.exe"


def _browser_storage_dirs():
    """可能存有 trae.cn localStorage 的 leveldb 目录（QQ 浏览器 / Chrome / Edge，含多 profile）。"""
    local = os.environ.get("LOCALAPPDATA")
    roots = [os.path.join(local, r"Tencent\QQBrowser\User Data"),
             os.path.join(local, r"Google\Chrome\User Data"),
             os.path.join(local, r"Microsoft\Edge\User Data")]
    dirs = []
    for r in roots:
        dirs.extend(glob.glob(os.path.join(r, "*", "Local Storage", "leveldb")))
    return dirs


_JWT_RE = re.compile(rb"eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")


def _jwt_exp(tok):
    """取 JWT 的 exp（秒级时间戳）；解析失败返回 0。"""
    try:
        p = tok.split(".")[1]
        p += "=" * (-len(p) % 4)
        return int(json.loads(base64.urlsafe_b64decode(p)).get("exp") or 0)
    except (ValueError, TypeError, KeyError, IndexError):
        return 0


def read_trae_token():
    """从浏览器 localStorage 的 leveldb 里取 trae.cn 的 Cloud-IDE-Token（JWT）。

    浏览器用的是追加写的日志文件，同一个 key 会留下历史值的碎片，
    而且多个浏览器可能共存，所以按 exp 取最新那个，而不是看文件时间。
    """
    best = None                      # (exp, token)
    for d in _browser_storage_dirs():
        try:
            files = glob.glob(os.path.join(d, "*.ldb")) + glob.glob(os.path.join(d, "*.log"))
        except OSError:
            continue
        for fp in files:
            try:
                data = open(fp, "rb").read()
            except OSError:
                continue            # 浏览器正在写，跳过这个文件
            if CREDITS_TOKEN_KEY.encode() not in data:
                continue
            for m in _JWT_RE.findall(data):
                tok = m.decode("ascii", "ignore")
                e = _jwt_exp(tok)
                if best is None or e > best[0]:
                    best = (e, tok)
    return best[1] if best else None


def fetch_credits(timeout=15):
    """拉取 Trae 积分余额。成功返回 dict，失败抛异常。"""
    token = read_trae_token()
    if not token:
        raise RuntimeError("未找到 Cloud-IDE-Token，请先在浏览器登录 trae.cn")
    if _jwt_exp(token) < time.time():
        raise RuntimeError("浏览器里的登录凭证过期了，去 trae.cn 刷新一下")
    req = urllib.request.Request(
        CREDITS_API, data=b'{"require_usage": true}', method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Cloud-IDE-JWT " + token,
                 "User-Agent": CREDITS_UA,
                 "Origin": "https://www.trae.cn",
                 "Referer": "https://www.trae.cn/"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        d = json.loads(resp.read().decode("utf-8", "ignore"))
    summ = d.get("usage_summary") or {}
    total = float(summ.get("total_amount") or 0)
    used = float(summ.get("consumed_amount") or 0)
    packs = []
    for p in d.get("user_entitlement_pack_list") or []:
        q = (p.get("entitlement_base_info") or {}).get("quota") or {}
        limit = float(q.get("credits_limit") or 0)
        if limit <= 0:
            continue
        packs.append({"name": p.get("group_name") or p.get("display_desc") or "积分包",
                      "limit": limit,
                      "used": float((p.get("usage") or {}).get("credits_amount") or 0)})
    return {"balance": round(total - used, 2), "total": total,
            "used": round(used, 2), "packs": packs, "ts": time.time()}


# ---------------- 性格系统 ----------------
PERSONALITIES = {
    "sunny": {
        "name": "小太阳", "talk_boost": 1.0, "heart_bonus": 0, "walk_bias": 1.0,
        "lines": ["今天也是元气满满的一天！", "有我在，bug 都绕道走～",
                  "你笑起来，代码都变好看啦", "加油加油，你最棒啦！", "阳光、代码、还有你，完美～"],
        "zones": {"head": ["呜哇……小太阳被你打熄了……", "好痛……阳光都黯淡了……"],
                  "belly": ["肚子痛痛……阳光漏出来了……"]},
        "feed": ["吧唧吧唧，这块饼干有阳光的味道！", "唔唔，能量满格啦！", "甜甜的，今天运气都会变好～"],
        "pick": ["举高高！像小太阳升起～"],
        "hover": ["你来啦！今天也要开心哦", "看到你就有好心情～"],
        "greet": "小太阳已上线，今天也要元气满满哦",
    },
    "clingy": {
        "name": "粘人精", "talk_boost": 1.35, "heart_bonus": 2, "walk_bias": 0.7,
        "lines": ["你去哪儿我就去哪儿～", "陪我多待一会儿嘛", "不许偷偷关掉我哦",
                  "你不在的时候，我数了 832 只羊", "抱抱我嘛，就一下下"],
        "zones": {"head": ["呜呜……你不要我了吗……", "我会乖乖听话的，别打了……"],
                  "belly": ["肚子好痛……抱抱我嘛……"], "feet": ["脚脚痛……不跟你跑了……"]},
        "feed": ["你喂的饼干，是世界上最好吃的！", "还要还要……再喂我一块嘛", "被你投喂的感觉，好幸福……"],
        "pick": ["被拎着也好幸福，因为是你拎的～"],
        "hover": ["终于来看我啦！我都想你了", "别走别走，再陪我三秒钟"],
        "greet": "你来啦！我等你好久好久了～",
    },
    "naughty": {
        "name": "淘气包", "talk_boost": 1.1, "heart_bonus": 0, "walk_bias": 1.6,
        "lines": ["嘿嘿，刚把你的图标藏起来了一个（骗你的）", "略略略，来抓我呀",
                  "我给你的代码加了点料——是糖", "桌面巡逻队长在此！", "嘘，我在密谋一件大事"],
        "zones": {"head": ["呜哇！我错了还不行嘛……", "哇啊，被偷袭了……好痛……"],
                  "belly": ["呜呜，我认输……别打了……", "你赢了……我肚子好痛……"],
                  "antenna": ["哔哔！天线被打歪了啦……呜……"], "feet": ["呜呜，我的涡轮增压器漏油了……"]},
        "feed": ["唔！……才、才不是因为好吃才吃的，哼", "咔嚓咔嚓……再来一块也不是不行", "这饼干归我了，不许抢！"],
        "pick": ["放我下来！……再飞一圈也行"],
        "hover": ["被我发现了！你在偷看我", "盯——我也盯回去"],
        "greet": "淘气包驾到！今天搞点什么事呢～",
    },
    "drama": {
        "name": "小戏精", "talk_boost": 1.25, "heart_bonus": 1, "walk_bias": 0.9,
        "lines": ["哦！这光标划过的弧度，堪称艺术", "命运让我们在这块屏幕上相遇……",
                  "我在这片桌面上，演着独角戏等你", "此时此刻，应当有掌声", "为你，我愿演一辈子的桌宠"],
        "zones": {"head": ["啊——这一拳打得我眼泪都出来了（真的）", "这一幕太残忍了……求导演喊卡……"],
                  "belly": ["哦！你击中了我的软肋……真的好痛……"]},
        "feed": ["这饼干……是爱的味道！（咀嚼声请自行想象）", "啊，美味的馈赠！我受宠若惊", "此等美味，应当配一段独白"],
        "pick": ["飞起来了！这就是自由的感觉吗！"],
        "hover": ["观众来了！那我要开始表演了", "你凝视我的眼神，像聚光灯"],
        "greet": "灯光！音乐！小戏精登场——",
    },
}
PERSONA_ORDER = ["sunny", "clingy", "naughty", "drama"]

# 各性格的「求关注」台词
PERSONA_NEED = {
    "sunny": ["有点安静呢，陪我晒会儿太阳吧", "要不要一起活动活动筋骨？"],
    "clingy": ["你都好久没理我了……", "人家想你了嘛，过来一下下"],
    "naughty": ["无聊死了！来点刺激的！", "喂——还活着吗？陪我玩！"],
    "drama": ["独角戏演久了，也需要观众呀", "这舞台，未免太冷清了……"],
}

# 主动问候（按小时）
HOUR_GREETS = {
    7: "早上好！新的一天，代码在等你～",
    9: "上午好呀，进入工作状态了吗？",
    12: "中午啦，先去吃饭吧，电脑我帮你看",
    14: "午后犯困时间，要不要站起来走走？",
    18: "傍晚啦，今天辛苦你了！",
    21: "晚上好，加班别太晚哦",
    23: "很晚了，早点休息呀",
}

# WMO 天气码 → 中文
WMO = {0: "晴", 1: "多云间晴", 2: "多云", 3: "阴", 45: "有雾", 48: "有雾",
       51: "毛毛雨", 53: "毛毛雨", 55: "毛毛雨", 61: "小雨", 63: "中雨",
       65: "大雨", 66: "冻雨", 67: "冻雨", 71: "小雪", 73: "中雪", 75: "大雪",
       77: "雪", 80: "阵雨", 81: "阵雨", 82: "暴雨", 85: "阵雪", 86: "阵雪",
       95: "雷雨", 96: "雷雨", 99: "雷雨"}
RAINY = {51, 53, 55, 61, 63, 65, 66, 67, 71, 73, 75, 77,
         80, 81, 82, 85, 86, 95, 96, 99}


# ---------------- 换装工坊：类型识别 / 真人Q化 / 身体部位补全 ----------------
_YUNET_FP = os.path.join(_asset_base(), "pet_art", "yunet.onnx")
_YUNET_TRIED = {"done": False}


def _sf_yunet_path():
    """首次换装时下载 YuNet 人脸模型（约230KB），失败则走肤色兜底。"""
    if os.path.exists(_YUNET_FP):
        return _YUNET_FP                     # 本地已有模型，直接用（不联网）
    if _YUNET_TRIED["done"]:
        return None
    _YUNET_TRIED["done"] = True
    try:
        req = urllib.request.Request(
            "https://github.com/opencv/opencv_zoo/raw/main/models/"
            "face_detection_yunet/face_detection_yunet_2023mar.onnx",
            headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=15).read()
        if len(data) > 100000:
            os.makedirs(os.path.dirname(_YUNET_FP), exist_ok=True)
            with open(_YUNET_FP, "wb") as f:
                f.write(data)
            return _YUNET_FP
    except Exception:
        pass
    return None


def _sf_detect_face(arr):
    """最大人脸框 + 双眼坐标；优先 YuNet（精确），失败用肤色团块兜底。
    返回 (box, eyes, precise)；precise=True 表示 YuNet 检出（真人脸可信度高）。"""
    import cv2
    import numpy as np
    h, w = arr.shape[:2]
    fp = _sf_yunet_path()
    if fp:
        try:
            det = cv2.FaceDetectorYN_create(fp, "", (w, h), 0.6, 0.3, 5000)
            _, faces = det.detect(cv2.cvtColor(arr, cv2.COLOR_RGB2BGR))
            if faces is not None and len(faces):
                f = max(faces, key=lambda r: r[2] * r[3])
                box = tuple(int(v) for v in f[:4])
                eyes = [(int(f[4]), int(f[5])), (int(f[6]), int(f[7]))]
                return box, eyes, True
        except Exception:
            pass
    # 肤色团块启发式：在上半部找最大肤色块当脸
    try:
        ycrcb = cv2.cvtColor(arr, cv2.COLOR_RGB2YCrCb)
        m = cv2.inRange(ycrcb, np.array([0, 135, 85], np.uint8),
                        np.array([255, 180, 135], np.uint8))
        m[int(h * 0.62):, :] = 0
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        n, _, stats, _ = cv2.connectedComponentsWithStats(m)
        best, min_area = None, h * w * 0.015
        for i in range(1, n):
            x, y, cw, ch, a2 = stats[i]
            if a2 > min_area and 0.35 < cw / max(1, ch) < 2.6:
                best, min_area = (x, y, cw, ch), a2
        if best:
            x, y, cw, ch = best
            return (x, y, cw, ch), [(x + 0.32 * cw, y + 0.42 * ch),
                                    (x + 0.68 * cw, y + 0.42 * ch)], False
    except Exception:
        pass
    return None


def _sf_remove_bg_flood(img):
    """纯色背景（动漫图常见）→ 边缘种子 floodfill 抠图"""
    import numpy as np
    from PIL import Image, ImageDraw
    img = img.convert("RGBA")
    w, h = img.size
    seeds = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
             (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]
    for s in seeds:
        try:
            ImageDraw.floodfill(img, s, (255, 0, 255, 255), thresh=48)
        except Exception:
            pass
    a = np.array(img)
    m = ((a[:, :, 0] == 255) & (a[:, :, 1] == 0) & (a[:, :, 2] == 255)) | (a[:, :, 3] < 12)
    a[m] = (0, 0, 0, 0)
    return Image.fromarray(a, "RGBA")


def _sf_remove_bg_photo(arr, face):
    """真人照片 → grabCut 主体抠图（居中大矩形，全身照也不会被截断）"""
    import cv2
    import numpy as np
    from PIL import Image
    h, w = arr.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    rect = (int(w * 0.04), int(h * 0.03), int(w * 0.92), int(h * 0.94))
    cv2.grabCut(cv2.cvtColor(arr, cv2.COLOR_RGB2BGR), mask, rect, bgd, fgd, 4,
                cv2.GC_INIT_WITH_RECT)
    alpha = np.where((mask == cv2.GC_BGD) | (mask == cv2.GC_PR_BGD), 0, 255).astype(np.uint8)
    alpha = cv2.erode(alpha, np.ones((3, 3), np.uint8), iterations=1)
    alpha = cv2.GaussianBlur(alpha, (5, 5), 0)
    # --- 关键修复：inpaint 掉 alpha 边缘的背景色 RGB ---
    # grabCut 的 alpha 边缘（半透明带）的 RGB 仍是原图背景色（白墙/灰纸），
    # resize/cartoonify 时背景色渗入主体 → 最终叠加成黑/灰边框。
    # 用 inpaint 把 alpha<200 的像素的 RGB 用周围主体像素填充，根除 background bleed。
    arr = arr.copy()
    inpaint_mask = (alpha < 220).astype(np.uint8) * 255
    if inpaint_mask.any():
        for c in range(3):
            arr[:, :, c] = cv2.inpaint(arr[:, :, c], inpaint_mask, 3, cv2.INPAINT_TELEA)
    return Image.fromarray(np.dstack([arr, alpha]), "RGBA")


def _sf_cartoonify(rgba):
    """真人照片 → 卡通化（平滑 + 色块量化 + 描边 + 提饱和）"""
    import cv2
    import numpy as np
    from PIL import Image
    a = np.array(rgba)
    rgb, alpha = a[:, :, :3], a[:, :, 3]
    smooth = cv2.bilateralFilter(rgb, 9, 110, 110)
    q = (smooth // 26) * 26 + 13
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.adaptiveThreshold(cv2.medianBlur(gray, 5), 255,
                                  cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 9, 8)
    out = cv2.bitwise_and(q, q, mask=edges)
    hsv = cv2.cvtColor(out, cv2.COLOR_RGB2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * 1.18, 0, 255)
    out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)
    return Image.fromarray(np.dstack([out, alpha]), "RGBA")


def _sf_draw_cartoon_body(head_w):
    """画一个可爱的卡通身体：椭圆身体 + 两只小手 + 两只小脚。
    输入头宽，返回 RGBA Image。整体风格：浅蓝色圆润体型，呆萌感。"""
    from PIL import Image, ImageDraw
    # 身体宽度 = 头宽 * 0.78（Q 版比例，身体比头略窄显得头大更萌）
    body_w = max(80, int(head_w * 0.78))
    body_h = 130                       # 总高（含小脚）
    img = Image.new("RGBA", (body_w, body_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 配色（柔和的浅蓝系）
    body_color = (150, 200, 245, 255)      # 浅蓝身体
    outline_color = (46, 124, 196, 255)    # 深蓝描边
    hand_color = (255, 220, 180, 255)      # 肤色小手
    foot_color = (90, 140, 200, 255)       # 深蓝小脚

    cx = body_w / 2

    # ---- 两只小脚（在最底层，先画）----
    foot_w = body_w * 0.24
    foot_h = 22
    foot_y = body_h - foot_h
    for fx in (cx - body_w * 0.20, cx + body_w * 0.20):
        d.ellipse([fx - foot_w / 2, foot_y, fx + foot_w / 2, body_h],
                  fill=foot_color, outline=outline_color, width=2)

    # ---- 椭圆身体（在中间层）----
    torso_w = body_w * 0.74
    torso_h = 92
    torso_y = 8                          # 顶部留一点空隙
    torso_x0 = cx - torso_w / 2
    torso_y1 = torso_y + torso_h
    d.ellipse([torso_x0, torso_y, torso_x0 + torso_w, torso_y1],
              fill=body_color, outline=outline_color, width=3)

    # ---- 两只小手（在最上层，最后画）----
    hand_r = body_w * 0.11
    hand_y = torso_y + torso_h * 0.45     # 手在身体中部偏上
    for hx in (torso_x0 - hand_r * 0.4, torso_x0 + torso_w + hand_r * 0.4):
        d.ellipse([hx - hand_r, hand_y - hand_r, hx + hand_r, hand_y + hand_r],
                  fill=hand_color, outline=outline_color, width=2)

    return img


def skin_forge(path, progress=print):
    """换装管线（简化版）：识别 → 抠头 → 自绘卡通身体 → 分层素材。
    不再识别身体/腿/脚，身体完全用代码画卡通版。"""
    import io
    import cv2
    import numpy as np
    from PIL import Image

    def _safe_progress(s):
        try:
            progress(s)
        except Exception:
            pass

    _safe_progress("正在识别照片类型……")
    img0 = Image.open(path).convert("RGB")
    img0.thumbnail((640, 640))
    arr = np.array(img0)
    det = _sf_detect_face(arr)
    face, eyes_abs, face_ok = det if det else (None, None, False)
    small = cv2.resize(arr, (96, 96))
    qq = small.reshape(-1, 3) // 43
    _, cnt = np.unique(qq, axis=0, return_counts=True)
    top6 = float(np.sort(cnt)[::-1][:6].sum()) / float(cnt.sum())
    edge_dn = float((cv2.Canny(cv2.cvtColor(small, cv2.COLOR_RGB2GRAY), 60, 140) > 0).mean())
    # YuNet 真人脸是强信号；肤色启发式脸可能是动漫角色的脸，只算半票
    score = (2 if face_ok else 0.5 if face else 0) \
        + (1 if top6 < 0.55 else 0) + (1 if edge_dn > 0.055 else 0)
    kind = "photo" if score >= 2 else "anime"
    if kind == "anime" and not face_ok:
        face, eyes_abs = None, None

    if kind == "photo":
        _safe_progress("识别到真人照片，提取主体中……")
        raw_rgba = _sf_remove_bg_photo(arr, face)
        _safe_progress("Q 化变形中……")
        rgba = _sf_cartoonify(raw_rgba)
    else:
        _safe_progress("识别到动漫形象，提取角色中……")
        rgba = _sf_remove_bg_flood(img0)
        # 主体与背景同色时 floodfill 会误伤 → 降级 grabCut
        if float((np.array(rgba)[:, :, 3] > 12).mean()) < 0.20:
            rgba = _sf_remove_bg_photo(arr, face)

    alpha = np.array(rgba)[:, :, 3]
    ys, xs = np.where(alpha > 12)
    if len(xs) < 40:
        raise ValueError("找不到清晰的主体")
    sx, sy, ex, ey = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    sub = rgba.crop((sx, sy, ex, ey))
    W, H = sub.size
    if W < 24 or H < 24:
        raise ValueError("主体太小")

    _safe_progress("识别头部……")
    sub_alpha = np.array(sub)[:, :, 3]

    def _silhouette_x(y0, y1):
        """取 [y0,y1) 区间剪影的左右边界（alpha>24），用来把头发两侧收紧。"""
        y0 = max(0, int(y0))
        y1 = max(y0 + 1, min(H, int(y1)))
        band = sub_alpha[y0:y1] > 24
        cols = np.where(band.any(axis=0))[0]
        if not len(cols):
            return 0, W
        span = int(cols.max() - cols.min() + 1)
        pad = max(3, int(span * 0.04))
        return max(0, int(cols.min()) - pad), min(W, int(cols.max()) + 1 + pad)

    def _neck_row(y0, y1, fallback):
        """在下巴下方区间找 alpha 最窄的一行 —— 那就是脖子，即头颅的下沿。"""
        y0 = max(0, int(y0))
        y1 = max(y0 + 2, min(H, int(y1)))
        best_y, best_w = None, None
        for yy in range(y0, y1):
            idx = np.where(sub_alpha[yy] > 24)[0]
            if len(idx) < 3:
                continue
            rw = int(idx.max() - idx.min() + 1)
            if best_w is None or rw < best_w:
                best_y, best_w = yy, rw
        return (best_y + 2) if best_y is not None else int(fallback)

    if face:
        # YuNet 检测到真人脸：头顶 - 下巴 - 脖子最窄处 三段定位，只切出头颅
        fx, fy, fw, fh = face[0] - sx, face[1] - sy, face[2], face[3]
        head_top = max(0, fy - int(0.85 * fh))
        chin_y = fy + int(0.98 * fh)
        head_bottom = _neck_row(chin_y, chin_y + max(6, int(0.55 * fh)),
                                fy + int(1.06 * fh))
        head_bottom = max(head_bottom, int(fy + 0.80 * fh))   # 别把下巴裁掉
    else:
        # 动漫图或没检测到脸：顶部一段 + 区间最窄行当颈线
        head_top = 0
        head_bottom = _neck_row(int(H * 0.30), int(H * 0.58), H * 0.40)
        head_bottom = max(head_bottom, int(H * 0.22))
    head_bottom = min(H, head_bottom)
    if head_bottom <= head_top + 8:
        head_top, head_bottom = 0, max(1, min(H, int(H * 0.40)))

    hx0, hx1 = _silhouette_x(head_top, chin_y if face else head_bottom)
    head_box = (hx0, head_top, hx1, head_bottom)
    eyes = ([(e[0] - sx, e[1] - sy) for e in eyes_abs] if eyes_abs else
            ([(fx + 0.30 * fw, fy + 0.44 * fh), (fx + 0.70 * fw, fy + 0.44 * fh)]
             if face else None))

    def _head_mask(im, geom):
        """把方块收成「只有头颅」的剪影：
        1) 下颌线以下按人脸宽度逐步收窄 —— 脖子根、衣领、肩膀全部裁掉
        2) 底边做圆角 + 轻微淡出，贴到卡通身体上不会有生硬横线
        geom = (脸左上x, 脸左上y, 脸宽, 脸高)，坐标相对 head_box；无脸时传 None。"""
        a = np.array(im)
        hh, ww = a.shape[:2]
        yy = np.arange(hh, dtype=np.float32)[:, None]
        xx = np.arange(ww, dtype=np.float32)[None, :]
        if geom:
            _fx, _fy, _fw, _fh = geom
            cx_f = _fx + _fw * 0.5
            y_jaw = _fy + _fh * 0.78             # 下巴附近开始收窄
            half0, half1 = _fw * 0.62, _fw * 0.38
        else:
            cx_f, y_jaw = ww * 0.5, hh * 0.72
            half0, half1 = ww * 0.50, ww * 0.30
        t = np.clip((yy - y_jaw) / max(1.0, (hh - 1) - y_jaw), 0.0, 1.0)
        half = half0 + (half1 - half0) * t
        soft = max(1.0, ww * 0.03)
        taper = np.where(t <= 0.0, 1.0,
                         np.clip((half - np.abs(xx - cx_f)) / soft, 0.0, 1.0))
        if geom:
            # 下半张脸 / 两侧：只有「贴近脸部肤色」的像素才留（下颌、脖子），
            # 衣领、帽子、肩膀、垂下来的头发颜色都对不上，直接剔除。
            # 脸部中央（嘴、鼻）不做色筛，避免误删五官。
            y0 = max(0, min(hh, int(_fy + _fh * 0.58)))
            px0, px1 = int(_fx + _fw * 0.28), int(_fx + _fw * 0.72)
            py0, py1 = int(_fy + _fh * 0.32), int(_fy + _fh * 0.68)
            patch = a[py0:py1, px0:px1]
            if y0 < hh and patch.size:
                skin = patch.reshape(-1, patch.shape[-1])[:, :3].astype(np.float32).mean(axis=0)
                diff = np.abs(a[:, :, :3].astype(np.float32) - skin).max(axis=2)
                skin_keep = np.clip((110.0 - diff) / 55.0, 0.0, 1.0)
                gw = max(1.0, _fw * 0.12)
                gx = np.clip((np.abs(xx - cx_f) - _fw * 0.34) / gw, 0.0, 1.0)
                gy = np.clip((yy - (_fy + _fh * 0.56)) / max(1.0, _fh * 0.10), 0.0, 1.0)
                apply = gx * gy
                taper = taper * (1.0 - apply * (1.0 - skin_keep))
        # 底边椭圆圆角（只作用在最下面 11%）
        band = max(6, int(hh * 0.11))
        f = np.clip((yy - (hh - 1 - band)) / float(band), 0.0, 1.0)
        half_b = (ww * 0.5) * np.sqrt(np.clip(1.0 - 0.80 * f * f, 0.0, 1.0))
        round_keep = np.where(f <= 0.0, 1.0,
                              np.clip((half_b - np.abs(xx - (ww - 1) / 2.0)) / soft, 0.0, 1.0))
        round_keep = round_keep * (1.0 - 0.32 * f * f)
        keep = np.clip(taper * round_keep, 0.0, 1.0)
        a[:, :, 3] = np.clip(a[:, :, 3].astype(np.float32) * keep, 0, 255).astype(np.uint8)
        # 去掉零星碎块（衣领边缘、背景残留），只保留最大的一块
        m = (a[:, :, 3] > 24).astype(np.uint8)
        if m.any():
            n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
            if n > 2:
                main_lab = 1 + int(np.argmax(stats[1:, 4]))
                a[(lab != main_lab) & (lab > 0), 3] = 0
        return Image.fromarray(a, "RGBA")

    head_h0 = max(1, head_box[3] - head_box[1])
    HEAD_H = max(210, head_h0 + 12)       # 自适应头高
    head_img = sub.crop(head_box)
    head_img = _head_mask(head_img, (fx - head_box[0], fy - head_box[1], fw, fh)
                          if face else None)
    hr = HEAD_H / head_img.height
    head_img = head_img.resize((max(1, round(head_img.width * hr)), HEAD_H), Image.LANCZOS)
    hw = head_img.width
    eyes_h = ([(min(hw - 2, max(2, round((e[0] - head_box[0]) * hr))),
                min(HEAD_H - 2, max(2, round((e[1] - head_box[1]) * hr))))
               for e in eyes] if eyes else None)

    _safe_progress("画卡通身体中……")
    body_img = _sf_draw_cartoon_body(hw)

    OVERLAP = 40                              # 头底部覆盖住身体顶部
    # --- 水平对齐：head 和 body 各自扩画布到同宽，alpha 中心对齐到共同中心 ---
    import cv2 as _cv2
    def _alpha_center_x(im):
        a = np.array(im)[:, :, 3]
        xs = np.where(a > 12)[1]  # [1]=列索引，才是 x
        return float(xs.mean()) if len(xs) else im.width / 2.0
    # 清 alpha 边缘 + inpaint RGB：
    def _clean_alpha(im):
        a = np.array(im)
        alpha = a[:, :, 3]
        rgb_mask = (alpha < 220).astype(np.uint8) * 255
        if rgb_mask.any():
            for c in range(3):
                a[:, :, c] = _cv2.inpaint(a[:, :, c], rgb_mask, 5, _cv2.INPAINT_TELEA)
        a[:, :, 3] = _cv2.GaussianBlur(alpha, (5, 5), 0)
        return Image.fromarray(a, "RGBA")
    head_img = _clean_alpha(head_img)
    body_img = _clean_alpha(body_img)
    # 统一画布宽度：让 head 和 body 的 alpha 中心都落在画布中心
    target_w = max(head_img.width, body_img.width, 2)
    head_cx = _alpha_center_x(head_img)
    body_cx = _alpha_center_x(body_img)
    head_canvas = Image.new("RGBA", (target_w, head_img.height), (0, 0, 0, 0))
    head_canvas.paste(head_img, (round(target_w / 2 - head_cx), 0), head_img)
    head_img = head_canvas
    body_canvas = Image.new("RGBA", (target_w, body_img.height), (0, 0, 0, 0))
    body_canvas.paste(body_img, (round(target_w / 2 - body_cx), 0), body_img)
    body_img = body_canvas
    # 合成 full：head 和 body 的 alpha 中心都在 target_w/2 → 对齐自然
    full_h = HEAD_H + body_img.height - OVERLAP
    full = Image.new("RGBA", (target_w, full_h), (0, 0, 0, 0))
    full.paste(body_img, (0, HEAD_H - OVERLAP), body_img)
    full.paste(head_img, (0, 0), head_img)

    def _png(im):
        buf = io.BytesIO()
        im.save(buf, "PNG")
        return buf.getvalue()

    _safe_progress("校准动作协调性……")
    return {"kind": kind, "head": _png(head_img), "body": _png(body_img),
            "full": _png(full),
            "meta": {"eyes": eyes_h, "neck_y": HEAD_H - OVERLAP, "overlap": OVERLAP,
                     "legs_added": True}}   # 卡通身体总是包含腿脚


class DesktopPet(QWidget):
    weather_ready = pyqtSignal(dict)
    skin_ready = pyqtSignal(object)
    skin_progress = pyqtSignal(str)
    credits_ready = pyqtSignal(object)      # (data|None, manual)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(W, H)

        # ---- animation state ----
        self.phase = 0.0
        self.state = "idle"              # idle | walk
        self.direction = random.choice([-1, 1])
        self.walk_enabled = True
        self.blink_frames = 0
        self.stretch_frames = 0
        self.chew_frames = 0
        self.shake_frames = 0
        self._punch_frames = 0           # 拳头挥击动画剩余帧
        self._punch_total = 18           # 一次挥拳总帧数（30ms/帧 ≈ 540ms）
        self._punch_kind = -1            # 0 右勾拳 / 1 左勾拳 / 2 正面直拳（随机出场）
        self._hit_streak = 0             # 连续被击中次数
        self._hit_last_ts = 0.0
        # ---- 击倒 / 爬起 ----
        self._down_state = None          # None | "fall" | "lie" | "up"
        self._down_kind = 0              # 0 右侧倒 / 1 左侧倒 / 2 脸朝下趴倒
        self._down_t = 0                 # 当前阶段已过帧数
        self._lie_until = 0.0            # 躺地结束时间戳
        self._ko_expanded = False        # 倒地期间窗口是否已扩展
        self._ko_geo = None              # 扩展前的窗口左上角
        self.sleepy = False
        self.hearts = []                 # [{x, y, life}]
        self.dragging = False
        self._moved = False
        self._drag_offset = QPoint()
        self.bubble_text = ""
        self.happy_until = 0.0

        # ---- hover menu & extra reactions ----
        self.setMouseTracking(True)
        self.hovered = False
        self.menu_alpha = 0.0
        self.hover_btn = None
        self._btn_clicked = False
        self.lean = 0.0
        self.hover_since = 0.0
        self.hover_said = False
        self.jump_frames = 0
        self.dizzy_frames = 0
        self.look_frames = 0
        self.look_dir = 0
        self.click_times = []
        self.persona = "sunny"
        self.skin = None
        self.skin_path = None
        self.skin_layers = None          # {head, body, eyes, neck_y, overlap}
        self.transforming = False        # 换装识别中

        # ---- 八方移动 ----
        self.vx, self.vy = 1.0, 0.0
        self.speed = 0.0
        self.target_speed = 0.0

        # ---- 吸附 & 翻转 ----
        self.flip_x = False               # 贴左吸附时水平镜像翻转
        self._snap_target = None           # QPoint 吸附目标位置
        self._snap_rate = 0.0              # 吸附动画插值 (0→1)
        # ---- 睡眠模式（菜单主动入睡；sleepy 则是长时间没互动后自动困倦）----
        self.sleep_mode = False
        # ---- 点击序列气泡 ----
        self.bubble_queue = []             # ["text", {"text": "...", "weight": 1}, ...]
        self._queue_idx = 0
        self._queue_advance_on_tap = True  # True=点一下推一项；False=点一下回首次
        self._last_random_idx = -1          # 不连续重复：上次抽中的台词 idx

        # ---- 主动性 ----
        self.weather = {}
        self._last_greet_hour = -1
        self._last_need = 0.0
        self._weather_alert_day = ""
        self.weather_ready.connect(self._on_weather)

        # ---- Trae 积分监控 ----
        self.credits = None              # {balance,total,used,packs,ts}
        self._credits_busy = False
        self._credits_warned = False
        self._credits_err = ""           # 最近一次同步失败的原因
        self.credits_ready.connect(self._on_credits)
        self.credits_timer = QTimer(self, timeout=self._sync_credits)
        self.credits_timer.start(CREDITS_SYNC_MS)
        QTimer.singleShot(9000, self._sync_credits)

        # ---- growth state ----
        self.xp = 0
        self.mood = 80
        self.satiety = 80
        self.counts = {"pat": 0, "poke": 0, "drag": 0, "feed": 0, "antenna": 0}
        self.achievements = set()
        self.visits = 0
        self.last_touch = time.time()

        # ---- character art (vector drawing used as fallback) ----
        self.art = {}
        art_dir = os.path.join(_asset_base(), "pet_art")
        for key in ("idle", "walk", "happy", "eat", "sleepy", "drag", "sad", "stretch"):
            fp = os.path.join(art_dir, key + ".png")
            if os.path.exists(fp):
                pm = QPixmap(fp)
                if not pm.isNull():
                    self.art[key] = pm.scaledToHeight(232, Qt.SmoothTransformation)
        self._load()
        if self.skin_path:
            self._restore_skin()
        self.skin_ready.connect(self._on_skin_ready)
        self.skin_progress.connect(self._on_skin_progress)

        geo = QApplication.desktop().availableGeometry(self)
        self.move(geo.right() - W - 60, geo.bottom() - H - 40)

        self.frame_timer = QTimer(self, timeout=self._tick)
        self.frame_timer.start(30)
        self.blink_timer = QTimer(self, timeout=self._blink)
        self.blink_timer.start(2600)
        self.behave_timer = QTimer(self, timeout=self._behave)
        self.behave_timer.start(5200)
        self.decay_timer = QTimer(self, timeout=self._decay)
        self.decay_timer.start(60000)
        self.bubble_timer = QTimer(self, singleShot=True, timeout=self._hide_bubble)
        self.proactive_timer = QTimer(self, timeout=self._proactive)
        self.proactive_timer.start(60000)              # 主动问候/需求/天气
        QTimer.singleShot(25000, self._fetch_weather_async)

        # ---- 悬停小对话框（回车=浏览器搜索，右侧可切 Trae / 网页）----
        edit_ss = ("QLineEdit{background:rgba(255,255,255,235);border:2px solid #4FA8EF;"
                   "border-radius:13px;padding:0 10px;font:9pt 'Microsoft YaHei';color:#1F3B4D}")
        self.chat_edit = QLineEdit(self)
        self.chat_edit.setPlaceholderText("问我点什么…")
        self.chat_edit.setGeometry(16, 264, 186, 26)
        self.chat_edit.setStyleSheet(edit_ss)
        self.chat_edit.returnPressed.connect(self._ask)
        btn_ss = ("QPushButton{background:rgba(255,255,255,235);border:2px solid #4FA8EF;"
                  "border-radius:13px;font:8pt 'Microsoft YaHei';color:#1F3B4D}"
                  "QPushButton:hover{background:#4FA8EF;color:#FFFFFF}")
        self.trae_btn = QPushButton("Trae", self)
        self.trae_btn.setGeometry(208, 264, 40, 26)
        self.trae_btn.setStyleSheet(btn_ss)
        self.trae_btn.setCursor(Qt.PointingHandCursor)
        self.trae_btn.setToolTip("唤起本机 Trae IDE")
        self.trae_btn.clicked.connect(self._ask_trae)
        self.web_btn = QPushButton("网页", self)
        self.web_btn.setGeometry(252, 264, 32, 26)
        self.web_btn.setStyleSheet(btn_ss)
        self.web_btn.setCursor(Qt.PointingHandCursor)
        self.web_btn.setToolTip("用默认浏览器搜索")
        self.web_btn.clicked.connect(self._ask_web)
        self._set_chat_visible(False)

        self._update_tooltip()
        if self.visits > 1:
            QTimer.singleShot(700, lambda: self.talk(f"第 {self.visits} 次见面啦，想我了没～", force=True))
        else:
            QTimer.singleShot(700, lambda: self.talk(PERSONALITIES[self.persona]["greet"], force=True))
        self.show()

    # ---------------- persistence ----------------
    def _load(self):
        try:
            with open(SAVE_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.xp = d.get("xp", 0)
            self.mood = d.get("mood", 80)
            self.satiety = d.get("satiety", 80)
            self.counts.update(d.get("counts", {}))
            self.achievements = set(d.get("achievements", []))
            self.visits = d.get("visits", 0) + 1
            if d.get("persona") in PERSONALITIES:
                self.persona = d["persona"]
            self.skin_path = d.get("skin")
            c = d.get("credits")
            if isinstance(c, dict) and "balance" in c:
                self.credits = c
        except (OSError, ValueError):
            self.visits = 1
        self._save()

    def _save(self):
        data = {
            "xp": self.xp, "mood": self.mood, "satiety": self.satiety,
            "counts": self.counts, "achievements": sorted(self.achievements),
            "visits": self.visits, "persona": self.persona, "skin": self.skin_path,
            "credits": self.credits,
        }
        try:
            with open(SAVE_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    # ---------------- growth helpers ----------------
    def level(self):
        lv = 1
        for i, t in enumerate(LEVELS):
            if self.xp >= t:
                lv = i + 1
        return lv

    def _add_xp(self, n):
        old = self.level()
        self.xp += n
        new = self.level()
        if new > old:
            self.happy_until = time.time() + 2.5
            self.talk(f"升级啦！现在是 LV{new}！", force=True)

    def _unlock(self, key):
        if key not in self.achievements:
            self.achievements.add(key)
            self.talk(f"★ 成就解锁：{ACHIEVEMENTS[key]}", force=True)
            self._save()

    def _check_achievements(self):
        c = self.counts
        if c["pat"] >= 1:
            self._unlock("first_pat")
        if c["pat"] >= 10:
            self._unlock("pat10")
        if c["drag"] >= 1:
            self._unlock("first_drag")
        if c["drag"] >= 10:
            self._unlock("drag10")
        if c["feed"] >= 1:
            self._unlock("first_feed")
        if c["feed"] >= 10:
            self._unlock("feed10")
        if self.level() >= 5:
            self._unlock("lv5")
        if 0 <= datetime.datetime.now().hour < 5:
            self._unlock("night")

    @staticmethod
    def _quiet_hours():
        h = datetime.datetime.now().hour
        return h >= 23 or h < 7

    def _update_tooltip(self):
        self.setToolTip(
            f"小T LV{self.level()}｜心情 {self.mood}｜饱食 {self.satiety}\n"
            f"成就 {len(self.achievements)}/{len(ACHIEVEMENTS)}｜鼠标移上来有菜单"
        )

    # ---------------- interactions ----------------
    def interact(self, zone):
        if self._down_state:
            return                       # 倒地中不响应点击，等它自己爬起来
        if self._asleep():
            # 睡着时点它一下 → 先把它叫醒，不算挨揍
            self.sleep_mode = False
            self.sleepy = False
            self.last_touch = time.time()
            self.happy_until = time.time() + 1.2
            self.talk("唔……被拍醒了……早呀", force=True)
            self._update_tooltip()
            self.update()
            return
        self.last_touch = time.time()
        self.sleepy = False
        p_zone = PERSONALITIES[self.persona]["zones"].get(zone) or ZONE_LINES[zone]
        line = random.choice(p_zone)
        if self._quiet_hours():
            line = "（小声啜泣）" + line
        # ---- 揍：所有部位都触发摇晃 + 心情下降 ----
        self.shake_frames = 18
        # 三套拳（右勾 / 左勾 / 正面直拳）完全随机出场，允许连续重复
        self._punch_kind = random.choice((0, 1, 2))
        self._punch_total = 20 if self._punch_kind == 2 else 18
        self._punch_frames = self._punch_total
        self.mood = max(5, self.mood - 2)
        self.counts["poke"] += 1
        self._add_xp(1)
        if zone == "head":
            self.counts["pat"] += 1
            self.shake_frames = 22     # 揍头晃得更厉害
        elif zone == "antenna":
            self.counts["antenna"] += 1
        # ---- 连续被击中计数 → 倒地 ----
        now = time.time()
        if now - self._hit_last_ts > KO_STREAK_GAP:
            self._hit_streak = 0
        self._hit_last_ts = now
        self._hit_streak += 1
        if self._hit_streak >= KO_HITS:
            self._hit_streak = 0
            self._knock_down()
            self._check_achievements()
            self._update_tooltip()
            self._save()
            return
        self.talk(line, force=True)
        self._check_achievements()
        self._update_tooltip()
        self._save()
    def _knock_down(self):
        """连续挨揍到上限：倒地。三种倒地方式随机（避免连续重复）。"""
        kinds = [0, 1, 2]
        if self._down_kind in kinds and len(kinds) > 1:
            kinds.remove(self._down_kind)
        self._down_kind = random.choice(kinds)
        self._down_state = "fall"
        self._down_t = 0
        if self._down_kind != 2:
            self._ko_expand()
        self.shake_frames = 0
        self._punch_frames = 0
        self.dizzy_frames = 0
        self.sleepy = False
        self.mood = max(5, self.mood - 8)
        if "knockdown" not in self.achievements:
            self._unlock("knockdown")
        else:
            self.talk(random.choice(KO_LINES[self._down_kind]), force=True)


    def _ko_expand(self):
        """倒地时把透明画布向右/向下临时扩大，长身体横躺也不会被窗口裁掉。
        窗口原点尽量不动 → 角色、菜单、气泡在屏幕上的位置都不跳；
        贴着屏幕右下角时把窗口往回挪一点，保证横躺的动画整段留在屏幕里。"""
        if self._ko_expanded:
            return
        nw, nh = W + KO_PAD_X, H + KO_PAD_B
        geo = QApplication.desktop().availableGeometry(self)
        x, y = self.x(), self.y()
        nx = max(geo.left(), min(x, geo.right() - nw - 2))
        ny = max(geo.top(), min(y, geo.bottom() - nh - 2))
        self._ko_geo = (x, y)
        self._ko_expanded = True
        self.setGeometry(nx, ny, nw, nh)
        self._set_chat_visible(False)

    def _ko_collapse(self):
        """爬起来后把画布收回原尺寸。"""
        if not self._ko_expanded:
            return
        self._ko_expanded = False
        if self._ko_geo is not None:
            x, y = self._ko_geo
            self.setGeometry(x, y, W, H)
        self._ko_geo = None
        if self.hovered and not self.dragging:
            self._set_chat_visible(True)

    def _down_pose(self):
        """返回倒地/爬起姿态：(旋转角度, scaleX, scaleY, dx, dy)。"""
        st, k = self._down_state, self._down_kind
        if not st:
            return 0.0, 1.0, 1.0, 0.0, 0.0
        if k == 2:                 # 脸朝下趴倒（被压扁）
            end_ang, end_dx, end_sx, end_sy = 0.0, 0.0, 1.20, 0.42
        elif k == 1:               # 向左倒＝右倒的镜像；镜像会甩到窗口左边界外，整体右移进画布
            end_ang, end_dx, end_sx, end_sy = 74.0, 22.0 - KO_LEFT_SHIFT, 1.0, 1.0
        else:                      # 向右侧倒
            end_ang, end_dx, end_sx, end_sy = 74.0, 22.0, 1.0, 1.0

        if st == "fall":
            e = min(1.0, self._down_t / float(KO_FALL_FRAMES)) ** 2.2   # 越倒越快
            return (end_ang * e, 1.0 + (end_sx - 1.0) * e,
                    1.0 + (end_sy - 1.0) * e, end_dx * e, 0.0)
        if st == "lie":
            # 躺地上轻轻起伏
            sy = end_sy * (1.0 + 0.02 * math.sin(self.phase * 1.6))
            ang = end_ang + 2.0 * math.sin(self.phase * 1.2) if end_ang else 0.0
            return ang, end_sx, sy, end_dx, 0.0

        # ---- 爬起：三种花式 ----
        u = min(1.0, self._down_t / float(KO_UP_FRAMES))
        if k == 0:
            # 一弹而起 + 落地过冲
            f = u ** 0.7
            ang = end_ang * (1.0 - f)
            if u > 0.72:
                ang = -9.0 * math.sin((u - 0.72) / 0.28 * math.pi)
            return ang, 1.0, 1.0, end_dx * (1.0 - f), -8.0 * math.sin(u * math.pi)
        if k == 1:
            # 先坐起来，再撑直
            if u < 0.55:
                ang = end_ang * (1.0 - (u / 0.55) * 0.72)
                return ang, 1.0, 1.0, end_dx * (1.0 - u / 0.55 * 0.7), 0.0
            v = (u - 0.55) / 0.45
            ang = -21.0 * (1.0 - v) - 5.0 * math.sin(v * math.pi)
            return ang, 1.0, 1.0, end_dx * 0.3 * (1.0 - v), 0.0
        # k == 2：抖一抖再撑起来
        if u < 0.22:
            v = u / 0.22
            return 0.0, 1.20 - 0.06 * v, 0.42 + 0.10 * v, 0.0, 0.0
        v = (u - 0.22) / 0.78
        sy = 0.52 + 0.48 * (1.0 - (1.0 - v) ** 2)
        if v > 0.78:
            sy = 1.0 + 0.07 * math.sin((v - 0.78) / 0.22 * math.pi)
        return 0.0, 1.20 - 0.20 * v, sy, 0.0, 0.0

    def _down_head_pos(self):
        """倒地时头部在窗口坐标里的位置（冒星星用）。"""
        face_y = 172.0
        if self.skin_layers:
            L = self.skin_layers
            hh = L["head"].height()
            face_y = (298 - L["body"].height() - hh + L["overlap"]) + hh * 0.5
        ang, _sx, sy, dx, dy = self._down_pose()
        ry = (face_y - 285.0) * sy
        a = math.radians(ang)
        hx = CX + dx - ry * math.sin(a)
        if self._down_kind == 1:
            hx = 2 * CX - hx           # 左倒是镜像绘制，头部位置也要镜像
        return hx, 285 + dy + ry * math.cos(a)

    def feed(self):
        self.last_touch = time.time()
        self.sleepy = False
        self.sleep_mode = False          # 投喂会把睡着的小T叫醒
        self.counts["feed"] += 1
        self.satiety = min(100, self.satiety + 25)
        self.mood = min(100, self.mood + 3)
        self.chew_frames = 24
        self._add_xp(5)
        self._spawn_hearts(2)
        self.happy_until = time.time() + 2.5
        self.talk(random.choice(PERSONALITIES[self.persona]["feed"]), force=True)
        self._check_achievements()
        self._update_tooltip()
        self._save()

    def _asleep(self):
        """是否睡着（菜单主动睡眠 sleep_mode，或长时间没互动自动困倦 sleepy）。"""
        return self.sleep_mode or self.sleepy

    def stroke_head(self):
        """菜单「摸头」：心情 +6，冒爱心、开心一下。"""
        if self._down_state:
            return
        self.last_touch = time.time()
        self.sleep_mode = False
        self.sleepy = False
        self.mood = min(100, self.mood + 6)
        self._add_xp(2)
        self.happy_until = time.time() + 2.4
        self._spawn_hearts(3)
        self.talk(random.choice(STROKE_LINES), force=True)
        self._update_tooltip()
        self._save()
    def toggle_sleep(self):
        """菜单「睡眠」：入睡 / 唤醒。睡着时原地不动，只有呼吸起伏 + ZZZ。"""
        if self._down_state:
            return
        self.sleep_mode = not self.sleep_mode
        if self.sleep_mode:
            self.sleepy = True
            self.target_speed = 0.0
            self.speed = 0.0
            if self.state == "walk":
                self.state = "idle"
            self.talk(random.choice(SLEEP_LINES), force=True)
        else:
            self.sleepy = False
            self.last_touch = time.time()
            self.happy_until = time.time() + 1.6
            self.talk(random.choice(WAKE_LINES), force=True)
        self._update_tooltip()
        self._save()
        self.update()

    # ---------------- 自由换装 ----------------
    def choose_skin(self):
        if self.transforming:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "选择一张图片做小T的新皮肤", "",
            "图片文件 (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not path:
            return
        self.transforming = True
        if self.state in ("walk", "run"):
            self.target_speed = 0.0
        self.bubble_text = "收到！让我仔细看看这张图……"
        self.bubble_timer.start(6000)
        self.update()
        threading.Thread(target=self._skin_worker, args=(path,), daemon=True).start()

    def _skin_worker(self, path):
        try:
            pl = skin_forge(path, lambda s: self.skin_progress.emit(s))
            self.skin_ready.emit(pl)
        except Exception as e:
            self.skin_ready.emit({"error": str(e)[:40]})

    def _on_skin_progress(self, s):
        if self.transforming:
            self.bubble_text = s + "\n（识别中，稍等我一下下）"
            self.bubble_timer.start(8000)
            self.update()

    def _on_skin_ready(self, pl):
        self.transforming = False
        if not pl or "error" in pl:
            self.talk("这张图我认不出来……\n换一张五官清楚点的试试？", force=True)
            return
        base = os.path.join(_save_base(), "pet_art")
        full_fp = os.path.join(base, "custom_skin.png")
        head_fp = os.path.join(base, "custom_skin_head.png")
        body_fp = os.path.join(base, "custom_skin_body.png")
        with open(full_fp, "wb") as f:
            f.write(pl["full"])
        with open(head_fp, "wb") as f:
            f.write(pl["head"])
        with open(body_fp, "wb") as f:
            f.write(pl["body"])
        with open(os.path.join(base, "custom_skin.json"), "w", encoding="utf-8") as f:
            json.dump(pl["meta"], f)
        full = QPixmap(full_fp)
        self.skin = full.scaledToHeight(232, Qt.SmoothTransformation)
        self.skin_path = full_fp
        self._set_skin_layers(QPixmap(head_fp), QPixmap(body_fp), pl["meta"])
        self._save()
        self.happy_until = time.time() + 2.5
        self._spawn_hearts(4)
        self.jump_frames = JUMP_FRAMES
        kind_txt = "真人 Q 化" if pl.get("kind") == "photo" else "动漫形象"
        extra = "，没拍到的部位也补好啦" if pl["meta"].get("legs_added") else ""
        self.talk(f"变装完成！{kind_txt}{extra}\n快摸摸我试试手感～", force=True)

    def _set_skin_layers(self, hp, bp, meta):
        total = hp.height() + bp.height() - meta["overlap"]
        f = 232.0 / max(1, total)
        head = hp.scaled(max(1, int(hp.width() * f)), max(1, int(hp.height() * f)),
                         Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        body = bp.scaled(max(1, int(bp.width() * f)), max(1, int(bp.height() * f)),
                         Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        eyes = ([(e[0] * f, e[1] * f) for e in meta["eyes"]] if meta.get("eyes") else None)
        self.skin_layers = {"head": head, "body": body, "eyes": eyes,
                            "neck_y": meta["neck_y"] * f, "overlap": meta["overlap"] * f}

    def _restore_skin(self):
        """启动时恢复皮肤：有分层素材则分层，否则单图。"""
        try:
            base = os.path.join(_save_base(), "pet_art")
            if not (self.skin_path and os.path.exists(self.skin_path)):
                self.skin_path = None
                return
            pm = QPixmap(self.skin_path)
            if pm.isNull():
                return
            self.skin = pm.scaledToHeight(232, Qt.SmoothTransformation)
            meta_fp = os.path.join(base, "custom_skin.json")
            if os.path.exists(meta_fp):
                with open(meta_fp, encoding="utf-8") as f:
                    meta = json.load(f)
                hp = QPixmap(os.path.join(base, "custom_skin_head.png"))
                bp = QPixmap(os.path.join(base, "custom_skin_body.png"))
                if not hp.isNull() and not bp.isNull():
                    self._set_skin_layers(hp, bp, meta)
        except Exception:
            pass

    def _clear_skin(self):
        self.skin = None
        self.skin_layers = None
        self.skin_path = None
        base = os.path.join(_save_base(), "pet_art")
        for name in ("custom_skin.png", "custom_skin_head.png",
                     "custom_skin_body.png", "custom_skin.json"):
            try:
                os.remove(os.path.join(base, name))
            except OSError:
                pass
        self._save()
        self.talk("换回经典皮肤啦，还是这个最自在～", force=True)

    def _set_persona(self, key):
        if key not in PERSONALITIES:
            return
        self.persona = key
        self._save()
        p = PERSONALITIES[key]
        self.happy_until = time.time() + 2.0
        self._spawn_hearts(1 + p["heart_bonus"])
        self.talk(p["greet"], force=True)

    def show_status(self):
        self.talk(
            f"LV{self.level()}　心情 {self.mood}/100\n"
            f"饱食 {self.satiety}/100　成就 {len(self.achievements)}/{len(ACHIEVEMENTS)}",
            force=True,
        )

    def _spawn_hearts(self, n):
        for _ in range(n):
            self.hearts.append({
                "x": CX + random.randint(-50, 50),
                "y": 110 + random.randint(-10, 10),
                "life": 42,
            })

    # ---------------- behavior ----------------
    def _tick(self):
        self.phase += 0.10
        for attr in ("blink_frames", "stretch_frames", "chew_frames", "shake_frames",
                     "jump_frames", "dizzy_frames", "look_frames"):
            if getattr(self, attr):
                setattr(self, attr, getattr(self, attr) - 1)
        # ---- 挥拳动画帧递减 ----
        if self._punch_frames > 0:
            self._punch_frames -= 1
        # ---- 击倒 / 躺地 / 爬起 状态机 ----
        if self._down_state == "fall":
            self._down_t += 1
            if self._down_t >= KO_FALL_FRAMES:
                self._down_state = "lie"
                self._down_t = 0
                self._lie_until = time.time() + KO_LIE_SECONDS
        elif self._down_state == "lie":
            if time.time() >= self._lie_until:
                self._down_state = "up"
                self._down_t = 0
        elif self._down_state == "up":
            self._down_t += 1
            if self._down_t >= KO_UP_FRAMES:
                self._down_state = None
                self._down_t = 0
                self._hit_streak = 0
                self._ko_collapse()
                self.talk(random.choice(KO_GETUP_LINES), force=True)
        if self._down_state or self.sleep_mode:
            # 倒地 / 睡着 → 原地不动
            self.target_speed = 0.0
            self.speed = 0.0
            if self.state == "walk":
                self.state = "idle"
        # ---- 四边吸附动画（ease-out 插值移动到目标） ----
        if self._snap_target is not None and not self.dragging and not self._down_state:
            self._snap_rate += 0.18
            if self._snap_rate >= 1.0:
                self.move(self._snap_target)
                self._snap_target = None
                self._snap_rate = 0.0
            else:
                ease = 1.0 - (1.0 - self._snap_rate) ** 2
                nx = int(self.x() + (self._snap_target.x() - self.x()) * 0.22)
                ny = int(self.y() + (self._snap_target.y() - self.y()) * 0.22)
                self.move(nx, ny)
        for h in self.hearts:
            h["y"] -= 1.2
            h["life"] -= 1
        self.hearts = [h for h in self.hearts if h["life"] > 0]

        # hover menu fade in / out
        self._check_cursor_left()       # 光标真离开时兜底收起悬停 UI
        target = 1.0 if (self.hovered and not self.dragging) else 0.0
        self.menu_alpha += (target - self.menu_alpha) * 0.28
        if self.hovered and not self.hover_said and time.time() - self.hover_since > 2.5:
            self.hover_said = True
            if random.random() < 0.4 and not self.bubble_text and not self.jump_frames \
                    and not self._asleep():
                self.happy_until = time.time() + 1.6
                self.talk(random.choice(PERSONALITIES[self.persona]["hover"]))

        if self.state in ("walk", "run") and not self.dragging and not self.hovered:
            # 起步由慢到快、停下由快到慢
            self.speed += (self.target_speed - self.speed) * 0.08
            if self.target_speed == 0 and self.speed < 0.25:
                self.state = "idle"
                self.speed = 0.0
            else:
                nx = self.x() + self.vx * self.speed
                ny = self.y() + self.vy * self.speed
                geo = QApplication.desktop().availableGeometry(self)
                if nx < geo.left() + 10:
                    nx = geo.left() + 10
                    self.vx = abs(self.vx)
                elif nx + W > geo.right() - 10:
                    nx = geo.right() - 10 - W
                    self.vx = -abs(self.vx)
                if ny < geo.top() + 10:
                    ny = geo.top() + 10
                    self.vy = abs(self.vy)
                elif ny + H > geo.bottom() - 10:
                    ny = geo.bottom() - 10 - H
                    self.vy = -abs(self.vy)
                self.direction = 1 if self.vx >= 0 else -1
                self.move(int(nx), int(ny))
        else:
            self.speed *= 0.85
        self.update()

    def _blink(self):
        self.blink_frames = 5
        self.blink_timer.start(random.randint(2200, 4600))

    def _behave(self):
        if self._down_state or self.sleep_mode:
            return                     # 倒地 / 睡着期间不主动走动/说话
        if not self.dragging:
            quiet = self._quiet_hours()
            self.sleepy = (time.time() - self.last_touch > 240
                           and self.state not in ("walk", "run"))
            r = random.random()
            if self.sleepy:
                if r < 0.25:
                    self.talk("Zzz……")
            elif self.state == "idle":
                if self.walk_enabled and not self.hovered and not self.transforming and \
                        r < min(0.6, 0.38 * PERSONALITIES[self.persona]["walk_bias"]):
                    ang = random.uniform(0, math.tau)
                    self.vx = math.cos(ang)
                    self.vy = math.sin(ang) * 0.6
                    if random.random() < 0.25 * PERSONALITIES[self.persona]["walk_bias"]:
                        self.state = "run"
                        self.target_speed = 4.6
                        if random.random() < 0.4 and not quiet:
                            self.talk(random.choice(["冲呀——！", "跑步时间到！", "全速前进！"]))
                    else:
                        self.state = "walk"
                        self.target_speed = 2.0
                elif r < 0.50:
                    self.look_frames = 44
                    self.look_dir = random.choice([-1, 1])
                elif r < 0.62:
                    self.stretch_frames = 26
                    if random.random() < 0.5 and not quiet:
                        self.talk("伸个懒腰～")
                elif r < min(0.92, 0.76 * PERSONALITIES[self.persona]["talk_boost"]) and not quiet:
                    self.talk()
            elif self.state in ("walk", "run") and r < 0.45:
                self.target_speed = 0.0       # 减速滑行后停下
        self.behave_timer.start(random.randint(4000, 8000))

    def _decay(self):
        self.satiety = max(0, self.satiety - 1)
        self.mood = max(0, self.mood - (2 if self.satiety <= 20 else 1))
        if (self.satiety <= 15 and not self._quiet_hours() and not self._asleep()
                and not self._down_state and random.random() < 0.4):
            self.talk(random.choice(HUNGRY_LINES))
        self._update_tooltip()
        self._save()

    def talk(self, text=None, force=False):
        if self._quiet_hours() and not force:
            return
        # ---- 队列模式：有队列 + 非 force → 按队列弹出 ----
        if text is None and not force and self.bubble_queue:
            idx = self._queue_idx % len(self.bubble_queue)
            item = self.bubble_queue[idx]
            # 推进到下一项（点按推进模式开启时）
            if self._queue_advance_on_tap:
                self._queue_idx = idx + 1
            else:
                self._queue_idx = 0
            if isinstance(item, dict):
                # A/B 加权选择
                choices = item.get("choices", [])
                weights = item.get("weights") or [1] * len(choices)
                text = random.choices(choices, weights=weights, k=1)[0]
            else:
                text = item
        # ---- 不连续重复：从 PERSONALITIES pool 抽时避开上次抽到的 ----
        if text is None:
            pool = PERSONALITIES[self.persona]["lines"]
            if len(pool) > 1:
                candidates = [i for i in range(len(pool)) if i != self._last_random_idx]
                self._last_random_idx = random.choice(candidates)
                text = pool[self._last_random_idx]
            else:
                text = pool[0]
        self.bubble_text = text
        self.bubble_timer.start(3600)
        self.update()

    def _hide_bubble(self):
        self.bubble_text = ""
        self.update()

    # ---------------- 主动性：问候 / 天气 / 需求 ----------------
    def _proactive(self):
        now = datetime.datetime.now()
        quiet = self._quiet_hours()
        away = self._asleep() or self._down_state is not None   # 睡着/倒地时不主动说话
        if not quiet and not away and now.hour in HOUR_GREETS \
                and self._last_greet_hour != now.hour:
            self._last_greet_hour = now.hour
            msg = HOUR_GREETS[now.hour]
            if self.weather.get("desc"):
                msg += (f"\n现在{self.weather.get('city') or '外面'} "
                        f"{self.weather['temp']}°C，{self.weather['desc']}")
            self.talk(msg)
        # 需求表达：10 分钟没人理 + 心情一般 → 求关注（15 分钟冷却）
        if not quiet and not away and time.time() - self._last_need > 900:
            if (time.time() - self.last_touch > 600 and self.mood < 70
                    and self.state == "idle" and not self.bubble_text
                    and not self.dragging):
                self._last_need = time.time()
                self.talk(random.choice(PERSONA_NEED[self.persona]))
        # 天气缓存 3 小时
        if time.time() - self.weather.get("ts", 0) > 3 * 3600:
            self._fetch_weather_async()

    def _fetch_weather_async(self):
        threading.Thread(target=self._fetch_weather, daemon=True).start()

    def _fetch_weather(self):
        try:
            loc = json.loads(urllib.request.urlopen(
                "http://ip-api.com/json/?fields=status,city,lat,lon",
                timeout=8).read().decode("utf-8", "ignore"))
            w = json.loads(urllib.request.urlopen(
                "https://api.open-meteo.com/v1/forecast"
                f"?latitude={loc['lat']}&longitude={loc['lon']}&current_weather=true",
                timeout=8).read().decode("utf-8", "ignore"))
            cw = w["current_weather"]
            self.weather_ready.emit({
                "desc": WMO.get(cw["weathercode"], "天气成谜"),
                "temp": round(cw["temperature"], 1),
                "code": cw["weathercode"],
                "city": loc.get("city", ""),
                "ts": time.time(),
            })
        except Exception:
            pass

    def _on_weather(self, d):
        self.weather = d
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        if (d["code"] in RAINY and self._weather_alert_day != today
                and not self._quiet_hours()):
            self._weather_alert_day = today
            kind = "雪" if d["code"] in (71, 73, 75, 77, 85, 86) else "雨"
            self.talk(f"外面要下{kind}啦（{d['desc']} {d['temp']}°C）\n出门记得带伞哦！",
                      force=True)

    # ---------------- Trae 积分 ----------------
    def _sync_credits(self, manual=False):
        """后台拉取积分；manual=True 时无论成败都会反馈。"""
        if self._credits_busy:
            return
        self._credits_busy = True

        def work():
            err = ""
            try:
                data = fetch_credits()
            except Exception as e:
                data, err = None, str(e)
            self._credits_err = err
            self._credits_busy = False
            self.credits_ready.emit((data, manual))

        threading.Thread(target=work, daemon=True).start()

    def _on_credits(self, payload):
        data, manual = payload
        if not data:
            if manual:
                self.talk(self._credits_err or random.choice(CREDITS_ERR_LINES), force=True)
            return
        old = self.credits
        self.credits = data
        self._save()
        bal = data["balance"]
        if bal < CREDITS_WARN:
            if not self._credits_warned:
                self._credits_warned = True
                self.talk(f"积分只剩 {bal:.0f} 了，{random.choice(CREDITS_LOW_LINES)}", force=True)
            return
        self._credits_warned = False
        if manual:
            self.talk(f"积分 {bal:.0f} / {data['total']:.0f}（已用 {data['used']:.0f}）", force=True)
        elif old and "balance" in old:
            delta = bal - float(old["balance"])
            if delta >= 1:
                self.talk(f"{random.choice(CREDITS_DOWN_LINES)} +{delta:.0f}，现在 {bal:.0f}", force=True)
            elif delta <= -1:
                self.talk(f"{random.choice(CREDITS_UP_LINES)} -{abs(delta):.0f}，还剩 {bal:.0f}",
                          force=True)

    def show_credits(self):
        """积分面板：余额 + 最近更新 + 各积分包剩余。"""
        c = self.credits
        if not c:
            self.talk("还没有积分数据，正在同步……", force=True)
            self._sync_credits(manual=True)
            return
        when = time.strftime("%m-%d %H:%M", time.localtime(c.get("ts", time.time())))
        lines = [f"积分余额 {c['balance']:.0f} / {c['total']:.0f}",
                 f"已用 {c['used']:.0f}　更新 {when}"]
        for p in c.get("packs", [])[:4]:
            lines.append(f"· {p['name']} {p['limit'] - p['used']:.0f}/{p['limit']:.0f}")
        if c["balance"] < CREDITS_WARN:
            lines.append("余额偏低，记得去签到补一点")
        self.talk("\n".join(lines), force=True)

    # ---------------- 悬停小对话框 ----------------
    def _set_chat_visible(self, v):
        # 倒地/被拎起时不显示输入框（子控件会盖住躺在地上的头）
        show = v and not self.dragging and not self._down_state
        self.chat_edit.setVisible(show)
        self.trae_btn.setVisible(show)
        self.web_btn.setVisible(show)

    def _ask(self):
        """回车：用系统默认浏览器搜索。"""
        q = self.chat_edit.text().strip()
        if not q:
            return
        self.chat_edit.clear()
        os.startfile("https://www.bing.com/search?q=" + urllib.parse.quote(q))
        self.talk("已打开浏览器帮你搜啦", force=True)

    def _ask_trae(self):
        """唤起本机 Trae IDE，并把问题放进剪贴板方便直接粘贴。"""
        q = self.chat_edit.text().strip()
        if q:
            QApplication.clipboard().setText(q)
        launched = False
        try:
            os.startfile(TRAE_SCHEME)
            launched = True
        except OSError:
            if os.path.exists(TRAE_EXE):
                try:
                    os.startfile(TRAE_EXE)
                    launched = True
                except OSError:
                    pass
        self.chat_edit.clear()
        if q and launched:
            self.talk("Trae 已打开，问题复制到剪贴板了，Ctrl+V 问它吧", force=True)
        elif launched:
            self.talk("Trae 已经喊出来了～", force=True)
        else:
            self.talk("没找到 Trae，装一个再来找我吧", force=True)

    def _ask_web(self):
        """「网页」按钮：显式走浏览器搜索。"""
        self._ask()

    # ---------------- mouse ----------------
    def enterEvent(self, e):
        self.hovered = True
        self.hover_since = time.time()
        self.hover_said = False
        if self.state in ("walk", "run"):
            self.target_speed = 0.0     # 减速停下看着你
        self._set_chat_visible(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._check_cursor_left()
        super().leaveEvent(e)

    def _check_cursor_left(self):
        # 透明缝隙、进入子控件都会触发 leaveEvent，属“假离开”；
        # 以光标是否真的移出窗口为准（_tick 里轮询兜底）
        if self.hovered and not self.rect().contains(self.mapFromGlobal(QCursor.pos())):
            self.hovered = False
            self.hover_btn = None
            self.lean = 0.0
            self._set_chat_visible(False)

    def _snap_if_close(self):
        """松手后自动吸附最近的屏幕边缘（吸附阈值 28px）。"""
        geo = QApplication.desktop().availableGeometry(self)
        x, y = self.x(), self.y()
        SNAP_THRESH = 28
        target = None
        flip = self.flip_x
        if x - geo.left() < SNAP_THRESH:
            target = QPoint(geo.left() + 2, y)
            flip = True
        elif geo.right() - (x + W) < SNAP_THRESH:
            target = QPoint(geo.right() - W - 2, y)
            flip = False
        elif y - geo.top() < SNAP_THRESH:
            target = QPoint(x, geo.top() + 2)
        elif geo.bottom() - (y + H) < SNAP_THRESH:
            target = QPoint(x, geo.bottom() - H - 2)
        if target is not None:
            self.flip_x = flip
            self._snap_target = target
            self._snap_rate = 0.0

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._btn_clicked = False
            idx = self._btn_at(e.pos())
            if idx is not None:
                self._btn_clicked = True
                self._menu_action(idx)
                return
            if self._ui_at(e.pos()):
                self._btn_clicked = True    # 点的是底部 UI，不算揍小T、也不拖动
                return
            if self._down_state:
                return                     # 倒地期间不能拖动
            self.dragging = True
            self._moved = False
            self._drag_offset = e.globalPos() - self.frameGeometry().topLeft()
            self._set_chat_visible(False)
            self.update()

    def mouseMoveEvent(self, e):
        if self.dragging:
            target = e.globalPos() - self._drag_offset
            if (target - self.pos()).manhattanLength() > 4:
                self._moved = True
            self.move(target)
        else:
            self.hover_btn = self._btn_at(e.pos())
            self.lean = max(-5.0, min(5.0, (e.pos().x() - CX) / 16.0))

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        if self._btn_clicked:
            self._btn_clicked = False
            return
        self.dragging = False
        if self._moved:
            self.last_touch = time.time()
            self.sleepy = False
            self.sleep_mode = False     # 被拎起来就醒了
            self.counts["drag"] += 1
            self.mood = min(100, self.mood + 2)
            self._add_xp(3)
            if random.random() < 0.35:
                self.talk(random.choice(PERSONALITIES[self.persona]["pick"]), force=True)
            self._check_achievements()
            self._update_tooltip()
            self._save()
            # ---- 拖拽松手 → 四边吸附检测 ----
            self._snap_if_close()
        else:
            if self._ui_at(e.pos()):
                return                     # 底部 UI（胶囊/聊天框）上的点击绝不揍小T
            y = e.pos().y()
            if y < 100:
                zone = "antenna"
            elif y < 205:
                zone = "head"
            elif y < 258:
                zone = "belly"
            else:
                zone = "feet"
            self.interact(zone)
            # 3 秒内连揍 5 下 → 晕乎乎（头上冒星星）
            now = time.time()
            self.click_times = [t for t in self.click_times if now - t < 3.0]
            self.click_times.append(now)
            if len(self.click_times) >= 5:
                self.click_times.clear()
                self.dizzy_frames = 54
                self.mood = max(5, self.mood - 5)
                if "dizzy" not in self.achievements:
                    self._unlock("dizzy")
                else:
                    self.talk("晕、晕乎乎的……别打了……眼前全是小星星……", force=True)
                self._update_tooltip()
                self._save()
        if self.rect().contains(e.pos()):
            self._set_chat_visible(True)
        self.update()

    def wheelEvent(self, e):
        """滚轮 → 原地弹跳。"""
        if self.dragging or self.jump_frames or self._down_state:
            return
        self.last_touch = time.time()
        self.sleepy = False
        self.sleep_mode = False         # 滚轮也能把它逗醒
        self.jump_frames = JUMP_FRAMES
        self.happy_until = time.time() + 1.6
        self._spawn_hearts(2)
        self._add_xp(1)
        if "jump" not in self.achievements:
            self._unlock("jump")
        else:
            self.talk(random.choice(["蹦！", "跳跳跳～", "嘿咻！", "看我弹跳力！"]), force=True)
        self._update_tooltip()

    def mouseDoubleClickEvent(self, e):
        # 双击事件会绕过 mousePressEvent，必须同样拦掉底部 UI，否则连点菜单会挥拳
        if self._btn_at(e.pos()) is not None or self._ui_at(e.pos()):
            return
        self.interact("head")

    # ---------------- hover menu helpers ----------------
    @staticmethod
    def _btn_layout():
        step = BTN_R * 2 + BTN_GAP
        total = len(MENU_ITEMS) * BTN_R * 2 + (len(MENU_ITEMS) - 1) * BTN_GAP
        x0 = CX - total / 2 + BTN_R
        return [(int(x0 + i * step), MENU_CY) for i in range(len(MENU_ITEMS))]

    def _btn_at(self, pos):
        if self.menu_alpha < 0.3 or self.dragging:
            return None
        for i, (bx, by) in enumerate(self._btn_layout()):
            if (pos.x() - bx) ** 2 + (pos.y() - by) ** 2 <= (BTN_R + 3) ** 2:
                return i
        return None

    def _ui_at(self, pos):
        """点击落在底部 UI（聊天框底板 / 菜单胶囊）上 → 不算揍小T。
        胶囊按「整条」判定（含按钮之间的缝隙），这样在胶囊上快速连点不会误触挥拳。"""
        if self.chat_edit.isVisible() and QRectF(8, 256, 284, 40).contains(pos):
            return True
        if self.menu_alpha > 0.0:
            pill_w = len(MENU_ITEMS) * BTN_R * 2 + (len(MENU_ITEMS) - 1) * BTN_GAP + 20
            if QRectF(CX - pill_w / 2 - 4, 296, pill_w + 8, 36).contains(pos):
                return True
        return False

    def _menu_action(self, idx):
        key = MENU_ITEMS[idx][0]
        if key == "talk":
            self.talk(force=True)
        elif key == "stroke":
            self.stroke_head()
        elif key == "pat":
            self.interact("head")
        elif key == "feed":
            self.feed()
        elif key == "walk":
            self.walk_enabled = not self.walk_enabled
            if self.walk_enabled:
                self.sleep_mode = False
                self.sleepy = False
                ang = random.uniform(0, math.tau)
                self.vx, self.vy = math.cos(ang), math.sin(ang) * 0.6
                self.state = "walk"
                self.target_speed = 2.0
                self.talk(random.choice(WALK_START_LINES), force=True)
            else:
                self.target_speed = 0.0
                self.talk(random.choice(WALK_STOP_LINES), force=True)
        elif key == "sleep":
            self.toggle_sleep()
        elif key == "more":
            self._show_context_menu(QCursor.pos())

    def contextMenuEvent(self, e):
        self._show_context_menu(e.globalPos())

    def _build_menu(self):
        m = QMenu(self)
        acts = {
            "say": m.addAction("说点什么"),
            "pat": m.addAction("揍一拳"),
            "feed": m.addAction("投喂数据饼干"),
            "status": m.addAction("看看状态"),
            "credits": m.addAction("积分面板"),
            "sync": m.addAction("立即同步积分"),
        }
        m.addSeparator()
        walk = m.addAction("到处走走")
        walk.setCheckable(True)
        walk.setChecked(self.walk_enabled)
        acts["walk"] = walk
        m.addSeparator()
        acts["skin"] = m.addAction("自由换装…")
        if self.skin is not None:
            acts["skin_off"] = m.addAction("恢复默认皮肤")
        sub = m.addMenu("性格")
        for k in PERSONA_ORDER:
            a = sub.addAction(PERSONALITIES[k]["name"])
            a.setCheckable(True)
            a.setChecked(self.persona == k)
            acts["persona:" + k] = a
        m.addSeparator()
        acts["about"] = m.addAction("自我介绍")
        acts["quit"] = m.addAction("退出")
        return m, acts

    def _show_context_menu(self, pos):
        m, acts = self._build_menu()
        act = m.exec_(pos)
        if act is None:
            return
        for key, a in acts.items():
            if act != a:
                continue
            if key == "say":
                self.talk(force=True)
            elif key == "pat":
                self.interact("head")
            elif key == "feed":
                self.feed()
            elif key == "status":
                self.show_status()
            elif key == "credits":
                self.show_credits()
            elif key == "sync":
                self._sync_credits(manual=True)
            elif key == "walk":
                self.walk_enabled = a.isChecked()
                if not self.walk_enabled:
                    self.target_speed = 0.0
            elif key == "skin":
                self.choose_skin()
            elif key == "skin_off":
                self._clear_skin()
            elif key.startswith("persona:"):
                self._set_persona(key.split(":", 1)[1])
            elif key == "about":
                self.talk("我是小T，Trae 的桌面分身～", force=True)
            elif key == "quit":
                self._save()
                QApplication.quit()
            break

    # ---------------- painting ----------------
    def _select_art(self, walking):
        """Pick a pose image by priority; None when art assets are missing."""
        self._art_key = None
        if self.skin is not None:
            self._art_key = "skin"
            return self.skin
        if not self.art:
            return None
        if self.dragging:
            key = "drag"
        elif self.chew_frames:
            key = "eat"
        elif time.time() < self.happy_until:
            key = "happy"
        elif self._asleep():
            key = "sleepy"
        elif self.mood < 30:
            key = "sad"
        elif self.stretch_frames:
            key = "stretch"
        elif walking:
            key = "walk"
        else:
            key = "idle"
        self._art_key = key
        return self.art.get(key) or self.art.get("idle")

    def _paint_skin_layers(self, p, walking, flip, tilt):
        """分层皮肤：身体随整体摇摆，头部带滞后摆动（更生动）。"""
        L = self.skin_layers
        body, head = L["body"], L["head"]
        bw, bh = body.width(), body.height()
        hw, hh = head.width(), head.height()
        bx, by = CX - bw / 2, 298 - bh
        hx, hy = CX - hw / 2, by - hh + L["overlap"]
        p.drawPixmap(int(bx), int(by), body)
        p.save()
        npx, npy = CX, hy + L["neck_y"]
        p.translate(npx, npy)
        p.rotate(tilt * 0.4)
        lag = math.sin(self.phase * 1.5 + 0.9) * (2.0 if walking else 1.2)
        p.translate(0, lag)
        p.translate(-npx, -npy)
        p.drawPixmap(int(hx), int(hy), head)
        p.restore()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        walking = self.state in ("walk", "run") and not self.dragging
        art = self._select_art(walking)
        if self.dragging:
            bob, tilt = -6.0, math.sin(self.phase * 0.6) * 6
        elif walking:
            # 摇晃速度恒定，不随移动速度变化（变速时 phase*freq 会相位跳变导致抽搐）；
            # 速度只体现在前倾幅度上
            sway = math.sin(self.phase * 1.5)
            bob = -abs(sway) * 5.0
            tilt = sway * 4 + self.direction * min(7, max(0.5, self.speed) * 1.6)
        elif self._asleep() and not self.dragging:
            # 睡觉时呼吸起伏更慢更轻
            bob, tilt = math.sin(self.phase * 0.45) * 1.5, 0.0
        else:
            bob, tilt = math.sin(self.phase) * 4, 0.0

        # 弹跳 / 晕眩 / 张望 / 悬停歪头
        q_jump = math.sin((1 - self.jump_frames / JUMP_FRAMES) * math.pi) if self.jump_frames else 0.0
        jump_y = -q_jump * 34
        if self.dizzy_frames:
            tilt += math.sin(self.phase * 11) * 9
        if self.look_frames:
            tilt += self.look_dir * 4
        if walking:
            tilt += self.direction * 2

        # shadow
        sw = 112 - bob * 1.6 - jump_y * 1.2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(20, 40, 60, max(30, min(95, 70 + int(bob * 3) + int(jump_y * 2)))))
        p.drawEllipse(QRectF(CX - sw / 2, 296, sw, 18))

        # 悬停小对话框底板：填平输入框与按钮之间的缝隙
        #（完全透明的像素在分层窗口里会被鼠标穿透，造成“假离开”）
        if self.chat_edit.isVisible():
            p.setPen(QPen(QColor(79, 168, 239, 70), 1))
            p.setBrush(QColor(255, 255, 255, 26))
            p.drawRoundedRect(QRectF(10, 258, 280, 38), 12, 12)

        p.save()
        if self.shake_frames or self.dizzy_frames:
            # 揍：快速左右猛晃；晕眩：慢速大晃
            if self.dizzy_frames:
                amp = 3.5
                freq = 13
            else:
                amp = 6.0          # 揍的摇晃幅度大，更有打击感
                freq = 16          # 频率高，显得更疼
            p.translate(math.sin(self.phase * freq) * amp, 0)
        p.translate(self.lean, bob + jump_y)
        # ---- 睡眠呼吸：身体轻微忽大忽小（锚在脚边，脚不位移） ----
        if self._asleep() and not self.dragging:
            br = math.sin(self.phase * 0.45)
            p.translate(CX, 298)
            p.scale(1.0 - 0.016 * br, 1.0 + 0.026 * br)
            p.translate(-CX, -298)
        p.translate(CX, 285)
        # ---- 击倒 / 躺地 / 爬起 姿态（原点在脚边 CX,285，底边 298） ----
        if self._down_state:
            _ang, _dsx, _dsy, _ddx, _ddy = self._down_pose()
            if self._down_kind == 1:
                p.scale(-1, 1)          # 左倒＝镜像的右倒（窗口只向右扩，才不会被裁）
            p.translate(_ddx, _ddy)
            if _ang:
                p.rotate(_ang)
            if abs(_dsx - 1.0) > 0.001 or abs(_dsy - 1.0) > 0.001:
                p.translate(0, 13)
                p.scale(_dsx, _dsy)
                p.translate(0, -13)
        # ---- 水平翻转（贴左吸附） ----
        if self.flip_x:
            p.scale(-1, 1)
        p.rotate(tilt)
        if self.stretch_frames and art is None:
            s = math.sin((26 - self.stretch_frames) / 26 * math.pi)
            p.scale(1 + 0.06 * s, 1 - 0.10 * s)
        if self.jump_frames:
            p.translate(CX, 292)
            p.scale(1 - 0.07 * q_jump, 1 + 0.09 * q_jump)
            p.translate(-CX, -292)
        p.translate(-CX, -285)

        if art is not None:
            iw, ih = art.width(), art.height()
            flip = (walking and self.direction < 0) or (self.look_frames and self.look_dir < 0)
            if flip:
                p.translate(CX, 0)
                p.scale(-1, 1)
                p.translate(-CX, 0)
            if self._art_key == "skin" and self.skin_layers:
                self._paint_skin_layers(p, walking, flip, tilt)
            else:
                p.drawPixmap(int(CX - iw / 2), int(298 - ih), art)
            # 眼睛盯鼠标：停下（idle）时，瞳孔朝光标方向偏移
            if self._art_key == "idle" and not self.dragging:
                mpos = self.mapFromGlobal(QCursor.pos())
                gx = max(-1.0, min(1.0, (mpos.x() - CX) / 110.0)) * 5.0
                gy = max(-1.0, min(1.0, (mpos.y() - EYE_POS[0][1]) / 110.0)) * 3.5
                if flip:
                    gx = -gx
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255, 245))
                for ex, ey in EYE_POS:
                    p.drawEllipse(QRectF(ex - 3.5 + gx, ey - 6 + gy, 7, 12))
        else:
            outline = QPen(QColor("#2E7CC4"), 3)
            outline.setJoinStyle(Qt.RoundJoin)

            # antenna
            pen = QPen(QColor("#2E7CC4"), 5, Qt.SolidLine, Qt.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawLine(CX, 112, CX, 92)
            rg = QRadialGradient(CX, 82, 16)
            rg.setColorAt(0, QColor("#FFE9A8"))
            rg.setColorAt(0.55, QColor("#FFD166"))
            rg.setColorAt(1, QColor(255, 209, 102, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(rg)
            p.drawEllipse(QRectF(CX - 16, 66, 32, 32))
            p.setBrush(QColor("#FFD166"))
            p.drawEllipse(QRectF(CX - 6, 76, 12, 12))

            # arms (raised when picked up / stretching)
            arm_dy = -18 if (self.dragging or self.stretch_frames) else 0
            arm_grad = QLinearGradient(CX, 170, CX, 240)
            arm_grad.setColorAt(0, QColor("#8CF2DC"))
            arm_grad.setColorAt(1, QColor("#4FA8EF"))
            p.setBrush(arm_grad)
            p.setPen(outline)
            p.drawRoundedRect(QRectF(56, 176 + arm_dy, 30, 56), 15, 15)
            p.drawRoundedRect(QRectF(214, 176 + arm_dy, 30, 56), 15, 15)

            # feet
            step = math.sin(self.phase * 1.7) * 4 if walking else 0
            p.setBrush(QColor("#2E7CC4"))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(96, 262 + step, 46, 26), 13, 13)
            p.drawRoundedRect(QRectF(158, 262 - step, 46, 26), 13, 13)

            # body
            grad = QLinearGradient(CX, 105, CX, 280)
            grad.setColorAt(0, QColor("#8CF2DC"))
            grad.setColorAt(1, QColor("#4FA8EF"))
            p.setBrush(grad)
            p.setPen(outline)
            p.drawRoundedRect(QRectF(75, 105, 150, 175), 68, 68)

            # belly + highlight
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 70))
            p.drawRoundedRect(QRectF(93, 202, 114, 64), 30, 30)
            p.setBrush(QColor(255, 255, 255, 100))
            p.drawEllipse(QRectF(92, 116, 42, 22))

            # blush
            p.setBrush(QColor(255, 140, 170, 95))
            p.drawEllipse(QRectF(80, 180, 22, 12))
            p.drawEllipse(QRectF(198, 180, 22, 12))

            # visor
            p.setBrush(QColor("#14303F"))
            p.setPen(QPen(QColor("#0B1F2B"), 3))
            p.drawRoundedRect(QRectF(95, 138, 110, 66), 30, 30)

            # eyes (blink / wide when picked up / droopy when sleepy)
            if self.blink_frames:
                prog = (5 - self.blink_frames) / 5.0
                eye_scale = max(0.08, 1.0 - math.sin(prog * math.pi) * 0.95)
            else:
                eye_scale = 1.0
            eh = 36 if self.dragging else 30 * eye_scale
            if self._asleep() and not self.dragging:
                eh *= 0.55
            for ex in (120, 166):
                y = 171 - eh / 2
                p.setBrush(QColor(124, 247, 255, 55))
                p.drawEllipse(QRectF(ex - 6, y - 6, 26, eh + 12))
                p.setBrush(QColor("#7CF7FF"))
                p.drawRoundedRect(QRectF(ex, y, 14, eh), 7, 7)

            # mouth (chewing / smile / frown by mood)
            if self.chew_frames:
                if (self.chew_frames // 4) % 2 == 0:
                    p.setBrush(QColor("#7CF7FF"))
                    p.drawEllipse(QRectF(CX - 5, 186, 10, 10))
                else:
                    pen = QPen(QColor("#7CF7FF"), 3, Qt.SolidLine, Qt.RoundCap)
                    p.setPen(pen)
                    p.drawLine(CX - 7, 191, CX + 7, 191)
            elif self.dragging:
                p.setBrush(QColor("#7CF7FF"))
                p.drawEllipse(QRectF(CX - 5, 186, 10, 10))
            else:
                pen = QPen(QColor("#7CF7FF"), 3, Qt.SolidLine, Qt.RoundCap)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                if self.mood < 30:
                    p.drawArc(QRectF(CX - 11, 188, 22, 12), 20 * 16, 140 * 16)   # frown
                elif self.mood > 75:
                    p.drawArc(QRectF(CX - 15, 176, 30, 18), 195 * 16, 150 * 16)  # big smile
                else:
                    p.drawArc(QRectF(CX - 13, 178, 26, 14), 200 * 16, 140 * 16)  # smile

        p.restore()


        # 跑步速度线
        if self.state == "run" and self.speed > 2.5 and not self.dragging:
            p.setPen(QPen(QColor(140, 200, 245, 170), 3, Qt.SolidLine, Qt.RoundCap))
            sx = -1 if self.vx >= 0 else 1
            bx0 = CX + sx * 86
            for i in range(3):
                yy = 170 + i * 42 + math.sin(self.phase * 2 + i) * 5
                p.drawLine(int(bx0), int(yy), int(bx0 + sx * 26), int(yy))

        # 晕乎乎：头顶转圈的小星星（被揍晕）
        if self.dizzy_frames:
            # 皮肤模式头顶更高（皮肤更"高瘦"），默认皮肤头顶在 118
            star_cy = 60 if self.skin_layers else 118
            # 5 颗星星围一圈，比原来的 3 颗更"晕"
            for i in range(5):
                ang = self.phase * 1.4 + i * (2 * math.pi / 5)
                self._draw_star(p, CX + math.cos(ang) * 46, star_cy + math.sin(ang) * 12,
                                7, min(220, self.dizzy_frames * 6))

        # 倒地：头顶持续冒星星（爬起过半后淡出）
        if self._down_state in ("fall", "lie") or (
                self._down_state == "up" and self._down_t < KO_UP_FRAMES * 0.55):
            hxp, hyp = self._down_head_pos()
            for i in range(4):
                ang = self.phase * 1.7 + i * (math.pi / 2)
                self._draw_star(p, hxp + math.cos(ang) * 30,
                                hyp - 20 + math.sin(ang) * 10, 7, 225)

        # ---- 睡眠：头顶冒 ZZZ 气泡 ----
        if self._asleep() and not self.dragging and not self._down_state:
            self._draw_zzz(p)

        # 变装识别中：天线旁旋转的小星星
        if self.transforming:
            for i in range(3):
                ang = self.phase * 5.0 + i * 2.094
                self._draw_star(p, CX + math.cos(ang) * 30, 82 + math.sin(ang) * 12,
                                6, 220)

        # ---- 揍：三套拳（右勾 / 左勾 / 正面直拳），随机出场 ----
        if self._punch_frames > 0:
            # 脸中心（皮肤模式按分层高度推算）
            face_y = 172.0
            if self.skin_layers:
                _hh = self.skin_layers["head"].height()
                _by = 298 - self.skin_layers["body"].height()
                face_y = (_by - _hh + self.skin_layers["overlap"]) + _hh * 0.55
            if self._punch_kind == 2:
                self._draw_front_punch(p, face_y)
            else:
                p.save()
                if self._punch_kind == 1:
                    # 左拳：以窗口中线镜像，拳头从左侧挥进来
                    p.translate(2 * CX, 0)
                    p.scale(-1, 1)
                hit_x, hit_y = CX + 8, face_y - 2
                start_x, start_y = CX + 180, face_y - 88
                t = 1.0 - self._punch_frames / float(self._punch_total)
                if t < 0.35:                       # 冲进来（ease-out 加速落地）
                    u = t / 0.35
                    ease = 1.0 - (1.0 - u) ** 3
                    fx = start_x + (hit_x - start_x) * ease
                    fy = start_y + (hit_y - start_y) * ease
                    alpha, on_hit = 255, 0.0
                    # 挥拳拖尾
                    for i, a in ((1, 90), (2, 45)):
                        p.setPen(QPen(QColor(255, 255, 255, a), 3, Qt.SolidLine, Qt.RoundCap))
                        p.drawLine(int(fx + 30), int(fy + 4),
                                   int(fx + 30 + i * 30), int(fy + 4 - i * 15))
                elif t < 0.60:                     # 命中：贴脸 + 高频微颤
                    u = (t - 0.35) / 0.25
                    fx = hit_x + math.sin(u * math.pi * 4) * 2.0
                    fy = hit_y + math.cos(u * math.pi * 4) * 1.2
                    alpha, on_hit = 255, 1.0
                else:                              # 收拳撤出
                    u = (t - 0.60) / 0.40
                    fx = hit_x + (start_x - hit_x) * (u ** 1.7)
                    fy = hit_y + (start_y - hit_y) * (u ** 1.7)
                    alpha, on_hit = int(255 * (1.0 - u)), 0.0
                self._draw_fist(p, fx, fy, 1.15, alpha)
                if on_hit:
                    # 命中冲击：拳头左边缘的星爆 + 白色亮心 + 向左放射线
                    bxp = hit_x - 24
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(255, 255, 255, 200))
                    p.drawEllipse(QRectF(bxp - 4, hit_y - 4, 8, 8))
                    self._draw_star(p, bxp, hit_y, 13, 235)
                    p.setPen(QPen(QColor(255, 209, 102, 210), 3, Qt.SolidLine, Qt.RoundCap))
                    for k in (-2.4, -1.55, -0.9, 1.0, 1.65, 2.4):
                        p.drawLine(int(bxp + math.cos(k) * 15), int(hit_y + math.sin(k) * 15),
                                   int(bxp + math.cos(k) * 28), int(hit_y + math.sin(k) * 28))
                p.restore()

        # floating hearts
        for h in self.hearts:
            self._draw_heart(p, h["x"], h["y"], 16, min(255, h["life"] * 8))

        # speech bubble
        if self.bubble_text:
            font = QFont("Microsoft YaHei", 10)
            p.setFont(font)
            fm = p.fontMetrics()
            lines = self.bubble_text.split("\n")
            tw = max(fm.horizontalAdvance(s) for s in lines)
            bw = min(tw + 30, W - 12)
            bh = 22 * len(lines) + 18
            bx = max(6, min(CX - bw / 2, W - bw - 6))
            by = 8
            p.setPen(QPen(QColor("#4FA8EF"), 2))
            p.setBrush(QColor(255, 255, 255, 246))
            tail = QPolygonF([QPoint(int(CX - 9), int(by + bh - 2)),
                              QPoint(int(CX + 9), int(by + bh - 2)),
                              QPoint(CX, int(by + bh + 14))])
            p.drawPolygon(tail)
            p.drawRoundedRect(QRectF(bx, by, bw, bh), 12, 12)
            p.setPen(QColor("#1F3B4D"))
            for i, s in enumerate(lines):
                p.drawText(QRectF(bx, by + 4 + 22 * i, bw, 22), Qt.AlignCenter, s)

        # ---- 悬停菜单（底部小圆按钮）----
        if self.menu_alpha > 0.03 and not self.dragging:
            a = self.menu_alpha
            p.save()
            p.translate(0, (1 - a) * 12)
            pill_w = len(MENU_ITEMS) * BTN_R * 2 + (len(MENU_ITEMS) - 1) * BTN_GAP + 20
            pill = QRectF(CX - pill_w / 2, 300, pill_w, 30)
            p.setPen(QPen(QColor(79, 168, 239, int(150 * a)), 2))
            p.setBrush(QColor(255, 255, 255, int(232 * a)))
            p.drawRoundedRect(pill, 15, 15)
            for i, (bx, by) in enumerate(self._btn_layout()):
                hover = i == self.hover_btn
                if hover:
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(79, 168, 239, int(255 * a)))
                    p.drawEllipse(QRectF(bx - BTN_R - 2, by - BTN_R - 2,
                                         BTN_R * 2 + 4, BTN_R * 2 + 4))
                fg = QColor(255, 255, 255, int(255 * a)) if hover else \
                    QColor(46, 124, 196, int(235 * a))
                bg = QColor(79, 168, 239, int(255 * a)) if hover else \
                    QColor(255, 255, 255, int(232 * a))
                self._draw_menu_icon(p, MENU_ITEMS[i][0], bx, by, fg, bg)
            if self.hover_btn is not None and a > 0.6:
                label = MENU_ITEMS[self.hover_btn][1]
                p.setFont(QFont("Microsoft YaHei", 9))
                fm = p.fontMetrics()
                lw = fm.horizontalAdvance(label) + 16
                bx, _ = self._btn_layout()[self.hover_btn]
                lx = max(4, min(bx - lw / 2, W - lw - 4))
                # 提示画在聊天框上方：聊天框是子控件，会盖住父级绘制的提示
                lb = QRectF(lx, 233, lw, 19)
                p.setPen(QPen(QColor(79, 168, 239, int(200 * a)), 1.5))
                p.setBrush(QColor(255, 255, 255, int(245 * a)))
                p.drawRoundedRect(lb, 9, 9)
                p.setPen(QColor(31, 59, 77, int(255 * a)))
                p.drawText(lb, Qt.AlignCenter, label)
            p.restore()

    def _sleep_head_pos(self):
        """睡着时头部上方的锚点（飘 ZZZ 用，窗口坐标）。"""
        if self.skin_layers:
            L = self.skin_layers
            hh = L["head"].height()
            top = 298 - L["body"].height() - hh + L["overlap"]
            return CX, top + hh * 0.28
        return CX, 118.0

    def _draw_zzz(self, p):
        """头顶往上飘的三个 Z（越飘越大越淡）。"""
        hx, hy = self._sleep_head_pos()
        for i in range(3):
            u = (self.phase * 0.055 + i * 0.34) % 1.0
            alpha = int(240 * min(1.0, u * 4.0) * min(1.0, (1.0 - u) * 2.2))
            if alpha <= 10:
                continue
            size = 10.0 + 7.0 * u
            zx = hx + 26 + u * 30 + math.sin(u * math.pi * 2) * 5
            zy = hy - 12 - u * 46
            self._draw_z(p, zx, zy, size, alpha)

    @staticmethod
    def _draw_z(p, x, y, size, alpha):
        """用画笔路径画 Z（不依赖字体，离屏渲染也能显示）。"""
        p.save()
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.moveTo(x - size * 0.5, y - size * 0.5)
        path.lineTo(x + size * 0.5, y - size * 0.5)
        path.lineTo(x - size * 0.5, y + size * 0.5)
        path.lineTo(x + size * 0.5, y + size * 0.5)
        pen = QPen(QColor(78, 128, 186, alpha), max(2.0, size * 0.19))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        # 先描一圈半透明白边，深浅桌面上都看得清
        halo = QPen(QColor(255, 255, 255, int(alpha * 0.8)), max(3.2, size * 0.33))
        halo.setCapStyle(Qt.RoundCap)
        halo.setJoinStyle(Qt.RoundJoin)
        p.setPen(halo)
        p.drawPath(path)
        p.setPen(pen)
        p.drawPath(path)
        p.restore()

    @staticmethod
    def _draw_star(p, x, y, size, alpha):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 209, 102, alpha))
        p.drawPolygon(QPolygonF([
            QPoint(int(x), int(y - size)), QPoint(int(x + size * 0.28), int(y)),
            QPoint(int(x), int(y + size)), QPoint(int(x - size * 0.28), int(y)),
        ]))
        p.drawPolygon(QPolygonF([
            QPoint(int(x - size), int(y)), QPoint(int(x), int(y - size * 0.28)),
            QPoint(int(x + size), int(y)), QPoint(int(x), int(y + size * 0.28)),
        ]))

    def _draw_front_punch(self, p, face_y):
        """正面直拳：拳头从画面下方迎面冲上来，放大贴脸命中，再缩小撤回。
        与左右勾拳（侧面拳形）视觉完全不同：拳面正对镜头。"""
        t = 1.0 - self._punch_frames / float(self._punch_total)
        hit_x, hit_y = CX + 2, face_y + 2
        start_x, start_y = CX + 2, face_y + 132        # 起点：下巴下方远处（拳小）
        p.save()
        if t < 0.35:                                   # 迎面冲上来
            u = t / 0.35
            ease = 1.0 - (1.0 - u) ** 3
            fx = start_x + (hit_x - start_x) * ease
            fy = start_y + (hit_y - start_y) * ease
            sc = 0.55 + 1.20 * ease
            alpha, on_hit = 255, 0.0
            # 冲刺残影（拳头下方两道竖直拖尾）
            p.setPen(QPen(QColor(255, 255, 255, 110), 4, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(int(fx - 11 * sc), int(fy + 30 * sc),
                       int(fx - 11 * sc), int(fy + 60 * sc))
            p.drawLine(int(fx + 12 * sc), int(fy + 30 * sc),
                       int(fx + 12 * sc), int(fy + 48 * sc))
        elif t < 0.60:                                 # 命中：贴脸 + 再涨一点 + 微颤
            u = (t - 0.35) / 0.25
            sc = 1.75 + 0.16 * math.sin(u * math.pi)
            fx = hit_x + math.sin(u * math.pi * 4) * 2.4
            fy = hit_y + math.cos(u * math.pi * 4) * 1.6
            alpha, on_hit = 255, 1.0
        else:                                          # 缩回下方
            u = (t - 0.60) / 0.40
            fx = hit_x + (start_x - hit_x) * (u ** 1.6)
            fy = hit_y + (start_y - hit_y) * (u ** 1.6)
            sc = 1.75 - 1.20 * (u ** 1.6)
            alpha, on_hit = int(255 * (1.0 - u)), 0.0
        self._draw_fist_front(p, fx, fy, sc, alpha)
        if on_hit:
            # 正面命中：脸左上方的星爆 + 白色亮心 + 向外放射线
            bxp, byp = hit_x - 30, hit_y - 34
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 200))
            p.drawEllipse(QRectF(bxp - 4, byp - 4, 8, 8))
            self._draw_star(p, bxp, byp, 13, 235)
            p.setPen(QPen(QColor(255, 209, 102, 210), 3, Qt.SolidLine, Qt.RoundCap))
            for k in range(6):
                a = k * math.pi / 3 + 0.35
                p.drawLine(int(bxp + math.cos(a) * 15), int(byp + math.sin(a) * 15),
                           int(bxp + math.cos(a) * 27), int(byp + math.sin(a) * 27))
        p.restore()

    @staticmethod
    def _draw_fist_front(p, cx, cy, sc, alpha):
        """画一只拳头朝向观众（正面视角）的卡通拳头：拳面 + 四个指节 + 拇指 + 小臂。"""
        if alpha <= 0:
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        ol = QPen(QColor(150, 96, 60, alpha), max(1.6, 2.2 * sc))
        ol.setJoinStyle(Qt.RoundJoin)
        # ---- 小臂（从下方伸上来，蓝色袖口）----
        p.setPen(ol)
        p.setBrush(QColor(79, 168, 239, alpha))
        p.drawRoundedRect(QRectF(cx - 15 * sc, cy + 10 * sc, 30 * sc, 34 * sc),
                          8 * sc, 8 * sc)
        p.setPen(QPen(QColor(255, 255, 255, 60), 2 * sc))
        p.drawLine(int(cx - 9 * sc), int(cy + 20 * sc),
                   int(cx - 9 * sc), int(cy + 38 * sc))
        # ---- 拳面（正对镜头的圆角方块）----
        p.setPen(ol)
        p.setBrush(QColor(255, 214, 170, alpha))
        p.drawRoundedRect(QRectF(cx - 20 * sc, cy - 14 * sc, 40 * sc, 30 * sc),
                          11 * sc, 11 * sc)
        # ---- 四个指节（顶边凸起）----
        for i in range(4):
            kx = cx - 14 * sc + i * 9.4 * sc
            p.drawEllipse(QRectF(kx - 5 * sc, cy - 20 * sc, 10 * sc, 11 * sc))
        # ---- 指节分隔线 ----
        p.setPen(QPen(QColor(226, 168, 122, alpha), max(1.0, 1.2 * sc)))
        for i in range(1, 4):
            xx = cx - 14 * sc + i * 9.4 * sc
            p.drawLine(int(xx), int(cy - 12 * sc), int(xx), int(cy + 6 * sc))
        # ---- 拇指（左下角，压在拳面外侧）----
        p.setPen(QPen(QColor(226, 168, 122, alpha), max(1.0, 1.3 * sc)))
        p.setBrush(QColor(250, 205, 158, alpha))
        p.drawEllipse(QRectF(cx - 24 * sc, cy + 1 * sc, 13 * sc, 16 * sc))
        # ---- 拳面高光 ----
        p.setPen(QPen(QColor(255, 255, 255, 90), 2 * sc, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(QRectF(cx - 15 * sc, cy - 10 * sc, 30 * sc, 22 * sc), 60 * 16, 60 * 16)
        p.restore()

    @staticmethod
    def _draw_fist(p, cx, cy, sc, alpha):
        """画一只朝左挥出的卡通拳头：蓝色袖口 + 圆润拳面 + 四指节凸起 + 拇指。"""
        if alpha <= 0:
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        ol = QPen(QColor(150, 96, 60, alpha), max(1.6, 2.2 * sc))
        ol.setJoinStyle(Qt.RoundJoin)
        # ---- 袖口（右后方，被拳面压住左侧一部分）----
        p.setPen(ol)
        p.setBrush(QColor(79, 168, 239, alpha))
        p.drawRoundedRect(QRectF(cx + 12 * sc, cy - 12 * sc, 36 * sc, 24 * sc),
                          7 * sc, 7 * sc)
        p.setPen(QPen(QColor(255, 255, 255, 60), 2 * sc))
        p.drawLine(int(cx + 20 * sc), int(cy - 9 * sc),
                   int(cx + 20 * sc), int(cy + 9 * sc))
        # ---- 拳面：左侧四个指节凸起，右侧圆角 ----
        path = QPainterPath()
        path.moveTo(cx - 16 * sc, cy + 16 * sc)
        for i in range(4):
            yb = cy + 16 * sc - 8 * sc * i
            path.arcTo(QRectF(cx - 20 * sc, yb - 8 * sc, 8 * sc, 8 * sc), 270, -180)
        path.lineTo(cx + 8 * sc, cy - 16 * sc)
        path.quadTo(cx + 19 * sc, cy - 16 * sc, cx + 19 * sc, cy - 4 * sc)
        path.lineTo(cx + 19 * sc, cy + 4 * sc)
        path.quadTo(cx + 19 * sc, cy + 16 * sc, cx + 8 * sc, cy + 16 * sc)
        path.closeSubpath()
        p.setPen(ol)
        p.setBrush(QColor(255, 214, 170, alpha))
        p.drawPath(path)
        # ---- 指节分隔线（横跨拳面，暗示四根手指）----
        p.setPen(QPen(QColor(226, 168, 122, alpha), max(1.0, 1.3 * sc)))
        for i in range(3):
            yy = cy - 8 * sc + i * 8 * sc
            p.drawLine(int(cx - 8 * sc), int(yy), int(cx + 14 * sc), int(yy))
        # ---- 拇指（左下侧压在拳面上）----
        p.setPen(QPen(QColor(226, 168, 122, alpha), max(1.0, 1.4 * sc)))
        p.setBrush(QColor(250, 205, 158, alpha))
        p.drawEllipse(QRectF(cx - 15 * sc, cy + 5 * sc, 15 * sc, 12 * sc))
        p.restore()

    @staticmethod
    def _draw_menu_icon(p, key, cx, cy, fg, bg):
        p.setPen(Qt.NoPen)
        p.setBrush(fg)
        if key == "talk":
            p.drawRoundedRect(QRectF(cx - 8, cy - 7, 16, 11), 4, 4)
            p.drawPolygon(QPolygonF([QPoint(int(cx - 3), int(cy + 3)),
                                     QPoint(int(cx + 3), int(cy + 3)),
                                     QPoint(int(cx), int(cy + 8))]))
            p.setBrush(bg)
            for dx in (-4, 0, 4):
                p.drawEllipse(QRectF(cx + dx - 1.1, cy - 2.6, 2.2, 2.2))
        elif key == "pat":
            # 拳头：圆 + 三根手指线 + 冲击星芒
            p.drawEllipse(QRectF(cx - 5, cy - 5, 10, 10))
            p.setPen(QPen(bg, 1.4))
            for dy in (-2, 0, 2):
                p.drawLine(int(cx - 4), int(cy + dy), int(cx + 4), int(cy + dy))
            p.setPen(Qt.NoPen)
            # 右上冲击星芒
            for ang in (-0.6, 0, 0.6):
                x1 = cx + 7 + math.cos(ang) * 4
                y1 = cy - 7 + math.sin(ang) * 4
                p.drawEllipse(QRectF(x1 - 1.2, y1 - 1.2, 2.4, 2.4))
        elif key == "feed":
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(fg, 2))
            p.drawEllipse(QRectF(cx - 8, cy - 8, 16, 16))
            p.setPen(Qt.NoPen)
            p.setBrush(fg)
            for dx, dy in ((-4, -3), (3, -4), (-1, 2), (4, 3)):
                p.drawEllipse(QRectF(cx + dx - 1.4, cy + dy - 1.4, 2.8, 2.8))
        elif key == "walk":
            # 脚印 + 向前的小虚线（比原来的三角形更容易读懂）
            p.drawEllipse(QRectF(cx - 7, cy - 8, 7, 10))          # 前掌
            p.drawRoundedRect(QRectF(cx - 4.5, cy + 3.6, 5, 4.2), 2, 2)   # 脚跟
            p.setPen(QPen(fg, 1.3, Qt.SolidLine, Qt.RoundCap))
            for yy in (-6, -1, 4):
                p.drawLine(int(cx + 3), int(cy + yy), int(cx + 8), int(cy + yy))
            p.setPen(Qt.NoPen)
        elif key == "stroke":
            # 摸头：手掌 + 三根手指 + 上方抚摸弧线
            p.drawRoundedRect(QRectF(cx - 7, cy, 14, 8), 3, 3)
            p.setPen(QPen(fg, 2.2, Qt.SolidLine, Qt.RoundCap))
            for dx in (-4, 0, 4):
                p.drawLine(int(cx + dx), int(cy - 1), int(cx + dx), int(cy - 7))
            p.setPen(QPen(fg, 1.4, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(QRectF(cx - 9, cy - 10, 11, 7), 0, 150 * 16)
            p.drawArc(QRectF(cx + 1, cy - 9, 9, 6), 30 * 16, 130 * 16)
            p.setPen(Qt.NoPen)
        elif key == "sleep":
            # 月牙 + 一颗小星
            moon = QPainterPath()
            moon.addEllipse(QRectF(cx - 7, cy - 7, 13, 13))
            bite = QPainterPath()
            bite.addEllipse(QRectF(cx - 12.8, cy - 9.4, 12, 12))
            p.drawPath(moon.subtracted(bite))
            p.drawPolygon(QPolygonF([
                QPoint(int(cx + 8), int(cy - 8)), QPoint(int(cx + 9.6), int(cy - 6.2)),
                QPoint(int(cx + 8), int(cy - 4)), QPoint(int(cx + 6.4), int(cy - 6.2))]))
        else:  # more
            for dy in (-6, 0, 6):
                p.drawEllipse(QRectF(cx - 2.2, cy + dy - 2.2, 4.4, 4.4))

    @staticmethod
    def _draw_heart(p, x, y, size, alpha):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 105, 150, alpha))
        r = size * 0.32
        p.drawEllipse(QRectF(x - size * 0.28 - r, y - size * 0.15 - r, 2 * r, 2 * r))
        p.drawEllipse(QRectF(x + size * 0.28 - r, y - size * 0.15 - r, 2 * r, 2 * r))
        tri = QPolygonF([QPoint(int(x - size * 0.55), int(y)),
                         QPoint(int(x + size * 0.55), int(y)),
                         QPoint(int(x), int(y + size * 0.7))])
        p.drawPolygon(tri)


if __name__ == "__main__":
    # ---- 崩溃日志：任何未捕获异常都写进 pet.log，方便排查闪退 ----
    import logging
    import traceback

    logging.basicConfig(
        filename=os.path.join(_save_base(), "pet.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8")
    logging.info("小T启动 (pid=%d)", os.getpid())

    def _crash_hook(exc_type, exc, tb):
        logging.error("未捕获异常，小T闪退:\n%s",
                      "".join(traceback.format_exception(exc_type, exc, tb)))
        sys.__excepthook__(exc_type, exc, tb)
    sys.excepthook = _crash_hook

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 防止后台模式下窗口未显示就被判定退出
    pet = DesktopPet()
    app.aboutToQuit.connect(pet._save)
    sys.exit(app.exec_())
