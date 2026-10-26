# -*- coding: utf-8 -*-
"""把目录下所有 .ogv 视频转成浏览器可播的 .mp4（H.264/AAC）
用法: python convert_ogv.py <目录> [更多目录...]
说明: Ren'Py/部分引擎的 .ogv 是 Theora 编码，Chromium 已移除解码器，
      网页里放不出来；转成 H.264 mp4 后 SakuraView 直接可播。
      已存在同名 mp4（>1KB）自动跳过，可重复执行。
"""
import os, sys, glob, subprocess
from concurrent.futures import ThreadPoolExecutor

def _find_ffmpeg():
    here = os.path.dirname(os.path.abspath(__file__))
    import glob as g
    cand = sorted(g.glob(os.path.join(here, 'ffmpeg*.exe')))
    for sub in ('tools', 'SakuraView-tools'):
        cand += sorted(g.glob(os.path.join(here, sub, 'ffmpeg*.exe')))
    try:
        import imageio_ffmpeg
        cand.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass
    for pat in ('../envs/*/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg*.exe',
                '../../envs/*/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg*.exe'):
        cand += sorted(g.glob(os.path.normpath(os.path.join(os.path.dirname(sys.executable), pat))))
    for p in cand:
        if os.path.exists(p):
            return p
    return 'ffmpeg'

FF = _find_ffmpeg()
VID_EXT = ('.webm', '.mp4', '.mkv', '.ogv')

def collect(dirs):
    out = []
    for d in dirs:
        for dp, dns, fns in os.walk(d):
            dns[:] = [x for x in dns if x not in ('assets', '_poster')]
            for fn in fns:
                if fn.lower().endswith('.ogv'):
                    src = os.path.join(dp, fn)
                    dst = os.path.splitext(src)[0] + '.mp4'
                    if not (os.path.exists(dst) and os.path.getsize(dst) > 1024):
                        out.append((src, dst))
    return out

def convert(job):
    src, dst = job
    r = subprocess.run([FF, '-y', '-hide_banner', '-loglevel', 'error', '-i', src,
                        '-c:v', 'libx264', '-preset', 'fast', '-crf', '22',
                        '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2', '-pix_fmt', 'yuv420p',
                        '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', dst],
                       capture_output=True)
    return r.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 1024

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法: python convert_ogv.py <目录> [更多目录...]'); sys.exit(1)
    jobs = collect(sys.argv[1:])
    print('待转码:', len(jobs), flush=True)
    ok = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        for i, r in enumerate(ex.map(convert, jobs)):
            ok += r
            if (i + 1) % 20 == 0 or i + 1 == len(jobs):
                print('进度 %d/%d 成功 %d' % (i + 1, len(jobs), ok), flush=True)
    print('完成:', ok, '/', len(jobs))
