# -*- coding: utf-8 -*-
"""图库自检：对照工作流 §5 验收清单做机器可核对的部分
用法: python verify_libs.py [key ...] [--videos]   # 缺省校验 rebuild_all.LIBS 里全部库
检查项:
  1) index.html / fav.html / assets/{style.css,app.js,nav.js} 齐全
  2) nav.js 的条目数与实际文件数一致（按生成器扫描口径：两级目录、跳过 _ 开头与 _thumbs/_poster）
  3) 每个分组页 PAGE.items 里的文件全部存在（不是 404 / 裂图）
  4) 有视频的分组：_poster 海报帧齐全
  5) 有缩略图时：_thumbs 覆盖率（缺了会回退原图，只报告不判失败）
  6) --videos：逐个视频用 ffmpeg 探一次，码流损坏（moov atom not found）/ 编码浏览器不吃 → 判失败
     （默认不跑：全库 ~3000 个视频约 1 分钟。缺海报只是症状，坏文件才是根因，这类问题只有它能抓到）
"""
import os, re, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from rebuild_all import all_libs

LIBS = all_libs()

try:                       # --videos 深度体检用；缺 ffmpeg 时自动跳过
    from convert_webvideo import playable as _playable
except Exception:
    _playable = None

IMG = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
VID = (".ogv", ".webm", ".mp4", ".mkv")
DEEP = False           # --videos 深度体检（在 __main__ 里设置）


def scan_files(cg):
    out = set()
    for dp, dns, fns in os.walk(cg):
        dns[:] = [d for d in dns if d not in ("assets", "_poster", "_thumbs", "_sprite")]
        for fn in fns:
            ext = os.path.splitext(fn)[1].lower()
            if fn.startswith("_") or ext not in IMG + VID:
                continue
            rel = os.path.relpath(os.path.join(dp, fn), cg).replace("\\", "/")
            if ext == ".ogv" and os.path.exists(os.path.join(cg, rel[:-4] + ".mp4")):
                continue
            out.add(rel)
    return out


def check(key):
    cg, name = LIBS[key]
    problems, notes = [], []
    if not os.path.isdir(cg):
        return ['目录不存在: %s' % cg], []
    for f in ("index.html", "fav.html", "assets/style.css", "assets/app.js", "assets/nav.js"):
        if not os.path.exists(os.path.join(cg, f)):
            problems.append('缺文件 %s' % f)
    nav = {}
    try:
        txt = open(os.path.join(cg, "assets", "nav.js"), encoding="utf-8").read()
        nav = json.loads(re.search(r"window\.NAV=(\{.*\});", txt, re.S).group(1))
    except Exception as e:
        problems.append('nav.js 解析失败 %s' % e)

    real = scan_files(cg)
    navk = sum(int(i["k"]) for g in nav.get("groups", []) for i in g.get("items", []))
    if navk != len(real):
        problems.append('nav 计数 %d ≠ 实际文件 %d' % (navk, len(real)))

    pages = [f for f in os.listdir(cg) if re.fullmatch(r"p\d+\.html", f)]
    ng = sum(len(g.get("items", [])) for g in nav.get("groups", []))
    if len(pages) != ng:
        problems.append('分组页 %d ≠ 分组数 %d' % (len(pages), ng))

    missing, vids, posters, thumb_ok, thumb_need = 0, 0, 0, 0, 0
    vpaths = []
    # 逐页读 PAGE.items，核对文件与海报/缩略图
    for f in sorted(pages):
        html = open(os.path.join(cg, f), encoding="utf-8").read()
        m = re.search(r"window\.PAGE=(\{.*?\});</script>", html, re.S)
        if not m:
            problems.append('%s 无 PAGE 数据' % f)
            continue
        try:
            items = json.loads(m.group(1)).get("items", [])
        except Exception:
            problems.append('%s PAGE JSON 解析失败' % f)
            continue
        for rel, w, h, isv in items:
            p = os.path.join(cg, rel.replace("/", os.sep))
            if not os.path.exists(p):
                missing += 1
                continue
            if isv:
                vids += 1
                vpaths.append(p)
                d, b = os.path.split(p)
                if not os.path.exists(os.path.join(d, "_poster", os.path.splitext(b)[0] + ".jpg")):
                    posters += 1
            else:
                thumb_need += 1
                d, b = os.path.split(p)
                if os.path.exists(os.path.join(d, "_thumbs", os.path.splitext(b)[0] + ".jpg")):
                    thumb_ok += 1
    if missing:
        problems.append('页面引用了不存在的文件 %d 个（裂图）' % missing)
    if posters:
        notes.append('缺海报帧 %d / %d 个视频' % (posters, vids))
    if thumb_need:
        notes.append('缩略图 %d / %d（%.0f%%）' % (thumb_ok, thumb_need, 100.0 * thumb_ok / thumb_need))
    # 浏览器放不了 .ogv（Theora）——只看 ffmpeg 能不能解会漏判，这里单列一条
    ogv_only = [p for p in vpaths if p.lower().endswith('.ogv')
                and not os.path.exists(os.path.splitext(p)[0] + '.mp4')]
    if ogv_only:
        problems.append('%d 个视频只有 .ogv 没有转 mp4，浏览器里放不了（先跑 convert_ogv.py）' % len(ogv_only))
    if DEEP and vpaths:
        bad = probe_videos(vpaths)
        if bad:
            problems.append('视频 %d 个打不开（占 %d）' % (len(bad), vids))
            for p, why in bad[:3]:
                notes.append('坏视频 %s — %s' % (os.path.relpath(p, cg).replace(chr(92), '/'), why))
        else:
            notes.append('视频可播性 %d / %d 正常' % (vids, vids))
    idx_p = os.path.join(cg, 'index.html')
    if os.path.exists(idx_p):
        try:
            if 'class="hublink"' not in open(idx_p, encoding='utf-8').read():
                notes.append('目录页没有「总收藏」入口（生成时没探测到常驻 Hub，或 Hub 当时还没生成）')
        except OSError:
            pass
    return problems, notes


def probe_videos(paths):
    """--videos：逐个探测可播性；返回 [(path, 原因)]。码流损坏时 playable 会得到 codec='?'"""
    if _playable is None:
        return []
    from concurrent.futures import ThreadPoolExecutor

    def one(p):
        try:
            ok, why = _playable(p)
        except Exception as e:
            return p, '探测失败 %s' % e
        return None if ok else (p, why)

    bad = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for r in ex.map(one, paths):
            if r:
                bad.append(r)
    return bad


def check_hub():
    """总收藏 Hub：hub_libs.json 存在、输出的 html 已生成且内含每个库的 key"""
    cfg = os.path.join(HERE, 'hub_libs.json')
    if not os.path.exists(cfg):
        return ['缺 hub_libs.json（Hub 无法重建）'], []
    try:
        c = json.load(open(cfg, encoding='utf-8'))
    except Exception as e:
        return ['hub_libs.json 解析失败 %s' % e], []
    out = c.get('output', '')
    if not (out and os.path.exists(out)):
        return ['Hub 未生成: %s' % (out or '(未配置 output)')], []
    html = open(out, encoding='utf-8').read()
    keys = [L.get('key') for L in c.get('libs', [])]
    miss = [k for k in keys if '"%s"' % k not in html]
    probs = ['Hub 里缺库: %s' % ', '.join(miss)] if miss else []
    extra = [k for k in LIBS if k not in keys]
    notes = ['Hub 未登记（可补 hub_libs.json）: %s' % ', '.join(extra)] if extra else []
    return probs, notes


if __name__ == "__main__":
    DEEP = "--videos" in sys.argv
    keys = [a for a in sys.argv[1:] if not a.startswith("--")] or list(LIBS)
    bad = 0
    for k in keys:
        pr, nt = check(k)
        status = 'OK  ' if not pr else 'FAIL'
        if pr:
            bad += 1
        print('%s %-18s %s' % (status, k, '; '.join(pr) if pr else '通过'))
        for n in nt:
            print('       · %s' % n)
    print('—' * 60)
    hp, hn = check_hub()
    print('%s %-18s %s' % ('OK  ' if not hp else 'FAIL', 'hub',
                           '; '.join(hp) if hp else '总收藏页已生成，含全部登记库'))
    for n in hn:
        print('       · %s' % n)
    print('—' * 60)
    print('%d / %d 个库通过%s' % (len(keys) - bad, len(keys), '' if not hp else ' · Hub 有问题'))
    sys.exit(1 if (bad or hp) else 0)
