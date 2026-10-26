# -*- coding: utf-8 -*-
"""通用多页面图库生成器
用法: python gen_site_generic.py <CG目录> "<标题>"
"""
import os, sys, html, json, struct, urllib.parse, re, hashlib, collections

def natkey(s):
    """自然排序：Jimin1 2 排在 Jimin1 10 前面"""
    parts = re.split(r"(\d+)", s.lower())
    return [(0, int(p)) if p.isdigit() else (1, p) for p in parts]

CG = sys.argv[1]
TITLE = sys.argv[2] if len(sys.argv) > 2 else "CG 图库"
KEY = sys.argv[3] if len(sys.argv) > 3 else "cg"
IMG = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
VID = (".ogv", ".webm", ".mp4", ".mkv")
SKIP_EXT = (".html", ".htm", ".css", ".js", ".txt", ".json")

def _png(f):
    h = f.read(24)
    if h[:8] == b"\x89PNG\r\n\x1a\n" and h[12:16] == b"IHDR":
        return struct.unpack(">II", h[16:24])
    return None

def _gif(f):
    h = f.read(10)
    if h[:3] == b"GIF":
        return struct.unpack("<HH", h[6:10])
    return None

def _jpg(f):
    f.seek(2)
    while True:
        b = f.read(1)
        if not b:
            return None
        if b != b"\xff":
            continue
        m = f.read(1)
        while m == b"\xff":
            m = f.read(1)
        if not m:
            return None
        c = m[0]
        if c in (0xC0, 0xC1, 0xC2, 0xC3):
            f.read(3)
            hh, ww = struct.unpack(">HH", f.read(4))
            return ww, hh
        if c in (0xD8, 0xD9) or 0xD0 <= c <= 0xD7:
            continue
        ln = struct.unpack(">H", f.read(2))[0]
        f.seek(ln - 2, 1)

def _webp(f):
    h = f.read(30)
    if h[:4] != b"RIFF" or h[8:12] != b"WEBP":
        return None
    cid = h[12:16]
    if cid == b"VP8X":
        w = int.from_bytes(h[24:27], "little") + 1
        ht = int.from_bytes(h[27:30], "little") + 1
        return w, ht
    if cid == b"VP8L":
        b = h[21:25]
        bits = int.from_bytes(b, "little")
        w = (bits & 0x3FFF) + 1
        ht = ((bits >> 14) & 0x3FFF) + 1
        return w, ht
    if cid == b"VP8 ":
        # 有损 WebP：chunk 负载从偏移 20 开始，前 3 字节是帧标签，
        # 起始码 9d 01 2a 在偏移 23，紧跟 14bit 宽 + 14bit 高
        f.seek(23)
        t = f.read(7)
        if len(t) >= 7 and t[:3] == b"\x9d\x01\x2a":
            w = struct.unpack("<H", t[3:5])[0] & 0x3FFF
            ht = struct.unpack("<H", t[5:7])[0] & 0x3FFF
            return w, ht
    return None

def enc(rel):
    """按路径分段编码：空格/CJK/#/?/%/& 全部安全，避免 encodeURI 漏 # 与 ?"""
    return urllib.parse.quote(rel, safe="/")

def base_of(rel):
    """差分基名，规则必须和前端 baseOf() 完全一致：
       去掉末尾序号后还剩 ≥2 段（含分隔符）才算差分；否则返回原名（不折叠）。"""
    b = os.path.splitext(rel.split("/")[-1])[0]
    s = re.sub(r"[_\-\s.]?\d+$", "", b)
    core = s.rstrip(" _-")
    if not core or not re.search(r"[\s_\-]", core):
        return b
    return s


_THUMB_CACHE = {}
def thumb_path(rel):
    """<dir>/<名>.jpg 对应的 _thumbs 缩略图相对路径；没生成过返回 None。
       只查文件存在性（不解析图片），一库 4 万次判断也就几秒。"""
    if not rel:
        return None
    if rel in _THUMB_CACHE:
        return _THUMB_CACHE[rel]
    d, bn = os.path.split(rel.replace("/", os.sep))
    stem = os.path.splitext(bn)[0]
    if os.path.exists(os.path.join(CG, d, "_thumbs", stem + ".jpg")):
        out = ((d.replace(os.sep, "/") + "/") if d else "") + "_thumbs/" + stem + ".jpg"
    else:
        out = None
    _THUMB_CACHE[rel] = out
    return out

def img_size(path):
    try:
        low = path.lower()
        with open(path, "rb") as f:
            r = None
            if low.endswith(".png"):
                r = _png(f)
            elif low.endswith((".jpg", ".jpeg")):
                r = _jpg(f)
            elif low.endswith(".webp"):
                r = _webp(f)
            elif low.endswith(".gif"):
                r = _gif(f)
            if r and 0 < r[0] < 30000 and 0 < r[1] < 30000:
                return r
    except Exception:
        pass
    return (0, 0)

# ---------- 扫描 ----------
files = []
for dp, dns, fns in os.walk(CG):
    dns[:] = [d for d in dns if d != "assets" and d != "_poster" and d != "_thumbs" and d != "_sprite"]
    for fn in sorted(fns):
        ext = os.path.splitext(fn)[1].lower()
        if ext in SKIP_EXT or fn.startswith("_"):
            continue
        if ext not in IMG and ext not in VID:
            continue
        full = os.path.join(dp, fn)
        rel = os.path.relpath(full, CG).replace("\\", "/")
        if ext == ".ogv" and os.path.exists(os.path.join(CG, rel[:-4] + ".mp4")):
            continue
        files.append((rel, ext, full))

buckets = {}
for rel, ext, full in files:
    parts = rel.split("/")
    key = "/".join(parts[:2]) if len(parts) >= 3 else parts[0]
    b = buckets.setdefault(key, {"cat": parts[0], "items": []})
    if ext in VID:
        b["items"].append([rel, 0, 0, 1])
    else:
        w, h = img_size(full)
        b["items"].append([rel, w, h, 0])

keys = sorted(buckets.keys(), key=lambda k: (-len(buckets[k]["items"]), k))
# 每组内部按「目录 + 文件名自然序」排列，保证 2 在 10 前面
for _k in buckets:
    buckets[_k]["items"].sort(
        key=lambda it: (os.path.dirname(it[0]), natkey(os.path.basename(it[0]))))

# 超大分组自动切片：一页放几千张图要滚几万像素，翻起来很痛苦（实测某库第1章 2225 张）。
# 超过 MAXG 就按当前顺序均分成若干组，组名后缀 #1 #2 #3（**不能用 (1/6)**：显示名取 split("/")[-1]，斜杠会被切碎），**只是分页，不折叠、不合并**。
MAXG = 300
_sliced = {}
for _k in keys:
    _b = buckets[_k]
    _its = _b["items"]
    if len(_its) <= MAXG:
        _sliced[_k] = _b
        continue
    _n = (len(_its) + MAXG - 1) // MAXG
    _per = (len(_its) + _n - 1) // _n
    for _i in range(_n):
        _part = _its[_i * _per:(_i + 1) * _per]
        if not _part:
            continue
        # 组名不能用「(1/6)」这种写法：显示名取 k.split("/")[-1]，会被斜杠切碎（实测变成 "6)"）
        _sliced["%s #%d" % (_k, _i + 1)] = {"cat": _b["cat"], "items": _part}
if len(_sliced) != len(buckets):
    print("大组切片：%d 组 → %d 组" % (len(buckets), len(_sliced)))
buckets = _sliced
keys = list(buckets.keys())
total = sum(len(b["items"]) for b in buckets.values())
print("目录:", CG)
print("文件:", total, " 分组:", len(keys))

# ---------- CSS ----------
CSS = """:root{--bg:#0a0b0f;--card:#151821;--line:#222733;--text:#e9ecf3;--muted:#79839a;
--accent:#6f8cff;--accent2:#a77bff;--fav:#ff5b8c}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth;scrollbar-color:#eef2fa #0b0d12;scrollbar-gutter:stable}
/* 兜底：不支持 scrollbar-gutter 的浏览器常驻滚动条，避免可用宽度随页面长度变化 */
@supports not (scrollbar-gutter:stable){html{overflow-y:scroll}}
body{background:var(--bg);color:var(--text);font:14px/1.6 "Segoe UI","PingFang SC","Microsoft YaHei",system-ui,sans-serif;-webkit-font-smoothing:antialiased}
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;
background:radial-gradient(900px 500px at 12% -10%,rgba(111,140,255,.13),transparent 60%),
radial-gradient(700px 400px at 90% 0%,rgba(167,123,255,.10),transparent 60%)}
a{color:inherit;text-decoration:none}
.navbar{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:16px;
padding:12px 26px;background:#0a0b0f;border-bottom:1px solid var(--line)}
.back{display:flex;align-items:center;gap:7px;padding:8px 14px;border-radius:9px;
border:1px solid var(--line);background:#12151d;color:#c8d0e2;font-size:12.5px;font-weight:600;
transition:.16s;white-space:nowrap}
.back:hover{background:#1b2231;color:#fff;border-color:rgba(111,140,255,.5)}
.crumb{font-size:12.5px;color:var(--muted);font-style:italic;font-weight:600}
.crumb b{color:#dfe4f0;font-weight:700}
.navbar .spacer{flex:1}
.search{position:relative;width:min(340px,40vw)}
.search input{width:100%;padding:9px 13px 9px 34px;border-radius:9px;border:1px solid var(--line);
background:#12151d;color:var(--text);font-size:12.5px;outline:none;transition:.2s}
.search input:focus{border-color:rgba(111,140,255,.6);box-shadow:0 0 0 3px rgba(111,140,255,.1)}
.search svg{position:absolute;left:11px;top:9px;opacity:.45}
.wrap{padding:20px 26px 80px;position:relative;z-index:1}
h1.hero{font-size:22px;font-weight:800;font-style:italic;margin-bottom:6px;
background:linear-gradient(100deg,#fff,#9db0ff 55%,#c6a8ff);
-webkit-background-clip:text;background-clip:text;color:transparent}
.sub{color:var(--muted);font-size:12.5px;margin-bottom:26px}
.catblock{margin-bottom:34px}
.cat-title{display:flex;align-items:center;gap:10px;font-size:13px;font-weight:800;
font-style:italic;letter-spacing:1px;color:#fff;margin-bottom:14px;padding:8px 14px;
border-radius:2px 9px 9px 2px;border-left:3px solid #ffb7c5;
background:linear-gradient(100deg,rgba(255,91,140,.26),rgba(255,183,197,.10) 58%,rgba(255,183,197,.02))}
.cat-title em{font-style:italic;font-weight:700;font-size:11px;color:#ffd3dd}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px}
.card{position:relative;border-radius:12px;overflow:hidden;background:var(--card);
border:1px solid var(--line);transition:.2s;display:block}
.card:hover{transform:translateY(-3px);border-color:rgba(111,140,255,.55);
box-shadow:0 14px 34px rgba(0,0,0,.55)}
.card .cover{width:100%;aspect-ratio:16/10;height:auto;object-fit:cover;display:block;background:#0e1117}
.card.tall .cover{aspect-ratio:3/4}
.card .cover-ph{width:100%;height:132px;display:grid;place-items:center;color:#2c3346;font-size:26px}
.card .meta{padding:9px 11px;display:flex;justify-content:space-between;align-items:center;gap:8px}
.card .nm{font-size:12.5px;font-weight:600;color:#dfe4f0;white-space:nowrap;
overflow:hidden;text-overflow:ellipsis}
.card .ct{font-size:10.5px;color:#8d97af;background:#1c2331;padding:1px 8px;
border-radius:20px;white-space:nowrap}
/* 缩略图尺寸只由缩放决定：固定轨道宽度，不再用「可用宽度 ÷ 列数」→ 不会因为窗口/滚动条/页面长度跳列而变大小 */
.masonry{display:grid;grid-template-columns:repeat(auto-fill,var(--card-w,206px));
gap:10px;justify-content:space-between;align-items:start}
/* 收藏页「按目录分组」的表头：横跨整行 */
.grphead{grid-column:1/-1;display:flex;align-items:baseline;gap:9px;padding:10px 2px 7px;
margin-top:4px;border-bottom:1px solid #222733;font-size:12.5px;font-weight:700;color:#ffb7c5}
.grphead span{font-weight:700}
.grphead em{font-style:normal;font-size:11.5px;color:#79839a;font-weight:600}
.item{margin:0;position:relative;border-radius:11px;overflow:hidden;
background:var(--card);border:1px solid var(--line);cursor:zoom-in;
transition:transform .2s cubic-bezier(.2,.7,.3,1),box-shadow .2s,border-color .2s}
.item img,.item video{display:block;width:100%;height:auto;min-height:60px;
transition:transform .35s cubic-bezier(.2,.7,.3,1),filter .3s}
.item:hover{transform:translateY(-3px);border-color:rgba(111,140,255,.45);
box-shadow:0 12px 30px rgba(0,0,0,.55)}.item:hover img{transform:scale(1.04);filter:brightness(1.06)}
/* 差分栈：同一格的多个 figure 叠放，只有第一个显形，其余透明但仍在 DOM（灯箱能翻到） */
.stack{position:relative;display:grid;grid-template-columns:1fr;border-radius:11px}
.stack>figure.item{grid-area:1/1;margin:0}
/* 用 first-of-type（不是 first-child）：栈里第一个子元素是角标 span */
.stack>figure.item:not(:first-of-type){opacity:0;pointer-events:none}
.dupbadge{position:absolute;right:8px;bottom:8px;z-index:6;cursor:pointer;
font-size:10px;line-height:1;padding:4px 8px;border-radius:20px;
background:rgba(255,91,140,.86);color:#fff;letter-spacing:.3px;box-shadow:0 2px 8px rgba(0,0,0,.4);
transition:.15s}
.dupbadge:hover{background:#ff5b8c;transform:scale(1.06)}
/* 差分速览：点角标弹出这一组的小缩略图，点哪张就看哪张（不改变网格布局） */
.dupPanel{position:fixed;inset:0;z-index:180;display:none;background:rgba(6,8,12,.86);
backdrop-filter:blur(3px);padding:5vh 24px;overflow:auto}
.dupPanel.open{display:block}
.dupPanel .dp-box{max-width:960px;margin:0 auto;background:#13161f;border:1px solid #2a3143;
border-radius:14px;padding:16px 18px 20px;box-shadow:0 24px 60px rgba(0,0,0,.6)}
.dupPanel h4{font-size:13px;font-weight:800;color:#ffb7c5;margin-bottom:4px;display:flex;
align-items:center;justify-content:space-between;gap:12px}
.dupPanel .dp-sub{font-size:11.5px;color:#79839a;margin-bottom:14px}
.dupPanel .dp-close{cursor:pointer;color:#8892a6;font-size:18px;line-height:1;padding:2px 6px;
border-radius:7px;border:1px solid transparent}
.dupPanel .dp-close:hover{color:#fff;background:#222938;border-color:#333c50}
.dupPanel .dp-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(112px,1fr));gap:9px}
.dupPanel .dp-item{position:relative;border-radius:8px;overflow:hidden;border:1px solid #2a3143;
cursor:pointer;background:#0e1117;transition:.15s}
.dupPanel .dp-item:hover{border-color:rgba(255,183,197,.7);transform:translateY(-2px)}
.dupPanel .dp-item img{display:block;width:100%;height:auto}
.dupPanel .dp-item b{position:absolute;left:4px;bottom:4px;font-size:9.5px;font-weight:700;
color:#fff;background:rgba(6,8,12,.78);border-radius:4px;padding:1px 5px}
.stack.flat{display:contents}
.stack.flat>figure.item{opacity:1;pointer-events:auto}
.stack.flat .dupbadge{display:none}
.stack>figure.item:hover{transform:none;box-shadow:none}
.item figcaption{position:absolute;left:0;right:0;bottom:0;padding:16px 9px 7px;font-size:10.5px;
color:#cfd6e6;background:linear-gradient(180deg,transparent,rgba(6,8,12,.92));
white-space:nowrap;overflow:hidden;text-overflow:ellipsis;opacity:0;transform:translateY(6px);transition:.2s}
.item:hover figcaption{opacity:1;transform:none}
.acts{position:absolute;top:7px;right:7px;display:flex;gap:5px;z-index:3;opacity:0;
transform:translateY(-5px);transition:.18s}
.item:hover .acts{opacity:.45;transform:none}
.acts:hover{opacity:1!important}
.act{width:27px;height:27px;padding:0;border-radius:8px;cursor:pointer;
border:1px solid rgba(255,255,255,.09);background:rgba(6,8,12,.6);color:#8791a6;
font-size:13px;line-height:1;display:grid;place-items:center;transition:.15s;font-family:inherit}
.act:hover{background:rgba(111,140,255,.62);border-color:rgba(111,140,255,.78);color:#fff}
.item.fav{border-color:rgba(255,91,140,.55);box-shadow:0 0 0 1px rgba(255,91,140,.22)}
.item.fav .acts{opacity:.6}
.item.fav .act-fav{background:rgba(255,91,140,.55);border-color:rgba(255,91,140,.65);color:#fff}
/* 最近查看：图片和视频共用，退出预览后仍保留（樱花粉） */
.item.seen{outline:2px solid #ffb7c5;outline-offset:-2px}
.item.seen::before{content:"";position:absolute;left:9px;top:9px;width:8px;height:8px;border-radius:50%;
background:#ffb7c5;box-shadow:0 0 0 3px rgba(8,10,16,.72);z-index:4;pointer-events:none}
.note{display:block;padding:8px 10px;background:rgba(255,255,255,.045);
border-top:1px solid rgba(255,255,255,.08);font-size:11px;line-height:1.45;color:#bcc5d8;
white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer;transition:.16s}
.note:hover{background:rgba(111,140,255,.16);color:#e9eefb}
.item.fav .note{background:rgba(255,91,140,.1);border-top-color:rgba(255,91,140,.28);color:#f1cbda}
.item.has-note figcaption{bottom:34px}
/* 批量选择：选中环 + 橡皮筋框 + 底部批量条 */
.item.sel{border-color:#ffb7c5;box-shadow:0 0 0 2px #ffb7c5,0 10px 26px rgba(0,0,0,.5)}
.item.sel::after{content:"\2713";position:absolute;left:9px;top:9px;width:19px;height:19px;border-radius:50%;
background:#ffb7c5;color:#1a1420;font-size:12px;font-weight:800;display:grid;place-items:center;z-index:5}
.selband{position:fixed;border:1px solid #ffb7c5;background:rgba(255,183,197,.16);
border-radius:4px;z-index:60;pointer-events:none;display:none}
.selbar{position:fixed;left:50%;bottom:22px;transform:translate(-50%,18px);z-index:70;
display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:12px;
background:rgba(18,22,31,.97);border:1px solid #2a3040;box-shadow:0 16px 40px rgba(0,0,0,.6);
opacity:0;pointer-events:none;transition:.2s}
.selbar.open{opacity:1;pointer-events:auto;transform:translate(-50%,0)}
.selbar b{font-size:12.5px;color:#ffb7c5;font-weight:700;white-space:nowrap}
.selbar button{padding:7px 13px;border-radius:8px;border:1px solid #2a3040;background:#171c26;
color:#cfd6e6;font-size:12.5px;font-weight:600;cursor:pointer;font-family:inherit;white-space:nowrap}
.selbar button:hover{background:#232a3a;color:#fff}
.selbar button.primary{background:linear-gradient(100deg,#3b57b8,#2a3d8a);border-color:#3b57b8;color:#fff}
.selbar input{width:112px;padding:7px 10px;border-radius:8px;border:1px solid #2a3040;
background:#0d1017;color:#dfe4f0;font-size:12.5px;font-family:inherit;outline:none}
.selbar input:focus{border-color:#ffb7c5}
/* 备注里的 Markdown 简写 */
.note b{color:#fff;font-weight:800}
.note .mdtag{color:#ffb7c5;font-weight:700;margin-left:2px}
.empty{text-align:center;padding:90px 20px;color:#5b6478}
.empty .big{font-size:34px;color:#2b3346;margin-bottom:14px;font-style:italic}
.empty b{display:block;font-size:15px;color:#8b93a7;margin-bottom:6px;font-style:italic;font-weight:700}
.empty span{display:block;font-size:12px;color:#5b6478}
.item-v{cursor:pointer}
.vlb{position:fixed;inset:0;z-index:120;background:#000;display:none}
.vlb.open{display:block}
.vlb video{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#000;outline:none}
.vtitle{position:absolute;left:26px;top:20px;z-index:125;color:#fff;font-size:40px;
font-weight:700;letter-spacing:.5px;line-height:1.25;
text-shadow:0 3px 16px rgba(0,0,0,.95),0 0 3px rgba(0,0,0,.85);
max-width:78vw;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
pointer-events:none;opacity:0;transition:opacity .25s}
.vlb.show-ui .vtitle{opacity:1}
/* 静止后控制条与标题一起淡出，指针也隐藏（全屏/非全屏一致） */
.vlb:not(.show-ui){cursor:none}
.vui{position:absolute;left:0;right:0;bottom:0;padding:46px 18px 12px;
background:linear-gradient(0deg,rgba(0,0,0,.88),rgba(0,0,0,.45) 55%,transparent);
opacity:0;transition:opacity .25s;pointer-events:none}
.vlb.show-ui .vui{opacity:1;pointer-events:auto}
.vbarwrap{height:4px;background:rgba(255,255,255,.22);border-radius:3px;cursor:pointer;
margin-bottom:10px;position:relative}
.vbarwrap:hover{height:7px}
.vbar{height:100%;background:#6f8cff;border-radius:3px;width:0;pointer-events:none}
.vrow{display:flex;align-items:center;gap:4px}
.vi{background:transparent;border:0;color:#e8ecf5;width:38px;height:38px;border-radius:8px;
display:grid;place-items:center;cursor:pointer;font-size:15px;transition:.15s;
font-family:inherit;padding:0;line-height:1}
.vi:hover{background:rgba(255,255,255,.16)}
/* 播放/暂停图标：用内联 SVG + .playing 类切换，不依赖字体里有没有 U+23F8（缺字形会显示成空白/方块） */
.vi .ic{width:17px;height:17px;fill:currentColor;display:none;pointer-events:none}
#vPlay .ic-play{display:block}
#vPlay.playing .ic-play{display:none}
#vPlay.playing .ic-pause{display:block}
.vi.on{background:rgba(255,91,140,.85);border-color:#ffb7c5;color:#fff}
.vi:disabled{opacity:.3;cursor:not-allowed}
.vtime{font-size:12px;color:#cfd6e6;margin-left:10px;font-variant-numeric:tabular-nums;
letter-spacing:.3px}
.vspacer{flex:1}
.vrate{width:auto;padding:0 12px;font-size:12.5px;font-weight:600;min-width:52px}
/* 音量：图标 + 滑块（拖动调节，不再点一下静音） */
.vvol{display:flex;align-items:center;gap:7px;padding:0 8px;height:38px;border-radius:8px}
.vvol:hover{background:rgba(255,255,255,.10)}
.vvic{font-size:14px;line-height:1;color:#cfd6e6;width:16px;text-align:center;user-select:none}
.vvol input[type=range]{-webkit-appearance:none;appearance:none;width:78px;height:4px;border-radius:3px;
background:linear-gradient(90deg,#ffb7c5 var(--vp,100%),rgba(255,255,255,.22) var(--vp,100%));
outline:none;cursor:pointer;margin:0}
.vvol input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:12px;height:12px;border-radius:50%;
background:#fff;border:0;box-shadow:0 1px 4px rgba(0,0,0,.65)}
.vvol input[type=range]::-moz-range-thumb{width:12px;height:12px;border:0;border-radius:50%;background:#fff}
@media (max-width:760px){.vvol input[type=range]{width:56px}.vvol{padding:0 4px;gap:5px}}
.vmenu{position:absolute;right:104px;bottom:62px;background:rgba(20,24,33,.98);
border:1px solid #2a3040;border-radius:10px;padding:6px;display:none;z-index:130;
box-shadow:0 12px 34px rgba(0,0,0,.65);min-width:96px}
.vmenu.open{display:block}
.vmenu button{display:block;width:100%;text-align:left;padding:7px 16px;border:0;
background:transparent;color:#c8d0e2;font-size:12.5px;font-family:inherit;cursor:pointer;
border-radius:6px}
.vmenu button:hover{background:#232a3a;color:#fff}
.vmenu button.on{color:#8aa2ff;font-weight:700}
/* 进度条悬停/拖动时的帧预览（雪碧图切片，本地图库没法用 canvas 抓帧） */
.vsprite{position:fixed;z-index:140;width:160px;height:90px;border-radius:8px;
border:1px solid #3a4356;background-color:#0a0c11;background-repeat:no-repeat;
box-shadow:0 12px 30px rgba(0,0,0,.7);display:none;pointer-events:none}
.vsprite.on{display:block}
.vsprite i{position:absolute;left:0;right:0;bottom:-19px;text-align:center;font-size:11px;color:#cfd6e6;
font-style:normal;text-shadow:0 1px 4px #000}
.vlb:fullscreen{background:#000}
.lb{position:fixed;inset:0;z-index:100;display:none;background:rgba(5,6,9,.97)}
.lb.open{display:flex;align-items:center;justify-content:center}
/* 全图模式：整屏铺满、整张图完整显示（contain），不再留圆角/阴影 */
.lb img{width:100vw;height:100vh;object-fit:contain;display:block;transition:opacity .18s;
border-radius:0;box-shadow:none;-webkit-user-drag:none;user-select:none}
.lb img.loading{opacity:.22}
/* 缩放/拖拽：grab 光标 + 关掉浏览器自带手势，交给 JS 处理 */
.lb img{cursor:zoom-in;touch-action:none;-webkit-user-drag:none;will-change:transform}
.lb img.zoomed{cursor:grab}
.lb img.dragging{cursor:grabbing}
.lb-bar{position:fixed;top:0;left:0;right:0;display:flex;justify-content:space-between;
align-items:center;padding:14px 20px;font-size:12.5px;color:#93a0b8}
.lb-bar b{font-weight:600;color:#dfe4f0}
/* 全屏观感：顶栏 / 箭头 / 关闭默认隐藏，动一下鼠标或点一下才浮现（2.4s 后自动淡出），只留图片本体 */
.lb-bar,.lb-btn,.lb-close{opacity:0;pointer-events:none;transition:opacity .2s ease}
.lb.ui-on .lb-bar,.lb.ui-on .lb-btn,.lb.ui-on .lb-close{opacity:1;pointer-events:auto}
/* 底部操作条：默认隐藏，鼠标/手指靠近屏幕下方才浮现（不挡看图） */
.lb-acts{position:fixed;bottom:22px;left:50%;transform:translate(-50%,16px);display:flex;gap:10px;z-index:102;
opacity:0;pointer-events:none;transition:opacity .2s ease,transform .2s ease}
.lb.show-acts .lb-acts{opacity:1;pointer-events:auto;transform:translate(-50%,0)}
.lb-act{display:flex;align-items:center;gap:7px;padding:10px 20px;border-radius:10px;
border:1px solid rgba(255,255,255,.18);background:rgba(20,24,33,.92);color:#dbe2f0;
font-size:13px;font-weight:600;cursor:pointer;transition:.16s;font-family:inherit}
.lb-act:hover{background:#232a3a;border-color:rgba(111,140,255,.6);color:#fff}
.lb-act.on{background:rgba(255,91,140,.85);border-color:#ff5b8c;color:#fff}
/* 幻灯速率：主按钮 + 速率小按钮，菜单向上弹出 */
.lbspd{display:flex;gap:0}
.lbspd .lb-act:first-child{border-radius:10px 0 0 10px}
.lb-act.lbcaret{border-radius:0 10px 10px 0;border-left:none;padding:10px 10px;font-size:11px}
.lb-act.lbcaret:hover{border-left:1px solid rgba(255,255,255,.12)}
.spdmenu{position:fixed;z-index:103;display:none;background:rgba(20,24,33,.98);
border:1px solid #2a3040;border-radius:10px;padding:6px;min-width:170px;
box-shadow:0 12px 34px rgba(0,0,0,.65)}
.spdmenu.open{display:block}
.spdmenu button{display:block;width:100%;text-align:left;padding:7px 16px;border:0;
background:transparent;color:#c8d0e2;font-size:12.5px;font-family:inherit;cursor:pointer;border-radius:6px}
.spdmenu button:hover{background:#232a3a;color:#fff}
.spdmenu button.on{color:#ffb7c5;font-weight:700}
.lb-btn{position:fixed;top:50%;transform:translateY(-50%);width:52px;height:52px;border-radius:50%;
border:1px solid #2a3040;background:rgba(20,24,33,.9);color:#cfd6e6;font-size:20px;cursor:pointer;
display:grid;place-items:center;transition:.18s;user-select:none;z-index:102}
.lb-btn:hover{background:#232a3a;border-color:rgba(111,140,255,.6);color:#fff}
.lb-prev{left:22px}.lb-next{right:22px}
.lb-close{position:fixed;top:14px;right:18px;width:36px;height:36px;border-radius:9px;
border:1px solid #2a3040;background:rgba(20,24,33,.9);color:#cfd6e6;cursor:pointer;
font-size:16px;display:grid;place-items:center;z-index:102}
.lb-close:hover{background:#232a3a;color:#fff}
.modal{position:fixed;inset:0;z-index:150;display:none;align-items:center;justify-content:center;
background:rgba(5,6,9,.8);padding:20px}
.modal.open{display:flex}
.modal-box{width:min(460px,100%);background:#12151d;border:1px solid #2a3040;
border-radius:14px;padding:20px;box-shadow:0 30px 80px rgba(0,0,0,.7)}
.modal-box h3{font-size:14px;font-weight:700;font-style:italic;margin-bottom:12px}
.modal-thumb{width:100%;max-height:170px;object-fit:contain;border-radius:9px;
background:#0b0d12;margin-bottom:12px;display:block}
.modal-box textarea{width:100%;height:96px;resize:vertical;padding:10px 12px;border-radius:9px;
border:1px solid #2a3040;background:#0b0d12;color:#e9ecf3;font-size:13px;line-height:1.5;
font-family:inherit;outline:none}
.modal-box input#tagInput{width:100%;margin-top:8px;padding:9px 12px;border-radius:9px;
border:1px solid #2a3040;background:#0b0d12;color:#e9ecf3;font-size:12.5px;outline:none}
.modal-box input#tagInput:focus{border-color:rgba(255,183,197,.55)}
.tagrow{padding:6px 10px;display:flex;flex-wrap:wrap;gap:4px;
background:rgba(255,183,197,.05);border-top:1px solid rgba(255,255,255,.07)}
.tagchip{font-size:10px;color:#ffb7c5;background:rgba(255,183,197,.1);
border:1px solid rgba(255,183,197,.35);border-radius:10px;padding:0 8px;line-height:1.7}
.lb-act.on{background:rgba(255,183,197,.85);border-color:#ffb7c5;color:#fff}
.modal-box textarea:focus{border-color:rgba(111,140,255,.6)}
.modal-acts{display:flex;gap:8px;justify-content:flex-end;margin-top:14px}
.tip-p{font-size:13px;line-height:1.75;color:#c2cbd9;margin:0 0 10px}
.tip-p code{background:#0d1017;border:1px solid #2a3040;border-radius:5px;padding:1px 6px;
font-size:12px;color:#ffb7c5;font-family:ui-monospace,Consolas,monospace}
.tip-p b{color:#eef1f7}
.modal-acts button{padding:9px 18px;border-radius:9px;border:1px solid #2a3040;background:#171c26;
color:#c8d0e2;font-size:12.5px;font-weight:600;cursor:pointer;font-family:inherit}
.modal-acts button:hover{background:#20283a;color:#fff}
.modal-acts .primary{background:linear-gradient(100deg,#3b57b8,#2a3d8a);
border-color:rgba(111,140,255,.6);color:#fff}
.modal-acts .danger{color:#ff9db6}
aside{position:fixed;top:0;left:0;width:236px;height:calc(100vh / var(--z-nav,1));
zoom:var(--z-nav,1);z-index:30;
background:linear-gradient(180deg,#0c0e14,#0a0b0f);border-right:1px solid var(--line);
display:flex;flex-direction:column}
aside .brand{padding:18px 18px 14px;border-bottom:1px solid var(--line)}
aside .brand h1{font-size:13.5px;font-weight:700;font-style:italic;letter-spacing:.2px;
background:linear-gradient(100deg,#fff,#9db0ff 60%,#c6a8ff);
-webkit-background-clip:text;background-clip:text;color:transparent;
white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
aside .brand p{font-size:10.5px;color:var(--muted);margin-top:4px;letter-spacing:.3px}
aside .brand .mark{font-size:10px;font-weight:700;color:#ffb7c5;letter-spacing:1.4px;margin-bottom:4px}
aside .brand .hublink{display:inline-flex;align-items:center;gap:5px;margin-top:9px;
font-size:11px;color:#ffb7c5;text-decoration:none;border:1px solid rgba(255,183,197,.34);
border-radius:6px;padding:2px 9px;letter-spacing:.2px;opacity:.78;transition:.16s}
aside .brand .hublink:hover{opacity:1;background:rgba(255,183,197,.13);border-color:rgba(255,183,197,.7)}
.mark-hero{font-size:12px;font-weight:700;color:#ffb7c5;letter-spacing:2px;margin-bottom:8px}
/* 横竖图筛选 chips */
.chips{display:flex;gap:6px;flex-wrap:wrap}
.chip{padding:6px 13px;border-radius:20px;border:1px solid var(--line);background:#12151d;
color:#c8d0e2;font-size:11.5px;font-weight:600;cursor:pointer;white-space:nowrap;transition:.15s;user-select:none}
.chip:hover{border-color:rgba(255,183,197,.5);color:#fff}
.chip.on{background:rgba(255,183,197,.22);border-color:rgba(255,183,197,.6);color:#fff}
.snav{flex:1;overflow-y:auto;padding:10px 10px 40px;
scrollbar-width:auto;scrollbar-color:#eef2fa #0c0e13}
.snav::-webkit-scrollbar{width:16px}
.snav::-webkit-scrollbar-thumb{background:#eef2fa;border-radius:5px;border:3px solid #0c0e13;min-height:48px}
.snav::-webkit-scrollbar-thumb:hover{background:#fff}
.snav::-webkit-scrollbar-track{background:#0c0e13;border-left:1px solid #1a1f2b}
.cat{margin-bottom:16px}
.cat-h{font-size:11.5px;letter-spacing:1.1px;color:#fff;padding:7px 11px;margin-bottom:7px;
display:flex;justify-content:space-between;align-items:center;font-weight:800;font-style:italic;
background:linear-gradient(100deg,rgba(255,91,140,.26),rgba(255,183,197,.10) 58%,rgba(255,183,197,.02));
border-left:3px solid #ffb7c5;border-radius:2px 8px 8px 2px;cursor:pointer;user-select:none}
/* 目录树折叠：grid 0fr→1fr 平滑展开/收起，各分类状态独立 */
.cat-h .ch{display:inline-block;font-size:9px;opacity:.85;transition:transform .25s ease}
.cat.open>.cat-h .ch{transform:rotate(90deg)}
.cat-h .ct2{flex:1;margin-left:7px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cat-body{display:grid;grid-template-rows:0fr;transition:grid-template-rows .28s ease}
.cat.open>.cat-body{grid-template-rows:1fr}
.cat-body>.cat-in{overflow:hidden;min-height:0}
.cat-h em{font-style:italic;color:#ffd3dd;font-weight:700;font-size:10.5px}
.nav-item{display:flex;justify-content:space-between;align-items:center;padding:7px 10px;
border-radius:8px;color:#c8d0e2;font-size:12.5px;font-weight:500;transition:.15s;
border:1px solid transparent;white-space:nowrap}
.nav-item em{font-style:normal;font-size:10.5px;color:#8d97af;background:#1c2331;
padding:1px 7px;border-radius:20px;margin-left:8px}
.nav-item:hover{background:#1b2231;color:#fff;border-color:#2c3547}
.nav-item.on{background:linear-gradient(90deg,rgba(255,183,197,.34),rgba(255,183,197,.07));
color:#fff;border-color:rgba(255,183,197,.6);box-shadow:inset 3px 0 0 #ffb7c5}
.nav-item.on em{background:rgba(255,143,168,.34);color:#ffe3ea}
.nav-item[data-g]{cursor:pointer}
#mainWrap{margin-left:calc(236px * var(--z-nav,1))}
.navbar{zoom:var(--z-main,1)}
.wrap{zoom:var(--z-main,1)}
#ztoast{position:fixed;right:24px;bottom:24px;z-index:200;padding:9px 16px;border-radius:9px;
background:rgba(20,24,33,.96);border:1px solid rgba(111,140,255,.55);color:#dfe4f0;
font-size:12.5px;font-weight:600;letter-spacing:.3px;opacity:0;transform:translateY(8px);
transition:.2s;pointer-events:none;box-shadow:0 10px 30px rgba(0,0,0,.5)}
#ztoast.show{opacity:1;transform:none}
::-webkit-scrollbar{width:16px;height:16px}
::-webkit-scrollbar-track{background:#0b0d12}
::-webkit-scrollbar-thumb{background:#eef2fa;border-radius:8px;border:3px solid #0b0d12;min-height:48px}
::-webkit-scrollbar-thumb:hover{background:#fff}
@media(max-width:860px){
aside{display:none}
#mainWrap{margin-left:0}
.navbar{zoom:1}
.wrap{zoom:1}
.vtitle{font-size:22px;left:14px;top:12px}
.navbar{flex-wrap:wrap;padding:10px 14px;gap:10px}
.search{width:100%;order:3}
.wrap{padding:16px 14px 60px}
.masonry{grid-template-columns:repeat(auto-fill,150px);gap:8px}
.cards{grid-template-columns:repeat(auto-fill,minmax(140px,1fr))}
}
"""

# ---------- JS ----------
JS = r"""(function(){
const FAV_KEY='cg_favs',NOTE_KEY='cg_notes';
let favOrder=[],notes={};
try{favOrder=JSON.parse(localStorage.getItem(FAV_KEY)||'[]')}catch(e){}
let favSet=new Set(favOrder);
try{notes=JSON.parse(localStorage.getItem(NOTE_KEY)||'{}')}catch(e){}
function saveFav(){try{localStorage.setItem(FAV_KEY,JSON.stringify(favOrder))}catch(e){}}
function saveNotes(){try{localStorage.setItem(NOTE_KEY,JSON.stringify(notes))}catch(e){}}
const TAGS_KEY='cg_tags';
let tags={};
try{tags=JSON.parse(localStorage.getItem(TAGS_KEY)||'{}')}catch(e){}
function saveTags(){try{localStorage.setItem(TAGS_KEY,JSON.stringify(tags))}catch(e){}}
const RECENT_KEY='cg_recent_'+location.pathname;
let recentRel='';
try{recentRel=localStorage.getItem(RECENT_KEY)||''}catch(e){}
/* 最近查看：图片灯箱 / 视频播放器共用同一状态，退出后仍保留高亮 */
function markRecent(rel){
if(!rel||rel===recentRel)return;
recentRel=rel;
try{localStorage.setItem(RECENT_KEY,rel)}catch(e){}
if(!grid)return;
grid.querySelectorAll('figure.item').forEach(function(f){
f.classList.toggle('seen',f.dataset.rel===rel);});
}
/* 目录树折叠：显式设置过的分类记住用户选择，未动过的默认收起（当前页/当前过滤所在分类默认展开） */
const CAT_KEY='cg_catopen';
const DUP_KEY='cg_dupv2';   /* 差分是否叠起（0/缺省=平铺直接看图，1=叠成一张），跨页记住 */
var catState={};
try{catState=JSON.parse(localStorage.getItem(CAT_KEY)||'{}')}catch(e){}
function catOpen(name,isActive){return (name in catState)?!!catState[name]:!!isActive}
function saveCatState(){try{localStorage.setItem(CAT_KEY,JSON.stringify(catState))}catch(e){}}
function catHead(name,label,count,open){
return '<div class="cat'+(open?' open':'')+'" data-cat="'+esc(name)+'">'
+'<div class="cat-h"><span class="ch">&#9656;</span><span class="ct2">'+esc(label)+'</span><em>'+count+'</em></div>'
+'<div class="cat-body"><div class="cat-in">';
}
var CAT_END='</div></div></div>';
const PAGE=window.PAGE||{items:[]};
const items=PAGE.items||[];
const grid=document.getElementById('grid');
const lb=document.getElementById('lb'),lbImg=document.getElementById('lbImg');
const lbName=document.getElementById('lbName'),lbIdx=document.getElementById('lbIdx');
const lbFav=document.getElementById('lbFav');
const noteModal=document.getElementById('noteModal'),noteInput=document.getElementById('noteInput');
const tagInput=document.getElementById('tagInput');
const modalThumb=document.getElementById('modalThumb');
const q=document.getElementById('q');
let noteRel=null,cur=[],pos=-1;
const KIND=document.querySelector('.cards')?'index':(/fav\.html$/.test(location.pathname)?'fav':'group');
function esc(s){return String(s).replace(/[&<>"]/g,function(c){
return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];})}
function encPath(p){return String(p).split('/').map(encodeURIComponent).join('/')}
/* 视频海报帧：与视频同目录的 _poster/<名称>.jpg（由 gen_posters.py 批量生成） */
function posterFor(rel){var i=rel.lastIndexOf('/');
var b=rel.slice(i+1).replace(/\.[^.]+$/,'');
return (i<0?'_poster/':rel.slice(0,i)+'/_poster/')+b+'.jpg'}
/* 缩略图：同目录 _thumbs/<名称>.jpg（gen_thumbs.py 生成），缺失时 onerror 回退原图 */
function thumbFor(rel){var i=rel.lastIndexOf('/');
var b=rel.slice(i+1).replace(/\.[^.]+$/,'');
return (i<0?'_thumbs/':rel.slice(0,i)+'/_thumbs/')+b+'.jpg'}
/* 轻提示：复用右下角 #ztoast，不新增按钮 */
var toastT=null;
function toast(t){
var el=document.getElementById('ztoast');
if(!el){el=document.createElement('div');el.id='ztoast';document.body.appendChild(el)}
el.textContent=t;el.classList.add('show');
clearTimeout(toastT);toastT=setTimeout(function(){el.classList.remove('show')},1300);
}
/* 收藏页：数量 / 副标题 / 空状态统一刷一次，避免分批渲染时数不准 */
var favFilter=null,favQ='';
function relDir(rel){var i=rel.lastIndexOf('/');return i<0?'':rel.slice(0,i)}
/* 收藏页增强：随机看图 + 按目录分组视图（跨库场景在总收藏 Hub 里按库分组） */
var favGrouped=false;
function groupFavByDir(on){
if(KIND!=='fav'||!grid)return;
var olds=grid.querySelectorAll('.grphead');
for(var i=0;i<olds.length;i++)olds[i].remove();
if(!on){favGrouped=false;return}
favGrouped=true;
var fs=Array.prototype.slice.call(grid.querySelectorAll('figure.item'));
var map={},order=[];
fs.forEach(function(f){
var p=f.dataset.rel.split('/'),d=p.slice(0,p.length-1).join('/')||'（根目录）';
if(!map[d]){map[d]=[];order.push(d)}map[d].push(f)});
order.sort();
order.forEach(function(d){
var h=document.createElement('div');h.className='grphead';
h.innerHTML='<span>'+esc(d)+'</span><em>'+map[d].length+' 张</em>';
grid.appendChild(h);
map[d].forEach(function(f){grid.appendChild(f)})});
}
if(KIND==='fav'&&grid){
var bRandom=document.getElementById('favRandom'),bGroup=document.getElementById('favGroup');
if(bRandom)bRandom.onclick=function(e){e.preventDefault();
var list=visible();if(!list.length){toast('当前没有可看的收藏');return}
openLb(list[Math.floor(Math.random()*list.length)])};
if(bGroup)bGroup.onclick=function(e){e.preventDefault();
groupFavByDir(!favGrouped);
bGroup.innerHTML=favGrouped?'&#9776; 平铺':'&#9776; 分组';
toast(favGrouped?'已按目录分组':'已切回平铺')};
}
function refreshFavUI(){
if(KIND!=='fav'||!grid)return;
if(favFilter||favQ){applyFavFilters();return}
var n=grid.querySelectorAll('figure.item').length;
var c=document.getElementById('fcnt');if(c)c.textContent=n;
var em=document.getElementById('favEmpty');if(em)em.style.display=n?'none':'';
var s=document.getElementById('fsub');
if(s)s.textContent=n?('共 '+n+' 个收藏 · 最近收藏在最前'):'还没有收藏，回目录挑几张点 ♡';
buildFavNav();
}
/* 收藏页目录导航：只列出「实际有收藏的目录」，与图片实时联动 */
function applyFavFilters(){
if(KIND!=='fav'||!grid)return;
if(favFilter){var ok=false;items.forEach(function(it){if(relDir(it[0])===favFilter)ok=true});
if(!ok)favFilter=null;}
var shown=0,total=items.length;
grid.querySelectorAll('figure.item').forEach(function(f){
var hit=true;
if(favFilter)hit=relDir(f.dataset.rel)===favFilter;
if(hit&&favQ){var t=(f.dataset.name+' '+f.dataset.rel).toLowerCase();hit=t.indexOf(favQ)>=0}
if(hit&&tagFilter)hit=(tags[f.dataset.rel]||[]).indexOf(tagFilter)>=0;
f.style.display=hit?'':'none';if(hit)shown++;
});
fixStacks();
var e=document.getElementById('emp');
if(!shown&&total){ensureEmp(favFilter?'该目录下暂无匹配的收藏':'没有匹配的内容','换个关键词，或点左侧「全部」')}
else if(e){e.style.display='none'}
var c=document.getElementById('fcnt');if(c)c.textContent=shown;
var s=document.getElementById('fsub');
if(s)s.textContent=!total?'还没有收藏，回目录挑几张点 ♡':(shown===total?('共 '+total+' 个收藏 · 最近收藏在最前'):('筛选出 '+shown+' / '+total+' 个收藏'));
buildFavNav();
}
function buildFavNav(){
if(KIND!=='fav'||!navbox)return;
var st=navbox.scrollTop;
/* 取消收藏后以 DOM 为准；初始构建时 render 还没跑，退回 items */
var src=[];
if(grid&&grid.children.length){
grid.querySelectorAll('figure.item').forEach(function(f){src.push(f.dataset.rel)});
}else{
items.forEach(function(it){src.push(it[0])});
}
var m={};
src.forEach(function(rel){
var d=relDir(rel);if(!d)return;
var c=d.split('/')[0];
(m[c]=m[c]||{})[d]=(m[c][d]||0)+1;
});
var nh='<a class="nav-item" href="index.html">&#9776; 目录总览</a>';
nh+='<a class="nav-item'+(favFilter?'':' on')+'" data-g="">&#9825; 全部 <em>'+items.length+'</em></a>';
var activeCat=favFilter?favFilter.split('/')[0]:null;
Object.keys(m).map(function(c){
var gs=m[c],tot=0;Object.keys(gs).forEach(function(k){tot+=gs[k]});
return {c:c,gs:gs,tot:tot};
}).sort(function(a,b){return b.tot-a.tot||a.c.localeCompare(b.c)}).forEach(function(o){
nh+=catHead(o.c,o.c,o.tot,catOpen(o.c,o.c===activeCat));
Object.keys(o.gs).map(function(g){return {g:g,k:o.gs[g]}})
.sort(function(a,b){return b.k-a.k||a.g.localeCompare(b.g)}).forEach(function(gi){
var short=gi.g.split('/').slice(1).join('/')||gi.g;
nh+='<a class="nav-item'+(favFilter===gi.g?' on':'')+'" data-g="'+esc(gi.g)+'" title="'+esc(gi.g)+'">'
+esc(short)+'<em>'+gi.k+'</em></a>';
});
nh+=CAT_END;
});
navbox.innerHTML=nh;navbox.scrollTop=st;
buildTagNav();
}
/* 侧栏标签维度：列出当前页出现过的标签，点选过滤（与搜索/横竖图/收藏目录叠加） */
var tagFilter='';
function buildTagNav(){
if(!navbox||(KIND!=='group'&&KIND!=='fav'))return;
var counts={};
Object.keys(tags).forEach(function(rel){
(tags[rel]||[]).forEach(function(t){counts[t]=(counts[t]||0)+1})});
var old=document.getElementById('tagcat');if(old)old.remove();
var names=Object.keys(counts).sort(function(a,b){return counts[b]-counts[a]||a.localeCompare(b)});
if(!names.length)return;
var st=navbox.scrollTop;
/* 开关状态尊重用户：显式设置过按用户来，没动过默认展开 */
var d=document.createElement('div');d.id='tagcat';
d.className='cat'+(catOpen('__tags__',true)?' open':'');d.dataset.cat='__tags__';
var h='<div class="cat-h"><span class="ch">&#9656;</span><span class="ct2">标签</span><em>'+names.length+'</em></div><div class="cat-body"><div class="cat-in">';
names.forEach(function(t){
h+='<a class="nav-item'+(tagFilter===t?' on':'')+'" data-tag="'+esc(t)+'">'+esc(t)+'<em>'+counts[t]+'</em></a>'});
d.innerHTML=h+'</div></div>';
navbox.appendChild(d);navbox.scrollTop=st;
}
function syncFavNav(rel){
if(KIND!=='fav'||!navbox||!rel)return;
var d=relDir(rel);if(!d)return;
navbox.querySelectorAll('a[data-g]').forEach(function(a){
var hit=a.dataset.g===d;
a.classList.toggle('on',hit);
if(hit){var cat=a.closest('.cat');
/* 联动到的分类若收起则自动展开，保证高亮可见 */
if(cat&&!cat.classList.contains('open')){cat.classList.add('open');
if(cat.dataset.cat){catState[cat.dataset.cat]=true;saveCatState()}}}
});
}
function ensureEmp(msg,sub,hint){
var host=grid?grid.parentNode:document.querySelector('.wrap');
if(!host)return null;
var e=document.getElementById('emp');
if(!e){e=document.createElement('div');e.id='emp';e.className='empty';
e.innerHTML='<div class="big">&#9825;</div><b></b><span></span>';host.appendChild(e)}
e.querySelector('b').textContent=msg;
e.querySelector('span').textContent=sub||'';
e.style.display='';
var fe=document.getElementById('favEmpty');if(fe)fe.style.display='none';
return e;
}
/* 差分折叠：同一场景的差分（y09_05_001/002/003…）叠成一张卡，右下角标数量。
   被叠起来的 figure 仍留在 DOM 里（只是 opacity:0），所以灯箱里 ←→ 照样能翻到每一张差分。
   判断依据：去掉末尾数字后的“基名”相同且相邻。立绘那种 001活01/002活02 基名不同，不会误折叠。 */
function baseOf(rel){
var b=rel.slice(rel.lastIndexOf('/')+1).replace(/\.[^.]+$/,'');
var s=b.replace(/[_\-\s.]?\d+$/,'');
var core=s.replace(/[\s_\-]+$/,'');
/* 只有「去掉序号后还剩至少两段」才当差分折叠。
   否则 dd 1..243 / 1..456 / cg1..cg999 这种顺序命名会被整页叠成一张（实测 Ripples 456→1）。 */
if(!core||!/[\s_\-]/.test(core))return b;
return s;
}
function itemHTML(it){
var rel=it[0],w=it[1],hh=it[2],isv=it[3];
var nm=rel.split('/').pop(),qq=encPath(rel);
var fav=favSet.has(rel),nt=notes[rel]||'';
var oc=isv?'v':(w&&hh?(w>=hh?'l':'p'):'l');
var h=[];
h.push('<figure class="item'+(isv?' item-v':'')+(fav?' fav':'')+(nt?' has-note':'')+(rel===recentRel?' seen':'')+'"'+(isv?'':' data-src="'+esc(qq)+'"')+' data-rel="'+esc(rel)+'" data-o="'+oc+'" data-name="'+esc(nm)+'">');
h.push('<div class="acts"><button class="act act-fav" title="收藏">'+(fav?'&#9829;':'&#9825;')+'</button>');
h.push('<button class="act act-note" title="备注">&#128172;</button></div>');
if(isv){h.push('<video preload="none" muted playsinline poster="'+esc(encPath(posterFor(rel)))+'" src="'+qq+'"></video>');}
else{var wh=(w&&hh)?' width="'+w+'" height="'+hh+'"':'';
h.push('<img loading="lazy" decoding="async" src="'+esc(encPath(thumbFor(rel)))+'" data-orig="'+esc(qq)+'" onerror="this.onerror=null;this.src=this.dataset.orig"'+wh+' alt="">');}
h.push('<figcaption title="'+esc(rel)+'">'+esc(nm)+'</figcaption>');
if(nt)h.push('<div class="note" title="'+esc(nt)+'">&#128172; '+mdInline(nt)+'</div>');
const tl=tags[rel]||[];
if(tl.length)h.push('<div class="tagrow">'+tl.map(function(x){return '<span class="tagchip" data-tag="'+esc(x)+'">'+esc(x)+'</span>'}).join('')+'</div>');
h.push('</figure>');
return h.join('');
}
/* 过滤/搜索后修正叠层：让「栈里第一个可见的」显形，整栈都没了就收起。
   已摊开（.flat）的栈不参与——它的每张都要正常显示。 */
function fixStacks(){
document.querySelectorAll('.stack').forEach(function(s){
if(s.classList.contains('flat')){
[].forEach.call(s.children,function(f){if(f.tagName==='FIGURE'){f.style.opacity='1';f.style.pointerEvents=''}});
s.style.display='';return;
}
var kids=[].slice.call(s.children).filter(function(f){return f.tagName==='FIGURE'}),vis=null,rec=null;
kids.forEach(function(f){
if(f.style.display==='none'||f.classList.contains('hide'))return;
if(!vis)vis=f;
if(recentRel&&f.dataset.rel===recentRel)rec=f;
});
/* 顶层优先显示「最近看过的那张」：看完第 7 张退出来，卡片就停在第七张，不用满栈找 */
var top=rec||vis;
/* 必须显式写 1：清空内联样式的话，CSS 里 .stack>figure:not(:first-of-type){opacity:0} 依旧生效 */
kids.forEach(function(f){
f.style.opacity=(f===top?'1':'0');
f.style.pointerEvents=(f===top?'':'none');
});
s.style.display=vis?'':'none';
var n=kids.filter(function(f){return f.style.display!=='none'&&!f.classList.contains('hide')}).length;
s.dataset.n=n||kids.length;
});
}
/* 最近查看变了（关灯箱 / 翻页）时重算 .seen 标记，并让对应的栈浮到顶层 */
function refreshSeen(){
document.querySelectorAll('figure.item').forEach(function(f){
f.classList.toggle('seen',!!recentRel&&f.dataset.rel===recentRel);
});
fixStacks();
}
/* 差分「平铺/叠起」：**默认平铺**（每张都显示，直接看图）；点导航栏 chip 才叠起来。
   切换要重建网格（plan 结构变了），所以直接 render()，并把状态按库记住。 */
function applyDupMode(expand,btn){
dupExpand=!!expand;
if(btn){
btn.classList.toggle('on',dupExpand);
var n=btn.getAttribute('data-n')||'';
btn.textContent=dupExpand?'平铺显示':('叠起差分'+(n?(' '+n+' 组'):''));
btn.title=dupExpand?'当前：同一场景的差分叠成一张。点这里恢复平铺（每张都显示）'
                   :'当前：每张都平铺显示。点这里把同一场景的差分叠成一张（右下角会标 +N）';
}
try{localStorage.setItem(DUP_KEY,dupExpand?'1':'0')}catch(e){}
}
var dupChip=document.getElementById('dupChip'),dupExpand=false;
try{dupExpand=localStorage.getItem(DUP_KEY)==='1'}catch(e){}
if(dupChip){
if(!dupChip.getAttribute('data-n')){
var mm=(dupChip.textContent||'').match(/(\d+)/);
if(mm)dupChip.setAttribute('data-n',mm[1]);
}
applyDupMode(dupExpand,dupChip);
dupChip.addEventListener('click',function(e){
e.preventDefault();
applyDupMode(!dupExpand,dupChip);
if(typeof render==='function')render();
toast(dupExpand?'差分已叠起（点角标可看整组）':'已恢复平铺');
});
}
if(grid){
grid.addEventListener('click',function(e){
var b=e.target.closest&&e.target.closest('.dupbadge');
if(!b)return;
e.preventDefault();e.stopPropagation();
openDup(b.parentNode);
},true);
}
/* 差分速览弹层：列出这一组每一张的小缩略图，点哪张就进灯箱看哪张 */
var dupPanel=document.getElementById('dupPanel'),dpGrid=document.getElementById('dpGrid');
function stackFigs(s){return [].slice.call(s.children).filter(function(f){return f.tagName==='FIGURE'})}
function openDup(stack){
if(!dupPanel||!stack)return;
var figs=stackFigs(stack);
document.getElementById('dpTitle').textContent='差分速览 · '+figs.length+' 张';
document.getElementById('dpSub').textContent=(figs[0].dataset.name||'')+' —— 点任意一张直接全屏查看，←→ 继续翻这一组';
dpGrid.innerHTML=figs.map(function(f,i){
var rel=f.dataset.rel;
return '<div class="dp-item" data-i="'+i+'" title="'+esc(rel)+'">'
+'<img loading="lazy" decoding="async" src="'+esc(encPath(thumbFor(rel)))+'" data-orig="'+esc(encPath(rel))+'" '
+'onerror="this.onerror=null;this.src=this.dataset.orig" alt=""><b>'+(i+1)+'</b></div>';
}).join('');
dupPanel.classList.add('open');
dupPanel._stack=stack;
}
function closeDup(){if(!dupPanel)return;dupPanel.classList.remove('open');dupPanel._stack=null}
if(dupPanel){
dpGrid.addEventListener('click',function(e){
var it=e.target.closest&&e.target.closest('.dp-item');if(!it)return;
var s=dupPanel._stack;if(!s)return;
var idx=+it.dataset.i,f=stackFigs(s)[idx];
closeDup();
if(f)openLb(f);
});
dupPanel.addEventListener('click',function(e){if(e.target===dupPanel)closeDup()});
var dpc=document.getElementById('dpClose');if(dpc)dpc.addEventListener('click',closeDup);
document.addEventListener('keydown',function(e){
if(e.key==='Escape'&&dupPanel.classList.contains('open')){
e.stopImmediatePropagation();e.preventDefault();closeDup();
}
},true);
}
function render(){
if(!grid)return;
grid.innerHTML='';
if(!items.length)return;
/* 差分默认**不折叠**——用户明确要求「我要直接看图」，所以每张都平铺。
   想叠起来看再点导航栏的「叠起差分」，这时才按基名聚合（收藏页永远不聚合）。 */
var plan=[];
if(KIND==='fav'||!dupExpand){
items.forEach(function(it){plan.push([it])});
}else{
var byBase={};
items.forEach(function(it){
var b=baseOf(it[0]);
if(!byBase[b]){byBase[b]=[];plan.push(byBase[b])}
byBase[b].push(it);
});
}
var pi=0;
function flush(){
var h=[],cnt=0;
while(pi<plan.length&&cnt<70){
var g=plan[pi++];cnt+=g.length;
if(g.length>1){
h.push('<div class="stack" data-n="'+g.length+'"><span class="dupbadge" title="点这里看这一组的所有差分">+'+g.length+' 差分</span>');
for(var k=0;k<g.length;k++)h.push(itemHTML(g[k]));
h.push('</div>');
}else h.push(itemHTML(g[0]));
}
grid.insertAdjacentHTML('beforeend',h.join(''));
if(pi<plan.length)requestAnimationFrame(flush);else refreshSeen();
}
flush();
}
if(q){
q.addEventListener('input',function(){
const v=q.value.trim().toLowerCase();let n=0;
/* 目录页：按分组卡片过滤，整块分类空了就一起收起 */
if(KIND==='index'){
document.querySelectorAll('.catblock').forEach(function(blk){
var any=false;
blk.querySelectorAll('.card').forEach(function(c){
var hit=!v||c.textContent.toLowerCase().indexOf(v)>=0;
c.style.display=hit?'':'none';if(hit){any=true;n++}
});
blk.style.display=any?'':'none';
});
var e0=document.getElementById('emp');
if(!n){ensureEmp('没有匹配的分组','换个关键词，或清空搜索框')}
else if(e0){e0.style.display='none'}
var sb=document.getElementById('isub');
if(sb)sb.textContent=v?('筛选出 '+n+' 个分组'):sb.dataset.all;
return;
}
if(KIND==='fav'){favQ=v;applyFavFilters();return}
gq=v;applyGroupFilters();
});}
/* 分组页：关键词 + 横竖图 + 标签筛选叠加 */
var gq='',curOrient='',tagFilter='';
function applyGroupFilters(){
if(KIND!=='group'||!grid)return;
var n=0;
grid.querySelectorAll('figure.item').forEach(function(f){
var hit=true;
if(gq){var t=(f.dataset.name+' '+f.dataset.rel).toLowerCase();hit=t.indexOf(gq)>=0}
if(hit&&curOrient)hit=f.dataset.o===curOrient;
if(hit&&tagFilter)hit=(tags[f.dataset.rel]||[]).indexOf(tagFilter)>=0;
f.style.display=hit?'':'none';if(hit)n++;});
fixStacks();
var e=document.getElementById('emp');
if(!n&&items.length){ensureEmp('没有匹配的内容','换个关键词或切换筛选')}
else if(e){e.style.display='none'}
buildTagNav();
}
var orientChips=document.getElementById('orientChips');
if(orientChips){orientChips.addEventListener('click',function(e){
var c=e.target.closest&&e.target.closest('.chip');if(!c)return;
curOrient=c.dataset.o||'';
orientChips.querySelectorAll('.chip').forEach(function(x){x.classList.toggle('on',x===c)});
applyGroupFilters();
});}
/* 收藏页：导出 / 导入收藏与备注 + 显示设置（JSON，跨设备迁移用） */
if(KIND==='fav'){
var expBtn=document.getElementById('expBtn');
if(expBtn)expBtn.onclick=function(){
toast('导出中…');
var K=FAV_KEY.replace('_favs','');
var data={app:'SakuraView',v:1,key:K,
exported:new Date().toISOString().slice(0,10),favs:favOrder.slice(),notes:notes,tags:tags,
settings:{zm:localStorage.getItem(K+'_zm'),zn:localStorage.getItem(K+'_zn'),
cat:localStorage.getItem(CAT_KEY)}};
try{var blob=new Blob([JSON.stringify(data,null,1)],{type:'application/json'});
var a=document.createElement('a');a.href=URL.createObjectURL(blob);
a.download='sakuraview-'+data.key+'-'+data.exported+'.json';
document.body.appendChild(a);a.click();
setTimeout(function(){URL.revokeObjectURL(a.href);a.remove()},800);
toast('已导出 '+favOrder.length+' 个收藏 / '+Object.keys(notes).length+' 条备注');
}catch(x){toast('导出失败：'+x.message)}};
var impBtn=document.getElementById('impBtn'),impFile=document.getElementById('impFile');
if(impBtn&&impFile){impBtn.onclick=function(){impFile.click()};
impFile.onchange=function(){
var f=impFile.files&&impFile.files[0];impFile.value='';if(!f)return;
var r=new FileReader();
r.onload=function(){var d;try{d=JSON.parse(r.result)}catch(x){toast('导入失败：不是有效的 JSON');return}
if(!d||!Array.isArray(d.favs)){toast('导入失败：文件里缺少 favs');return}
var addF=0,addN=0,addS=0,addT=0;
d.favs.forEach(function(rel){if(rel&&!favSet.has(rel)){favSet.add(rel);favOrder.push(rel);addF++}});
if(d.notes)Object.keys(d.notes).forEach(function(k){
if(d.notes[k]&&!(k in notes)){notes[k]=String(d.notes[k]).slice(0,200);addN++}});
if(d.tags)Object.keys(d.tags).forEach(function(k){
var arr=(d.tags[k]||[]).filter(function(x){return typeof x==='string'&&x}).slice(0,8);
if(arr.length&&!(k in tags)){tags[k]=arr;addT++}});
if(d.settings){var K=FAV_KEY.replace('_favs','');
['zm','zn'].forEach(function(s){if(d.settings[s]){try{localStorage.setItem(K+'_'+s,d.settings[s]);addS++}catch(x){}}});
if(d.settings.cat){try{localStorage.setItem(CAT_KEY,d.settings.cat);addS++}catch(x){}}}
saveFav();saveNotes();saveTags();
toast('导入 '+addF+' 个收藏 / '+addN+' 条备注'+(addT?' / '+addT+' 组标签':'')+(addS?' / '+addS+' 项设置':'')+'，刷新中…');
setTimeout(function(){location.reload()},800);};
r.onerror=function(){toast('读取文件失败')};
r.readAsText(f)};
}
}
function toggleFav(rel){
const on=!favSet.has(rel);
if(on){favSet.add(rel);favOrder.push(rel)}else{favSet.delete(rel);favOrder=favOrder.filter(function(r){return r!==rel})}
saveFav();
const drop=(KIND==='fav'&&!on);
grid.querySelectorAll('figure.item').forEach(function(f){
if(f.dataset.rel!==rel)return;
if(!drop){
f.classList.toggle('fav',on);
const b=f.querySelector('.act-fav');if(b)b.innerHTML=on?'&#9829;':'&#9825;';return;
}
/* 收藏页取消收藏：直接撤掉这张卡，别留着让人以为还收藏着 */
if(lb.classList.contains('open')){if(f.parentNode)f.remove();return}
f.style.transition='opacity .16s,transform .16s,box-shadow .16s';
f.style.opacity='0';f.style.transform='scale(.97)';
setTimeout(function(){if(f.parentNode){f.remove();refreshFavUI()}},160);
});
if(drop){
if(lb.classList.contains('open')){
refreshFavUI();cur=visible();
if(!cur.length){closeLb();return}
if(pos>cur.length-1)pos=cur.length-1;
show();return;
}
toast('已取消收藏 · 从收藏夹移除');
return;
}
if(lb.classList.contains('open'))syncLb();
}
function openNote(rel){
slideStop();noteRel=rel;noteInput.value=notes[rel]||'';
tagInput.value=(tags[rel]||[]).join(' ');
const f=grid.querySelector('figure.item[data-rel="'+rel.replace(/"/g,'\\"')+'"]');
if(f&&!f.querySelector('video')){modalThumb.src=f.dataset.src;modalThumb.style.display=''}
else{modalThumb.removeAttribute('src');modalThumb.style.display='none'}
noteModal.classList.add('open');setTimeout(function(){noteInput.focus()},60);
}
function closeNote(){noteModal.classList.remove('open');noteRel=null}
function parseTags(s){return s.split(/[\s,，、]+/).map(function(t){return t.trim().slice(0,20)})
.filter(function(t,i,a){return t&&a.indexOf(t)===i}).slice(0,8)}
/* 备注的 Markdown 简写：**粗体** / `代码` / #标签（渲染前先 esc，安全）
   存储仍是原始文本，标签只做展示 + 保存时把 #xxx 合并进 tags（不改变导出格式） */
function mdInline(t){
var s=esc(String(t||''));
s=s.replace(/\*\*([^*]+)\*\*/g,'<b>$1</b>');
s=s.replace(/`([^`]+)`/g,'<code>$1</code>');
s=s.replace(/(^|[\s，。,.!?！？])#([^\s#<>]{1,16})/g,'$1<span class="mdtag">#$2</span>');
return s.replace(/\s+/g,' ');}
function hashTags(t){
var out=[],m,re=/(^|[\s，。,.!?！？])#([^\s#<>]{1,16})/g;
while((m=re.exec(String(t||''))))out.push(m[2]);
return out.filter(function(x,i,a){return a.indexOf(x)===i})}
function commitNote(){
const t=noteInput.value.trim();
if(t)notes[noteRel]=t;else delete notes[noteRel];
var tg=parseTags(tagInput.value);
/* 备注里写的 #标签 自动并入标签表（渲染仍按原文） */
hashTags(t).forEach(function(x){if(tg.indexOf(x)<0&&tg.length<8)tg.push(x)});
if(tg.length)tags[noteRel]=tg;else delete tags[noteRel];
saveNotes();saveTags();
const rel=noteRel;
grid.querySelectorAll('figure.item').forEach(function(f){
if(f.dataset.rel!==rel)return;
let el=f.querySelector('.note');
if(!t){if(el)el.remove();f.classList.remove('has-note');return}
if(!el){el=document.createElement('div');el.className='note';f.appendChild(el)}
el.innerHTML='&#128172; '+mdInline(t);el.title=t;f.classList.add('has-note');
let tr=f.querySelector('.tagrow');
const list=tags[rel]||[];
if(list.length){if(!tr){tr=document.createElement('div');tr.className='tagrow';f.appendChild(tr)}
tr.innerHTML=list.map(function(x){return '<span class="tagchip">'+esc(x)+'</span>'}).join('')}
else if(tr)tr.remove();});
buildTagNav();closeNote();
}
if(document.getElementById('noteSave')){
document.getElementById('noteSave').onclick=commitNote;
document.getElementById('noteCancel').onclick=closeNote;
document.getElementById('noteDel').onclick=function(){
delete notes[noteRel];saveNotes();
delete tags[noteRel];saveTags();
const rel=noteRel;
grid.querySelectorAll('figure.item').forEach(function(f){
if(f.dataset.rel!==rel)return;
const el=f.querySelector('.note');if(el)el.remove();f.classList.remove('has-note');
const tr=f.querySelector('.tagrow');if(tr)tr.remove();});
buildTagNav();closeNote();};
noteModal.addEventListener('click',function(e){if(e.target===noteModal)closeNote()});
noteInput.addEventListener('keydown',function(e){
if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();commitNote()}});
}
/* ---------- 批量选择：Shift 点选 / 空白处拖框 / 批量收藏 · 批量加标签 ---------- */
var selSet=new Set(),selAnchor=null,bandEl=document.getElementById('selBand'),bandOn=false,bandStart=null;
var selBar=document.getElementById('selBar');
function figs(){return Array.prototype.slice.call(grid.querySelectorAll('figure.item')).filter(function(f){return f.style.display!=='none'})}
function applySelClasses(){if(!grid)return;
grid.querySelectorAll('figure.item').forEach(function(f){f.classList.toggle('sel',selSet.has(f.dataset.rel))})}
function refreshSel(){if(!selBar)return;
document.getElementById('selN').textContent=selSet.size;
selBar.classList.toggle('open',selSet.size>0);
var b=document.getElementById('selFav');
if(b)b.innerHTML=(KIND==='fav'?'&#9825; 取消收藏':'&#9829; 收藏');}
function clearSel(){selSet.clear();selAnchor=null;applySelClasses();refreshSel()}
function selAdd(f){if(!f)return;selSet.add(f.dataset.rel);f.classList.add('sel')}
function selToggle(f){if(!f)return;var r=f.dataset.rel;
if(selSet.has(r)){selSet.delete(r);f.classList.remove('sel')}else{selSet.add(r);f.classList.add('sel')}}
if(grid){
grid.addEventListener('click',function(e){
var f=e.target.closest('figure.item');
if(!f||e.target.closest('.acts')||e.target.closest('.note'))return;
if(!e.shiftKey)return;
e.preventDefault();e.stopPropagation();
if(selAnchor&&selAnchor!==f&&selAnchor.isConnected){
var list=figs(),a=list.indexOf(selAnchor),b=list.indexOf(f);
if(a>=0&&b>=0){for(var i=Math.min(a,b);i<=Math.max(a,b);i++)selAdd(list[i])}
else selToggle(f);
}else selToggle(f);
selAnchor=f;refreshSel();
},true);
/* 空白处拖出选框（触摸/鼠标通用） */
grid.addEventListener('pointerdown',function(e){
if(e.button!==0||!bandEl)return;
if(e.target.closest('figure.item'))return;
bandOn=true;bandStart={x:e.clientX,y:e.clientY};
bandEl.style.display='block';
bandEl.style.left=e.clientX+'px';bandEl.style.top=e.clientY+'px';
bandEl.style.width='0px';bandEl.style.height='0px';});
document.addEventListener('pointermove',function(e){
if(!bandOn)return;
var x=Math.min(bandStart.x,e.clientX),y=Math.min(bandStart.y,e.clientY);
var w=Math.abs(e.clientX-bandStart.x),h=Math.abs(e.clientY-bandStart.y);
bandEl.style.left=x+'px';bandEl.style.top=y+'px';
bandEl.style.width=w+'px';bandEl.style.height=h+'px';});
document.addEventListener('pointerup',function(e){
if(!bandOn)return;
bandOn=false;bandEl.style.display='none';
var x1=Math.min(bandStart.x,e.clientX),y1=Math.min(bandStart.y,e.clientY);
var x2=Math.max(bandStart.x,e.clientX),y2=Math.max(bandStart.y,e.clientY);
if(x2-x1<8&&y2-y1<8)return;
figs().forEach(function(f){var r=f.getBoundingClientRect();
if(r.right>x1&&r.left<x2&&r.bottom>y1&&r.top<y2)selAdd(f)});
refreshSel();});
}
if(selBar){
document.getElementById('selAll').onclick=function(){figs().forEach(selAdd);refreshSel()};
document.getElementById('selClear').onclick=clearSel;
document.getElementById('selFav').onclick=function(){
var n=0;
if(KIND==='fav'){/* 收藏页：批量取消收藏 */
selSet.forEach(function(rel){if(favSet.has(rel)){favSet.delete(rel);favOrder=favOrder.filter(function(r){return r!==rel});n++}});
saveFav();toast('已取消收藏 '+n+' 张');setTimeout(function(){location.reload()},600);return}
selSet.forEach(function(rel){if(!favSet.has(rel)){favSet.add(rel);favOrder.push(rel);n++}});
saveFav();
grid.querySelectorAll('figure.item').forEach(function(f){
if(!selSet.has(f.dataset.rel))return;
f.classList.add('fav');var b=f.querySelector('.act-fav');if(b)b.innerHTML='&#9829;'});
toast('已收藏 '+n+' 张');clearSel()};
function applyBatchTags(){
var inp=document.getElementById('selTag');var list=parseTags(inp.value||'');
if(!list.length){toast('先输入标签，空格分隔');return}
var n=0;
selSet.forEach(function(rel){
var cur=tags[rel]||[];var add=false;
list.forEach(function(t){if(cur.indexOf(t)<0&&cur.length<8){cur.push(t);add=true}});
if(add){tags[rel]=cur;n++}});
saveTags();buildTagNav();
grid.querySelectorAll('figure.item').forEach(function(f){
if(!selSet.has(f.dataset.rel))return;
var tr=f.querySelector('.tagrow'),l=tags[f.dataset.rel]||[];
if(!l.length)return;
if(!tr){tr=document.createElement('div');tr.className='tagrow';f.appendChild(tr)}
tr.innerHTML=l.map(function(x){return '<span class="tagchip">'+esc(x)+'</span>'}).join('')});
inp.value='';toast('已给 '+n+' 张加标签');}
document.getElementById('selTagApply').onclick=applyBatchTags;
document.getElementById('selTag').addEventListener('keydown',function(e){
if(e.key==='Enter'){e.preventDefault();applyBatchTags()}});
refreshSel();
}

/* 视频卡：单击延迟 230ms 再开（给双击留窗口），双击第一击排队、第二击直接开+全屏 */
var vCardT=null;
function openVCard(rel,e){
if(e&&e.detail>1){clearTimeout(vCardT);vCardT=null;openVlb(rel);goFullV();return}
clearTimeout(vCardT);
vCardT=setTimeout(function(){vCardT=null;openVlb(rel)},230);
}
document.addEventListener('click',function(e){
const ntEl=e.target.closest('.note');
if(ntEl){e.stopPropagation();openNote(ntEl.closest('figure').dataset.rel);return}
const fav=e.target.closest('.act-fav');
if(fav){e.stopPropagation();e.preventDefault();toggleFav(fav.closest('figure').dataset.rel);return}
const nt=e.target.closest('.act-note');
if(nt){e.stopPropagation();e.preventDefault();openNote(nt.closest('figure').dataset.rel);return}
const vcard=e.target.closest('figure.item-v[data-rel]');
if(vcard){e.stopPropagation();openVCard(vcard.dataset.rel,e);return}
const item=e.target.closest('figure.item[data-src]');
if(item&&!e.target.closest('.acts')){
if(e.shiftKey)return;   /* Shift 点选交给批量选择逻辑 */
openLb(item)}
});
var pageY=0;
function visible(){return Array.prototype.slice.call(grid.querySelectorAll('figure.item[data-src]')).filter(function(f){return f.style.display!=='none'})}
function openLb(f){pageY=window.scrollY;cur=visible();pos=cur.indexOf(f);if(pos<0)return;
markRecent(f.dataset.rel);lb.classList.add('open');show();hideChrome();lbHintOnce();enterFs()}
/* 点缩略图直接进全屏（真全屏，浏览器地址栏/标签一起隐藏）；不支持或被拒就退化成整屏遮罩 */
function enterFs(){try{
if(document.fullscreenElement||!lb.requestFullscreen)return;
var p=lb.requestFullscreen();if(p&&p.catch)p.catch(function(){})}catch(e){}}
function exitFs(){try{
if(document.fullscreenElement===lb&&document.exitFullscreen)document.exitFullscreen().catch(function(){})}catch(e){}}
/* 首次打开给一句操作提示（点左右半屏翻页 / 底部才浮出操作条），只提示一次 */
var LB_HINT_KEY='cg_lbhint';
function lbHintOnce(){
try{if(localStorage.getItem(LB_HINT_KEY)==='1')return;localStorage.setItem(LB_HINT_KEY,'1')}catch(e){}
toast('点左右半屏翻页 · 底部是收藏/幻灯/备注 · Esc 关闭')}
/* 底部操作条：靠屏幕下方才浮现，离开即隐藏；顶栏/箭头/关闭由 ui-on 控制（2.4s 后自动淡出） */
var actsHideT=null,chromeT=null;
function showChrome(){lb.classList.add('ui-on');clearTimeout(chromeT);
chromeT=setTimeout(function(){lb.classList.remove('ui-on')},2400)}
function hideChrome(){lb.classList.remove('ui-on');clearTimeout(chromeT)}
function showActs(){lb.classList.add('show-acts');showChrome();clearTimeout(actsHideT);
if(matchMedia('(hover:none)').matches)actsHideT=setTimeout(hideActs,3200)}
function hideActs(){lb.classList.remove('show-acts');clearTimeout(actsHideT)}
/* 退出预览后定位：把刚看的那张滚到视口上部约 1/6 处；目标不在（如已取消收藏）则回原位置 */
function scrollToFig(f){
if(!f||!f.isConnected)return;
var off=Math.max(56,Math.round(window.innerHeight*0.16));
function jump(){
/* html 上有 scroll-behavior:smooth，长距离程序化滚动会变成动画，这里强制即时 */
var de=document.documentElement,prev=de.style.scrollBehavior;
de.style.scrollBehavior='auto';
var r=f.getBoundingClientRect();
window.scrollTo(0,Math.max(0,Math.round(window.scrollY+r.top-off)));
de.style.scrollBehavior=prev;
}
jump();
/* 图片懒加载/布局稳定后再校正一次 */
setTimeout(function(){if(!f.isConnected)return;
var r=f.getBoundingClientRect();
if(Math.abs(r.top-off)>4)jump()},90);
}
/* 幻灯片放映：速率 200ms~2s 五档可调（记忆在 <key>_slide），主按钮开停、旁边小按钮选速率 */
const SLIDES=[16,100,200,500,1000,1500,2000];
const SLIDE_KEY='cg_slide';
var slideMs=16;
try{slideMs=parseInt(localStorage.getItem(SLIDE_KEY),10)||16;
if(SLIDES.indexOf(slideMs)<0)slideMs=16}catch(e){}
var slideT=null,slideOn=false;
function slideArm(){clearTimeout(slideT);
if(slideOn)slideT=setTimeout(function(){step(1);slideArm()},slideMs)}
function slideLabel(){
var b=document.getElementById('lbPlay'),m=document.getElementById('lbSpdMs');
if(b)b.innerHTML=(slideOn?'&#9208;':'&#9654;')+' 幻灯';
if(m)m.textContent=slideMs<1000?slideMs+'ms':(slideMs/1000)+'s'}
function slideStart(){slideOn=true;
var b=document.getElementById('lbPlay');if(b)b.classList.add('on');
slideLabel();slideArm()}
function slideStop(){slideOn=false;clearTimeout(slideT);
var b=document.getElementById('lbPlay');if(b){b.classList.remove('on');b.innerHTML='&#9654; 幻灯'}
var m=document.getElementById('spdMenu');if(m)m.classList.remove('open')}
function closeLb(){var f=cur[pos];if(f)markRecent(f.dataset.rel);
saveCurView();viewRel=null;exitFs();resetView();rotQ=0;
lb.classList.remove('open');lb.classList.remove('ui-on');hideActs();slideStop();
if(f&&f.isConnected)scrollToFig(f);
else window.scrollTo(0,pageY);
refreshSeen()}
/* ---------- 全图视图：缩放 / 旋转 / 拖拽 / 滑动翻页 ----------
   坐标模型：图片按 contain 摆进视口（fitW×fitH），再用 translate+scale+rotate 变换。
   zS=1 即"整屏 contain"，是缩放下限；上限保证能放大到原始像素的 2 倍以上（长图看细节）。
   每张图的缩放/旋转按 rel 记在 <key>_imgstate，退出再进能回到上次的位置。 */
var zS=1,zTx=0,zTy=0,rotQ=0,fitW=0,fitH=0,maxScaleNow=6;
var IMG_STATE_KEY='cg_imgstate',imgState={};
try{imgState=JSON.parse(localStorage.getItem(IMG_STATE_KEY)||'{}')||{}}catch(e){imgState={}}
function saveImgState(){try{localStorage.setItem(IMG_STATE_KEY,JSON.stringify(imgState))}catch(e){}}
var viewRel=null;   /* 当前内存里的 zS/rotQ 属于哪张图（换图前要存回它） */
function saveCurView(){var r=viewRel;if(!r)return;
if(zS<=1.001&&rotQ===0){delete imgState[r]}
else imgState[r]={z:Math.round(zS*100)/100,r:rotQ};
saveImgState()}
function layoutFit(){
var nw=lbImg.naturalWidth||0,nh=lbImg.naturalHeight||0;if(!nw||!nh)return;
var swap=(rotQ%2===1),w=swap?nh:nw,h=swap?nw:nh;
var k=Math.min(innerWidth/w,innerHeight/h);
fitW=Math.max(1,Math.round(w*k));fitH=Math.max(1,Math.round(h*k));
lbImg.style.width=fitW+'px';lbImg.style.height=fitH+'px';
maxScaleNow=Math.max(3,Math.min(16,Math.max(nw/fitW,nh/fitH)*2));}
function applyT(){
var vw=innerWidth,vh=innerHeight,bw=fitW*zS,bh=fitH*zS;
if(bw<=vw+0.5)zTx=0;else zTx=Math.max((vw-bw)/2,Math.min((bw-vw)/2,zTx));
if(bh<=vh+0.5)zTy=0;else zTy=Math.max((vh-bh)/2,Math.min((bh-vh)/2,zTy));
lbImg.style.transform='translate('+zTx+'px,'+zTy+'px) scale('+zS+') rotate('+(rotQ*90)+'deg)';
lbImg.classList.toggle('zoomed',zS>1.001);}
function resetView(){zS=1;zTx=0;zTy=0;applyT()}
function zoomAt(px,py,factor){
var ns=Math.max(1,Math.min(maxScaleNow,zS*factor));
if(Math.abs(ns-zS)<0.0008)return;
var cx=innerWidth/2+zTx,cy=innerHeight/2+zTy;
var dx=(px-cx)/zS,dy=(py-cy)/zS;
zS=ns;zTx=px-innerWidth/2-dx*zS;zTy=py-innerHeight/2-dy*zS;
applyT();}
function rotateCur(){rotQ=(rotQ+1)%4;zS=1;zTx=0;zTy=0;layoutFit();applyT();saveCurView();
toast('旋转 '+(rotQ*90)+'° · 已按此图记住')}
function show(){const f=cur[pos];if(!f)return;
saveCurView();
var src=f.dataset.src,rel=f.dataset.rel;
lbName.textContent=f.dataset.name;
lbIdx.textContent=(pos+1)+' / '+cur.length;syncLb();syncFavNav(rel);
var st=imgState[rel]||{};
rotQ=st.r||0;
viewRel=rel;
/* 换图：原图未就绪时先淡到 22% 再淡入，避免上一张残影停留 */
function ready(){
lbImg.classList.remove('loading');
layoutFit();
zS=(slideOn?1:(st.z||1));zTx=0;zTy=0;
if(zS>maxScaleNow)zS=maxScaleNow;
applyT();}
if(lbImg.getAttribute('src')!==src){lbImg.classList.add('loading');
lbImg.onload=ready;
lbImg.onerror=function(){lbImg.classList.remove('loading')};
lbImg.src=src}else ready();
/* 预取左右各一张：点半屏翻页时不再等原图 */
[1,-1].forEach(function(d){var n=cur[(pos+d+cur.length)%cur.length];
if(!n)return;var im=new Image();im.src=n.dataset.src});
hideActs();}
function syncLb(){const f=cur[pos];if(!f)return;
const on=favSet.has(f.dataset.rel);
lbFav.classList.toggle('on',on);
lbFav.innerHTML=on?'&#9829; 已收藏':'&#9825; 收藏';}
function step(d){if(!cur.length)return;pos=(pos+d+cur.length)%cur.length;show()}
if(lbFav){
lbFav.onclick=function(e){e.stopPropagation();const f=cur[pos];if(f)toggleFav(f.dataset.rel)};
/* 幻灯片：主按钮开停，旁边小按钮弹出院内速率菜单（200ms~2s 五档） */
var lbPlay=document.getElementById('lbPlay'),lbSpd=document.getElementById('lbSpd'),
spdMenu=document.getElementById('spdMenu');
lbPlay.onclick=function(e){e.stopPropagation();slideOn?slideStop():slideStart()};
lbSpd.onclick=function(e){e.stopPropagation();
var r=lbSpd.getBoundingClientRect();
spdMenu.style.left=Math.max(8,Math.round(r.left+r.width/2-48))+'px';
spdMenu.style.bottom=Math.round(window.innerHeight-r.top+12)+'px';
spdMenu.classList.toggle('open')};
SLIDES.forEach(function(ms){var b=document.createElement('button');
b.textContent=ms<1000?ms+'ms':(ms/1000)+'s';
if(ms===slideMs)b.classList.add('on');
b.onclick=function(e){e.stopPropagation();slideMs=ms;
try{localStorage.setItem(SLIDE_KEY,ms)}catch(x){}
[].slice.call(spdMenu.querySelectorAll('button')).forEach(function(x){x.classList.toggle('on',x===b)});
slideLabel();spdMenu.classList.remove('open');if(slideOn)slideArm()};
spdMenu.appendChild(b)});
slideLabel();
document.getElementById('lbNote').onclick=function(e){e.stopPropagation();const f=cur[pos];if(f)openNote(f.dataset.rel)};
document.getElementById('lbPrev').onclick=function(e){e.stopPropagation();step(-1)};
document.getElementById('lbNext').onclick=function(e){e.stopPropagation();step(1)};
document.getElementById('lbClose').onclick=function(e){e.stopPropagation();closeLb()};
/* 全图模式：点右半侧=下一张、左半侧=上一张；底部 120px 只负责浮出操作条；✕ / Esc 关闭。
   放大状态（zS>1）下点击不翻页，避免拖拽看细节时误触。 */
lb.addEventListener('click',function(e){
if(Date.now()<suppressClickUntil)return;
if(e.detail>1)return;
if(e.target.closest('.lb-acts')||e.target.closest('.lb-btn')||e.target.closest('.lb-close')
||e.target.closest('.spdmenu')||e.target.closest('.lb-bar'))return;
if(e.clientY>window.innerHeight-120){showActs();return}
if(zS>1.001)return;
if(e.clientX<window.innerWidth/2)step(-1);else step(1);});
lb.addEventListener('mousemove',function(e){
if(e.pointerType==='touch')return;
showChrome();
if(e.clientY>window.innerHeight-120)showActs();else hideActs();});
lb.addEventListener('touchstart',function(e){
var t=e.touches&&e.touches[0];if(!t)return;
if(t.clientY>window.innerHeight-140)showActs();},{passive:true});

/* 缩放：滚轮（桌面）/ 双指（触屏）；拖拽平移；zS=1 时横向滑动翻页 */
var ptrs={},pinchD0=0,pinchZ0=1,swipe=null,dragging=false,suppressClickUntil=0,dragO=null;
function pDist(a,b){return Math.sqrt((a.x-b.x)*(a.x-b.x)+(a.y-b.y)*(a.y-b.y))}
function pMid(a,b){return{x:(a.x+b.x)/2,y:(a.y+b.y)/2}}
function pCount(){var n=0;for(var k in ptrs)if(ptrs.hasOwnProperty(k))n++;return n}
function setZoomAbs(ns,px,py){
ns=Math.max(1,Math.min(maxScaleNow,ns));
if(Math.abs(ns-zS)<0.0008)return;
var cx=innerWidth/2+zTx,cy=innerHeight/2+zTy;
var dx=(px-cx)/zS,dy=(py-cy)/zS;
zS=ns;zTx=px-innerWidth/2-dx*zS;zTy=py-innerHeight/2-dy*zS;applyT();}
lb.addEventListener('wheel',function(e){
if(!lb.classList.contains('open'))return;
e.preventDefault();
zoomAt(e.clientX,e.clientY,e.deltaY<0?1.16:1/1.16);
if(slideOn)slideStop();
},{passive:false});
lb.addEventListener('pointerdown',function(e){
if(!lb.classList.contains('open'))return;
if(e.target.closest('.lb-acts,.lb-btn,.lb-close,.lb-bar,.spdmenu'))return;
if(e.pointerType==='mouse'&&e.button!==0)return;
ptrs[e.pointerId]={x:e.clientX,y:e.clientY};
var n=pCount();
if(n>=2){var ks=[];for(var k in ptrs)if(ptrs.hasOwnProperty(k))ks.push(ptrs[k]);
pinchD0=Math.max(1,pDist(ks[0],ks[1]));pinchZ0=zS;swipe=null;dragging=false}
else{swipe={x0:e.clientX,y0:e.clientY,t:Date.now(),moved:0};
if(zS>1.001){dragging=true;lbImg.classList.add('dragging')}}
});
lb.addEventListener('pointermove',function(e){
var p=ptrs[e.pointerId];if(!p)return;
var dxm=e.clientX-p.x,dym=e.clientY-p.y;p.x=e.clientX;p.y=e.clientY;
if(pCount()>=2){
var ks=[];for(var k in ptrs)if(ptrs.hasOwnProperty(k))ks.push(ptrs[k]);
var d=pDist(ks[0],ks[1]),m=pMid(ks[0],ks[1]);
if(pinchD0>8)setZoomAbs(pinchZ0*(d/pinchD0),m.x,m.y);
suppressClickUntil=Date.now()+600;swipe=null;return}
if(dragging&&zS>1.001){zTx+=dxm;zTy+=dym;applyT();suppressClickUntil=Date.now()+420;return}
if(swipe)swipe.moved+=Math.abs(dxm)+Math.abs(dym);
});
function ptrEnd(e){
if(!ptrs[e.pointerId])return;
delete ptrs[e.pointerId];
if(pCount()===0){
lbImg.classList.remove('dragging');dragging=false;
if(swipe&&zS<=1.001){
var dx=e.clientX-swipe.x0,dy=e.clientY-swipe.y0,dt=Date.now()-swipe.t;
if(swipe.moved>=14&&Math.abs(dx)>55&&Math.abs(dx)>Math.abs(dy)*1.35&&dt<900){
suppressClickUntil=Date.now()+520;hideActs();step(dx<0?1:-1)}
else if(swipe.moved>=14&&Math.abs(dy)>70&&Math.abs(dy)>Math.abs(dx)*1.2&&e.clientY>innerHeight*0.7){
showActs();suppressClickUntil=Date.now()+400}
}
swipe=null}}
lb.addEventListener('pointerup',ptrEnd);
lb.addEventListener('pointercancel',ptrEnd);
/* 视口变化（进出全屏 / 转屏）后重新算 contain 尺寸 */
function relayoutView(){if(!lb.classList.contains('open'))return;layoutFit();applyT()}
window.addEventListener('resize',relayoutView);
document.addEventListener('fullscreenchange',relayoutView);
var lbRotBtn=document.getElementById('lbRot');
if(lbRotBtn)lbRotBtn.onclick=function(e){e.stopPropagation();rotateCur();showActs()};
/* 键盘：←/→ 与 J/K 翻页、空格开停幻灯、F 收藏、R 旋转、0 复位、Esc 逐层退出
   层级：提示弹窗 → 备注弹窗 → 批量选择 → 真全屏 → 全图模式，一层一个 Esc */
document.addEventListener('keydown',function(e){
var k=e.key;
if(k==='Escape'){
var tip=document.getElementById('shotTip');
if(tip&&tip.classList.contains('open')){tip.classList.remove('open');return}
if(noteModal&&noteModal.classList.contains('open')){closeNote();return}
if(selSet.size){clearSel();return}
if(document.fullscreenElement){exitFs();return}
if(lb.classList.contains('open')){closeLb();return}
return}
if(!lb.classList.contains('open'))return;
if(k==='ArrowLeft'||k==='k'||k==='K'){step(-1);if(slideOn)slideArm();return}
if(k==='ArrowRight'||k==='j'||k==='J'){step(1);if(slideOn)slideArm();return}
if(k===' '){e.preventDefault();slideOn?slideStop():slideStart();return}
if(k==='f'||k==='F'){const f=cur[pos];if(f)toggleFav(f.dataset.rel);return}
if(k==='r'||k==='R'){rotateCur();return}
if(k==='0'){resetView();return}
});
}
/* 页面滚动位置记忆：切页面回来自动回到原位 */
var SCROLL_KEY='cg_scroll_'+location.pathname;
try{
var sy0=parseInt(sessionStorage.getItem(SCROLL_KEY)||'0')||0;
if(sy0>0){
window.addEventListener('load',function(){
setTimeout(function(){window.scrollTo(0,sy0)},50);
});
}
}catch(e){}
window.addEventListener('scroll',function(){
try{sessionStorage.setItem(SCROLL_KEY,window.scrollY)}catch(e){}
});

/* 侧边导航 */
var navbox=document.getElementById('navbox');
if(navbox&&window.NAV){
var curF=(location.pathname.split('/').pop()||'index.html');
var nh='';
/* 分类标题点击 → 展开/收起该分类的子目录，各分类状态独立并按库记忆 */
navbox.addEventListener('click',function(e){
var h=e.target.closest&&e.target.closest('.cat-h');
if(!h)return;
var cat=h.closest('.cat');if(!cat)return;
var open=!cat.classList.contains('open');
cat.classList.toggle('open',open);
if(cat.dataset.cat){catState[cat.dataset.cat]=open;saveCatState()}
});
/* 标签点击 → 过滤网格（再点同标签取消） */
navbox.addEventListener('click',function(e){
var tg=e.target.closest&&e.target.closest('a[data-tag]');
if(!tg)return;e.preventDefault();
tagFilter=(tagFilter===tg.dataset.tag)?'':tg.dataset.tag;
buildTagNav();
if(KIND==='fav')applyFavFilters();else applyGroupFilters();
});
if(KIND==='fav'){
/* 收藏页：目录条由收藏项动态生成，只列「实际有收藏」的目录 */
buildFavNav();
navbox.addEventListener('click',function(e){
var a=e.target.closest&&e.target.closest('a[data-g]');
if(!a)return;e.preventDefault();
favFilter=a.dataset.g||null;applyFavFilters();
});
}else{
var activeCat=null;
window.NAV.groups.forEach(function(g){g.items.forEach(function(it){if(it.f===curF)activeCat=g.c})});
if(curF==='index.html')nh+='<a class="nav-item on" href="index.html">&#9776; 目录总览</a>';
window.NAV.groups.forEach(function(g){
nh+=catHead(g.c,g.c,g.tc,catOpen(g.c,g.c===activeCat));
g.items.forEach(function(it){
nh+='<a class="nav-item'+(it.f===curF?' on':'')+'" href="'+it.f+'">'+esc(it.n)+'<em>'+it.k+'</em></a>';
});
nh+=CAT_END;
});
navbox.innerHTML=nh;
buildTagNav();
}
/* 侧栏滚动位置记忆：切页后停在原位，不自动跳 */
try{
var nsKey='cg_navscroll';
var nsY=parseInt(sessionStorage.getItem(nsKey)||'0')||0;
if(nsY>0)requestAnimationFrame(function(){navbox.scrollTop=nsY});
navbox.addEventListener('scroll',function(){
try{sessionStorage.setItem(nsKey,navbox.scrollTop)}catch(e){}
});
}catch(e){}
}
/* 视频播放器（B 站式控制条） */
var vlb=document.getElementById('vlb'),vPlayer=document.getElementById('vPlayer');
var vBar=document.getElementById('vBar'),vBarWrap=document.getElementById('vBarWrap');
var vPlay=document.getElementById('vPlay'),vTime=document.getElementById('vTime');
var vPrev=document.getElementById('vPrev'),vNext=document.getElementById('vNext');
var vRate=document.getElementById('vRate'),vMenu=document.getElementById('vMenu');
var vFull=document.getElementById('vFull'),vClose=document.getElementById('vClose');
var vName=document.getElementById('vName');
var vlist=[],vpos=-1,rate=1,hideT=null;
/* 播放位置记忆：按视频 rel 记录观看进度，下次打开自动续播（仅记 3s<t<d-3s，避免记忆"已看完"） */
var vposMap={};
try{vposMap=JSON.parse(localStorage.getItem('cg_vpos')||'{}')||{}}catch(e){vposMap={}}
function saveVpos(){
  if(vpos<0||!vlist[vpos])return;
  var rel=vlist[vpos];
  try{var t=vPlayer.currentTime||0,d=vPlayer.duration||0;
    if(d>0&&t>3&&t<d-3)vposMap[rel]=t;else delete vposMap[rel];
    localStorage.setItem('cg_vpos',JSON.stringify(vposMap));}catch(e){}
}
function applyVpos(){
  if(vpos<0||!vlist[vpos])return;
  var rel=vlist[vpos],t=vposMap[rel];
  if(t&&t>0){try{vPlayer.currentTime=t;
    if(vTime)vTime.textContent=fmt(t)+' / '+fmt(vPlayer.duration||0);
    toast('↺ 续播 '+fmt(t));}catch(e){}}
}
/* 目录页没有播放器 DOM（无 EXTRA 块）→ 必须判空，否则整段顶层代码从这里断掉，
   后面的 Ctrl+滚轮缩放 / Ctrl+0 全部注册不上（第二十五轮修复） */
if(vPlayer)vPlayer.addEventListener('loadedmetadata',applyVpos);
var RATES=[0.5,0.75,1,1.25,1.5,2];
try{rate=parseFloat(localStorage.getItem('cg_rate')||'1')||1}catch(e){}
function fmt(s){s=Math.floor(s||0);var m=Math.floor(s/60);var q=s%60;
return m+':'+(q<10?'0':'')+q}
function setRate(r){
rate=r;
try{vPlayer.playbackRate=r}catch(e){}
try{localStorage.setItem('cg_rate',r)}catch(e){}
if(vRate)vRate.textContent=r+'x';
if(vMenu)vMenu.querySelectorAll('button').forEach(function(b){
b.classList.toggle('on',parseFloat(b.dataset.r)===r);});
}
if(vMenu){
RATES.forEach(function(r){
var b=document.createElement('button');
b.textContent=r+'x';b.dataset.r=r;
if(r===rate)b.className='on';
b.onclick=function(){setRate(r);vMenu.classList.remove('open')};
vMenu.appendChild(b);});
}
function showUI(){
if(!vlb)return;
vlb.classList.add('show-ui');
clearTimeout(hideT);
hideT=setTimeout(function(){
if(!vPlayer.paused&&!(vMenu&&vMenu.classList.contains('open')))
vlb.classList.remove('show-ui');
},2400);
}
/* 播放/暂停图标：以 vPlayer 的媒体事件为唯一真相（按钮、空格、点画面、切集、播完都走这里），
   不再靠 onplay 里改 innerHTML——那样 pause/ended 之后图标永远停在暂停符号 */
function syncPlayIcon(){
if(!vPlay)return;
var on=!vPlayer.paused&&!vPlayer.ended;
vPlay.classList.toggle('playing',on);
vPlay.title=on?'暂停':'播放';}
function openVlb(rel){
vlist=items.filter(function(it){return it[3]===1}).map(function(it){return it[0]});
var np=vlist.indexOf(rel);
if(np<0)return;
/* 同一个视频已经在播：不重开（否则双击进全屏会把进度清零） */
if(vlb.classList.contains('open')&&np===vpos){showUI();return}
if(!vlb.classList.contains('open'))pageY=window.scrollY;
vpos=np;markRecent(rel);playV();vlb.classList.add('open');showUI();
}
/* 双击视频卡：直接进全屏播放（桌面双击 / 移动端双击即双击手势，见下方 touchend） */
function goFullV(){showUI();
if(!document.fullscreenElement&&vlb.requestFullscreen)vlb.requestFullscreen().catch(function(){})}
function playV(){
spriteRel=null;hideSprite();preloadSprite(vlist[vpos]);
vPlayer.src=encPath(vlist[vpos]);
setRate(rate);
try{vPlayer.play().catch(function(){})}catch(e){}
vPrev.disabled=vpos<=0;
vNext.disabled=vpos>=vlist.length-1;
if(vName)vName.textContent=vlist[vpos].split('/').pop()+'  ·  '+(vpos+1)+' / '+vlist.length;
vTime.textContent='0:00 / 0:00';
syncFavNav(vlist[vpos]);showUI();
}
function stepV(d){var n=vpos+d;if(n<0||n>=vlist.length)return;vpos=n;playV()}
function closeV(){
if(vpos>=0&&vlist[vpos]){markRecent(vlist[vpos]);saveVpos();}
var f=null;
if(vpos>=0&&vlist[vpos]&&grid){
f=grid.querySelector('figure.item[data-rel="'+vlist[vpos].replace(/"/g,'\\"')+'"]')}
vlb.classList.remove('open');vPlayer.pause();syncPlayIcon();hideSprite();
/* 全屏退出是异步的：先退全屏，等布局恢复再定位，否则 rect 全错 */
var wasFs=!!(document.fullscreenElement&&document.exitFullscreen);
if(wasFs)document.exitFullscreen().catch(function(){});
if(f){
if(wasFs){var h=function(){document.removeEventListener('fullscreenchange',h);scrollToFig(f)};
document.addEventListener('fullscreenchange',h);
setTimeout(function(){document.removeEventListener('fullscreenchange',h)},800);
}else scrollToFig(f);
}else window.scrollTo(0,pageY);
}
if(vlb){
vPlay.onclick=function(){vPlayer.paused?vPlayer.play():vPlayer.pause()};
vPrev.onclick=function(){stepV(-1)};
vNext.onclick=function(){stepV(1)};
vClose.onclick=closeV;
/* 连播/单曲循环：单按钮三态循环切换（关→连播→单曲循环），状态持久化（<key>_vplay） */
var vPM=document.getElementById('vPlayMode');
var vplayMode='off';
try{vplayMode=localStorage.getItem('cg_vplay')||
(localStorage.getItem('cg_vcont')==='1'?'cont':(localStorage.getItem('cg_vloop')==='1'?'loop':'off'))}catch(e){}
if(['off','cont','loop'].indexOf(vplayMode)<0)vplayMode='off';
var VLBL={off:'单集',cont:'连播',loop:'循环'};
function applyMode(){if(!vPM)return;
vPlayer.loop=(vplayMode==='loop');
vPM.textContent=VLBL[vplayMode];
vPM.classList.toggle('on',vplayMode!=='off');
vPM.title={off:'连播/循环：关（点击开启连播）',
cont:'连播：开（点击切换为单曲循环）',
loop:'单曲循环：开（点击关闭）'}[vplayMode]}
if(vPM){applyMode();
vPM.onclick=function(e){e.stopPropagation();
vplayMode=vplayMode==='off'?'cont':(vplayMode==='cont'?'loop':'off');
try{localStorage.setItem('cg_vplay',vplayMode)}catch(x){}applyMode()}}
vPlayer.addEventListener('ended',function(){
if(vplayMode==='cont'&&vpos<vlist.length-1)stepV(1)});
['play','playing','pause','ended','emptied','seeking','loadedmetadata'].forEach(function(n){
vPlayer.addEventListener(n,function(){syncPlayIcon();if(n==='play')showUI()})});
syncPlayIcon();
/* 双击视频画面 → 全屏切换；单击 → 播放/暂停（延迟 260ms 区分单双击） */
var vclickT=null;
vPlayer.addEventListener('click',function(e){e.stopPropagation();
if(vclickT){clearTimeout(vclickT);vclickT=null;
showUI();
if(!document.fullscreenElement){if(vlb.requestFullscreen)vlb.requestFullscreen().catch(function(){})}
else if(document.exitFullscreen)document.exitFullscreen().catch(function(){});
return}
vclickT=setTimeout(function(){vclickT=null;
vPlayer.paused?vPlayer.play():vPlayer.pause()},260)});
vPlayer.ontimeupdate=function(){
var d=vPlayer.duration||0,c=vPlayer.currentTime||0;
vBar.style.width=(d?c/d*100:0)+'%';
vTime.textContent=fmt(c)+' / '+fmt(d);
};
vBarWrap.onclick=function(e){
var r=vBarWrap.getBoundingClientRect();
var p=Math.max(0,Math.min(1,(e.clientX-r.left)/r.width));
if(vPlayer.duration)vPlayer.currentTime=vPlayer.duration*p;
};
/* 进度条帧预览：本地库没法用 canvas 抓帧（file:// 污染），改用 gen_sprites.py 预生成的
   「10 帧雪碧图」(_sprite/<名>.jpg，10×160×90)，悬停/拖动时按位置换 background-position。 */
var SPRITE_TILES=10;
var vSprite=document.getElementById('vSprite'),vSpriteT=document.getElementById('vSpriteT');
var spriteRel=null,spriteLoaded={};
function spriteURL(rel){
var i=rel.lastIndexOf('/'),dir=i<0?'':rel.slice(0,i)+'/';
return dir+'_sprite/'+encodeURIComponent(rel.slice(i+1).replace(/\.[^.]+$/,''))+'.jpg';}
function preloadSprite(rel){
var u=spriteURL(rel);if(u in spriteLoaded)return;
spriteLoaded[u]=null;
var im=new Image();
im.onload=function(){spriteLoaded[u]=true};
im.onerror=function(){spriteLoaded[u]=false};
im.src=u;}
function showSprite(e){
if(!vSprite||!vPlayer.duration)return;
var rel=vlist[vpos]||'',sp=spriteURL(rel);
if(spriteLoaded[sp]!==true){preloadSprite(rel);return}
var r=vBarWrap.getBoundingClientRect();
var p=Math.max(0,Math.min(0.999,(e.clientX-r.left)/r.width));
var idx=Math.floor(p*SPRITE_TILES);
if(spriteRel!==sp){spriteRel=sp;
vSprite.style.backgroundImage='url("'+sp+'")';
vSprite.style.backgroundSize=(160*SPRITE_TILES)+'px 90px';}
vSprite.style.backgroundPosition=(-idx*160)+'px 0';
vSprite.classList.add('on');
vSprite.style.left=Math.max(8,Math.min(innerWidth-170,r.left+r.width*p-80))+'px';
vSprite.style.top=Math.max(8,r.top-104)+'px';
if(vSpriteT)vSpriteT.textContent=fmt(vPlayer.duration*p);
}
function hideSprite(){if(vSprite)vSprite.classList.remove('on')}
vBarWrap.addEventListener('mousemove',showSprite);
vBarWrap.addEventListener('mouseleave',hideSprite);
vBarWrap.addEventListener('pointerdown',function(e){
showSprite(e);
var mv=function(ev){showSprite(ev)};
window.addEventListener('pointermove',mv);
window.addEventListener('pointerup',function(){window.removeEventListener('pointermove',mv);hideSprite()},{once:true});
});
vRate.onclick=function(e){e.stopPropagation();vMenu.classList.toggle('open');showUI()};
/* 音量：滑块拖动调节（0-100），图标随音量显示 🔇/🔉/🔊，状态存 <key>_vvol；
   旧版只有「点一下静音」，这里读不到 _vvol 时用旧的 _vmute 当初始值，保证设置不丢 */
var vVol=document.getElementById('vVol'),vVolIcon=document.getElementById('vVolIcon');
var vol=1;
try{
var _vv=localStorage.getItem('cg_vvol');
vol=(_vv===null||_vv==='')?((localStorage.getItem('cg_vmute')==='1')?0:1):parseFloat(_vv);
}catch(e){}
if(!isFinite(vol))vol=1;
function volGlyph(v){return v<=0.001?'&#128263;':(v<0.5?'&#128265;':'&#128266;')}
function applyVol(){if(!vVol)return;
vol=Math.max(0,Math.min(1,vol));
vPlayer.volume=vol;vPlayer.muted=vol<=0.001;
vVol.value=Math.round(vol*100);
vVol.style.setProperty('--vp',(vol*100)+'%');
if(vVolIcon)vVolIcon.innerHTML=volGlyph(vol);
vVol.title='音量 '+Math.round(vol*100)+'%'+(vol<=0.001?'（静音）':'');
vVol.setAttribute('aria-valuetext',Math.round(vol*100)+'%')}
if(vVol){applyVol();
vVol.addEventListener('input',function(e){
vol=parseInt(vVol.value,10)/100;applyVol();
try{localStorage.setItem('cg_vvol',String(vol))}catch(x){}showUI()});
/* 拖滑块别顺手触发播放器/画面上的其它点击逻辑 */
['click','pointerdown','mousedown'].forEach(function(n){
vVol.addEventListener(n,function(e){e.stopPropagation()})});
/* 滚轮在滑块上也能调音量（桌面小便利） */
vVol.addEventListener('wheel',function(e){e.preventDefault();e.stopPropagation();
vol=Math.max(0,Math.min(1,vol+(e.deltaY<0?0.05:-0.05)));applyVol();
try{localStorage.setItem('cg_vvol',String(vol))}catch(x){}},{passive:false});
}
/* 截图：抓当前帧存 PNG。
   file:// 下浏览器把本地视频判为跨源资源，canvas 会被污染、
   toBlob/toDataURL 抛 SecurityError（captureStream / VideoFrame 同样被拒），
   这不是 bug 而是安全策略 —— 这里做两件事：给出明确原因 + 引导用 http:// 打开。 */
var vShot=document.getElementById('vShot');
function shotName(){
var b=vlist[vpos].split('/').pop().replace(/\.[^.]+$/,'');
var t=Math.round(vPlayer.currentTime||0);
return b+'_'+Math.floor(t/60)+'m'+(t%60)+'s.png'}
function shotTipOnce(){
var m=document.getElementById('shotTip');if(!m)return;
m.classList.add('open');
var ok=document.getElementById('shotTipOk');
if(ok)ok.onclick=function(){m.classList.remove('open')};
m.onclick=function(e){if(e.target===m)m.classList.remove('open')}}
function shotFail(msg){
var tainted=/taint|security/i.test(msg);
toast(tainted?'截图失败：浏览器禁止读取本地视频画面（file:// 安全限制）':'截图失败：'+msg);
if(tainted)setTimeout(shotTipOnce,900)}
function shotFrame(){
if(!vPlayer.videoWidth){toast('画面还没解码出来，等一秒再点');return}
var c=document.createElement('canvas');
c.width=vPlayer.videoWidth;c.height=vPlayer.videoHeight;
var ctx=c.getContext('2d');
try{ctx.drawImage(vPlayer,0,0)}catch(x){shotFail(x.message);return}
var name=shotName();
function done(blob){
if(!blob){toast('截图失败：浏览器无法导出画面');return}
var url=URL.createObjectURL(blob);
var a=document.createElement('a');
a.href=url;a.download=name;
document.body.appendChild(a);a.click();a.remove();
setTimeout(function(){URL.revokeObjectURL(url)},15000);
toast('已截图：'+name)}
if(c.toBlob){try{c.toBlob(done,'image/png')}catch(x){shotFail(x.message)}}
else{try{var u=c.toDataURL('image/png');
var a2=document.createElement('a');a2.href=u;a2.download=name;
document.body.appendChild(a2);a2.click();a2.remove();toast('已截图：'+name)}
catch(x){shotFail(x.message)}}}
if(vShot){
vShot.onclick=function(e){e.stopPropagation();shotFrame()};
/* file:// 下必然失败，直接把按钮标题说清楚，别让人反复点 */
if(location.protocol==='file:')vShot.title='截图（file:// 下浏览器禁止读取视频画面，需用 http:// 打开）';
}
/* 画中画：不支持的环境自动隐藏 */
var vPip=document.getElementById('vPip');
if(vPip){
if('requestPictureInPicture' in HTMLVideoElement.prototype){
vPip.onclick=function(e){e.stopPropagation();
if(document.pictureInPictureElement){document.exitPictureInPicture().catch(function(){})}
else vPlayer.requestPictureInPicture().catch(function(){toast('无法进入画中画')})};
}else vPip.style.display='none'}
vFull.onclick=function(){
showUI();
if(!document.fullscreenElement){
if(vlb.requestFullscreen)vlb.requestFullscreen().catch(function(){});
}else if(document.exitFullscreen){document.exitFullscreen().catch(function(){})}
};
vlb.addEventListener('mousemove',showUI);
vlb.addEventListener('click',function(e){if(e.target===vlb)closeV()});
document.addEventListener('keydown',function(e){
if(!vlb.classList.contains('open'))return;
if(e.key==='Escape'){
if(document.fullscreenElement&&document.exitFullscreen){document.exitFullscreen();return}
closeV();return;
}
if(e.key==='ArrowLeft'){stepV(-1);return}
if(e.key==='ArrowRight'){stepV(1);return}
if(e.key===' '){e.preventDefault();vPlayer.paused?vPlayer.play():vPlayer.pause();return}
if(e.key==='f'||e.key==='F'){vFull.click();return}
});
}

/* 卡片悬停预览：鼠标移上去播，移开暂停并回到开头 */
if(grid){
grid.addEventListener('mouseover',function(e){
var f=e.target.closest&&e.target.closest('figure.item-v');
if(!f)return;
var v=f.querySelector('video');
if(!v||v.dataset.hov==='1')return;
v.dataset.hov='1';v.muted=true;
try{v.currentTime=0;v.play().catch(function(){})}catch(x){}
});
grid.addEventListener('mouseout',function(e){
var f=e.target.closest&&e.target.closest('figure.item-v');
if(!f)return;
if(e.relatedTarget&&f.contains(e.relatedTarget))return;
var v=f.querySelector('video');
if(!v)return;
v.dataset.hov='0';
try{v.pause();v.currentTime=0}catch(x){}
});
/* 双击视频卡 = 直接全屏播放（桌面 dblclick；移动端用 340ms 内的二次 tap 兜底，保证两端一致） */
grid.addEventListener('dblclick',function(e){
var f=e.target.closest&&e.target.closest('figure.item-v[data-rel]');
if(!f)return;
openVlb(f.dataset.rel);goFullV();
});
var vTapLast=0,vTapFig=null;
grid.addEventListener('touchend',function(e){
var f=e.target.closest&&e.target.closest('figure.item-v[data-rel]');
if(!f)return;
var now=Date.now();
if(vTapFig===f&&now-vTapLast<340){
vTapLast=0;vTapFig=null;e.preventDefault();
openVlb(f.dataset.rel);goFullV();
return}
vTapLast=now;vTapFig=f;
},{passive:false});
}

/* 分区独立缩放：Ctrl+滚轮，鼠标在哪边缩哪边 */
(function(){
var zn=1,zm=1;
try{zn=parseFloat(localStorage.getItem('cg_zn')||'1')||1}catch(e){}
try{zm=parseFloat(localStorage.getItem('cg_zm')||'1')||1}catch(e){}
var root=document.documentElement;
function applyZ(){root.style.setProperty('--z-nav',zn);root.style.setProperty('--z-main',zm)}
document.addEventListener('wheel',function(e){
if(!e.ctrlKey)return;
e.preventDefault();
var inNav=!!(e.target.closest&&e.target.closest('aside'));
var d=e.deltaY<0?0.05:-0.05;
if(inNav){
zn=Math.min(1.9,Math.max(0.8,zn+d));
try{localStorage.setItem('cg_zn',zn)}catch(x){}
}else{
zm=Math.min(2.4,Math.max(0.5,zm+d));
try{localStorage.setItem('cg_zm',zm)}catch(x){}
}
applyZ();
toast((inNav?'导航栏 ':'内容区 ')+Math.round((inNav?zn:zm)*100)+'%');
},{passive:false});
document.addEventListener('keydown',function(e){
if(e.ctrlKey&&(e.key==='0'||e.code==='Digit0')){
e.preventDefault();zn=1;zm=1;applyZ();
try{localStorage.setItem('cg_zn',1);localStorage.setItem('cg_zm',1)}catch(x){}
toast('两边已重置');
}
});
applyZ();
})();

render();
/* 深链：#open=<rel> 直接打开某张（总收藏 Hub 的卡片、随机看图都靠它）
   分批渲染，目标可能还没插入 DOM → 最多重试 ~12 次（4s） */
(function(){
var m=location.hash.match(/open=([^&]+)/);if(!m)return;
var rel=decodeURIComponent(m[1]);
if(!rel)return;
var tries=0;
(function find(){
if(!grid)return;
var f=null;
grid.querySelectorAll('figure.item[data-rel]').forEach(function(x){if(x.dataset.rel===rel)f=x});
if(f){
if(f.classList.contains('item-v'))openVlb(rel);else openLb(f);
history.replaceState&&history.replaceState(null,'',location.pathname);
return}
if(++tries>12)return;
setTimeout(find,320)})();
})();
})();
"""

def write(rel, txt):
    p = os.path.join(CG, rel)
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(txt)

write("assets/style.css", CSS)
JS_OUT = (JS.replace("cg_favs", KEY + "_favs").replace("cg_notes", KEY + "_notes")
          .replace("cg_zn", KEY + "_zn").replace("cg_zm", KEY + "_zm").replace("cg_rate", KEY + "_rate")
          .replace("cg_navscroll", KEY + "_navscroll").replace("cg_scroll", KEY + "_scroll")
          .replace("cg_recent", KEY + "_recent")
          .replace("cg_catopen", KEY + "_catopen").replace("cg_tags", KEY + "_tags")
          .replace("cg_dupv2", KEY + "_dupv2")
          .replace("cg_slide", KEY + "_slide")          .replace("cg_vloop", KEY + "_vloop")
          .replace("cg_vcont", KEY + "_vcont").replace("cg_vmute", KEY + "_vmute")
          .replace("cg_vplay", KEY + "_vplay").replace("cg_vpos", KEY + "_vpos")
          .replace("cg_vvol", KEY + "_vvol").replace("cg_lbhint", KEY + "_lbhint")
          .replace("cg_imgstate", KEY + "_imgstate"))
write("assets/app.js", JS_OUT)

# 资源指纹：file:// 下浏览器会缓存 css/js，改完不刷新看不到效果；按内容算版本号，改一次变一次
def _v(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:8]
CSS_V, JS_V = _v(CSS), _v(JS_OUT)

def finish(s):
    """填入资源指纹（在 nav.js 写完后调用）"""
    return (s.replace("__CV__", CSS_V).replace("__JV__", JS_V)
            .replace("__NV__", NAV_V).replace("__HUB__", HUB_LINK))

TPL = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__T__ · __N__ · SakuraView</title><link rel="stylesheet" href="assets/style.css?v=__CV__"></head><body>
<aside>
  <div class="brand"><div class="mark">&#127800; SakuraView</div><h1>__T__</h1><p>__SUB__</p>__HUB__</div>
  <div class="snav" id="navbox"></div>
</aside>
<div id="mainWrap">
<div class="navbar">
__BACK__
  <div class="crumb">__C__</div>
  <div class="spacer"></div>
  <a class="back" href="fav.html">&#9829; 收藏</a>
__SEARCH__
__CHIPS__
</div>
<div class="wrap">__BODY__</div>
</div>
__EXTRA__
<script src="assets/nav.js?v=__NV__"></script>
<script>window.PAGE=__DATA__;</script>
<script src="assets/app.js?v=__JV__"></script>
</body></html>"""

EXTRA = """<div class="vlb" id="vlb">
  <video id="vPlayer" playsinline></video>
  <div class="vtitle" id="vName"></div>
  <div class="vmenu" id="vMenu"></div>
  <div class="vsprite" id="vSprite"><i id="vSpriteT"></i></div>
  <div class="vui">
    <div class="vbarwrap" id="vBarWrap"><div class="vbar" id="vBar"></div></div>
    <div class="vrow">
      <button class="vi" id="vPrev" title="上一个">&#9198;</button>
      <button class="vi" id="vPlay" title="播放" aria-label="播放 / 暂停"><svg class="ic ic-play" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.2v13.6L19 12z"/></svg><svg class="ic ic-pause" viewBox="0 0 24 24" aria-hidden="true"><rect x="6.6" y="5.2" width="3.8" height="13.6" rx="1.1"/><rect x="13.6" y="5.2" width="3.8" height="13.6" rx="1.1"/></svg></button>
      <button class="vi" id="vNext" title="下一个">&#9197;</button>
      <span class="vtime" id="vTime">0:00 / 0:00</span>
      <div class="vspacer"></div>
      <button class="vi vrate" id="vRate" title="播放速度">1x</button>
      <button class="vi" id="vPlayMode" title="连播/循环：关（点击开启连播）">单集</button>
      <span class="vvol" id="vVolWrap">
        <span class="vvic" id="vVolIcon" aria-hidden="true">&#128266;</span>
        <input id="vVol" type="range" min="0" max="100" step="1" value="100" aria-label="音量">
      </span>
      <button class="vi" id="vShot" title="截图当前画面（PNG）">&#128247;</button>
      <button class="vi" id="vPip" title="画中画">&#10697;</button>
      <button class="vi" id="vFull" title="全屏">&#9974;</button>
      <button class="vi" id="vClose" title="关闭">&#10005;</button>
    </div>
  </div>
</div>
<div class="lb" id="lb">
  <div class="lb-bar"><b id="lbName"></b><span id="lbIdx"></span></div>
  <img id="lbImg" alt="">
  <div class="lb-acts">
    <button class="lb-act" id="lbFav">&#9825; 收藏</button>
    <button class="lb-act" id="lbRot" title="旋转 90°（R）">&#8635; 旋转</button>
    <span class="lbspd">
      <button class="lb-act" id="lbPlay" title="幻灯片放映（空格）">&#9654; 幻灯</button>
      <button class="lb-act lbcaret" id="lbSpd" title="放映速率"><span id="lbSpdMs">16ms</span> ▾</button>
    </span>
    <button class="lb-act" id="lbNote">&#128172; 备注</button>
  </div>
      <div class="spdmenu" id="spdMenu"></div>
  <button class="lb-btn lb-prev" id="lbPrev">&#8249;</button>
  <button class="lb-btn lb-next" id="lbNext">&#8250;</button>
  <button class="lb-close" id="lbClose">&#10005;</button>
</div>
<div class="selband" id="selBand"></div>
<div class="selbar" id="selBar">
  <b><span id="selN">0</span> 已选</b>
  <button id="selAll" title="选中当前筛选结果里的全部">全选</button>
  <button class="primary" id="selFav">&#9829; 收藏</button>
  <input id="selTag" placeholder="标签（空格分隔）" maxlength="80">
  <button id="selTagApply">加标签</button>
  <button id="selClear">清空</button>
</div>
<div class="modal" id="shotTip"><div class="modal-box">
  <h3>&#128247; 截图在 file:// 下用不了</h3>
  <p class="tip-p">浏览器把本地视频当成<b>跨源资源</b>，禁止把画面导出成图片（控制台会报
  <code>Tainted canvases may not be exported</code>）。这是安全策略，不是文件坏了，也不是按钮没接上。</p>
  <p class="tip-p">想用截图：在工具包目录跑一次 <code>python serve_site.py</code>，按提示用
  <code>http://127.0.0.1:8765/…</code> 打开图库——截图、画中画、播放位置记忆都会正常。</p>
  <div class="modal-acts"><button class="primary" id="shotTipOk">知道了</button></div>
</div></div>
<div class="modal" id="noteModal"><div class="modal-box">
  <h3>&#128172; 备注</h3>
  <img class="modal-thumb" id="modalThumb" alt="">
  <textarea id="noteInput" placeholder="给这张图写点什么…（最多 200 字）" maxlength="200"></textarea>
  <input id="tagInput" placeholder="标签（空格分隔，最多 8 个，如：名场面 海边）" maxlength="120">  <div class="modal-acts">
    <button class="danger" id="noteDel">删除</button>
    <button id="noteCancel">取消</button>
    <button class="primary" id="noteSave">保存</button>
  </div>
</div></div>
<div class="dupPanel" id="dupPanel"><div class="dp-box">
  <h4><span id="dpTitle">差分速览</span><span class="dp-close" id="dpClose">&#215;</span></h4>
  <div class="dp-sub" id="dpSub"></div>
  <div class="dp-grid" id="dpGrid"></div>
</div></div>"""

SEARCH_TPL = """  <div class="search">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#8892a6" stroke-width="2">
      <circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
    <input id="q" placeholder="__PH__" autocomplete="off" spellcheck="false">
  </div>"""
def search(ph="搜索文件名…"):
    return SEARCH_TPL.replace("__PH__", ph)
SEARCH_HTML = search()
# 收藏页专属：收藏 / 备注的导出导入
FAV_TOOLS = ('  <input type="file" id="impFile" accept=".json,application/json" hidden>\n'
             '  <a class="back" id="favRandom" title="从当前收藏里随机抽一张看">&#127922; 随机</a>\n'
             '  <a class="back" id="favGroup" title="按目录分组显示">&#9776; 分组</a>\n'
             '  <a class="back" id="expBtn" title="把收藏与备注导出为 JSON 文件">&#10515; 导出</a>\n'
             '  <a class="back" id="impBtn" title="从 JSON 文件导入收藏与备注">&#8679; 导入</a>')
BACK_LINK = '  <a class="back" href="index.html">&#8592; 目录</a>'

def _hub_rel(cg, maxup=5):
    """算「总收藏 Hub」相对本 CG 目录的路径；找不到返回空串（那就不渲染入口）。
       ① 先读同目录 hub_libs.json 的 output——图库不在 Hub 同级（放别的根/别的盘）也能算对；
       ② 兜底再从 CG 逐级往上找 SakuraView-hub.html（≤5 层）。"""
    cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hub_libs.json')
    try:
        with open(cfg, encoding='utf-8') as f:
            out = json.load(f).get('output', '')
        if out and os.path.exists(out):
            return os.path.relpath(out, os.path.abspath(cg)).replace('\\', '/')
    except Exception:
        pass
    d = os.path.abspath(cg)
    for n in range(1, maxup + 1):
        d2 = os.path.dirname(d)
        if not d2 or d2 == d:
            break
        d = d2
        if os.path.exists(os.path.join(d, 'SakuraView-hub.html')):
            return '../' * n + 'SakuraView-hub.html'
    return ''

HUB_REL = _hub_rel(CG)
HUB_LINK = ('  <a class="hublink" href="%s" title="跨库总收藏（Hub）">&#127800; 总收藏 · 全部图库</a>'
            % HUB_REL) if HUB_REL else ''
if HUB_REL:
    print("  Hub: %s" % HUB_REL)
SUB = "%d FILES · %d GROUPS" % (total, len(keys))

# ---------- 首页 ----------
cats = {}
for k in keys:
    cats.setdefault(buckets[k]["cat"], []).append(k)
# 章节型分类（「第12章」）按章序排在最前，其余分类（立绘、补丁…）保持原有顺序垫后
cats = dict(sorted(cats.items(), key=lambda kv: (
    0, float(re.fullmatch(r"第([\d.]+)章", kv[0]).group(1))
) if re.fullmatch(r"第[\d.]+章", kv[0]) else (1, 0)))
pos = {k: i + 1 for i, k in enumerate(keys)}

# 侧边导航数据
nav_groups = []
for cat, ks in cats.items():
    items = [{"n": k.split("/")[-1], "f": "p%02d.html" % pos[k], "k": len(buckets[k]["items"])} for k in ks]
    nav_groups.append({"c": cat, "tc": sum(i["k"] for i in items), "items": items})
NAV_OUT = "window.NAV=" + json.dumps({"groups": nav_groups}, ensure_ascii=False, separators=(",", ":")) + ";"
NAV_V = _v(NAV_OUT)
write("assets/nav.js", NAV_OUT)

blocks = []
for cat, ks in cats.items():
    tc = sum(len(buckets[k]["items"]) for k in ks)
    blocks.append('<div class="catblock"><div class="cat-title">%s <em>%d 组 / %d 张</em></div><div class="cards">'
                  % (html.escape(cat), len(ks), tc))
    for k in ks:
        b = buckets[k]
        short = k.split("/")[-1]
        cover = next((it[0] for it in b["items"] if it[3] == 0), None)
        trel = thumb_path(cover) if cover else None
        # 封面按真实方向给比例：竖图用 3:4，横图用 16:10，不再统统塞进 132px 里裁掉两边
        portrait = False
        if cover:
            cw, ch = img_size(os.path.join(CG, cover.replace("/", os.sep)))
            portrait = bool(cw and ch and ch > cw)
        if trel:
            # 目录页封面优先缩略图（208 张原图 ≈ 200MB+），缺失时 onerror 回退原图
            cov = ('<img class="cover" loading="lazy" src="%s" data-full="%s" alt="" '
                   'onerror="this.onerror=null;this.src=this.dataset.full">' % (enc(trel), enc(cover)))
        elif cover:
            cov = '<img class="cover" loading="lazy" src="%s" alt="">' % enc(cover)
        else:
            cov = '<div class="cover-ph">&#9654;</div>'
        blocks.append('<a class="card%s" href="%s">%s<div class="meta"><span class="nm">%s</span>'
                      '<span class="ct">%d</span></div></a>'
                      % (" tall" if portrait else "", "p%02d.html" % (keys.index(k) + 1),
                         cov, html.escape(short), len(b["items"])))
    blocks.append("</div></div>")

_idx_all = "%s 个文件 · %s 个分组 · 点击卡片进入" % (total, len(keys))
idx_body = ('<div class="mark-hero">&#127800; SakuraView</div>'
            '<h1 class="hero">%s</h1><div class="sub" id="isub" data-all="%s">%s</div>%s'
            % (html.escape(TITLE), html.escape(_idx_all), _idx_all, "".join(blocks)))
idx = (TPL.replace("__T__", html.escape(TITLE)).replace("__N__", "目录")
       .replace("__SUB__", SUB).replace("__BACK__", "").replace("__SEARCH__", search("搜索分组…"))
       .replace("__CHIPS__", "")
       .replace("__C__", "<b>目录</b>")
       .replace("__BODY__", idx_body).replace("__EXTRA__", "").replace("__DATA__", "{}"))
write("index.html", finish(idx))

# ---------- 分组页 ----------
for i, k in enumerate(keys):
    b = buckets[k]
    short = k.split("/")[-1]
    data = json.dumps({"items": b["items"]}, ensure_ascii=False, separators=(",", ":"))
    ctx = '<b>%s</b> / %s' % (html.escape(b["cat"]), html.escape(short))
    body = ('<div class="cat-title" style="margin-bottom:16px">%s <em>%d 个</em></div>'
            '<div class="masonry" id="grid"></div>' % (html.escape(short), len(b["items"])))
    has_v = any(it[3] == 1 for it in b["items"])
    # 这一页有多少「含差分的组」，有才显示开关
    _dup = collections.Counter(base_of(it[0]) for it in b["items"])
    n_dup = sum(1 for v in _dup.values() if v > 1)
    chips = ('<div class="chips" id="orientChips">'
             '<a class="chip on" data-o="">全部</a><a class="chip" data-o="l">横图</a>'
             '<a class="chip" data-o="p">竖图</a>'
             + ('<a class="chip" data-o="v">视频</a>' if has_v else '')
             + (('<a class="chip" id="dupChip" title="默认把同一场景的差分叠成一张；点这里展开成平铺">'
                 '叠起差分 %d 组</a>' % n_dup) if n_dup else '')
             + '</div>')
    h = (TPL.replace("__T__", html.escape(TITLE)).replace("__N__", html.escape(short))
         .replace("__SUB__", SUB).replace("__BACK__", BACK_LINK).replace("__SEARCH__", SEARCH_HTML)
         .replace("__CHIPS__", chips)
         .replace("__C__", ctx).replace("__BODY__", body)
         .replace("__EXTRA__", EXTRA).replace("__DATA__", data))
    write("p%02d.html" % (i + 1), finish(h))

# ---------- 收藏页 ----------
# 倒序：最近收藏排最前（与 v4 独立收藏视图一致）
fav_data = ("(function(){var o=[];try{o=JSON.parse(localStorage.getItem('" + KEY + "_favs')||'[]')}"
            "catch(e){}return {items:o.slice().reverse().map(function(r){"
            "var v=/\\.(mp4|webm|ogv|mkv)$/i.test(r);return [r,0,0,v?1:0]})}})()")
fav_body = ('<h1 class="hero">我的收藏</h1><div class="sub" id="fsub">读取中…</div>'
            '<div class="cat-title" style="margin:16px 0">收藏夹 <em id="fcnt">0</em></div>'
            '<div class="masonry" id="grid"></div>'
            '<div class="empty" id="favEmpty" style="display:none">'
            '<div class="big">&#9825;</div><b>还没有收藏</b>'
            '<span>在任意分组页把鼠标移到图上，点左上角的 ♡</span></div>')
# 数量直接取 PAGE.items 长度：分批渲染时数 DOM 会漏掉未插入的批次
fav_stat = """<script>document.addEventListener('DOMContentLoaded',function(){
var n=(window.PAGE&&window.PAGE.items)?window.PAGE.items.length:0;
var c=document.getElementById('fcnt');if(c)c.textContent=n;
var s=document.getElementById('fsub');
if(s)s.textContent=n?('共 '+n+' 个收藏 · 最近收藏在最前'):'还没有收藏，回目录挑几张点 ♡';
var em=document.getElementById('favEmpty');if(em)em.style.display=n?'none':'';});</script>"""
fav = (TPL.replace("__T__", html.escape(TITLE)).replace("__N__", "我的收藏")
       .replace("__SUB__", SUB).replace("__BACK__", BACK_LINK)
       .replace("__SEARCH__", search("搜索收藏…") + FAV_TOOLS)
       .replace("__CHIPS__", "")
       .replace("__C__", "<b>收藏</b> / 全部").replace("__BODY__", fav_body)
       .replace("__EXTRA__", EXTRA + fav_stat).replace("__DATA__", fav_data))
write("fav.html", finish(fav))

# ---------- 清理孤儿页：组数变少后旧的 pNN.html 不能留 ----------
_n = len(keys)
for _f in os.listdir(CG):
    if re.fullmatch(r"p\d+\.html", _f) and int(_f[1:-5]) > _n:
        try:
            os.remove(os.path.join(CG, _f))
            print("清理孤儿页:", _f)
        except OSError:
            pass

print("OK ->", CG)
print("  index.html + %d 页 + fav.html + assets/" % len(keys))
