# -*- coding: utf-8 -*-
"""通用整理器：extracted\\ → CG\\<分类>\\<分组>\\*

用法: python build_jing.py <key> [--dry]
  第二种用法：python build_jing.py --dir "游戏目录" [--key mykey]

两条路线：① 认得出目录名就按角色/章节归类；② 一个都认不出就按「目录即分类」兜底。
  · 任意 data*\\...\\画像\\<子目录>\\*  → CG\\CG图\\<子目录>\\*      （跳过 movie 子目录，视频单独收）
  · 任意 data*\\...\\立ち絵\\*.png        → CG\\立绘\\<角色>\\*        （角色 = 文件名第一个 _ 之前）
  · 任意 data*\\...\\face\\*.png          → CG\\头像\\<角色>\\*
  · 全库 *.ogv（排除 thumbnail）          → CG\\动画\\全部\\*
  · 剔除：thumbnail / system / avg / script / misc / 音楽 / 効果音 / fade / 语音
"""
import os, re, sys, glob, shutil
from collections import Counter

def _games_from_libs():
    """游戏目录不写死在代码里：从 my_libs.json 的 CG 路径往上推一级（CG 就在游戏根下）。
       这样 `python build_jing.py <key>` 依然能用，仓库里却不留任何私人路径。"""
    import json
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        libs = json.load(open(os.path.join(here, 'my_libs.json'), encoding='utf-8'))
    except Exception:
        return {}
    out = {}
    for k, v in libs.items():
        cg = os.path.dirname(os.path.normpath(v[0]))    # 游戏目录\CG -> 游戏目录
        if os.path.isdir(cg):
            out[k] = cg
    return out


GAMES = _games_from_libs()
IMG = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif')
VID = ('.ogv', '.webm', '.mp4', '.mkv')
SKIP_DIR = {'thumbnail', 'system', 'avg', 'script', 'scenario', 'misc', '音楽', '効果音',
            'fade', 'ボイス', 'voice', 'se', 'bgm'}


def find_extracted(top):
    """这些包解压后是「同名目录套同名目录」，extracted 的位置不固定，直接找"""
    hits = []
    for dp, dns, fns in os.walk(top):
        if os.path.basename(dp).lower() == 'extracted':
            hits.append(dp)
            dns[:] = []
    return hits[0] if hits else None


def mk(p):
    os.makedirs(p, exist_ok=True)


def cg_group(fn, sub):
    """事件 CG 的分组名：有子目录就用子目录；平铺的（镜1）按文件名前缀切
       n01_xxx → 第01章；0_xxx（背景图）→ 背景；其余 → 其它"""
    if sub:
        return sub
    m = re.match(r'^n(\d+)', fn, re.I)
    if m:
        return '第%02d章' % int(m.group(1))
    if re.match(r'^0_|^bg', fn, re.I):
        return '背景'
    return '其它'


def plan_files(src, out):
    """扫描解包目录，产出 [(源文件, 目标目录)]。oneclick.py 也用它。"""
    plan = []

    for dp, dns, fns in os.walk(src):
        parts = os.path.relpath(dp, src).split(os.sep)
        low = [x.lower() for x in parts]
        if any(x in SKIP_DIR for x in low):
            dns[:] = []
            continue
        # 事件 CG：不同代叫法不同 —— 镜3/4 是「画像」，镜1/2 是「image」
        cg_idx = next((i for i, x in enumerate(parts) if x in ('画像', 'image', 'images')), None)
        if cg_idx is not None:
            sub = parts[cg_idx + 1] if len(parts) > cg_idx + 1 else ''
            if sub.lower() == 'movie':
                continue
            for fn in fns:
                if os.path.splitext(fn)[1].lower() in IMG:
                    plan.append((os.path.join(dp, fn),
                                 os.path.join(out, 'CG图', cg_group(fn, sub))))
            continue
        # 立绘 / 头像：镜3/4 是「立ち絵」「face」，镜1/2 是「charaimage」「charaface」
        for cat, names in (('立绘', ('立ち絵', '立ち绘', 'charaimage', 'chara')),
                           ('头像', ('face', 'charaface'))):
            if any(n in parts for n in names):
                for fn in fns:
                    if os.path.splitext(fn)[1].lower() not in IMG:
                        continue
                    ch = fn.split('_')[0] if '_' in fn else 'その他'
                    plan.append((os.path.join(dp, fn), os.path.join(out, cat, ch)))
                break

    # 视频：ogv/webm/mp4/mkv 全收（thumbnail 目录已跳过）
    vids = []
    for dp, dns, fns in os.walk(src):
        if 'thumbnail' in [x.lower() for x in dp.split(os.sep)]:
            continue
        for fn in fns:
            if os.path.splitext(fn)[1].lower() in VID:
                vids.append((os.path.join(dp, fn), os.path.join(out, '动画', '全部')))
    plan.extend(vids)

    # 兜底：上面的规则只认日式视觉小说常见的那几套目录名，遇到别的游戏可能只收到视频、一张图都没有。
    # 只要「一张图都没匹配上」就整盘按「目录即分类」重收：<首层目录>\<次层目录>\*.png|webp|...
    if not any(os.path.splitext(s0)[1].lower() in IMG for s0, _ in plan):
        plan = generic_plan(src, out)
    return plan


def generic_plan(src, out):
    """通用兜底：不猜语义，直接按目录结构分成 分类/分组。"""
    plan = []
    for dp, dns, fns in os.walk(src):
        low = [x.lower() for x in os.path.relpath(dp, src).split(os.sep)]
        if any(x in SKIP_DIR for x in low):
            dns[:] = []
            continue
        rel = os.path.relpath(dp, src)
        segs = [] if rel == '.' else rel.split(os.sep)
        cat = segs[0] if segs else '素材'
        grp = segs[1] if len(segs) > 1 else '全部'
        for fn in fns:
            ext = os.path.splitext(fn)[1].lower()
            if ext in IMG:
                plan.append((os.path.join(dp, fn), os.path.join(out, cat, grp)))
            elif ext in VID:
                plan.append((os.path.join(dp, fn), os.path.join(out, '动画', grp)))
    return plan


def organize(src, out, dry=False):
    """清理旧分类目录后按规则落盘；返回 plan"""
    keep = {'assets', '_poster', '_thumbs', '_sprite'}
    plan = plan_files(src, out)
    cnt = Counter()
    for _, d in plan:
        cnt[os.path.relpath(d, out)] += 1
    for k in sorted(cnt):
        print('  %-24s %5d' % (k, cnt[k]))
    print('  合计 %d 个文件' % len(plan))
    if dry:
        return plan
    if os.path.isdir(out):
        for d in os.listdir(out):
            if os.path.isdir(os.path.join(out, d)) and d not in keep:
                shutil.rmtree(os.path.join(out, d))
    for s, d in plan:
        mk(d)
        shutil.copy2(s, os.path.join(d, os.path.basename(s)))
    print('已写入', out)
    return plan


def build(key, dry=False):
    top = GAMES[key]
    src = find_extracted(top)
    if not src:
        print('!! 没找到 extracted 目录:', top)
        return
    return organize(src, os.path.join(top, 'CG'), dry)


if __name__ == '__main__':
    dry = '--dry' in sys.argv
    argv = sys.argv[1:]
    # 用法1：python build_jing.py --dir "D:\game\某游戏" [--key mykey]
    if '--dir' in argv:
        top = argv[argv.index('--dir') + 1]
        key = argv[argv.index('--key') + 1] if '--key' in argv else os.path.basename(os.path.normpath(top))
        print('==', key, top)
        src = find_extracted(top)
        if not src:
            print('!! 没找到 extracted 目录（先解包，产物放 <游戏目录>\\extracted）')
            raise SystemExit(3)
        organize(src, os.path.join(top, 'CG'), dry)
        raise SystemExit(0)
    # 用法2：python build_jing.py <key> [--dry]，key 来自 my_libs.json
    args = [a for a in argv if not a.startswith('--')]
    if not args:
        print(__doc__ or '用法: python build_jing.py <key> | --dir <游戏目录>')
        print('已登记的 key:', ', '.join(sorted(GAMES)) or '（无，先建 my_libs.json）')
        raise SystemExit(2)
    for k in args:
        if k not in GAMES:
            print('!! 没登记过这个 key:', k, '（可用:', ', '.join(sorted(GAMES)), '）')
            continue
        print('==', k)
        build(k, dry)
