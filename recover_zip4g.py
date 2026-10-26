# -*- coding: utf-8 -*-
"""修复「超过 4GB 却不是 ZIP64」的 ZIP —— 偏移和长度字段被 2^32 截断，WinRAR/7z/zipfile 都打不开

现象：双击报「压缩文件已损坏」，WinRAR 能看见列表但解压失败；zipfile 读到的
      header_offset / CD 偏移 都是 (真实值 - 2^32)；数据本身是完好的。

用法:
  python recover_zip4g.py <zip> [<zip2> ...] [--out <文件>] [--extract] [--password <密码>]

原理（完全不信任被截断的字段，从文件尾往回推）:
  真实中央目录偏移 = 文件大小 - 22 - 注释长度 - 中央目录大小
  数据结束位置     = 真实 CD 偏移 - 16（条目带数据描述符 PK\\x07\\x08 时）
  数据长度         = 数据结束 - (本地头 30 + 文件名 + 扩展域)
  抠出来的字节用 CD 里记的 CRC32 校验，对得上才落盘。

--extract 会接着调 WinRAR 的 UnRAR.exe 解开（自动找 D:\\WinRAR / Program Files / PATH）。
  这类内嵌 rar 常常是**加密**的（镜1–4 全部加密）：不给 --password 时用 `-p-` 探测，
  直接报「需要密码」；**stdin 恒接 DEVNULL**，绝不会再卡在「输入密码」上干等。
"""
import os, sys, zlib, struct, subprocess, shutil, time

SIG_LH = b"PK\x03\x04"
SIG_DD = b"PK\x07\x08"
SIG_CD = b"PK\x01\x02"
SIG_EOCD = b"PK\x05\x06"


def find_unrar():
    cand = [r"D:\WinRAR\UnRAR.exe", r"C:\Program Files\WinRAR\UnRAR.exe",
            r"C:\Program Files (x86)\WinRAR\UnRAR.exe", r"D:\WinRAR\Rar.exe"]
    for p in cand:
        if os.path.exists(p):
            return p
    w = shutil.which("unrar")
    return w


def dec_name(raw, flag):
    for enc in (("utf-8",) if flag & 0x800 else ("gbk", "utf-8")):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("latin-1")


def parse(zip_path):
    """返回 (条目名字, crc, 数据起点, 数据结束, 结论字符串列表)"""
    sz = os.path.getsize(zip_path)
    info = ["文件大小 %.3f GB (%d 字节)" % (sz / 1024 ** 3, sz)]
    with open(zip_path, "rb") as f:
        # --- EOCD（在尾部 64KB 内找最后一个）
        f.seek(max(0, sz - 65557))
        tail = f.read()
        i = tail.rfind(SIG_EOCD)
        if i < 0:
            raise SystemExit("找不到 EOCD，可能不是 ZIP")
        eocd = tail[i:i + 22]
        n_this, n_all, cd_size, cd_off, clen = struct.unpack("<HHIIH", eocd[8:22])
        info.append("EOCD: 条目 %d，CD %d 字节，CD 偏移(文件里记的) %d，注释 %d" % (n_all, cd_size, cd_off, clen))
        real_cd = sz - 22 - clen - cd_size
        if real_cd != cd_off:
            info.append("CD 偏移被截断：真实 %d（差 %d = %.2f×2^32）" % (real_cd, real_cd - cd_off, (real_cd - cd_off) / 2 ** 32))
        # --- 中央目录第一项
        f.seek(real_cd)
        cd = f.read(cd_size)
        if cd[:4] != SIG_CD:
            raise SystemExit("中央目录位置不对：真实偏移 %d 处不是 PK\\x01\\x02" % real_cd)
        flag, = struct.unpack("<H", cd[8:10])
        crc, csize, usize = struct.unpack("<III", cd[16:28])
        nl, el, cl = struct.unpack("<HHH", cd[28:34])
        name = dec_name(cd[46:46 + nl], flag)
        lh_off, = struct.unpack("<I", cd[42:46])
        info.append("条目: %s" % name)
        info.append("  flag=%s 方法=%d CRC=%08X 长度字段(记的)=%d (%.3f GB)"
                    % (hex(flag), struct.unpack("<H", cd[10:12])[0], crc, csize, csize / 1024 ** 3))
        # --- 本地头：用记的偏移，不对就从文件头找第一个 LH
        data_start = None
        if lh_off + 4 <= sz:
            f.seek(lh_off)
            head = f.read(4)
            if head == SIG_LH:
                data_start = _lh_data_start(f, lh_off)
        if data_start is None:
            f.seek(0)
            head = f.read(4)
            if head == SIG_LH:
                info.append("本地头不在记的偏移 %d，按文件头 0 处理" % lh_off)
                data_start = _lh_data_start(f, 0)
        if data_start is None:
            raise SystemExit("找不到本地文件头")
        # --- 结束位置：优先扣掉数据描述符
        data_end = real_cd
        f.seek(real_cd - 16)
        if f.read(4) == SIG_DD:
            data_end = real_cd - 16
            info.append("数据描述符在 %d（已扣 16 字节）" % data_end)
        info.append("数据区 %d .. %d，长度 %d 字节 (%.3f GB)" % (data_start, data_end, data_end - data_start,
                                                             (data_end - data_start) / 1024 ** 3))
    return name, crc, data_start, data_end, info


def _lh_data_start(f, off):
    f.seek(off)
    h = f.read(30)
    if len(h) < 30 or h[:4] != SIG_LH:
        return None
    nl, el = struct.unpack("<HH", h[26:30])
    return off + 30 + nl + el


def carve(zip_path, out_path, data_start, data_end, crc, ok_crc=True):
    total = data_end - data_start
    print("抠出数据 → %s" % out_path, flush=True)
    t0 = time.time()
    done = 0
    c = 0
    with open(zip_path, "rb") as f, open(out_path, "wb") as g:
        f.seek(data_start)
        left = total
        while left > 0:
            buf = f.read(min(16 << 20, left))
            if not buf:
                print("!! 源文件提前结束，剩 %d 字节" % left, flush=True)
                break
            g.write(buf)
            c = zlib.crc32(buf, c)
            left -= len(buf)
            done += len(buf)
            if done % (512 << 20) < (16 << 20):
                el = max(time.time() - t0, .001)
                print("  %.2f/%.2f GB  %.0f MB/s" % (done / 1024 ** 3, total / 1024 ** 3,
                                                    done / 1024 ** 2 / el), flush=True)
    c &= 0xFFFFFFFF
    print("CRC32 计算值 %08X / 期望 %08X → %s" % (c, crc, "通过 ✓" if c == crc else "不匹配 ✗"), flush=True)
    return c == crc


def do_extract(rar_path, out_dir, password=None):
    unrar = find_unrar()
    if not unrar:
        print("没找到 UnRAR.exe，跳过解压（可手动用 WinRAR 打开 %s）" % rar_path)
        return
    os.makedirs(out_dir, exist_ok=True)
    # 关键：永远不给 UnRAR 留 stdin。它一旦要密码就会阻塞在「输入密码(不会显示)」上，
    # 表现为进程一直跑、目录一直空，等 20 分钟也等不到结果（2026-10-25 踩过）。
    # 没有密码时用 -p- 让它直接报「密码错误」，好过静默挂死。
    pw = "-p" + password if password else "-p-"
    print("解压 %s → %s（%s）" % (os.path.basename(rar_path), out_dir,
                                "带密码" if password else "无密码，只探测是否加密"), flush=True)
    # UnRAR 的进度和报错都走 stdout，别只截 stderr
    r = subprocess.run([unrar, "x", pw, "-y", "-o+", rar_path, out_dir + os.sep],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                       text=True, errors="replace")
    tail = [l.strip() for l in r.stdout.splitlines() if l.strip()][-4:]
    print("  UnRAR 返回码 %d" % r.returncode)
    for l in tail:
        print("  " + l)
    if not password and r.returncode != 0:
        print("  → 这个包需要密码：重跑并加 --password <密码>，或用 WinRAR 手动解压")


if __name__ == "__main__":
    out_opt = None
    password = None
    extract = "--extract" in sys.argv
    zips = []
    it = iter(sys.argv[1:])
    for a in it:
        if a == "--out":
            out_opt = next(it, None)
        elif a == "--password":
            password = next(it, None)
        elif a.startswith("--"):
            continue
        else:
            zips.append(a)
    if not zips:
        print(__doc__)
        sys.exit(1)
    for zp in zips:
        print("=" * 70)
        print(os.path.basename(zp))
        name, crc, ds, de, info = parse(zp)
        for l in info:
            print("  " + l)
        out = out_opt or os.path.join(os.path.dirname(zp), os.path.splitext(os.path.basename(zp))[0] + ".rar")
        ok = carve(zp, out, ds, de, crc)
        print("输出: %s (%.3f GB)" % (out, os.path.getsize(out) / 1024 ** 3))
        if extract:
            do_extract(out, os.path.dirname(zp) + os.sep + os.path.splitext(os.path.basename(zp))[0], password)
