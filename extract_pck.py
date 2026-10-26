# -*- coding: utf-8 -*-
"""Godot PCK 提取器（SakuraView 工具链）
用法:
  python extract_pck.py --list <pck文件或目录>                 # 只打印索引概况（不落盘）
  python extract_pck.py <pck文件或目录> <输出目录> [--images-only]
说明:
  * 支持 Godot 3.x(PCK v1) / 4.x(PCK v2) 的 *.pck
  * .stex/.ctex 是引擎内纹理容器，内部通常嵌 PNG/WebP，本脚本自动"雕刻"出来，
    按 .import 登记的原图路径(如 res://assets/100/images/xxx/cg_01.png)还原文件名
  * 保留原始文件名与目录结构（图库备注/收藏挂在文件名上）
"""
import os, sys, struct, collections

MAGIC = b'GDPC'
IMG_EXT = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp')
SKIP_PREFIX = ('res://.import/',)


def pck_entries(path):
    """解析 PCK 索引，返回 [(res_path, offset, size, encrypted)]"""
    with open(path, 'rb') as f:
        h = f.read(88)
        if h[:4] != MAGIC:
            raise ValueError('不是 Godot PCK: %s' % path)
        ver = struct.unpack_from('<I', h, 4)[0]
        cnt = struct.unpack_from('<I', h, 84)[0]
        f.seek(88)
        out = []
        for _ in range(cnt):
            ln = struct.unpack('<I', f.read(4))[0]
            if ln == 0 or ln > 4096:
                raise ValueError('索引异常 len=%d @%s' % (ln, os.path.basename(path)))
            p = f.read(ln).rstrip(b'\x00').decode('utf-8', 'replace')
            if ln % 4:
                f.read(4 - ln % 4)
            off, size = struct.unpack('<QQ', f.read(16))
            f.read(16)  # md5
            enc = 0
            if ver >= 2:
                enc = struct.unpack('<I', f.read(4))[0] & 1
            out.append((p, off, size, enc))
        return out


def read_entry(f, off, size, enc):
    if enc:
        return None
    f.seek(off)
    return f.read(size)


def carve_image(data):
    """从 stex/ctex 里雕刻内嵌的 PNG / WebP / JPEG"""
    if not data:
        return None, None
    i = data.find(b'\x89PNG\r\n\x1a\n')
    if i >= 0:
        j = data.find(b'IEND\xaeB`\x82', i)
        return (data[i:j + 8], '.png') if j > 0 else (data[i:], '.png')
    k = data.find(b'RIFF')
    while k >= 0:
        if data[k + 8:k + 12] == b'WEBP':
            sz = struct.unpack_from('<I', data, k + 4)[0]
            return data[k:k + 8 + sz], '.webp'
        k = data.find(b'RIFF', k + 4)
    i = data.find(b'\xff\xd8\xff')
    if i >= 0:
        return data[i:], '.jpg'
    return None, None


def import_map(f, entries):
    """从 *.import 文本推出 stex 文件名 -> 原始资源路径"""
    m = {}
    for p, off, size, enc in entries:
        if not p.endswith('.import'):
            continue
        raw = read_entry(f, off, size, enc)
        if not raw:
            continue
        txt = raw.decode('utf-8', 'replace')
        src = None
        for line in txt.splitlines():
            if line.startswith('source_file='):
                src = line.split('=', 1)[1].strip().strip('"').replace('res://', '')
            elif line.startswith('dest_files='):
                for tok in line.split('=', 1)[1].strip().strip('[]').split(','):
                    dst = tok.strip().strip('"').replace('res://.import/', '').replace('res://', '')
                    if src and dst:
                        m[dst] = src
    return m


def name_for_stex(p, imap):
    """res://.import/xx.png-<md5>.stex -> xx.png（优先用 .import 登记的原路径）"""
    base = p.replace('res://.import/', '')
    if base in imap:
        return imap[base]
    core = base.rsplit('-', 1)[0]
    if not os.path.splitext(core)[1]:
        core += '.png'
    return core


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = {a for a in sys.argv[1:] if a.startswith('--')}
    if not args:
        print(__doc__)
        sys.exit(1)
    src = args[0]
    listing = '--list' in flags
    out = None if listing else (args[1] if len(args) > 1 else None)
    if not listing and not out:
        print('缺少输出目录'); sys.exit(1)

    pcks = []
    if os.path.isdir(src):
        for fn in sorted(os.listdir(src)):
            if fn.lower().endswith('.pck'):
                pcks.append(os.path.join(src, fn))
    else:
        pcks = [src]
    if not pcks:
        print('没找到 .pck'); sys.exit(1)

    total_img = total_other = 0
    stats = collections.Counter()
    for pk in pcks:
        entries = pck_entries(pk)
        exts = collections.Counter(os.path.splitext(p)[1].lower() for p, _, _, _ in entries)
        print('[%s] %d 项  %s' % (os.path.basename(pk), len(entries),
                                  dict(exts.most_common(6))), flush=True)
        if listing:
            dirs = collections.Counter()
            with open(pk, 'rb') as f:
                imap = import_map(f, entries)
            for p, _, _, _ in entries:
                low = p.lower()
                if low.endswith(('.stex', '.ctex')):
                    rel = name_for_stex(p, imap)
                elif low.endswith(IMG_EXT):
                    rel = p.replace('res://', '')
                else:
                    continue
                dirs[os.path.dirname(rel)] += 1
            for d, c in dirs.most_common(15):
                print('   %5d  %s' % (c, d))
            print('   合计图片 %d' % sum(dirs.values()))
            continue

        with open(pk, 'rb') as f:
            imap = import_map(f, entries)
            for p, off, size, enc in entries:
                low = p.lower()
                is_img = low.endswith(('.stex', '.ctex')) or low.endswith(IMG_EXT)
                if '--images-only' in flags and not is_img:
                    continue
                if p.startswith(SKIP_PREFIX) and low.endswith(('.stex', '.ctex')):
                    rel = name_for_stex(p, imap)
                elif p.startswith(SKIP_PREFIX):
                    continue
                else:
                    rel = p.replace('res://', '')
                data = read_entry(f, off, size, enc)
                if data is None:
                    stats['encrypted'] += 1
                    continue
                if low.endswith(('.stex', '.ctex')):
                    img, ext = carve_image(data)
                    if not img:
                        stats['carve_fail'] += 1
                        continue
                    # 按真实内容定扩展名：Godot 常把 WebP 塞进 .stex，而原资源名是 .png，
                    # 若沿用 .png 会导致生成器按扩展名读尺寸失败（0x0）→ 版式错乱
                    rel = os.path.splitext(rel)[0] + ext
                else:
                    img = data
                dst = os.path.join(out, rel.replace('/', os.sep))
                os.makedirs(os.path.dirname(dst) or out, exist_ok=True)
                with open(dst, 'wb') as g:
                    g.write(img)
                if is_img:
                    total_img += 1
                else:
                    total_other += 1
        print('   累计 图片 %d / 其它 %d  %s' % (total_img, total_other, dict(stats)), flush=True)

    if not listing:
        print('DONE 图片 %d 个 / 其它 %d 个 -> %s' % (total_img, total_other, out))
        if stats:
            print('  异常:', dict(stats))


if __name__ == '__main__':
    main()
