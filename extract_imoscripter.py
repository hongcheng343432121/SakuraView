# -*- coding: utf-8 -*-
"""ImoScripter FilePackVer3.1 解包（配合 tools/filepack31.exe）
用法:
  python extract_imoscripter.py <GameData目录> [输出根目录] [--only data1,data3] [--keep]
说明:
  · 校验每个 .pack 尾部是否含 "FilePackVer3.1" 标识，只处理匹配的包；
  · 路径可能含中文/日文，所以一律用 subprocess 传参，不经 shell 拼接；
  · 解出的 .png 很可能是引擎私有的 DPNG，需要再过 dpng2png.exe -a <目录>（见 --dpng）；
  · 已解过的包（输出目录存在且非空）默认跳过，可反复执行。
"""
import os, sys, subprocess, collections

HERE = os.path.dirname(os.path.abspath(__file__))
FPK = os.path.join(HERE, 'tools', 'filepack31.exe')
DPNG = os.path.join(HERE, 'tools', 'dpng2png.exe')


def is_imoscripter(pack):
    """尾部 64KB 内找 FilePackVer3.1 标识"""
    try:
        sz = os.path.getsize(pack)
        with open(pack, 'rb') as f:
            f.seek(max(0, sz - 65536))
            return b'FilePackVer3.1' in f.read()
    except OSError:
        return False


def unpack(pack, out):
    os.makedirs(out, exist_ok=True)
    r = subprocess.run([FPK, 'unpack', pack, out], capture_output=True,
                       text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or '')[-200:]
    return True, ''


def dpng_convert(d):
    r = subprocess.run([DPNG, '-a', d], capture_output=True,
                       text=True, encoding='utf-8', errors='replace')
    return r.returncode == 0


def stat_ext(out):
    c = collections.Counter()
    for dp, _, fns in os.walk(out):
        for fn in fns:
            c[os.path.splitext(fn)[1].lower() or '(无扩展名)'] += 1
    return c


if __name__ == '__main__':
    argv = sys.argv[1:]
    only = None
    pos = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith('--only'):
            val = a.split('=', 1)[1] if '=' in a else (argv[i + 1] if i + 1 < len(argv) else '')
            if '=' not in a:
                i += 1
            only = {x.strip() for x in val.split(',') if x.strip()}
        elif a.startswith('--'):
            pass
        else:
            pos.append(a)
        i += 1
    flags = [a for a in argv if a.startswith('--')]
    if not pos:
        print(__doc__); sys.exit(1)
    gd = pos[0]
    outroot = pos[1] if len(pos) > 1 else os.path.join(os.path.dirname(gd), 'extracted')

    packs = sorted([p for p in os.listdir(gd) if p.lower().endswith('.pack')],
                   key=lambda x: os.path.getsize(os.path.join(gd, x)))
    print('发现 %d 个 .pack，输出到 %s' % (len(packs), outroot), flush=True)
    total_ok = 0
    for p in packs:
        name = os.path.splitext(p)[0]
        if only and name not in only:
            continue
        full = os.path.join(gd, p)
        if not is_imoscripter(full):
            print('  %-12s 跳过（不是 FilePackVer3.1）' % p); continue
        out = os.path.join(outroot, name)
        n_before = sum(len(f) for _, _, f in os.walk(out)) if os.path.isdir(out) else 0
        if n_before:
            print('  %-12s 已有 %d 个文件，跳过' % (p, n_before)); total_ok += 1; continue
        mb = os.path.getsize(full) / 1048576
        print('  %-12s %.0f MB 解包中…' % (p, mb), flush=True)
        ok, err = unpack(full, out)
        n = sum(len(f) for _, _, f in os.walk(out))
        if ok:
            ext = stat_ext(out)
            top = ', '.join('%s×%d' % (k, v) for k, v in ext.most_common(5))
            print('      → %d 个文件（%s）' % (n, top), flush=True)
            if '--dpng' in flags and '.png' in ext:
                print('      DPNG 转换…', flush=True)
                dpng_convert(out)
            total_ok += 1
        else:
            print('      ✗ 失败: %s' % err, flush=True)
    print('完成 %d 个包' % total_ok)
