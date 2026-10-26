"""Ren'Py .rpa 解包。

用法: python extract_rpa.py <rpa> [输出目录] [--only=webp,png,mp4]
      --only 只解指定扩展名（逗号分隔，不带点），大归档里只要 CG 时能省一大半时间
"""
import pickle, zlib, os, sys, time

# 用法: python extract_rpa.py <rpa> <输出目录> [--only=webp,png,mp4]
#   --only 只解指定扩展名（逗号分隔，不带点），大归档里只要 CG 时能省一大半时间
pos = [a for a in sys.argv[1:] if not a.startswith('--')]
ONLY = None
for a in sys.argv[1:]:
    if a.startswith('--only='):
        ONLY = {('.' + x.strip().lower().lstrip('.')) for x in a.split('=', 1)[1].split(',') if x.strip()}

if not pos:
    print(__doc__)
    raise SystemExit(2)
RPA = pos[0]
OUT = pos[1] if len(pos) > 1 else os.path.join(os.path.dirname(os.path.abspath(RPA)), 'extracted')

with open(RPA, "rb") as f:
    header = f.readline()
    parts = header.split()
    indexoff = int(parts[1], 16)
    key = int(parts[2], 16)
    f.seek(indexoff)
    index = pickle.loads(zlib.decompress(f.read()), encoding="latin1")

items = []
for name, entries in index.items():
    if ONLY and os.path.splitext(name)[1].lower() not in ONLY:
        continue
    for (o, l, prefix) in entries:
        items.append((o ^ key, l ^ key, prefix, name))
items.sort(key=lambda x: x[0])

total_bytes = sum(it[1] + len(it[2]) for it in items)
print("files:", len(items), "total: %.2f GB" % (total_bytes / 1024 ** 3), flush=True)

done = 0
start = time.time()
fh = open(RPA, "rb")
pos = fh.tell()
for i, (off, length, prefix, name) in enumerate(items):
    dst = os.path.join(OUT, name.replace("/", os.sep))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if off != pos:
        fh.seek(off)
    data = fh.read(length)
    pos = fh.tell()
    with open(dst, "wb") as g:
        if prefix:
            g.write(prefix)
        g.write(data)
    done += length + len(prefix)
    if (i + 1) % 500 == 0 or i == len(items) - 1:
        el = time.time() - start
        print("%6d/%d  %.2f/%.2f GB  %.1f MB/s" % (
            i + 1, len(items), done / 1024 ** 3, total_bytes / 1024 ** 3,
            done / 1024 ** 2 / max(el, 0.001)), flush=True)
fh.close()
print("DONE in %.1f s" % (time.time() - start), flush=True)
