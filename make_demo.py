# -*- coding: utf-8 -*-
"""生成 SakuraView 的「合法示例库」——全部图像用程序合成，不含任何游戏素材。

用途：让人第一次跑通管线时有个能看的东西，也用于 README 截图。
用法: python make_demo.py [输出目录]      # 默认 demo\\CG
需要 Pillow 与 ffmpeg（生成示例视频）。

素材构成：
  · 事件CG  24 张 1280×720 —— 8 种场景（晨樱/晴空/黄昏海/月夜/雨街/雪峰/林间/晚霞窗）× 3 幕
  · 立绘    16 张 720×1080 —— 2 个角色 × 8 张（4 种表情 × 2 种手位）
  · 头像     8 张 360×360  —— 立绘头部放大裁切 + 圆框
  · 动画     2 个 1280×720 4 秒 —— 樱吹雪 / 夜萤（逐帧绘制后管给 ffmpeg）
"""
import os, sys, math, random, subprocess, glob, shutil
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'demo', 'CG')
FONT = r"C:\Windows\Fonts\msyh.ttc"
FONT_B = r"C:\Windows\Fonts\msyhbd.ttc"

W, H = 1280, 720            # 事件 CG / 视频尺寸
SS = 2                      # 超采样倍数（画大图再缩小，边缘才不毛）


# ────────────────────────────── 基础工具 ──────────────────────────────
def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def stop_color(stops, t):
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    for i in range(len(stops) - 1):
        p0, c0 = stops[i]
        p1, c1 = stops[i + 1]
        if p0 <= t <= p1:
            u = 0.0 if p1 <= p0 else (t - p0) / (p1 - p0)
            return lerp(c0, c1, u)
    return stops[-1][1]


def vgrad(size, stops):
    """竖向多段渐变（1px 列 → 放大，比逐块填快得多且没有色带）。"""
    w, h = size
    col = Image.new('RGB', (1, h))
    px = col.load()
    for y in range(h):
        px[0, y] = stop_color(stops, y / max(1, h - 1))
    return col.resize((w, h), Image.BICUBIC)


def alpha_layer(size, paint, blur=0):
    """在 L 蒙版上执行 paint(draw)，可选高斯模糊，返回同尺寸蒙版。"""
    m = Image.new('L', size, 0)
    paint(ImageDraw.Draw(m))
    if blur:
        m = m.filter(ImageFilter.GaussianBlur(blur))
    return m


def paste_alpha(base, mask, color):
    layer = Image.new('RGBA', base.size, tuple(color) + (255,))
    layer.putalpha(mask)
    base.alpha_composite(layer)


def radial_mask(size, center, radius, power=1.6, invert=False):
    """径向蒙版。默认中心亮→边缘暗（invert 反过来）。
       注意：PIL 的 radial_gradient 是「角 = 255」，内切圆处只有 180，
       所以查表要按 255/√2 归一，否则蒙版方形边界上会留一圈台阶（暗场景里一眼看到）。"""
    r = max(2, int(radius))
    g = Image.radial_gradient('L').resize((r * 2, r * 2), Image.BILINEAR)
    edge_v = 255 / math.sqrt(2)
    if invert:
        lut = [int(255 * (1 - max(0.0, 1 - v / edge_v) ** power)) for v in range(256)]
        edge = 255
    else:
        lut = [int(255 * max(0.0, 1 - v / edge_v) ** power) for v in range(256)]
        edge = 0
    g = g.point(lut)
    out = Image.new('L', size, edge)
    out.paste(g, (int(center[0] - r), int(center[1] - r)))
    return out


def bez(p0, p1, p2, p3, n=26):
    out = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        out.append((mt ** 3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t ** 3 * p3[0],
                    mt ** 3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t ** 3 * p3[1]))
    return out


def rot_ellipse(cx, cy, rx, ry, ang, n=18, wobble=0.0, phase=0.0):
    """旋转椭圆的点列（用于花瓣雪片等，不用建临时图）。"""
    ca, sa = math.cos(ang), math.sin(ang)
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        k = 1.0 + wobble * math.sin(a * 2 + phase)
        x = rx * math.cos(a) * k
        y = ry * math.sin(a) * k
        pts.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
    return pts


def grain(img, sigma=10, opacity=0.05):
    n = Image.effect_noise(img.size, sigma).convert('RGB')
    return Image.blend(img, n, opacity)


# ────────────────────────────── 场景元件 ──────────────────────────────
def sky(img, stops, seed_shift=0.0):
    base = vgrad(img.size, stops)
    img.paste(base, (0, 0))


def orb(img, center, r, core, glow_col, glow_r=None, glow_a=150):
    """太阳 / 月亮：柔光 + 实心盘。"""
    gr = int(glow_r or r * 4)
    m = radial_mask(img.size, center, gr, 2.2)
    m = m.point(lambda v: int(v * glow_a / 255))
    paste_alpha(img, m, glow_col)
    d = ImageDraw.Draw(img, 'RGBA')
    d.ellipse([center[0] - r, center[1] - r, center[0] + r, center[1] + r], fill=tuple(core) + (255,))


def rays(img, center, count, length, color, alpha=26, blur=6, seed=1):
    rnd = random.Random(seed)
    w, h = img.size
    def paint(d):
        for i in range(count):
            a = math.pi * 2 * i / count + rnd.uniform(-.12, .12)
            wd = rnd.uniform(.05, .14)
            p1 = (center[0] + math.cos(a - wd) * length, center[1] + math.sin(a - wd) * length)
            p2 = (center[0] + math.cos(a + wd) * length, center[1] + math.sin(a + wd) * length)
            d.polygon([center, p1, p2], fill=int(alpha * rnd.uniform(.5, 1.2)))
    paste_alpha(img, alpha_layer(img.size, paint, blur), color)


def clouds(img, bands, color=(255, 255, 255), seed=3, blur=None):
    """云：每个云团由 4~5 个椭圆叠成（比单个扁椭圆自然）。bands = [(y 比例, 厚度, 团数, 透明度)]"""
    rnd = random.Random(seed)
    w, h = img.size
    bl = blur if blur is not None else h * 0.012
    def paint(d):
        for yp, th, cnt, a in bands:
            for _ in range(cnt):
                cx = rnd.uniform(-.05, 1.05) * w
                cy = yp * h + rnd.uniform(-.6, .6) * th * h
                sc = rnd.uniform(.7, 1.4)
                bw = rnd.uniform(.045, .10) * w * sc
                bh = th * h * sc
                for _j in range(5):
                    ox = rnd.uniform(-1.1, 1.1) * bw
                    oy = rnd.uniform(-.45, .45) * bh
                    rw = bw * rnd.uniform(.45, .95)
                    rh = bh * rnd.uniform(.45, .95)
                    d.ellipse([cx + ox - rw, cy + oy - rh, cx + ox + rw, cy + oy + rh], fill=a)
    paste_alpha(img, alpha_layer(img.size, paint, bl), color)


def ridge(img, base_y, amp, color, seed=1, freq=2.6, alpha=255, jag=0.0):
    """远山剪影（多层叠加就有纵深感）。"""
    w, h = img.size
    rnd = random.Random(seed)
    ph = [rnd.uniform(0, 6.28) for _ in range(4)]
    n = 90
    pts = [(0, h)]
    for i in range(n + 1):
        t = i / n
        y = base_y - amp * (0.52 * math.sin(t * freq * math.pi + ph[0])
                            + 0.30 * math.sin(t * freq * 2.4 * math.pi + ph[1])
                            + 0.18 * math.sin(t * freq * 5.3 * math.pi + ph[2]))
        if jag:
            y += rnd.uniform(-jag, jag)
        pts.append((w * t, y))
    pts.append((w, h))
    d = ImageDraw.Draw(img, 'RGBA')
    d.polygon(pts, fill=tuple(color) + (alpha,))


def _path_y(ctrl, w, sharp):
    """把控制点 [(x比例, y比例)] 连成脊线，返回覆盖全宽的 y 列表。"""
    ctrl = sorted(ctrl)
    xs = [c[0] for c in ctrl]
    ys = [c[1] for c in ctrl]
    out = []
    n = 240
    for i in range(n + 1):
        t = i / n
        if t <= xs[0]:
            out.append(ys[0])
            continue
        if t >= xs[-1]:
            out.append(ys[-1])
            continue
        for j in range(len(xs) - 1):
            if xs[j] <= t <= xs[j + 1]:
                u = (t - xs[j]) / max(1e-9, xs[j + 1] - xs[j])
                if sharp:   # 尖峰：像山峰那样陡起缓落
                    u2 = u ** 0.62 if ys[j + 1] > ys[j] else u ** 1.6
                    u = 0.5 - 0.5 * math.cos(math.pi * u2) if False else u
                    v = ys[j] + (ys[j + 1] - ys[j]) * u2
                else:       # 缓丘：余弦插值
                    v = ys[j] + (ys[j + 1] - ys[j]) * (0.5 - 0.5 * math.cos(math.pi * u))
                out.append(v)
                break
    return out


def mount(img, ctrl, base_y, color, alpha=255, sharp=False, blur=0, snow=None):
    """按控制点画山脊。ctrl=[(x比, y比)]；snow=雪线比例（0~1，从峰顶往下算）。"""
    w, h = img.size
    ys = _path_y(ctrl, w, sharp)
    n = len(ys) - 1
    pts = [(0, base_y)]
    for i, y in enumerate(ys):
        pts.append((w * i / n, y * h))
    pts += [(w, base_y), (w, h), (0, h)]
    mask = Image.new('L', img.size, 0)
    ImageDraw.Draw(mask).polygon(pts, fill=alpha)
    if blur:
        mask = mask.filter(ImageFilter.GaussianBlur(blur))
    paste_alpha(img, mask, color)
    if snow:
        # 雪线跟着山脊走：脊线下移 depth，形成厚薄不一的雪帽（不是一条水平切线）
        top_y = min(ys) * h
        depth = (base_y - top_y) * snow
        rnd = random.Random(int(top_y) + len(ys))
        # 雪线在 depth 上下抖一抖，雪帽边缘才碎
        ph, ph2 = rnd.uniform(0, 6.28), rnd.uniform(0, 6.28)
        upper = [(w * i / n, ys[i] * h) for i in range(n + 1)]
        lower = [(w * i / n, min(base_y - 1, ys[i] * h + depth *
                                 (1 + .28 * math.sin(i * .09 + ph) + .14 * math.sin(i * .23 + ph2))))
                 for i in range(n + 1)][::-1]
        spts = upper + lower
        sm = Image.new('L', img.size, 0)
        ImageDraw.Draw(sm).polygon(spts, fill=255)
        sm = ImageChops.multiply(sm, mask)
        sm = sm.filter(ImageFilter.GaussianBlur(max(1, h * .003)))
        paste_alpha(img, sm, (255, 255, 255))


def water(img, horizon, stops, tint=(255, 255, 255), reflect=0.55, seed=7):
    """水面：把天空镜像压暗贴下去 + 横向波纹。"""
    w, h = img.size
    band = img.crop((0, max(0, horizon - (h - horizon)), w, horizon)).transpose(Image.FLIP_TOP_BOTTOM)
    band = band.resize((w, h - horizon), Image.BICUBIC).filter(ImageFilter.GaussianBlur(max(1, h // 300)))
    band = band.convert('RGB')
    band = Image.blend(band, vgrad((w, h - horizon), stops), 1 - reflect)
    img.paste(band, (0, horizon))
    rnd = random.Random(seed)
    d = ImageDraw.Draw(img, 'RGBA')
    for i in range(16):
        y = horizon + rnd.uniform(0, 1) ** 1.3 * (h - horizon)
        cxn = w * (.5 + rnd.uniform(-.30, .30))
        ln = rnd.uniform(.015, .075) * w
        a = int(rnd.uniform(10, 34) * (1 - (y - horizon) / max(1, h - horizon)))
        d.line([(cxn - ln / 2, y), (cxn + ln / 2, y)], fill=tuple(tint) + (max(0, a),),
               width=max(1, int(h / 520)))


def stars(img, count, seed=11, color=(255, 255, 255), ymax=1.0):
    w, h = img.size
    rnd = random.Random(seed)
    d = ImageDraw.Draw(img, 'RGBA')
    for _ in range(count):
        x, y = rnd.uniform(0, w), rnd.uniform(0, h * ymax)
        r = rnd.uniform(.5, 2.1) * (w / 1280)
        a = int(70 + 150 * (r / (2.1 * w / 1280)) ** 2)
        d.ellipse([x - r, y - r, x + r, y + r], fill=tuple(color) + (a,))
        if r > 1.85 * (w / 1280):     # 只有最亮几颗带十字光
            d.line([(x - r * 3.4, y), (x + r * 3.4, y)], fill=tuple(color) + (a // 5,), width=1)
            d.line([(x, y - r * 3.4), (x, y + r * 3.4)], fill=tuple(color) + (a // 5,), width=1)


def petals(img, count, seed, color=(255, 190, 214), size=9, drift=(0, 0), alpha=220):
    w, h = img.size
    rnd = random.Random(seed)
    d = ImageDraw.Draw(img, 'RGBA')
    for _ in range(count):
        cx = rnd.uniform(-.05, 1.05) * w + drift[0]
        cy = rnd.uniform(-.05, 1.05) * h + drift[1]
        r = rnd.uniform(.55, 1.25) * size * (w / 1280)
        ang = rnd.uniform(0, math.pi)
        d.polygon(rot_ellipse(cx, cy, r * .62, r, ang, wobble=.18, phase=rnd.uniform(0, 6)),
                  fill=tuple(color) + (int(alpha * rnd.uniform(.5, 1)),))


def snow(img, count, seed, size=4):
    petals(img, count, seed, color=(255, 255, 255), size=size, alpha=200)


def rain(img, count, seed, color=(210, 228, 245), length=60, alpha=90):
    w, h = img.size
    rnd = random.Random(seed)
    d = ImageDraw.Draw(img, 'RGBA')
    for _ in range(count):
        x, y = rnd.uniform(-.1, 1.1) * w, rnd.uniform(-.2, 1.05) * h
        ln = rnd.uniform(.5, 1.3) * length * (h / 720)
        d.line([(x, y), (x + ln * .28, y + ln)], fill=tuple(color) + (int(alpha * rnd.uniform(.4, 1)),),
               width=max(1, int(h / 480)))


def tree(img, x, ground, h, color, seed=5, alpha=255, leaves=True):
    """剪影树：主干 + 分枝 + 叶团。"""
    rnd = random.Random(seed)
    d = ImageDraw.Draw(img, 'RGBA')
    c = tuple(color) + (alpha,)
    tw = max(2, int(h * .035))
    d.line([(x, ground), (x - h * .03, ground - h * .55)], fill=c, width=tw)
    top = (x - h * .03, ground - h * .55)
    for i in range(4):
        a = -math.pi / 2 + rnd.uniform(-.9, .9)
        ln = h * rnd.uniform(.22, .38)
        d.line([top, (top[0] + math.cos(a) * ln, top[1] + math.sin(a) * ln)], fill=c, width=max(2, tw // 2))
    if leaves:
        for _ in range(9):
            cx = top[0] + rnd.uniform(-.30, .30) * h
            cy = top[1] + rnd.uniform(-.26, .12) * h
            rr = h * rnd.uniform(.10, .20)
            d.ellipse([cx - rr, cy - rr * .8, cx + rr, cy + rr * .8], fill=c)


def person(img, x, ground, h, color, alpha=255, flip=False, braid=True, skirt=2.5):
    """远景人物剪影：7 头身，肩宽≈1.9 头宽、腰≈1.1、裙摆≈2.5，手臂在肩线内侧。"""
    layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    c = tuple(color) + (alpha,)
    s_ = -1 if flip else 1
    hd = h / 7.0            # 头高
    hw = hd * .40           # 头半宽（头宽≈0.8 头高）
    top = ground - h
    chin = top + hd * .96
    sh = top + hd * 1.30    # 肩线
    waist = ground - h * .38
    hem = ground
    # 头部：先发团再脸，发团略宽略高
    d.ellipse([x - hw * 1.16, top - hd * .04, x + hw * 1.16, chin + hd * .06], fill=c)
    # 颈
    d.polygon([(x - hw * .55, chin - hd * .06), (x + hw * .55, chin - hd * .06),
               (x + hw * .52, sh + hd * .10), (x - hw * .52, sh + hd * .10)], fill=c)
    # 上身 + 裙：肩(1.85) → 腰(1.10) → 裙摆(2.50)
    up = [(x - hw * 1.85, sh + hd * .18), (x - hw * 1.70, sh),
          (x - hw * .62, sh - hd * .02), (x + hw * .62, sh - hd * .02),
          (x + hw * 1.70, sh), (x + hw * 1.85, sh + hd * .18),
          (x + hw * 1.22, waist), (x + hw * skirt, hem),
          (x - hw * skirt, hem), (x - hw * 1.22, waist)]
    d.polygon(up, fill=c)
    # 手臂：从肩内侧垂到腰下，略收
    for sx in (-1, 1):
        d.line([(x + sx * hw * 1.62, sh + hd * .22),
                (x + sx * hw * 1.50, waist + h * .02)],
               fill=c, width=max(3, int(hw * .52)))
    # 垂在身侧的长发
    if braid:
        d.polygon([(x + s_ * hw * 1.05, top + hd * .34), (x + s_ * hw * 1.52, chin + hd * .20),
                   (x + s_ * hw * 1.34, waist - h * .03), (x + s_ * hw * .92, waist - h * .06)], fill=c)
    img.alpha_composite(layer)


def torii(img, x, ground, h, color, alpha=255):
    """鸟居剪影：内倾双柱 + 上翘的笠木 + 岛木 + 贯 + 额束。"""
    layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    c = tuple(color) + (alpha,)
    top = ground - h
    span = h * .40                 # 柱半距
    pw = h * .042                  # 柱宽

    def beam(cy, half, th, up):
        """带轻微上翘的横梁：两端比中间高 up。"""
        n = 24
        up_e, lo_e = [], []
        for i in range(n + 1):
            t = -1 + 2 * i / n
            xx = x + t * half
            yy = cy - up * (t * t)
            up_e.append((xx, yy))
            lo_e.append((xx, yy + th))
        d.polygon(up_e + lo_e[::-1], fill=c)

    # 柱（内倾）
    for sx in (-1, 1):
        d.polygon([(x + sx * span - pw / 2, ground),
                   (x + sx * span + pw / 2, ground),
                   (x + sx * span * .93 + pw * .40, top),
                   (x + sx * span * .93 - pw * .40, top)], fill=c)
    beam(top + h * .035, span + h * .13, h * .050, h * .028)   # 笠木
    beam(top + h * .105, span + h * .02, h * .030, h * .008)   # 岛木
    beam(top + h * .30, span + h * .07, h * .034, 0)           # 贯
    d.rectangle([x - h * .028, top + h * .075, x + h * .028, top + h * .30], fill=c)  # 额束
    img.alpha_composite(layer)


def umbrella(img, x, y, r, color, alpha=255):
    """半圆伞面 + 伞骨 + 短柄。"""
    layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    c = tuple(color) + (alpha,)
    d.chord([x - r, y - r * .96, x + r, y + r * .96], 180, 360, fill=c)
    d.line([(x, y - r * .02), (x, y + r * .30)], fill=c, width=max(2, int(r * .10)))
    img.alpha_composite(layer)


def vignette(img, strength=.5):
    """暗角：中心保留原图，边缘压到 (1-strength)。"""
    w, h = img.size
    r = int(math.hypot(w, h) / 2)
    g = Image.radial_gradient('L').resize((r * 2, r * 2), Image.BILINEAR)
    lut = [int(255 * (1 - strength * (v / 255.0) ** 1.8)) for v in range(256)]
    g = g.point(lut)
    m = Image.new('L', (w, h), lut[255])
    m.paste(g, (w // 2 - r, h // 2 - r))
    dark = Image.new('RGB', (w, h), (0, 0, 0))
    return Image.composite(img, dark, m)


def caption(img, main, sub, color=(255, 255, 255)):
    d = ImageDraw.Draw(img, 'RGBA')
    w, h = img.size
    sc = w / 1280
    try:
        fb = ImageFont.truetype(FONT_B, int(21 * sc))
        fs = ImageFont.truetype(FONT, int(14 * sc))
    except OSError:
        fb = fs = ImageFont.load_default()
    pad = int(34 * sc)
    y = h - pad - int(30 * sc)
    d.text((pad + int(2 * sc), y + int(2 * sc)), main, font=fb, fill=(0, 0, 0, 90))
    d.text((pad, y), main, font=fb, fill=tuple(color) + (238,))
    d.text((pad, y + int(30 * sc)), sub, font=fs, fill=tuple(color) + (150,))


# ────────────────────────────── 8 种场景 ──────────────────────────────
def sc_dawn_sakura(size, seed, t=0.0):
    """晨樱：粉橘天空、低垂的日、远山、樱枝、飘瓣。"""
    img = Image.new('RGBA', size)
    w, h = size
    sky(img, [(0, (86, 104, 158)), (.32, (188, 150, 186)), (.62, (255, 196, 178)),
              (.86, (255, 226, 196)), (1, (255, 240, 214))])
    orb(img, (w * .70, h * .62 - t * h * .04), h * .052, (255, 246, 224), (255, 214, 170), h * .40, 165)
    rays(img, (w * .70, h * .62 - t * h * .04), 12, h * 1.5, (255, 226, 190), 16, h * .012, seed)
    clouds(img, [(.20, .05, 4, 60), (.34, .04, 3, 46)], (255, 214, 214), seed)
    ridge(img, h * .70, h * .16, (140, 128, 168), seed + 1, 2.2)
    ridge(img, h * .78, h * .13, (104, 96, 138), seed + 2, 3.1)
    ridge(img, h * .88, h * .10, (74, 68, 104), seed + 3, 4.2)
    trees = random.Random(seed)
    for i in range(3):
        tree(img, trees.uniform(.05, .95) * w, h * (.90 + .03 * i), h * trees.uniform(.16, .26),
             (52, 46, 74), seed + i, leaves=True)
    petals(img, 46, seed + t * 1000, (255, 208, 224), 10)
    torii(img, w * .63, h * 1.0, h * .55, (38, 32, 54), 245)
    return img


def sc_day_cloud(size, seed, t=0.0):
    """晴空：高饱和蓝天、堆云、草原与孤单的电线杆影子。"""
    img = Image.new('RGBA', size)
    w, h = size
    sky(img, [(0, (58, 122, 208)), (.45, (128, 186, 236)), (.78, (198, 226, 246)), (1, (232, 244, 250))])
    orb(img, (w * .84, h * .16), h * .042, (255, 255, 250), (255, 250, 220), h * .22, 95)
    clouds(img, [(.13, .048, 2, 130), (.27, .042, 2, 100), (.42, .036, 1, 55)],
           (255, 255, 255), seed, blur=h * .009)
    ridge(img, h * .73, h * .05, (150, 190, 200), seed + 1, 1.6, jag=0)
    # 草坡
    d = ImageDraw.Draw(img, 'RGBA')
    rnd = random.Random(seed)
    pts = [(0, h)]
    for i in range(41):
        x = w * i / 40
        y = h * (.80 + .035 * math.sin(i * .5 + seed) + rnd.uniform(-.008, .008))
        pts.append((x, y))
    pts.append((w, h))
    d.polygon(pts, fill=(96, 158, 104, 255))
    pts2 = [(x, y + h * .02) for x, y in pts[1:]] + [(w, h), (0, h)]
    d.polygon(pts2, fill=(66, 126, 82, 255))
    # 电线杆 + 线
    px = w * .12
    d.line([(px, h * .84), (px, h * .30)], fill=(52, 60, 76, 255), width=int(h * .012))
    d.line([(px - w * .035, h * .36), (px + w * .035, h * .36)], fill=(52, 60, 76, 255), width=int(h * .009))
    for i in range(3):
        d.line([(px - w * .035 + i * w * .028, h * .355),
                (w * 1.05, h * (.30 + i * .02))], fill=(52, 60, 76, 150), width=max(1, int(h * .003)))
    # 云影
    m = alpha_layer(size, lambda dr: [dr.ellipse([w * (.2 + .55 * k), h * .70, w * (.45 + .55 * k), h * .80],
                                                 fill=70) for k in range(2)], h * .04)
    paste_alpha(img, m, (40, 80, 60))
    return img


def sc_sunset_sea(size, seed, t=0.0):
    """黄昏海：橙红天、落日、海面金色反光、海鸥。"""
    img = Image.new('RGBA', size)
    w, h = size
    hz = int(h * .62)
    sky(img, [(0, (46, 58, 118)), (.28, (146, 88, 132)), (.52, (241, 132, 104)),
              (.78, (255, 176, 108)), (1, (255, 214, 150))])
    orb(img, (w * .5, hz - h * .03), h * .055, (255, 238, 206), (255, 176, 116), h * .46, 190)
    clouds(img, [(.30, .03, 4, 90), (.42, .025, 3, 70)], (255, 170, 130), seed, blur=h * .01)
    # 远处的岛（先画，水面镜像时才会被反射到海里）
    mount(img, [(0, hz / h), (.1, hz / h - .02), (.22, hz / h - .055), (.34, hz / h - .02),
                (.5, hz / h - .008), (1, hz / h)], hz, (86, 62, 96), 235, sharp=True)
    water(img, hz, [(0, (168, 96, 92)), (.6, (96, 62, 84)), (1, (44, 40, 66))],
          (255, 210, 160), .55, seed)
    # 日落在水面的光柱
    d = ImageDraw.Draw(img, 'RGBA')
    rnd = random.Random(seed)
    for i in range(18):
        y = hz + rnd.uniform(0, 1) ** 1.5 * (h - hz) * .9
        ln = rnd.uniform(.015, .085) * w * (1 - (y - hz) / (h - hz) * .5)
        a = int(80 * (1 - (y - hz) / (h - hz)) ** 1.1)
        cx0 = w * .5 + rnd.uniform(-.02, .02) * w
        d.line([(cx0 - ln / 2, y), (cx0 + ln / 2, y)],
               fill=(255, 224, 168, max(0, a)), width=max(1, int(h / 420)))
    # 前景礁石
    mount(img, [(0, 1.06), (.08, 1.0), (.16, 1.03), (.24, .995), (.33, 1.04), (.42, 1.02),
                (.52, 1.12), (1, 1.2)], h * 1.01, (34, 28, 46), 255, sharp=True)
    # 海鸥
    for i, (bx, by, s) in enumerate(((0.34, 0.28, 1.0), (0.40, 0.24, .8), (0.30, 0.33, .7))):
        for sx in (-1, 1):
            d.arc([bx * w + sx * s * 14 - 14, by * h - 8, bx * w + sx * s * 14 + 14, by * h + 10],
                  200 if sx < 0 else 340, 340 if sx < 0 else 480, fill=(50, 40, 60, 200),
                  width=max(1, int(h * .004)))
    return img


def sc_night_moon(size, seed, t=0.0):
    """月夜：深蓝渐变、大月、星、远树、湖面。"""
    img = Image.new('RGBA', size)
    w, h = size
    hz = int(h * .74)
    sky(img, [(0, (12, 18, 44)), (.40, (26, 42, 84)), (.72, (58, 72, 118)), (1, (96, 108, 148))])
    stars(img, 150, seed, (226, 238, 255), ymax=.72)
    orb(img, (w * .68, h * .26 - t * h * .02), h * .062, (250, 250, 235), (200, 216, 255), h * .42, 120)
    clouds(img, [(.30, .035, 3, 70), (.42, .03, 2, 55)], (150, 168, 210), seed, blur=h * .014)
    # 远岸 + 树，画在水面前面才有倒影
    mount(img, [(0, hz / h - .01), (.18, hz / h - .045), (.40, hz / h - .012),
                (.62, hz / h - .05), (.84, hz / h - .015), (1, hz / h - .03)],
          hz, (14, 20, 40), 255)
    rnd = random.Random(seed)
    for i in range(5):
        tree(img, rnd.uniform(0, 1) * w, h * .745, h * rnd.uniform(.10, .16), (10, 14, 30), seed + i)
    water(img, hz, [(0, (30, 42, 74)), (1, (14, 20, 40))], (190, 210, 255), .45, seed)
    # 萤火（带光晕的小点）
    for i in range(11):
        x = rnd.uniform(.05, .95) * w
        y = h * (.60 + rnd.uniform(0, .30)) - t * h * .05
        r = rnd.uniform(1.3, 2.2) * (w / 1280)
        m = radial_mask(size, (x, y), r * 6, 2.0)
        m = m.point(lambda v: int(v * .38))
        paste_alpha(img, m, (255, 238, 160))
        ImageDraw.Draw(img, 'RGBA').ellipse([x - r, y - r, x + r, y + r], fill=(255, 250, 208, 245))
    return img


def sc_rain_street(size, seed, t=0.0):
    """雨街：冷灰天、楼房剪影、湿润路面反光、雨线。"""
    img = Image.new('RGBA', size)
    w, h = size
    hz = int(h * .70)
    sky(img, [(0, (58, 68, 88)), (.45, (92, 104, 126)), (.75, (128, 138, 156)), (1, (150, 158, 174))])
    clouds(img, [(.16, .05, 4, 80), (.30, .04, 3, 60)], (170, 180, 200), seed, blur=h * .02)
    d = ImageDraw.Draw(img, 'RGBA')
    rnd = random.Random(seed)
    # 楼房
    x = -w * .02
    while x < w * 1.02:
        bw = rnd.uniform(.05, .13) * w
        bh = rnd.uniform(.16, .42) * h
        d.rectangle([x, hz - bh, x + bw, hz], fill=(44, 50, 66, 255))
        # 窗
        cols = max(1, int(bw / (w * .028)))
        rows = max(1, int(bh / (h * .075)))
        for cx in range(cols):
            for cy in range(rows):
                if rnd.random() < .38:
                    wx = x + (cx + .5) * bw / cols - w * .008
                    wy = hz - bh + (cy + .5) * bh / rows - h * .012
                    warm = rnd.random() < .7
                    col = (255, 214, 148, 210) if warm else (170, 210, 240, 170)
                    d.rectangle([wx, wy, wx + w * .014, wy + h * .016], fill=col)
        x += bw + w * .004
    # 地面 + 反光
    d.rectangle([0, hz, w, h], fill=(36, 40, 52, 255))
    band = img.crop((0, hz - (h - hz), w, hz)).transpose(Image.FLIP_TOP_BOTTOM)
    band = band.filter(ImageFilter.GaussianBlur(h * .01))
    band.putalpha(90)
    img.alpha_composite(band, (0, hz))
    for i in range(9):
        y = hz + rnd.uniform(.08, 1) * (h - hz)
        d.line([(rnd.uniform(0, w * .8), y), (rnd.uniform(w * .2, w), y)],
               fill=(180, 200, 230, int(rnd.uniform(4, 11))), width=max(1, int(h / 400)))
    # 路灯
    lx = w * .82
    d.line([(lx, h * .76), (lx, h * .34)], fill=(24, 28, 40, 255), width=int(h * .008))
    d.line([(lx, h * .35), (lx - w * .045, h * .345)], fill=(24, 28, 40, 255), width=int(h * .006))
    m = radial_mask(size, (lx - w * .045, h * .36), h * .22, 2.0)
    m = m.point(lambda v: int(v * .75))
    paste_alpha(img, m, (255, 226, 168))
    # 伞下的人
    person(img, w * .46, h * .965, h * .42, (18, 22, 34), 248, skirt=2.2)
    umbrella(img, w * .46, h * .60, w * .075, (20, 24, 38), 252)
    rain(img, 130, seed, (198, 218, 240), 78, 55)
    rain(img, 26, seed + 1, (222, 236, 250), 130, 34)
    return img


def sc_snow_peak(size, seed, t=0.0):
    """雪峰：冷青天、三层雪脊（近处深、远处淡）、雾带、雪片。"""
    img = Image.new('RGBA', size)
    w, h = size
    sky(img, [(0, (38, 62, 96)), (.42, (108, 148, 186)), (.72, (176, 204, 226)), (1, (214, 230, 240))])
    orb(img, (w * .22, h * .20), h * .04, (255, 255, 248), (232, 244, 255), h * .28, 110)
    clouds(img, [(.22, .035, 3, 60), (.34, .03, 2, 45)], (255, 255, 255), seed, blur=h * .016)
    # 远 → 近：山脊一样高，只是颜色加深、雪线降低
    mount(img, [(0, .70), (.12, .62), (.22, .50), (.31, .60), (.44, .45), (.55, .58),
                (.68, .48), (.80, .60), (.90, .54), (1, .66)],
          h * .90, (170, 192, 214), 255, sharp=True, snow=.34)
    mount(img, [(0, .82), (.10, .76), (.20, .66), (.30, .76), (.42, .62), (.52, .74),
                (.64, .64), (.76, .76), (.88, .68), (1, .80)],
          h * 1.0, (110, 136, 168), 255, sharp=True, snow=.26)
    mount(img, [(0, .98), (.08, .92), (.16, .84), (.24, .94), (.33, .86), (.42, .98),
                (.52, .92), (.62, .84), (.72, .96), (.82, .90), (.92, .98), (1, 1.02)],
          h * 1.08, (62, 82, 112), 255, sharp=True, snow=.20)
    # 雾：山腰的软云团（比横条自然）
    def fog(dr):
        rnd = random.Random(seed + 7)
        for _ in range(16):
            cx = rnd.uniform(-.1, 1.1) * w
            cy = h * rnd.uniform(.58, .86)
            rx = rnd.uniform(.10, .26) * w
            ry = rnd.uniform(.012, .035) * h
            dr.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=rnd.randint(40, 85))
    paste_alpha(img, alpha_layer(size, fog, h * .022), (228, 240, 250))
    snow(img, 150, seed, 4)
    return img


def sc_forest_light(size, seed, t=0.0):
    """林间光：树冠压顶、树干逆光、斜射光柱、地面光斑、浮尘。"""
    img = Image.new('RGBA', size)
    w, h = size
    rnd = random.Random(seed)
    sky(img, [(0, (196, 210, 130)), (.18, (168, 196, 116)), (.55, (120, 168, 104)),
              (.82, (92, 140, 92)), (1, (64, 104, 76))])
    # 逆光光斑（远处林间空地）
    m = radial_mask(size, (w * .62, h * .30), h * .70, 2.0)
    m = m.point(lambda v: int(v * .9))
    paste_alpha(img, m, (246, 246, 178))
    # 光柱（斜向，先画，稍后被树挡）
    def rays_(dr):
        r2 = random.Random(seed + 5)
        for i in range(7):
            x0 = w * (.30 + i * .11) + r2.uniform(-.03, .03) * w
            wd = w * r2.uniform(.012, .028)
            dr.polygon([(x0, -h * .05), (x0 + wd, -h * .05),
                        (x0 + wd * 1.5 - w * .22, h * 1.05), (x0 + wd * .4 - w * .22, h * 1.05)],
                       fill=r2.randint(30, 60))
    paste_alpha(img, alpha_layer(size, rays_, h * .010), (255, 252, 206))
    # 树干（近处粗、远处细；带两根分枝）
    for i in range(5):
        x = w * (i + .35) / 5.0 + rnd.uniform(-.02, .02) * w
        tw = w * rnd.uniform(.016, .032)
        lean = rnd.uniform(-.012, .012) * w
        d = ImageDraw.Draw(img, 'RGBA')
        d.polygon([(x - tw / 2, h * 1.02), (x + tw / 2, h * 1.02),
                   (x + tw * .26 + lean, -h * .05), (x - tw * .26 + lean, -h * .05)],
                  fill=(36, 48, 38, 250))
        # 受光侧的一线暖光
        d.line([(x + tw * .18, h), (x + tw * .10 + lean, -h * .04)], fill=(178, 186, 120, 120),
               width=max(1, int(tw * .16)))
    # 树冠：顶部一条起伏的暗绿带 + 下沿挂下来的叶团
    def canopy(dr):
        r2 = random.Random(seed + 9)
        n = 90
        top_pts = [(0, -h * .05)]
        bot = []
        for i in range(n + 1):
            xx = w * i / n
            u = i / n
            yy = h * (.10 + .05 * math.sin(u * 5.1 + r2.uniform(0, .4))
                      + .03 * math.sin(u * 11 + 1.3))
            bot.append((xx, yy))
        dr.polygon(top_pts + bot + [(w, -h * .05)], fill=255)
        for i in range(0, n + 1, 2):
            xx, yy = bot[i]
            rr = r2.uniform(.018, .045) * w
            dr.ellipse([xx - rr, yy - rr * .5, xx + rr, yy + rr * 1.1], fill=255)
    paste_alpha(img, alpha_layer(size, canopy, h * .004), (22, 36, 28))
    # 地面
    d = ImageDraw.Draw(img, 'RGBA')
    gy = h * .84
    d.polygon([(0, gy + h * .02), (w * .3, gy - h * .02), (w * .62, gy + h * .01),
               (w, gy - h * .03), (w, h), (0, h)], fill=(58, 80, 54, 255))
    # 地面光斑（暖色、模糊）
    def pools(dr):
        for _ in range(18):
            cx, cy = rnd.uniform(0, w), h * rnd.uniform(.85, 1.02)
            rr = rnd.uniform(.02, .055) * w
            dr.ellipse([cx - rr * 2.6, cy - rr * .5, cx + rr * 2.6, cy + rr * .5],
                       fill=rnd.randint(30, 95))
    paste_alpha(img, alpha_layer(size, pools, h * .018), (240, 234, 168))
    # 前景灌木剪影（压住下方，视线才往中间收）
    def bush(dr):
        for _ in range(26):
            cx = rnd.choice((rnd.uniform(-.08, .18), rnd.uniform(.82, 1.08))) * w
            cy = h * rnd.uniform(.90, 1.06)
            rr = rnd.uniform(.03, .075) * w
            dr.ellipse([cx - rr, cy - rr * .8, cx + rr, cy + rr * .5], fill=255)
    paste_alpha(img, alpha_layer(size, bush, h * .006), (26, 42, 32))
    # 浮尘
    d = ImageDraw.Draw(img, 'RGBA')
    for i in range(46):
        cx, cy = rnd.uniform(0, w), rnd.uniform(0, h)
        rr = rnd.uniform(.0015, .0045) * w
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(255, 255, 226, rnd.randint(70, 200)))
    return img


def sc_window_dusk(size, seed, t=0.0):
    """晚霞窗：室内暗、窗外交接黄昏天空、窗棂剪影、桌上的花。"""
    img = Image.new('RGBA', size, (26, 22, 32, 255))
    w, h = size
    # 窗外天空（贴在小图上再放大到窗框区域）
    sky_img = Image.new('RGBA', (w, h))
    sky(sky_img, [(0, (72, 78, 140)), (.35, (186, 116, 148)), (.62, (255, 158, 118)), (1, (255, 206, 150))])
    orb(sky_img, (w * .30, h * .48), h * .05, (255, 240, 214), (255, 168, 120), h * .34, 170)
    ridge(sky_img, h * .55, h * .16, (92, 66, 104), seed, 2.4, alpha=230)
    ridge(sky_img, h * .60, h * .12, (60, 44, 78), seed + 1, 3.4, alpha=240)
    petals(sky_img, 18, seed + 3, (255, 226, 214), 9, alpha=160)
    wx0, wy0, wx1, wy1 = w * .10, h * .12, w * .90, h * .84
    img.paste(sky_img.crop((int(wx0), int(wy0), int(wx1), int(wy1))), (int(wx0), int(wy0)))
    d = ImageDraw.Draw(img, 'RGBA')
    # 窗棂
    bar = w * .016
    d.rectangle([wx0 - bar, wy0 - bar, wx1 + bar, wy0], fill=(30, 26, 34, 255))
    d.rectangle([wx0 - bar, wy1, wx1 + bar, wy1 + bar * 2.4], fill=(30, 26, 34, 255))
    d.rectangle([wx0 - bar * 1.6, wy0 - bar, wx0, wy1 + bar * 2.4], fill=(30, 26, 34, 255))
    d.rectangle([wx1, wy0 - bar, wx1 + bar * 1.6, wy1 + bar * 2.4], fill=(30, 26, 34, 255))
    d.rectangle([(wx0 + wx1) / 2 - bar * .5, wy0, (wx0 + wx1) / 2 + bar * .5, wy1], fill=(30, 26, 34, 255))
    # 窗台
    d.rectangle([0, wy1 + bar * 2.0, w, wy1 + bar * 4.2], fill=(44, 36, 44, 255))
    # 花瓶与花枝
    cx = w * .22
    base = wy1 + bar * 2.0
    d.polygon([(cx - w * .026, base), (cx + w * .026, base), (cx + w * .018, base - h * .13),
               (cx - w * .018, base - h * .13)], fill=(58, 48, 62, 255))
    for i in range(5):
        a = -math.pi / 2 + (i - 2) * .30
        ln = h * (.13 + .035 * (i % 2))
        ex, ey = cx + math.cos(a) * ln, base - h * .13 + math.sin(a) * ln
        d.line([(cx, base - h * .12), (ex, ey)], fill=(40, 34, 46, 255), width=max(2, int(h * .006)))
        # 叶片
        d.polygon(rot_ellipse(cx + math.cos(a) * ln * .55 + h * .012,
                              base - h * .12 + math.sin(a) * ln * .55,
                              h * .014, h * .034, a + .9),
                  fill=(52, 62, 46, 255))
        # 五瓣花
        rr = h * .014
        for k in range(5):
            pa = k * math.pi * 2 / 5 + i
            d.ellipse([ex + math.cos(pa) * rr * .9 - rr * .8, ey + math.sin(pa) * rr * .9 - rr * .8,
                       ex + math.cos(pa) * rr * .9 + rr * .8, ey + math.sin(pa) * rr * .9 + rr * .8],
                      fill=(226, 150, 158, 255))
        d.ellipse([ex - rr * .5, ey - rr * .5, ex + rr * .5, ey + rr * .5], fill=(250, 226, 190, 255))
    # 室内暖光晕
    m = radial_mask(size, (w * .78, h * .82), h * .55, 2.4)
    m = m.point(lambda v: int(v * .28))
    paste_alpha(img, m, (255, 196, 140))
    return img


SCENES = [
    ('晨樱', 'Sakura Dawn', sc_dawn_sakura),
    ('晴空', 'Clear Sky', sc_day_cloud),
    ('黄昏海', 'Sunset Sea', sc_sunset_sea),
    ('月夜', 'Moonlit Night', sc_night_moon),
    ('雨街', 'Rainy Street', sc_rain_street),
    ('雪峰', 'Snow Peak', sc_snow_peak),
    ('林间光', 'Forest Light', sc_forest_light),
    ('晚霞窗', 'Dusk Window', sc_window_dusk),
]


def render_scene(fn, seed, t=0.0, size=(W, H), ss=SS):
    big = (size[0] * ss, size[1] * ss)
    img = fn(big, seed, t).convert('RGB')
    if ss != 1:
        img = img.resize(size, Image.LANCZOS)
    return img


def finish(img, main, sub, soft=.45):
    img = vignette(img, soft)
    img = grain(img, 9, .045)
    caption(img, main, sub)
    return img


# ────────────────────────────── 立绘（角色） ──────────────────────────────
CHARS = [
    dict(name='アカネ', hair=(247, 150, 176), hair_d=(214, 112, 146), hair_l=(255, 200, 214),
         eye=(196, 78, 110), back=(255, 226, 232), accent=(240, 130, 160)),
    dict(name='ミドリ', hair=(126, 194, 160), hair_d=(90, 158, 126), hair_l=(186, 226, 200),
         eye=(64, 148, 116), back=(224, 244, 234), accent=(110, 190, 156)),
]
SKIN = (255, 233, 222)
SKIN_D = (243, 206, 194)
UNI = (58, 66, 94)
UNI_D = (42, 48, 72)
WHITE = (250, 250, 252)


def draw_face(img, cx, cy, ch, expr, sc=1.0):
    """在 (cx,cy) 头部中心画面部：眼、眉、鼻、嘴、腮红。sc 为整体比例。"""
    d = ImageDraw.Draw(img, 'RGBA')
    k = sc
    # 腮红
    for sx in (-1, 1):
        d.ellipse([cx + sx * 62 * k - 20 * k, cy + 22 * k - 9 * k,
                   cx + sx * 62 * k + 20 * k, cy + 22 * k + 9 * k], fill=(255, 146, 156, 46))
    ey = cy + 8 * k
    for sx in (-1, 1):
        ex = cx + sx * 46 * k
        if expr == 3:      # 闭眼：弯月
            d.arc([ex - 26 * k, ey - 16 * k, ex + 26 * k, ey + 16 * k], 200, 340,
                  fill=(60, 48, 58, 255), width=max(3, int(5 * k)))
        else:
            hh = 30 * k if expr != 2 else 34 * k
            d.ellipse([ex - 24 * k, ey - hh, ex + 24 * k, ey + hh], fill=WHITE + (255,))
            pw = 17 * k if expr != 2 else 15 * k
            d.ellipse([ex - pw, ey - hh * .95, ex + pw, ey + hh * .95], fill=ch['eye'] + (255,))
            d.ellipse([ex - 8 * k, ey - 10 * k, ex + 8 * k, ey + 12 * k], fill=(34, 26, 36, 255))
            d.ellipse([ex - pw * .55, ey - hh * .62, ex + pw * .1, ey - hh * .2], fill=(255, 255, 255, 235))
            d.ellipse([ex + pw * .1, ey + hh * .18, ex + pw * .55, ey + hh * .5], fill=(255, 255, 255, 120))
            # 上眼线
            d.arc([ex - 26 * k, ey - hh - 4 * k, ex + 26 * k, ey + hh * .5], 190, 350,
                  fill=(52, 42, 52, 255), width=max(3, int(4.5 * k)))
        # 眉
        by = ey - (44 if expr != 2 else 50) * k
        d.arc([ex - 24 * k, by - 10 * k, ex + 24 * k, by + 12 * k], 200, 340,
              fill=(150, 106, 100, 220), width=max(2, int(3.4 * k)))
    # 鼻
    d.arc([cx - 5 * k, cy + 34 * k, cx + 9 * k, cy + 46 * k], 110, 200,
          fill=(206, 152, 142, 210), width=max(2, int(2.6 * k)))
    # 嘴
    my = cy + 62 * k
    if expr == 0:      # 微笑
        d.arc([cx - 16 * k, my - 12 * k, cx + 16 * k, my + 12 * k], 20, 160,
              fill=(176, 92, 100, 255), width=max(2, int(3.2 * k)))
    elif expr == 2:    # 惊讶
        d.ellipse([cx - 8 * k, my - 9 * k, cx + 8 * k, my + 9 * k], fill=(168, 84, 94, 255))
    else:              # 平静
        d.line([(cx - 12 * k, my), (cx + 12 * k, my)], fill=(176, 92, 100, 240),
               width=max(2, int(3.0 * k)))


def draw_character(size, ch, expr=0, arm=0, tilt=0.0, seed=0):
    """半身立绘。顺序：身体剪影 → 后发 → 颈 → 脸 → 刘海 → 领口/领结 → 脸。
       关键：身体是一整块（不画独立手臂），细节全部压在它上面，才不会出现「一块块板子」。"""
    Wc, Hc = size
    s = 2 * (Wc / 720.0)
    canvas = Image.new('RGBA', (Wc * 2, Hc * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas, 'RGBA')
    cx = Wc * s / 2
    hy = 340 * s                    # 头中心
    hrx, hry = 116 * s, 140 * s     # 头半宽/半高
    sy = hy + hry * 1.06            # 肩线

    # ① 身体（肩 → 躯干，底部出画；两侧略放宽，像外套）
    body = [(cx - hrx * 1.86, sy + 70 * s),
            (cx - hrx * 1.66, sy - 10 * s),
            (cx - hrx * .70, sy - 34 * s),
            (cx + hrx * .70, sy - 34 * s),
            (cx + hrx * 1.66, sy - 10 * s),
            (cx + hrx * 1.86, sy + 70 * s),
            (cx + hrx * 1.92, Hc * 2), (cx - hrx * 1.92, Hc * 2)]
    d.polygon(body, fill=UNI + (255,))
    # 侧光：左肩一条暗面
    d.polygon([(cx - hrx * 1.86, sy + 70 * s), (cx - hrx * 1.66, sy - 10 * s),
               (cx - hrx * 1.20, sy - 26 * s), (cx - hrx * 1.34, Hc * 2),
               (cx - hrx * 2.30, Hc * 2)], fill=UNI_D + (255,))

    # ② 后发（从左肩垂到胸口，右侧也留一绺）
    d.polygon(bez((cx - hrx * 1.04, hy - hry * .86),
                  (cx - hrx * 1.52, hy + hry * .20),
                  (cx - hrx * 1.42, hy + hry * 1.10),
                  (cx - hrx * 1.16, hy + hry * 1.75)) +
              [(cx - hrx * .74, hy + hry * 1.80), (cx - hrx * .82, hy + hry * .90),
               (cx - hrx * .94, hy + hry * .10)], fill=ch['hair_d'] + (255,))
    d.polygon(bez((cx + hrx * 1.04, hy - hry * .86),
                  (cx + hrx * 1.52, hy + hry * .24),
                  (cx + hrx * 1.44, hy + hry * 1.16),
                  (cx + hrx * 1.20, hy + hry * 1.82)) +
              [(cx + hrx * .78, hy + hry * 1.86), (cx + hrx * .86, hy + hry * .92),
               (cx + hrx * .96, hy + hry * .10)], fill=ch['hair_d'] + (255,))
    # 头顶发量
    d.ellipse([cx - hrx * 1.10, hy - hry * 1.24, cx + hrx * 1.10, hy + hry * 1.06],
              fill=ch['hair'] + (255,))

    # ③ 颈
    d.polygon([(cx - hrx * .40, hy + hry * .62), (cx + hrx * .40, hy + hry * .62),
               (cx + hrx * .46, sy + hry * .10), (cx - hrx * .46, sy + hry * .10)],
              fill=SKIN_D + (255,))

    # ④ 脸（下颌带一点尖）
    d.polygon([(cx - hrx * .90, hy - hry * .30), (cx - hrx * .88, hy + hry * .34),
               (cx - hrx * .48, hy + hry * .86), (cx, hy + hry * 1.02),
               (cx + hrx * .48, hy + hry * .86), (cx + hrx * .88, hy + hry * .34),
               (cx + hrx * .90, hy - hry * .30)], fill=SKIN + (255,))
    d.ellipse([cx - hrx * .90, hy - hry * .98, cx + hrx * .90, hy + hry * .40], fill=SKIN + (255,))

    # ⑤ 刘海：先把发际线补满（脸是后画的，不补会露出皮肤形成锯齿），再挂几片尖角
    d.ellipse([cx - hrx * 1.06, hy - hry * 1.22, cx + hrx * 1.06, hy - hry * .26],
              fill=ch['hair'] + (255,))
    for k in range(8):
        u = -0.94 + k * (1.88 / 7)
        x0 = cx + u * hrx * .98
        ln = hry * (0.40 + 0.22 * math.cos(u * 1.5) + (0.05 if k % 2 else 0))
        wd = hrx * .16
        tx = x0 + u * hrx * .10 + wd * .18        # 尖端往外偏一点，才有「分束」感
        d.polygon([(x0 - wd, hy - hry * .70), (x0 + wd, hy - hry * .70),
                   (tx + wd * .28, hy - hry * .70 + ln * .70),
                   (tx, hy - hry * .70 + ln)],
                  fill=ch['hair'] + (255,))
    # 发丝高光：头顶一小片柔亮（太大就像秃了一块）
    d.ellipse([cx - hrx * .60, hy - hry * 1.14, cx + hrx * .58, hy - hry * .88],
              fill=ch['hair_l'] + (34,))
    # 发带
    d.polygon([(cx + hrx * .74, hy - hry * .92), (cx + hrx * 1.30, hy - hry * 1.02),
               (cx + hrx * 1.26, hy - hry * .80), (cx + hrx * .76, hy - hry * .76)],
              fill=ch['accent'] + (255,))

    # ⑥ 领口：白衬衫 V + 藏青翻领 + 领结
    y0 = sy + hry * .02
    d.polygon([(cx - hrx * .78, y0), (cx + hrx * .78, y0),
               (cx + hrx * .50, y0 + hry * .52), (cx, y0 + hry * .72),
               (cx - hrx * .50, y0 + hry * .52)], fill=WHITE + (255,))
    for sx in (-1, 1):
        d.polygon([(cx + sx * hrx * .78, y0 - hry * .02), (cx + sx * hrx * 1.26, y0 + hry * .18),
                   (cx + sx * hrx * .84, y0 + hry * .74), (cx + sx * hrx * .44, y0 + hry * .50)],
                  fill=UNI_D + (255,))
    # 腰带（把整块深蓝切开，不然像一件大斗篷）
    wy = sy + hry * 1.30
    d.rectangle([cx - hrx * 1.87, wy, cx + hrx * 1.87, wy + hry * .10],
                fill=lerp(ch['accent'], UNI, .35) + (255,))
    by = y0 + hry * .60
    d.polygon([(cx, by), (cx - hrx * .52, by - hry * .16), (cx - hrx * .52, by + hry * .16)],
              fill=ch['accent'] + (255,))
    d.polygon([(cx, by), (cx + hrx * .52, by - hry * .16), (cx + hrx * .52, by + hry * .16)],
              fill=ch['accent'] + (255,))
    d.ellipse([cx - hrx * .14, by - hry * .13, cx + hrx * .14, by + hry * .13],
              fill=ch['hair_d'] + (255,))

    # ⑦ 五官
    draw_face(canvas, cx, hy, ch, expr, s)

    out = canvas.resize((Wc, Hc), Image.LANCZOS)
    if tilt:
        out = out.rotate(tilt, resample=Image.BICUBIC, center=(Wc / 2, Hc * .55))
    return out


def make_portrait(path, ch, expr, arm, seed):
    """立绘 = 背景 + 角色叠层（背景是柔光 + 花瓣，不能抢脸）。"""
    Wc, Hc = 720, 1080
    bg = Image.new('RGBA', (Wc, Hc))
    base = vgrad((Wc, Hc), [(0, lerp(ch['back'], (255, 255, 255), .55)),
                            (.55, ch['back']),
                            (1, lerp(ch['back'], (150, 150, 165), .28))]).convert('RGBA')
    bg.paste(base, (0, 0))
    m = radial_mask((Wc, Hc), (Wc * .5, Hc * .30), Hc * .62, 2.0)
    m = m.point(lambda v: int(v * .85))
    paste_alpha(bg, m, lerp(ch['back'], (255, 255, 255), .8))
    # 背景：左下角一团暗、右上角一团亮，再撒几片大花瓣（原来那层斜纹太抢，删掉）
    m = radial_mask((Wc, Hc), (Wc * .18, Hc * .92), Hc * .55, 2.2)
    m = m.point(lambda v: int(v * .35))
    paste_alpha(bg, m, lerp(ch['back'], (120, 110, 140), .45))
    petals(bg, 16, seed, lerp(ch['hair_l'], (255, 255, 255), .35), 13, alpha=130)
    bg.alpha_composite(draw_character((Wc, Hc), ch, expr, arm, seed=seed))
    out = bg.convert('RGB')
    out = vignette(out, .30)
    return out


def make_avatar(path, ch, expr, seed):
    """头像 = 立绘头部放大 + 圆框（不新画，保证和立绘同一个人）。"""
    port = make_portrait(None, ch, expr, 0, seed)
    S = 360
    head = port.crop((int(720 * .5 - 210), int(1080 * .315 - 210), int(720 * .5 + 210), int(1080 * .315 + 210)))
    head = head.resize((S * 2, S * 2), Image.LANCZOS).resize((S, S), Image.LANCZOS)
    canvas = Image.new('RGB', (S, S), lerp(ch['back'], (28, 26, 34), .25))
    mask = Image.new('L', (S, S), 0)
    ImageDraw.Draw(mask).ellipse([3, 3, S - 4, S - 4], fill=255)
    canvas.paste(head, (0, 0), mask)
    d = ImageDraw.Draw(canvas)
    d.ellipse([2, 2, S - 3, S - 3], outline=ch['accent'], width=5)
    d.ellipse([9, 9, S - 10, S - 10], outline=(255, 255, 255), width=2)
    return canvas


# ────────────────────────────── 视频 ──────────────────────────────
def find_ffmpeg():
    """ffmpeg 探测：本地 tools/ → 系统 PATH → imageio_ffmpeg 自带的那个（不写死任何用户目录）"""
    for d in ('tools', 'SakuraView-tools', '.'):
        hits = sorted(glob.glob(os.path.join(HERE, d, 'ffmpeg*.exe')))
        if hits:
            return hits[-1]
    w = shutil.which('ffmpeg')
    if w:
        return w
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def make_video(ff, path, bg_fn, fg_fn, seconds=4, fps=30, size=(W, H)):
    """背景渲一次，逐帧只叠动效 → 管 rawvideo 给 ffmpeg。"""
    n = seconds * fps
    bg = render_scene(bg_fn, 21, 0.0, size, ss=1)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cmd = [ff, '-y', '-hide_banner', '-loglevel', 'error',
           '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '%dx%d' % size, '-r', str(fps), '-i', '-',
           '-pix_fmt', 'yuv420p', '-c:v', 'libx264', '-preset', 'medium', '-crf', '20',
           '-movflags', '+faststart', path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for i in range(n):
            frame = bg.copy()
            img = frame.convert('RGBA')
            fg_fn(img, i / n)
            p.stdin.write(img.convert('RGB').tobytes())
    finally:
        p.stdin.close()
        err = p.stderr.read().decode('utf-8', 'replace')
        rc = p.wait()
    return rc == 0, err


def fg_sakura(img, t):
    w, h = img.size
    petals(img, 70, 1234 + int(t * 1000), (255, 206, 224), 12, drift=(0, t * h * .22))
    petals(img, 30, 777 + int(t * 1000), (255, 236, 244), 8, drift=(-t * w * .05, t * h * .34))
    d = ImageDraw.Draw(img, 'RGBA')
    m = radial_mask(img.size, (w * .70, h * .58 - t * h * .04), h * .30, 2.2)
    m = m.point(lambda v: int(v * .18))
    paste_alpha(img, m, (255, 235, 200))


def fg_firefly(img, t):
    w, h = img.size
    rnd = random.Random(99)
    d = ImageDraw.Draw(img, 'RGBA')
    for i in range(26):
        bx = rnd.uniform(0, 1) * w
        by = h * (.52 + rnd.uniform(0, .44))
        ph = rnd.uniform(0, 6.28)
        x = bx + math.sin(ph + t * 6.28 * rnd.uniform(.6, 1.4)) * w * .035
        y = by - t * h * .10 * rnd.uniform(.5, 1.2) + math.cos(ph + t * 5) * h * .012
        a = .35 + .65 * (0.5 + 0.5 * math.sin(ph + t * 6.28 * 2))
        r = rnd.uniform(1.0, 2.0) * (w / 1280)
        for k in (6, 3):                       # 两层柔光，别做成实心球
            d.ellipse([x - r * k, y - r * k, x + r * k, y + r * k],
                      fill=(255, 240, 160, int(9 * a * k / 3)))
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 250, 205, int(230 * a)))


# ────────────────────────────── 站点 ──────────────────────────────
def build_site():
    """生成素材后顺手把站点和缩略图/海报都做好，一条命令可用。
       生成期临时藏起 hub_libs.json：示例库不该带「总收藏」外链（别人机器上没有那个文件）。"""
    hub = os.path.join(HERE, 'hub_libs.json')
    bak = hub + '.demo-bak'
    hidden = False
    if os.path.exists(hub):
        os.rename(hub, bak)
        hidden = True
    try:
        gen = [sys.executable, os.path.join(HERE, 'gen_site_generic.py'), OUT, 'SakuraView · 示例库', 'demo']
        subprocess.run(gen, capture_output=True)
        for nm in ('gen_posters.py', 'gen_sprites.py', 'gen_thumbs.py'):
            subprocess.run([sys.executable, os.path.join(HERE, nm), OUT], capture_output=True)
        r = subprocess.run(gen, capture_output=True, text=True, errors='replace')
        print((r.stdout.strip().splitlines() or [''])[-1])
    finally:
        if hidden:
            os.rename(bak, hub)


def clean():
    """只清掉本脚本自己产出的东西，不碰别的。"""
    for d in ('事件CG', '立绘', '头像', '动画', 'assets', '_thumbs', '_poster', '_sprite'):
        p = os.path.join(OUT, d)
        if os.path.isdir(p):
            shutil.rmtree(p)
    for f in glob.glob(os.path.join(OUT, '*.html')):
        os.remove(f)


if __name__ == '__main__':
    print('输出:', OUT)
    clean()
    n = 0
    # 事件 CG：8 种场景滚动出现，3 幕
    for ch in range(1, 4):
        for i in range(1, 9):
            cn, en, fn = SCENES[((ch - 1) * 3 + (i - 1)) % len(SCENES)]   # 每幕错开 3 个场景
            img = render_scene(fn, ch * 100 + i)
            img = finish(img, '第%02d幕 场景 %02d · %s' % (ch, i, cn), 'SakuraView demo · %s · 合成素材' % en)
            p = os.path.join(OUT, '事件CG', '第%02d幕' % ch, 'demo_c%02d_%02d.jpg' % (ch, i))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            img.save(p, quality=90, subsampling=1)
            n += 1
    print('事件CG %d 张' % n)

    # 立绘：2 角色 × 8 张
    m = 0
    for ci, ch in enumerate(CHARS):
        for i in range(1, 9):
            expr = (i - 1) % 4
            arm = (i - 1) // 4
            img = make_portrait(None, ch, expr, arm, ci * 50 + i)
            p = os.path.join(OUT, '立绘', ch['name'], '%s_制服_%02d.jpg' % (ch['name'], i))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            img.save(p, quality=92, subsampling=0)
            m += 1
    print('立绘 %d 张' % m)

    # 头像：2 角色 × 4 张
    a = 0
    for ci, ch in enumerate(CHARS):
        for i in range(1, 5):
            img = make_avatar(None, ch, (i - 1) % 4, 900 + ci * 20 + i)
            p = os.path.join(OUT, '头像', ch['name'], '%s_顔_%02d.png' % (ch['name'], i))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            img.save(p)
            a += 1
    print('头像 %d 张' % a)

    # 视频
    ff = find_ffmpeg()
    if ff:
        ok1, e1 = make_video(ff, os.path.join(OUT, '动画', '全部', 'demo_sakura_mau.mp4'), sc_dawn_sakura, fg_sakura)
        ok2, e2 = make_video(ff, os.path.join(OUT, '动画', '全部', 'demo_firefly.mp4'), sc_night_moon, fg_firefly)
        print('视频:', 'OK' if (ok1 and ok2) else '失败 %s %s' % (e1[:200], e2[:200]))
    else:
        print('没找到 ffmpeg，跳过示例视频')

    build_site()
    print('示例库: %s' % os.path.join(OUT, 'index.html'))
