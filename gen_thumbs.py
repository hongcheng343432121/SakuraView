# -*- coding: utf-8 -*-
"""为图库图片批量生成缩略图
用法: python gen_thumbs.py <CG目录> [--pillow]
规则: 每张图 X.ext → 同目录 _thumbs/X.jpg（宽 cap 640，等比）；已存在自动跳过；
      网页端 src 优先用缩略图，缺图时 onerror 自动回退原图，可随时中断补跑。
引擎: 默认 ffmpeg（体积稳、便携包自带）；--pillow 走 Pillow（有 Pillow 才可用），
      4K WebP 实测只快 ~9% 但文件大 1.18–1.47 倍，所以不设默认；ffmpeg 缺失时自动回退 Pillow。
"""
import os, sys, subprocess, glob
from concurrent.futures import ThreadPoolExecutor

try:                       # 可选加速：没有 Pillow 也不能崩
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    PILLOW = True
except Exception:
    PILLOW = False
USE_PILLOW = False         # 在 __main__ 里按参数/可用性决定

def _find_ffmpeg():
    """依次找：脚本同目录 / tools / SakuraView-tools 下的 ffmpeg*.exe →
    imageio_ffmpeg（含本机 envs/* 里的）→ PATH 里的 ffmpeg"""
    here = os.path.dirname(os.path.abspath(__file__))
    cand = sorted(glob.glob(os.path.join(here, 'ffmpeg*.exe')))
    for sub in ('tools', 'SakuraView-tools'):
        cand += sorted(glob.glob(os.path.join(here, sub, 'ffmpeg*.exe')))
    try:
        import imageio_ffmpeg
        cand.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass
    # managed python: <py>/versions/<ver>/../envs/*/Lib/site-packages/imageio_ffmpeg/binaries
    for pat in ('../envs/*/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg*.exe',
                '../../envs/*/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg*.exe'):
        cand += sorted(glob.glob(os.path.normpath(os.path.join(os.path.dirname(sys.executable), pat))))
    for p in cand:
        if os.path.isabs(p) and os.path.exists(p):
            return p
    try:
        if subprocess.run(['ffmpeg', '-version'], capture_output=True).returncode == 0:
            return 'ffmpeg'
    except OSError:
        pass
    return None

FF = _find_ffmpeg()
IMG = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')
# 线程数跟随 CPU（ffmpeg 是按图起进程的短任务，核多就该多开；上限 16 免得把机器拖死）
WORKERS = max(4, min(16, os.cpu_count() or 4))

def jobs(cg):
    out = []
    for dp, dns, fns in os.walk(cg):
        dns[:] = [d for d in dns if d not in ('assets', '_poster', '_thumbs', '_sprite')]
        for fn in sorted(fns):
            if os.path.splitext(fn)[1].lower() not in IMG:
                continue
            full = os.path.join(dp, fn)
            base = os.path.splitext(fn)[0]
            thumb = os.path.join(dp, '_thumbs', base + '.jpg')
            if not os.path.exists(thumb):
                out.append((full, thumb))
    return out

def _make_pillow(src, thumb):
    """等价于 ffmpeg 的 scale='min(640,iw)':-2：按宽度缩、不放大小图、高度取偶数"""
    im = Image.open(src)
    iw, ih = im.size
    if iw <= 0 or ih <= 0:
        return False
    tw = min(640, iw)
    th = max(2, int(round(ih * tw / float(iw) / 2.0)) * 2)
    if (tw, th) != (iw, ih):
        im = im.resize((tw, th), Image.LANCZOS)
    if im.mode in ('RGBA', 'LA', 'P'):
        im = im.convert('RGBA')
        bg = Image.new('RGB', im.size, (0, 0, 0))   # 与 ffmpeg 丢 alpha 的观感一致
        bg.paste(im, mask=im.split()[-1])
        im = bg
    elif im.mode != 'RGB':
        im = im.convert('RGB')
    im.save(thumb, 'JPEG', quality=78)
    return True


def _make_ffmpeg(src, thumb):
    r = subprocess.run([FF, '-y', '-hide_banner', '-loglevel', 'error', '-i', src,
                        '-vf', "scale='min(640,iw)':-2", '-q:v', '4', thumb],
                       capture_output=True)
    return r.returncode == 0


def make(job):
    src, thumb = job
    os.makedirs(os.path.dirname(thumb), exist_ok=True)
    try:
        if USE_PILLOW:
            ok = _make_pillow(src, thumb)
        else:
            ok = _make_ffmpeg(src, thumb)
    except Exception:          # 坏图/超大图/不支持的编码 → 换另一个引擎再试一次
        try:
            ok = _make_pillow(src, thumb) if (not USE_PILLOW and PILLOW) else \
                 (bool(FF) and _make_ffmpeg(src, thumb))
        except Exception:
            ok = False
    if ok and os.path.exists(thumb) and os.path.getsize(thumb) > 300:
        return True
    try:
        os.remove(thumb)
    except OSError:
        pass
    return False

if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        print('用法: python gen_thumbs.py <CG目录> [--pillow]')
        sys.exit(1)
    cg = args[0]
    # 默认 ffmpeg；--pillow 或 ffmpeg 缺失时才用 Pillow
    USE_PILLOW = PILLOW and ('--pillow' in sys.argv or not FF)
    if not FF and not PILLOW:
        print('未找到 ffmpeg 也没有 Pillow：请把 ffmpeg.exe 放到本脚本同目录，或 pip install imageio-ffmpeg / pillow')
        sys.exit(1)
    js = jobs(cg)
    print('待生成:', len(js), '（%d 线程 / %s）' % (WORKERS, 'Pillow' if USE_PILLOW else 'ffmpeg'), flush=True)
    ok = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for i, r in enumerate(ex.map(make, js)):
            ok += r
            if (i + 1) % 200 == 0 or i + 1 == len(js):
                print('进度 %d/%d 成功 %d' % (i + 1, len(js), ok), flush=True)
    print('完成:', ok, '/', len(js))
