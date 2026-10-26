# -*- coding: utf-8 -*-
"""为视频生成「进度条预览雪碧图」（10 帧拼一张）
用法: python gen_sprites.py <CG目录> [更多目录...] [--hw]
规则: 每个视频 X.ext → 同目录 _sprite/X.jpg（10 × 160×90 横排，共 1600×90）；
      已存在自动跳过，可随时中断补跑。
      --hw 用 GPU 解码（按源编码自动选 cuvid），解码是抽 10 帧的主要开销；
      实测 6 个 1440p60 VP9 并发抽帧 CPU 87.4% → 49.7%。tile/pad 仍走 CPU。
说明: 本地图库用 file:// 打开时 canvas 读不到视频像素（安全策略），
      所以进度条悬停预览只能在建库阶段用 ffmpeg 预抽帧，前端按位置切雪碧图。
"""
import os, re, sys, glob, subprocess, collections
from concurrent.futures import ThreadPoolExecutor

VID = ('.mp4', '.webm', '.mkv', '.ogv')
TILES = 10
TW, TH = 160, 90


def find_ffmpeg():
    here = os.path.dirname(os.path.abspath(__file__))
    cand = sorted(glob.glob(os.path.join(here, 'ffmpeg*.exe')))
    for sub in ('tools', 'SakuraView-tools'):
        cand += sorted(glob.glob(os.path.join(here, sub, 'ffmpeg*.exe')))
    try:
        import imageio_ffmpeg
        cand.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass
    for pat in ('../envs/*/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg*.exe',
                '../../envs/*/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg*.exe'):
        cand += sorted(glob.glob(os.path.normpath(os.path.join(os.path.dirname(sys.executable), pat))))
    for p in cand:
        if os.path.isabs(p) and os.path.exists(p):
            return p
    return 'ffmpeg'


FF = find_ffmpeg()
HW = '--hw' in sys.argv        # GPU 解码（NVDEC/cuvid），实测 6 个 1440p60 VP9 抽帧 CPU 87% → 50%


def duration(path):
    r = subprocess.run([FF, '-hide_banner', '-i', path], capture_output=True, text=True, errors='replace')
    m = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', r.stderr)
    if not m:
        return 0.0
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


CUVID = {'vp9': 'vp9_cuvid', 'vp8': 'vp8_cuvid', 'h264': 'h264_cuvid', 'hevc': 'hevc_cuvid',
         'av1': 'av1_cuvid', 'mpeg4': 'mpeg4_cuvid', 'mpeg2video': 'mpeg2_cuvid', 'vc1': 'vc1_cuvid'}


def codec_of(path):
    """和 duration() 共用一次 ffmpeg -i：拿 Video 行的编码名"""
    r = subprocess.run([FF, '-hide_banner', '-i', path], capture_output=True, text=True, errors='replace')
    for line in r.stderr.splitlines():
        if 'Video:' in line:
            return line.split('Video:')[1].strip().split(',')[0].split('(')[0].strip().split()[0].lower()
    return ''


def jobs(roots):
    out = []
    for cg in roots:
        for dp, dns, fns in os.walk(cg):
            dns[:] = [d for d in dns if d not in ('assets', '_poster', '_thumbs', '_sprite')]
            for fn in sorted(fns):
                if os.path.splitext(fn)[1].lower() not in VID:
                    continue
                src = os.path.join(dp, fn)
                dst = os.path.join(dp, '_sprite', os.path.splitext(fn)[0] + '.jpg')
                if os.path.exists(dst) and os.path.getsize(dst) > 500:
                    continue
                out.append((src, dst))
    return out


def make(job):
    src, dst = job
    dur = duration(src)
    if dur < 0.1:
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    iv = max(0.03, dur / TILES)
    tail = ('fps=1/%.4f,scale=%d:%d:force_original_aspect_ratio=decrease,'
            'pad=%d:%d:(ow-iw)/2:(oh-ih)/2,tile=%dx1' % (iv, TW, TH, TW, TH, TILES))
    # GPU 只接解码这一棒（tile/pad 只能 CPU）；没有 cuvid 解码器就走原路径
    dec = CUVID.get(codec_of(src)) if HW else None
    pre = ['-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda', '-c:v', dec] if dec else []
    vf = ('hwdownload,format=nv12,' + tail) if dec else tail
    r = subprocess.run([FF, '-y', '-hide_banner', '-loglevel', 'error'] + pre + ['-i', src,
                        '-vf', vf, '-frames:v', '1', '-q:v', '4', dst], capture_output=True)
    if r.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 500:
        return True
    if dec:                        # GPU 路失败 → 软解再试一次
        r = subprocess.run([FF, '-y', '-hide_banner', '-loglevel', 'error', '-i', src,
                            '-vf', tail, '-frames:v', '1', '-q:v', '4', dst], capture_output=True)
        if r.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 500:
            return True
    if os.path.exists(dst):
        os.remove(dst)
    return False


if __name__ == '__main__':
    roots = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not roots:
        print(__doc__)
        sys.exit(1)
    js = jobs(roots)
    print('待生成雪碧图: %d%s' % (len(js), '（GPU 解码）' if HW else ''), flush=True)
    ok = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        for i, r in enumerate(ex.map(make, js)):
            ok += r
            if (i + 1) % 50 == 0 or i + 1 == len(js):
                print('进度 %d/%d 成功 %d' % (i + 1, len(js), ok), flush=True)
    print('完成:', ok, '/', len(js))
