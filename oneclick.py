# -*- coding: utf-8 -*-
"""SakuraView 一键处理：把一个游戏目录（或已经解好的素材目录）变成能双击浏览的图库

用法:
  python oneclick.py <目录> [选项]
     --name "标题"    默认用目录名
     --key  key      默认从目录名生成（非 ASCII 时用 lib+哈希）
     --out  目录     默认 <目录>\\CG
     --no-extract    跳过解包（目录里已经有 extracted 时用）
     --no-media      跳过 ogv 转码 / 海报 / 雪碧图 / 缩略图（只出页面）
     --no-hub        不登记总收藏 Hub
     --no-open       结束时不自动打开浏览器
     --dry           只打印计划，不动文件

流程:
  1) 识别引擎：QLIE(FilePackVer3.0/3.1) / Ren'Py(*.rpa) / Godot(*.pck) / Unity(*_Data)
  2) 解包到 <游戏>\\extracted
  3) 按「分类/分组」整理成 <out>\\CG图|立绘|头像|动画
  4) gen_site_generic 建站（index.html + pNN.html + fav.html + assets/）
  5) 视频转 mp4、抽海报帧、生成雪碧图、生成缩略图
  6) 写进 hub_libs.json 并重建 Hub，最后打开浏览器
"""
import os, sys, glob, json, time, hashlib, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
def script(n):
    return os.path.join(HERE, n)


LOG_FP = None


def say(msg):
    print(msg, flush=True)
    if LOG_FP:
        try:
            LOG_FP.write(msg + '\n')
            LOG_FP.flush()
        except Exception:
            pass


def run(args, quiet=False):
    """跑子脚本；返回 (ok, 最后一行输出)"""
    r = subprocess.run([PY] + args, capture_output=True, text=True, errors='replace')
    out = r.stdout.strip().splitlines()
    tail = out[-1] if out else (r.stderr.strip().splitlines() or [''])[-1]
    if not quiet:
        say('    ' + tail[:160])
    return r.returncode == 0, tail


# ---------- 引擎识别 ----------
def pack_version(pack):
    try:
        sz = os.path.getsize(pack)
        with open(pack, 'rb') as f:
            f.seek(sz - 28)
            sig = f.read(16)
        if b'FilePackVer3.1' in sig:
            return 'qlie31'
        if b'FilePackVer3.0' in sig:
            return 'qlie30'
    except OSError:
        pass
    return None


def find_gamedata(d, depth=4):
    """游戏目录常常外面还套一两层同名文件夹，往下找 GameData"""
    base = os.path.abspath(d)
    for root, dirs, files in os.walk(base):
        if root.count(os.sep) - base.count(os.sep) >= depth:
            dirs[:] = []
            continue
        for name in dirs:
            if name.lower() == 'gamedata':
                cand = os.path.join(root, name)
                if glob.glob(os.path.join(cand, '*.pack')):
                    return cand
    return None


def detect(d):
    """返回 (引擎, 说明, 解包需要的主路径)"""
    gd = os.path.join(d, 'GameData')
    if not os.path.isdir(gd):
        gd = find_gamedata(d)
    if gd and os.path.isdir(gd):
        packs = sorted(glob.glob(os.path.join(gd, '*.pack')))
        if packs:
            vers = {pack_version(p) for p in packs}
            if 'qlie31' in vers:
                return 'qlie31', 'QLIE FilePackVer3.1（%d 个包）' % len(packs), gd
            if 'qlie30' in vers:
                return 'qlie30', 'QLIE FilePackVer3.0（%d 个包）' % len(packs), gd
    rpas = glob.glob(os.path.join(d, '**', '*.rpa'), recursive=True)
    if rpas:
        return 'renpy', "Ren'Py 归档（%d 个 .rpa）" % len(rpas), rpas
    pcks = glob.glob(os.path.join(d, '**', '*.pck'), recursive=True)
    if pcks:
        return 'godot', 'Godot PCK（%d 个）' % len(pcks), pcks
    for x in os.listdir(d):
        p = os.path.join(d, x)
        if os.path.isdir(p) and x.lower().endswith('_data'):
            return 'unity', 'Unity（%s）' % x, p
    return 'images', '没有找到打包文件，按「已经解好的素材目录」处理', d


# ---------- 解包 ----------
def unpack(engine, src, out):
    if engine == 'qlie31':
        return run([script('extract_imoscripter.py'), src, out, '--dpng'])
    if engine == 'qlie30':
        return run([script('extract_qlie30.py'), src, out, '--dpng', '--skip-audio'])
    if engine == 'renpy':
        ok_all = True
        for rpa in src:
            ok, _ = run([script('extract_rpa.py'), rpa, out])
            ok_all = ok_all and ok
        return ok_all, 'renpy 批量'
    if engine == 'godot':
        ok_all = True
        for pck in src:
            ok, _ = run([script('extract_pck.py'), pck, out, '--images-only'])
            ok_all = ok_all and ok
        return ok_all, 'godot 批量'
    if engine == 'unity':
        exe = find_assetstudio()
        if not exe:
            say('    Unity 资源要先导出纹理：把 AssetStudioModCLI 放到 tools\\ 或 SakuraView-tools\\ 下再跑，')
            say('    或手动执行：AssetStudioModCLI "<Data目录>" -t texture2d -g container --image-format jpg -o <输出>')
            return False, 'unity 缺 AssetStudio'
        run([exe, src, '-t', 'texture2d', '-g', 'container',
             '--image-format', 'jpg', '-o', out])
        return True, 'unity/AssetStudio'
    return True, '不需要解包'


# ---------- 工具 ----------
def auto_key(d):
    base = os.path.basename(os.path.abspath(d).rstrip('\\/'))
    a = ''.join(ch for ch in base.lower() if ch.isascii() and ch.isalnum())
    if len(a) >= 3:
        return a[:20]
    return 'lib' + hashlib.md5(base.encode('utf-8')).hexdigest()[:6]


def auto_title(d):
    base = os.path.basename(os.path.abspath(d).rstrip('\\/'))
    return base.strip(' -_') or 'Untitled'


def find_assetstudio():
    """本包自带 AssetStudioModCLI（在 SakuraView-tools 下），也允许放 tools 下"""
    pats = ['AssetStudioModCLI*' + os.sep + '**' + os.sep + 'AssetStudioModCLI.exe',
            'AssetStudioModCLI.exe']
    for base in (os.path.join(HERE, 'tools'), os.path.join(HERE, 'SakuraView-tools'),
                 HERE, os.path.dirname(HERE)):
        for pat in pats:
            hits = glob.glob(os.path.join(base, pat), recursive=True)
            if hits:
                return hits[0]
    return None


def find_extracted(d):
    for dp, dns, fns in os.walk(d):
        if os.path.basename(dp).lower() == 'extracted':
            return dp
    return None


def register_lib(key, title, cg):
    """把新库写进 libs_extra.json —— rebuild_all / verify_libs 会自动读它，不用手改 .py"""
    path = script('libs_extra.json')
    try:
        data = json.load(open(path, encoding='utf-8'))
    except Exception:
        data = {}
    if data.get(key) and data[key][0] == cg:
        return 'libs_extra.json 里已有 %s（不用再登记）' % key
    data[key] = [cg, title]
    json.dump(data, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    return '已写入 libs_extra.json（下次 rebuild_all 会带上它）'


def register_hub(key, title, cg):
    cfg = script('hub_libs.json')
    try:
        data = json.load(open(cfg, encoding='utf-8'))
    except Exception:
        # 没登记表时的默认位置：CG 的上一级（也就是游戏目录）旁边，不写死任何盘符
        data = {'output': os.path.join(os.path.dirname(os.path.normpath(cg)), 'SakuraView-hub.html'),
                'libs': []}
    if any(L.get('key') == key for L in data['libs']):
        return 'Hub 里已有 %s，跳过登记' % key
    out_dir = os.path.dirname(data.get('output', ''))
    try:
        base = os.path.relpath(cg, out_dir).replace('\\', '/')
    except ValueError:
        base = cg.replace('\\', '/')
    data['libs'].append({'name': title, 'base': base, 'key': key})
    json.dump(data, open(cfg, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    return 'Hub 已登记 %s → %s' % (key, base)


def self_check(cg):
    """轻量自检：入口/页面数/图片数/缩略图覆盖率"""
    import re
    pages = [f for f in os.listdir(cg) if re.fullmatch(r'p\d+\.html', f)] if os.path.isdir(cg) else []
    keep = {'assets', '_poster', '_thumbs', '_sprite'}
    imgs = thumbs = 0
    for dp, dns, fns in os.walk(cg):
        dns[:] = [d for d in dns if d not in keep]
        for fn in fns:
            if os.path.splitext(fn)[1].lower() in ('.png', '.jpg', '.jpeg', '.webp', '.bmp'):
                imgs += 1
    for dp, dns, fns in os.walk(cg):
        if os.path.basename(dp) == '_thumbs':
            thumbs += len(fns)
    ok = os.path.exists(os.path.join(cg, 'index.html')) and pages and imgs
    say('    %s  %d 页 / %d 张图 / 缩略图 %d（%.0f%%）' % (
        'OK' if ok else 'FAIL', len(pages), imgs, thumbs, 100.0 * thumbs / imgs if imgs else 0))
    return ok


if __name__ == '__main__':
    argv = sys.argv[1:]
    pos = [a for a in argv if not a.startswith('--')]
    flags = [a for a in argv if a.startswith('--')]

    def opt(name, default=None):
        if name in argv:
            i = argv.index(name)
            return argv[i + 1] if i + 1 < len(argv) else default
        return default

    if not pos:
        print(__doc__)
        sys.exit(1)
    game = os.path.abspath(pos[0])
    if not os.path.isdir(game):
        say('不是目录：%s' % game)
        sys.exit(1)
    title = opt('--name') or auto_title(game)
    key = opt('--key') or auto_key(game)
    cg = os.path.abspath(opt('--out') or os.path.join(game, 'CG'))
    dry = '--dry' in flags

    os.makedirs(os.path.join(HERE, 'logs'), exist_ok=True)
    LOG_FP = open(os.path.join(HERE, 'logs', 'oneclick-%s.log' % time.strftime('%Y%m%d-%H%M%S')),
                  'w', encoding='utf-8')
    say('== SakuraView 一键处理 %s' % time.strftime('%Y-%m-%d %H:%M:%S'))
    say('目录: %s' % game)
    engine, desc, target = detect(game)
    say('引擎: %s — %s' % (engine, desc))
    say('标题: %s    key: %s    输出: %s' % (title, key, cg))
    if dry:
        say('（--dry，仅预览，不动文件）')
        sys.exit(0)

    # 1) 解包
    extracted = find_extracted(game)
    if '--no-extract' not in flags and engine != 'images':
        say('[1/6] 解包 …')
        ok, _ = unpack(engine, target, os.path.join(game, 'extracted'))
        extracted = find_extracted(game)
        if not ok or not extracted:
            say('      解包失败或没产出，停止。可先用 --no-extract 指定已有 extracted 再跑。')
            sys.exit(2)
    else:
        say('[1/6] 跳过解包（%s）' % ('已有素材' if extracted else '按 --no-extract'))
    src = extracted or game

    # 2) 整理
    say('[2/6] 整理成 分类/分组 …')
    sys.path.insert(0, HERE)
    from build_jing import organize
    plan = organize(src, cg)
    if not plan:
        say('      一个图片/视频都没收到，停止。解包目录长这样：')
        try:
            tops = sorted(os.listdir(src))[:12]
            say('      %s%s' % ('、'.join(tops), ' …' if len(os.listdir(src)) > 12 else ''))
        except OSError:
            pass
        say('      如果这里明显有图（扩展名可能是 .tga/.dds 之类），告诉我，我给解包器加支持。')
        sys.exit(3)

    # 3) 建站
    say('[3/6] 建站 …')
    ok, tail = run([script('gen_site_generic.py'), cg, title, key])
    if not ok:
        say('      建站失败：%s' % tail)
        sys.exit(4)

    # 4) 媒体处理
    if '--no-media' not in flags:
        say('[4/6] 视频转码 / 海报 / 雪碧图 / 缩略图 …')
        run([script('convert_ogv.py'), cg], quiet=True)
        run([script('gen_posters.py'), cg], quiet=True)
        run([script('gen_sprites.py'), cg], quiet=True)
        run([script('gen_thumbs.py'), cg], quiet=True)
        # 缩略图/海报就位后要再建一次站，目录页封面才会用缩略图
        run([script('gen_site_generic.py'), cg, title, key], quiet=True)
    else:
        say('[4/6] 跳过媒体处理（--no-media）')

    # 5) Hub
    if '--no-hub' not in flags:
        say('[5/6] ' + register_hub(key, title, cg))
        run([script('gen_hub.py')], quiet=True)
    else:
        say('[5/6] 跳过 Hub（--no-hub）')
    say('      ' + register_lib(key, title, cg))

    # 6) 自检 + 打开
    say('[6/6] 自检 …')
    self_check(cg)
    say('    日志: %s' % (LOG_FP.name if LOG_FP else '（未开启）'))
    idx = os.path.join(cg, 'index.html')
    say('完成: %s' % idx)
    if '--no-open' not in flags and os.path.exists(idx):
        os.startfile(idx)
