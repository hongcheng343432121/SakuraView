# -*- coding: utf-8 -*-
"""SakuraView 全库重建（权威映射表，防止标题/key 传错）

用法:
  python rebuild_all.py                  # 重建全部图库（没变的库自动跳过）
  python rebuild_all.py mayfly eternum   # 只重建指定 key 的库
  python rebuild_all.py --force          # 强制全量重建
  python rebuild_all.py --list           # 只打印各库状态，不重建

增量判断：对每个 CG 目录算指纹（文件数 + 总字节 + 最新 mtime + 生成器 mtime），
与上次成功构建时存下的指纹比对，一致就跳过。改了 gen_site_generic.py 会自动全量重建。
指纹存在项目根的 build_stamp.json（不放 CG 目录里，免得被生成器扫成素材）。
"""
import os, sys, json, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
GEN = os.path.join(HERE, 'gen_site_generic.py')
STAMP_FILE = os.path.join(HERE, 'build_stamp.json')
KEEP = {'assets', '_poster', '_thumbs', '_sprite'}

# 库表不放代码里：个人图库路径属于私有配置，写到 my_libs.json（.gitignore 已排除）。
#   my_libs.json 格式（路径可以是绝对路径，也可以相对本文件）：
#   { "mygame": ["D:/game/MyGame/CG", "My Game 1.0"] }
# oneclick.py 处理新库时会自动往 libs_extra.json 里追加，不用手改本文件。
MY_LIBS_FILE = os.path.join(HERE, 'my_libs.json')
LIBS = {}


def _load_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def all_libs():
    """my_libs.json（人工登记）+ libs_extra.json（oneclick 自动登记）合并去重。"""
    libs = {}
    for name in ('my_libs.json', 'libs_extra.json'):
        for k, v in _load_json(os.path.join(HERE, name)).items():
            if k not in libs:
                libs[k] = (v[0], v[1])
    return libs


def fingerprint(cg):
    """CG 目录指纹：[文件数, 总字节, 最新 mtime, 生成器 mtime]
       用 scandir + DirEntry.stat()：Windows 上这些数据跟着目录枚举一起返回，
       比逐文件 os.stat 快一个数量级（10 万张图从 2 分钟降到几秒）。"""
    n = 0
    size = 0
    msum = 0.0
    stack = [cg]
    while stack:
        d = stack.pop()
        try:
            it = os.scandir(d)
        except OSError:
            continue
        with it:
            for e in it:
                try:
                    if e.is_dir(follow_symlinks=False):
                        if e.name not in KEEP:
                            stack.append(e.path)
                        continue
                    if d == cg:
                        continue        # 根目录下的 index.html / pNN.html 是产物，不算素材
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                n += 1
                size += st.st_size
                msum += st.st_mtime        # 用「mtime 之和」而不是 max：改动任何一个文件都能感知
    try:
        gen_m = os.path.getmtime(GEN)
    except OSError:
        gen_m = 0
    return [n, size, int(msum * 1000), round(gen_m, 2)]


def load_stamps():
    try:
        return json.load(open(STAMP_FILE, encoding='utf-8'))
    except Exception:
        return {}


def save_stamps(d):
    try:
        json.dump(d, open(STAMP_FILE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    except OSError:
        pass


def run_gen(cg, name, key):
    r = subprocess.run([PY, GEN, cg, name, key], capture_output=True, text=True)
    tail = (r.stdout.strip().splitlines() or [''])[-1]
    return ('OK ->' in r.stdout), tail


if __name__ == '__main__':
    argv = sys.argv[1:]
    force = '--force' in argv
    list_only = '--list' in argv
    libs = all_libs()
    keys = [a for a in argv if not a.startswith('--')] or list(libs)
    stamps = load_stamps()
    n_ok = n_skip = n_fail = 0
    for k in keys:
        if k not in libs:
            print('未知 key:', k)
            continue
        cg, name = libs[k]
        if not os.path.isdir(cg):
            print('SKIP %-18s 目录不存在：%s' % (k, cg))
            continue
        fp = fingerprint(cg)
        old = stamps.get(k)
        fresh = (not force) and old == fp and os.path.exists(os.path.join(cg, 'index.html'))
        if list_only:
            print('%-18s %s  %d 个文件  %s' % (k, '未变' if fresh else '有变化', fp[0], cg))
            continue
        if fresh:
            print('SKIP %-18s 没有变化（%d 个文件）' % (k, fp[0]))
            n_skip += 1
            continue
        ok, tail = run_gen(cg, name, k)
        print(('OK   ' if ok else 'FAIL ') + '%-18s %s | %s' % (k, name, tail), flush=True)
        if ok:
            stamps[k] = fp
            n_ok += 1
        else:
            n_fail += 1
    if not list_only:
        save_stamps(stamps)
        print('—' * 56)
        print('重建 %d / 跳过 %d / 失败 %d' % (n_ok, n_skip, n_fail))
    sys.exit(1 if n_fail else 0)
