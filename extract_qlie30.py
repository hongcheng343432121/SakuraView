# -*- coding: utf-8 -*-
"""QLIE「FilePackVer3.0」解包（纯 Python，不需要外部 exe）

用途：某些 QLIE 时代的 GameData\\data*.pack 是 **FilePackVer3.0**，
      tools\\filepack31.exe 只认 3.1，解不了这些包。本脚本按 QLIE 3.0 的格式实现。

用法:
  python extract_qlie30.py <GameData目录> [输出根目录] [--only data1,data3] [--dpng] [--skip-audio]

格式要点（对照 GARbro ArcFormats/Qlie 与 arc_unpacker dec/qlie 两份实现核对过）:
  · 头在 EOF-28：16 字节 "FilePackVer3.0" + u32 条目数 + u64 条目表偏移
  · 键块 EOF-1088：32 签名 + u32 hash_size + 1024 字节 key
  · ArcKey = V3Hash(EOF-0x41C 起 0x100 字节) & 0x0FFFFFFF
      V3Hash 是双通道 PAddW：h = PAddW(h, 0x0307030703070307); k = PAddW(k, blk ^ h);
      返回 k ^ (k >> 32)
  · 条目：u16 **字节**长度 + 名字（逐字节混淆，x = ((ArcKey ^ 0x3E) + len) & 0xFF，
    每字节 ^= ((i ^ x) & 0xFF) + i；cp932 编码）+ 28 字节（u64 偏移 / u32 存储长 /
    u32 原始长 / u32 压缩 / u32 加密方法 / u32 哈希）
  · 数据解密需要两把钥匙：
      key1 = 游戏目录里的 key.fkey（4096 字节级）
      key2 = **游戏 exe 里 Delphi 窗体 TFORM1 的 IconKeyImage 图标数据**，
             即文件里 `\\x05TIcon` 标记后 256 字节（arc_unpacker 同款提取法）
    再走 MT19937(64 状态 / 39 偏移 / 非标 tempering)：
      seed = f(名字字节 × 序号, ArcKey, 数据长度)，有 key2 时再 ^= 0x453A；
      mt.xor_state(key1); mt.xor_state(key2)；取 16 个 u64 表 + 9 次丢弃 + 1 个 u64 + 1 个索引，
      然后按 PAddD/PAddB/PSllD/PAddW 四步滚动解密。
  · 名字喂给 seed 时用**解密后的**名字字节（cp932），不是密文 —— 这是当初卡最久的地方。
  · 压缩条目解出后是 BPE 流（"1PC\\xFF" 头），--dpng 会顺手把 DPNG 转真 PNG。
"""
import os, sys, struct, subprocess, collections
from multiprocessing import Pool
from array import array

HERE = os.path.dirname(os.path.abspath(__file__))
DPNG = os.path.join(HERE, 'tools', 'dpng2png.exe')
M32 = 0xFFFFFFFF
M64 = 0xFFFFFFFFFFFFFFFF
MB = 0x00FF00FF00FF00FF   # padb 用：偶数号字节
MW = 0x0000FFFF0000FFFF   # padw 用：0/2 号 16 位道
AUDIO = ('.ogg', '.wav', '.mp3', '.opus')
MAGICS = (b'\x89PNG', b'DPNG', b'ABMP', b'\x31PC\xff', b'BM\x00\x00')


# ---------- 分道运算（C#/C++ 里都是无检查溢出，一律按道宽截断） ----------
def pada_b(a, b):
    r = 0
    for i in range(8):
        r |= ((((a >> (8 * i)) & 0xFF) + ((b >> (8 * i)) & 0xFF)) & 0xFF) << (8 * i)
    return r & M64


def pada_w(a, b):
    r = 0
    for i in range(4):
        r |= ((((a >> (16 * i)) & 0xFFFF) + ((b >> (16 * i)) & 0xFFFF)) & 0xFFFF) << (16 * i)
    return r & M64


def pada_d(a, b):
    r = 0
    for i in range(2):
        r |= ((((a >> (32 * i)) & M32) + ((b >> (32 * i)) & M32)) & M32) << (32 * i)
    return r & M64


def psll_d(a, n):
    r = 0
    for i in range(2):
        r |= ((((a >> (32 * i)) & M32) << n) & M32) << (32 * i)
    return r & M64


def v3_hash(data):
    h = k = 0
    for i in range(len(data) // 8):
        blk = int.from_bytes(data[i * 8:i * 8 + 8], 'little')
        h = pada_w(h, 0x0307030703070307)
        k = pada_w(k, blk ^ h)
    return (k ^ (k >> 32)) & M32


class MT:
    """QLIE 魔改 MT19937：64 状态 / m=39 / 非标 tempering"""

    def __init__(self, seed):
        self.mt = [0] * 64
        self.mt[0] = seed & M32
        for i in range(1, 64):
            self.mt[i] = (0x6611BC19 * (self.mt[i - 1] ^ (self.mt[i - 1] >> 30)) + i) & M32
        self.mti = 64

    def xor_state(self, data):
        n = min(len(data) // 4, 64)
        for i in range(n):
            self.mt[i] ^= int.from_bytes(data[i * 4:i * 4 + 4], 'little')

    def rand(self):
        mt = self.mt
        if self.mti >= 64:
            for kk in range(25):
                y = (mt[kk] & 0x80000000) | ((mt[kk + 1] & 0x7FFFFFFF) >> 1)
                mt[kk] = mt[kk + 39] ^ y ^ (0x9908B0DF if mt[kk + 1] & 1 else 0)
            for kk in range(25, 63):
                y = (mt[kk] & 0x80000000) | ((mt[kk + 1] & 0x7FFFFFFF) >> 1)
                mt[kk] = mt[kk - 25] ^ y ^ (0x9908B0DF if mt[kk + 1] & 1 else 0)
            y = (mt[63] & 0x80000000) | ((mt[0] & 0x7FFFFFFF) >> 1)
            mt[63] = mt[38] ^ y ^ (0x9908B0DF if mt[62] & 1 else 0)
            self.mti = 0
        y = mt[self.mti]
        self.mti += 1
        y = (y ^ (y >> 11)) & M32
        y = (y ^ ((y << 7) & 0x9C4F88E3)) & M32
        y = (y ^ ((y << 15) & 0xE7F70000)) & M32
        y = (y ^ (y >> 18)) & M32
        return y

    def rand64(self):
        v = self.rand()
        return v | (self.rand() << 32)


# ---------- 解密 ----------
def decrypt(data, name, arc_key, key1, key2, packed_len):
    """name 必须是**解密后**的名字字节（cp932）；key1=fkey，key2=exe 图标密钥"""
    if key1 is None:
        # 没有 fkey 时退化成 QLIE v2 的链式异或
        n = len(data)
        h = 0xA73C5F9DA73C5F9D
        x = (((n + arc_key) & M32) ^ 0xFEC9753E)
        x |= x << 32
        out = bytearray(data)
        for off in range(0, n // 8 * 8, 8):
            h = pada_d(h, 0xCE24F523CE24F523) ^ x
            x = int.from_bytes(data[off:off + 8], 'little') ^ h
            out[off:off + 8] = x.to_bytes(8, 'little')
        return bytes(out)

    n = len(data)
    h = 0x85F532
    seed = 0x33F641
    for i, ch in enumerate(name):
        h = (h + ch * (i & 0xFF)) & M32
        seed ^= h
    seed = (seed + (arc_key ^ ((7 * (n & 0xFFFFFF) + n + h + (h ^ n ^ 0x8F32DC)) & M32))) & M32
    seed = (9 * (seed & 0xFFFFFF)) & M32
    if key2:
        seed ^= 0x453A
    mt = MT(seed)
    mt.xor_state(key1)
    if key2:
        mt.xor_state(key2)
    table = [mt.rand64() for _ in range(16)]
    for _ in range(9):
        mt.rand()
    h64 = mt.rand64()
    t = mt.rand() & 0xF
    # 热循环：把 PAddD / PAddB / PSllD / PAddW 内联展开（比调用分道函数快 3.4 倍，实测 2.0 → 6.8 MB/s）
    cnt = n // 8
    buf = array('Q')
    buf.frombytes(data[:cnt * 8])
    for i in range(cnt):
        tv = table[t]
        x = h64 ^ tv
        h64 = (((x & M32) + (tv & M32)) & M32) | ((((x >> 32) + (tv >> 32)) & M32) << 32)
        d = buf[i] ^ h64
        buf[i] = d
        a = (h64 & MB) + (d & MB)
        b = ((h64 >> 8) & MB) + ((d >> 8) & MB)
        h64 = ((a & MB) | ((b & MB) << 8)) ^ d
        s = (((h64 & M32) << 1) & M32) | (((((h64 >> 32) << 1)) & M32) << 32)
        a = (s & MW) + (d & MW)
        b = ((s >> 16) & MW) + ((d >> 16) & MW)
        h64 = (a & MW) | ((b & MW) << 16)
        t = (t + 1) & 0xF
    return buf.tobytes() + data[cnt * 8:]


def bpe_decompress(buf, expected):
    """QLIE BPE（头 "1PC\\xFF"）；一个压缩条目里可以有多段字典+数据"""
    if len(buf) < 12 or buf[:4] != b'\x31PC\xff':
        return None
    flags = int.from_bytes(buf[4:8], 'little')
    if int.from_bytes(buf[8:12], 'little') != expected:
        return None
    src = 12
    total = len(buf)
    out = bytearray()
    table = [(0, 0)] * 256
    while src < total:
        ti = 0
        stack = []
        while ti < 256:
            if src >= total:
                return bytes(out)
            c = buf[src]; src += 1
            if c > 127:
                lits, pairs = c - 127, 1
            else:
                lits, pairs = 0, c + 1
            for _ in range(lits):
                if ti < 256:
                    table[ti] = (ti, 0)
                    ti += 1
            for _ in range(pairs):
                if ti >= 256 or src >= total:
                    break
                left = buf[src]; src += 1
                if ti != left:
                    if src >= total:
                        return bytes(out)
                    right = buf[src]; src += 1
                else:
                    right = 0
                table[ti] = (left, right)
                ti += 1
        if src >= total:
            break
        if flags & 1:
            block = int.from_bytes(buf[src:src + 2], 'little'); src += 2
        else:
            block = int.from_bytes(buf[src:src + 4], 'little'); src += 4
        while block or stack:
            if stack:
                v = stack.pop()
            else:
                if src >= total:
                    break
                v = buf[src]; src += 1
                block -= 1
            left, right = table[v]
            if v == left:
                out.append(v)
            else:
                stack.append(right)
                stack.append(left)
    return bytes(out[:expected]) if len(out) >= expected else bytes(out)


# ---------- 包头 ----------
def dec_name(buf, arc_key):
    n = len(buf)
    x = ((arc_key ^ 0x3E) + n) & 0xFF
    out = bytearray(buf)
    for k in range(n):
        out[k] ^= (((k + 1) ^ x) & 0xFF) + (k + 1) & 0xFF
    return bytes(out)


def read_index(pack):
    sz = os.path.getsize(pack)
    with open(pack, 'rb') as f:
        f.seek(sz - 28)
        sig, count, entry_off = struct.unpack('<16sIQ', f.read(28))
        if b'FilePackVer3.0' not in sig:
            return None
        f.seek(sz - 0x41C)
        arc_key = v3_hash(f.read(0x100)) & 0x0FFFFFFF
        f.seek(entry_off)
        entries = []
        for _ in range(count):
            nl = struct.unpack('<H', f.read(2))[0]
            nb = dec_name(f.read(nl), arc_key)
            off, size, unp, packed, enc, hsh = struct.unpack('<QIIIII', f.read(28))
            try:
                name = nb.decode('cp932')
            except UnicodeDecodeError:
                name = nb.decode('cp932', 'replace')
            entries.append({'name': name, 'nb': nb, 'off': off, 'size': size,
                            'unp': unp, 'packed': packed, 'enc': enc})
    return {'arc_key': arc_key, 'entries': entries}


def find_fkey(gd):
    base = os.path.abspath(gd)
    for _ in range(4):
        for cand in ('key.fkey', os.path.join('DLL', 'key.fkey')):
            p = os.path.join(base, cand)
            if os.path.exists(p):
                return open(p, 'rb').read(), p
        base = os.path.dirname(base)
    return None, ''


def find_exe_key(gd):
    """游戏 exe 里 Delphi 窗体的 IconKeyImage 图标后 256 字节 = 第二把钥匙"""
    base = os.path.abspath(gd)
    root = os.path.dirname(base) if os.path.basename(base).lower() == 'gamedata' else base
    cands = []
    for fn in os.listdir(root):
        if not fn.lower().endswith('.exe'):
            continue
        try:
            b = open(os.path.join(root, fn), 'rb').read()
        except OSError:
            continue
        i = 0
        while True:
            i = b.find(b'\x05TIcon', i)
            if i < 0:
                break
            if i + 6 + 256 <= len(b):
                cands.append((fn, b[i + 6:i + 6 + 256]))
            i += 1
    return cands


def verify_keys(gd, idx, fkey, key2):
    """用加密条目验一把：压缩条目应解出 1PC 头，图片应解出图魔数"""
    pack = None
    for fn in sorted(os.listdir(gd)):
        if fn.lower().endswith('.pack'):
            p = os.path.join(gd, fn)
            i = read_index(p)
            if i:
                pack, idx = p, i
                break
    if pack is None:
        return False
    tests = [e for e in idx['entries'] if e['packed']][:2]
    if not tests:
        tests = [e for e in idx['entries'] if e['name'].lower().endswith(('.png', '.bmp'))][:2]
    if not tests:
        return True
    with open(pack, 'rb') as f:
        for e in tests:
            f.seek(e['off'])
            d = decrypt(f.read(e['size']), e['nb'], idx['arc_key'], fkey, key2, e['unp'])
            if d[:4] not in MAGICS:
                return False
    return True


# ---------- 多进程 ----------
_G = {}


def _init(pack, out, arc_key, key1, key2):
    _G.update(pack=pack, out=out, arc_key=arc_key, key1=key1, key2=key2)


def _work(e):
    dst = os.path.join(_G['out'], e['name'].replace('\\', os.sep))
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        return 'skip'
    os.makedirs(os.path.dirname(dst) or _G['out'], exist_ok=True)
    with open(_G['pack'], 'rb') as f:
        f.seek(e['off'])
        data = f.read(e['size'])
    if e['enc']:
        data = decrypt(data, e['nb'], _G['arc_key'], _G['key1'], _G['key2'], e['unp'])
    if e['packed']:
        dec = bpe_decompress(data, e['unp'])
        if dec is not None:
            data = dec
    try:
        with open(dst, 'wb') as g:
            g.write(data)
    except OSError:
        return 'fail'
    return 'ok'


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = [a for a in sys.argv[1:] if a.startswith('--')]
    if not argv:
        print(__doc__)
        sys.exit(1)
    gd = argv[0]
    outroot = argv[1] if len(argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(gd)), 'extracted')
    only = None
    for i, a in enumerate(sys.argv):
        if a.startswith('--only'):
            val = a.split('=', 1)[1] if '=' in a else (sys.argv[i + 1] if i + 1 < len(sys.argv) else '')
            only = {x.strip() for x in val.split(',') if x.strip()}
    skip_audio = '--skip-audio' in flags
    workers = max(2, min(12, (os.cpu_count() or 4)))

    fkey, fpath = find_fkey(gd)
    if fkey is None:
        print('!! 找不到 key.fkey（一般在 <游戏根>\\DLL\\key.fkey），3.0 包基本都要它')
    exe_cands = find_exe_key(gd)
    probe = None
    for fn in sorted(os.listdir(gd)):
        if fn.lower().endswith('.pack'):
            probe = read_index(os.path.join(gd, fn))
            if probe:
                break
    key2, src = None, ''
    if probe:
        for fn, k in exe_cands:
            if verify_keys(gd, probe, fkey, k):
                key2, src = k, fn
                break
    print('fkey: %s   第二把钥匙: %s' % (fpath or '无', ('%s（%d 个候选）' % (src, len(exe_cands))) if key2 else '未找到'))

    packs = sorted([p for p in os.listdir(gd) if p.lower().endswith('.pack')],
                   key=lambda x: os.path.getsize(os.path.join(gd, x)))
    print('发现 %d 个 .pack → %s（%d 进程）' % (len(packs), outroot, workers), flush=True)
    for p in packs:
        stem = os.path.splitext(p)[0]
        if only and stem not in only:
            continue
        full = os.path.join(gd, p)
        idx = read_index(full)
        if idx is None:
            print('  %-12s 跳过（不是 FilePackVer3.0）' % p, flush=True)
            continue
        entries = idx['entries']
        if skip_audio:
            entries = [e for e in entries if os.path.splitext(e['name'])[1].lower() not in AUDIO]
        out = os.path.join(outroot, stem)
        os.makedirs(out, exist_ok=True)
        print('  %-12s %7.1f MB  %5d 个文件  ArcKey=%08X' % (
            p, os.path.getsize(full) / 1048576, len(entries), idx['arc_key']), flush=True)
        stat = collections.Counter()
        with Pool(workers, initializer=_init, initargs=(full, out, idx['arc_key'], fkey, key2)) as pool:
            done = 0
            for r in pool.imap_unordered(_work, entries, chunksize=8):
                stat[r] += 1
                done += 1
                if done % 200 == 0 or done == len(entries):
                    print('      进度 %d/%d  写入 %d 跳过 %d 失败 %d' % (
                        done, len(entries), stat['ok'], stat['skip'], stat['fail']), flush=True)
        if '--dpng' in flags:
            subprocess.run([DPNG, '-a', out], capture_output=True)
    print('完成')


if __name__ == '__main__':
    main()
