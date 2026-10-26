# -*- coding: utf-8 -*-
"""自动更新：盯着各库的 CG 目录，发现有新增/删除/改名就自动重建对应图库
用法:
  python watch_update.py                 # 常驻，默认每 90s 检查一次（Ctrl+C 停）
  python watch_update.py --interval 30   # 改检查间隔
  python watch_update.py --once          # 只检查一轮（适合放进计划任务/开机脚本）
  python watch_update.py mayfly jing5    # 只盯指定库（key 见 rebuild_all.py）
说明:
  · 变更判定用「目录 mtime + 文件数」，跳过 assets/_poster/_thumbs/_sprite，开销很小；
  · 检测到变更后先等 3s 去抖（一次拷很多文件不会反复重建），再按库重建；
  · 重建顺序 = gen_site_generic（必须）→ gen_posters（新视频海报）→ gen_thumbs（新图缩略图）
    → gen_sprites（新视频进度条预览）；后三个都是增量，没新文件时几秒结束；
  · 全部库处理完若确实重建过，再重建总收藏 Hub（gen_hub.py 读 hub_libs.json）；
  · 只读磁盘、只写图库自己的 html/assets 与 _poster/_thumbs/_sprite，不动素材本体。
"""
import os, sys, time, glob, argparse, subprocess, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from rebuild_all import LIBS

PY = sys.executable
SKIP_DIR = {'assets', '_poster', '_thumbs', '_sprite'}
DEBOUNCE = 3.0


def log(msg):
    print('%s  %s' % (datetime.datetime.now().strftime('%H:%M:%S'), msg), flush=True)


def signature(cg):
    """目录级指纹：[(相对路径, mtime, 文件数)]，跳过保留目录。
       注意：CG 根目录本身要跳过——重建会写 html 进去，否则会自己触发自己（死循环）。"""
    sig = []
    for dp, dns, fns in os.walk(cg):
        dns[:] = sorted(d for d in dns if d not in SKIP_DIR)
        rel = os.path.relpath(dp, cg).replace('\\', '/')
        if rel == '.':
            continue
        try:
            mt = int(os.path.getmtime(dp))
        except OSError:
            mt = 0
        sig.append((rel, mt, len(fns)))
    sig.sort()
    return sig


def run(args, title):
    t0 = time.time()
    r = subprocess.run([PY] + args, cwd=HERE, capture_output=True, text=True, errors='replace')
    tail = (r.stdout or '').strip().splitlines()[-1:] or ['']
    ok = r.returncode == 0
    log('%s %-16s %5.1fs  %s' % ('✓' if ok else '✗', title, time.time() - t0, tail[0].strip()))
    if not ok:
        log('   stderr: ' + (r.stderr or '').strip()[-300:])
    return ok


def rebuild(key, cg, title, deep=True):
    ok = run(['gen_site_generic.py', cg, title, key], title + ' 站点')
    if not deep or not ok:
        return ok
    run(['gen_posters.py', cg], title + ' 海报')
    run(['gen_thumbs.py', cg], title + ' 缩略图')
    run(['gen_sprites.py', cg], title + ' 帧预览')
    return ok


def build_hub():
    cfg = os.path.join(HERE, 'hub_libs.json')
    if not os.path.exists(cfg):
        return
    out = os.path.join(HERE, 'gen_hub.py')
    if not os.path.exists(out):
        return
    run(['gen_hub.py'], '总收藏 Hub')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('keys', nargs='*', help='只盯指定库（缺省全部）')
    ap.add_argument('--interval', type=int, default=90)
    ap.add_argument('--once', action='store_true', help='只检查一轮就退出')
    a = ap.parse_args()

    keys = a.keys or list(LIBS)
    unknown = [k for k in keys if k not in LIBS]
    if unknown:
        print('未知库: %s（可用: %s）' % (', '.join(unknown), ', '.join(LIBS)))
        sys.exit(1)

    state = {}
    for k in keys:
        cg = LIBS[k][0]
        if not os.path.isdir(cg):
            log('跳过（目录不存在）%s: %s' % (k, cg))
            continue
        state[k] = signature(cg)
    if not state:
        sys.exit(1)
    log('开始监视 %d 个库，间隔 %ds%s' % (len(state), a.interval, '（单轮模式）' if a.once else '，Ctrl+C 停止'))

    while True:
        if not a.once:
            time.sleep(max(5, a.interval))
        changed = []
        for k in list(state):
            cg = LIBS[k][0]
            sig = signature(cg)
            if sig != state[k]:
                added = sum(x[2] for x in sig) - sum(x[2] for x in state[k])
                state[k] = sig
                changed.append((k, added))
        if not changed:
            if a.once:
                log('无变化（%d 个库）' % len(state))
                break
            continue
        # 去抖：等文件拷完再重建
        time.sleep(DEBOUNCE)
        for k, added in changed:
            log('检测到变更 %-16s 文件数 %+d，开始重建' % (k, added))
            rebuild(k, LIBS[k][0], LIBS[k][1])
            # 重建会生成 _thumbs/_sprite/assets，刷新指纹放在重建之后，
            # 否则"自己写自己"会多触发一轮空重建
            state[k] = signature(LIBS[k][0])
        build_hub()
        log('本轮完成')
        if a.once:
            break


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n已停止')
