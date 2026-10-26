# -*- coding: utf-8 -*-
"""为图库里的视频批量生成海报帧
用法: python gen_posters.py <CG目录> [--hw]
规则: 每个视频 X.ext → 同目录 _poster/X.jpg（480 宽）；已存在则跳过；
      .ogv 若存在同名 .mp4 则跳过（与生成器口径一致）。
      --hw 用 GPU 解码（NVDEC/cuvid 按源编码自动选），实测 6 个 1440p60 VP9 并发抽帧：
      系统 CPU 87.4% → 49.7%，耗时 1.46s → 1.05s。缩放/JPEG 编码仍在 CPU（抽帧产物是 jpg，
      NVENC 没有 jpeg 编码器）。没有对应 cuvid 解码器时自动回退软解。
"""
import os, sys, subprocess, glob, re
from concurrent.futures import ThreadPoolExecutor

CUVID = {'vp9': 'vp9_cuvid', 'vp8': 'vp8_cuvid', 'h264': 'h264_cuvid', 'hevc': 'hevc_cuvid',
         'av1': 'av1_cuvid', 'mpeg4': 'mpeg4_cuvid', 'mpeg2video': 'mpeg2_cuvid', 'vc1': 'vc1_cuvid'}
HW = '--hw' in sys.argv
_codec_cache = {}


def probe_codec(path):
    """读 ffmpeg -i 的 Video: 行拿编码名；拿不到返回 ''"""
    if path in _codec_cache:
        return _codec_cache[path]
    codec = ''
    try:
        r = subprocess.run([FF, '-hide_banner', '-i', path], capture_output=True, text=True, errors='replace')
        for line in r.stderr.splitlines():
            if 'Video:' in line:
                codec = line.split('Video:')[1].strip().split(',')[0].split('(')[0].strip().split()[0].lower()
                break
    except Exception:
        pass
    _codec_cache[path] = codec
    return codec

def _find_ffmpeg():
    """依次找：脚本同目录 / tools / SakuraView-tools 的 ffmpeg*.exe → imageio_ffmpeg → PATH"""
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
    cand.append('ffmpeg')
    for p in cand:
        if os.path.isabs(p) and os.path.exists(p):
            return p
        if p == 'ffmpeg':
            try:
                r = subprocess.run(['ffmpeg', '-version'], capture_output=True)
                if r.returncode == 0:
                    return 'ffmpeg'
            except OSError:
                pass
    return None

FF = _find_ffmpeg()
VID = ('.webm', '.mp4', '.mkv', '.ogv')

def jobs(cg):
    out = []
    for dp, dns, fns in os.walk(cg):
        dns[:] = [d for d in dns if d not in ('assets', '_poster', '_sprite')]
        for fn in sorted(fns):
            base, ext = os.path.splitext(fn)
            ext = ext.lower()
            if ext not in VID:
                continue
            if ext == '.ogv' and os.path.exists(os.path.join(dp, base + '.mp4')):
                continue
            full = os.path.join(dp, fn)
            poster = os.path.join(dp, '_poster', base + '.jpg')
            if not os.path.exists(poster):
                out.append((full, poster))
    return out

def make(job):
    src, pst = job
    os.makedirs(os.path.dirname(pst), exist_ok=True)
    dec = CUVID.get(probe_codec(src)) if HW else None
    # GPU 解 → 拉回内存 → CPU 缩放/编码；没有 cuvid 解码器就走原路径
    pre = ['-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda', '-c:v', dec] if dec else []
    vf = 'hwdownload,format=nv12,scale=480:-2' if dec else 'scale=480:-2'
    # 先在 1s 处抽帧，失败（多为超短片段）退回 0s
    for ss in ('1', '0'):
        r = subprocess.run([FF, '-y', '-hide_banner', '-loglevel', 'error'] + pre +
                           ['-ss', ss, '-i', src, '-frames:v', '1',
                            '-vf', vf, '-q:v', '5', pst],
                           capture_output=True)
        if r.returncode == 0 and os.path.exists(pst) and os.path.getsize(pst) > 500:
            return True
        if dec and ss == '0':      # GPU 路失败时用软解再试一次
            r = subprocess.run([FF, '-y', '-hide_banner', '-loglevel', 'error',
                                '-ss', ss, '-i', src, '-frames:v', '1',
                                '-vf', 'scale=480:-2', '-q:v', '5', pst], capture_output=True)
            if r.returncode == 0 and os.path.exists(pst) and os.path.getsize(pst) > 500:
                return True
    try:
        os.remove(pst)
    except OSError:
        pass
    return False

if __name__ == '__main__':
    _pos = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not _pos:
        print(__doc__)
        sys.exit(1)
    cg = _pos[0]
    if not FF:
        print('未找到 ffmpeg：请把 ffmpeg.exe 放到本脚本同目录，或 pip install imageio-ffmpeg')
        sys.exit(1)
    js = jobs(cg)
    print('待生成: %d%s' % (len(js), '（GPU 解码）' if HW else ''), flush=True)
    ok = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        for i, r in enumerate(ex.map(make, js)):
            ok += r
            if (i + 1) % 100 == 0 or i + 1 == len(js):
                print('进度 %d/%d 成功 %d' % (i + 1, len(js), ok), flush=True)
    print('完成:', ok, '/', len(js))
