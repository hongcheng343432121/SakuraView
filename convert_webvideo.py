# -*- coding: utf-8 -*-
"""把图库里「浏览器放不出来」的视频就地转成 H.264/AAC mp4
用法:
  python convert_webvideo.py <CG目录> [更多目录...] [--dry] [--crf 20] [--hw] [--cq 26]
说明:
  浏览器只认这几种：mp4 里的 h264(yuv420p) / av1、webm 里的 vp8 / vp9。
  其余（mpeg4/mp4v、h264-4:4:4、ffv1、mpeg2、wmv、theora .ogv…）一律黑屏——文件没坏，
  是解码器不支持。本脚本逐个探测，能播的跳过，不能播的就地转 H.264（yuv420p + faststart），
  文件名保持不变（收藏/备注/海报帧都挂在文件名上）。可重复执行，已转好的会跳过。

  --hw  改用 GPU 跑全链路（NVIDIA NVDEC 解码 + NVENC 编码）。实测 6 个 1440p60 VP9 并发：
        系统 CPU 94.2% → **33.5%**（峰值 100% → 71%），耗时 11.7s → 5.7s。
        关键：必须显式 `-hwaccel_output_format cuda` + 指定 `-c:v vp9_cuvid`
        （只给 `-hwaccel cuda` 会退回软解，`scale_cuda` 报 -40）。
        注意 ①NVENC 的 --cq 与 x264 的 --crf 不等价，cq=26 体积比 crf=20 大约 35%（cq=30 才接近）；
             ②消费级卡并发编码会话上限 8，脚本会自动把并发降到 8；
             ③源码编码没有对应 cuvid 解码器时自动回退软解+libx264，不会失败。
"""
import os, re, sys, glob, subprocess, collections
from concurrent.futures import ThreadPoolExecutor

VID = ('.mp4', '.webm', '.mkv', '.ogv', '.mov', '.avi')
SAFE_CODEC = {'h264', 'vp8', 'vp9', 'av1'}
SAFE_PIX = {'yuv420p', 'yuvj420p', 'nv12'}


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


def nvenc_ok():
    """能不能用 NVIDIA 硬编：真跑一帧测试，比 grep -encoders 可靠。
       注意分辨率不能太小（NVENC 对 H.264 有最小尺寸限制，128x128 会报
       「Frame Dimension less than the minimum supported value」），用 320x240。"""
    try:
        r = subprocess.run([FF, '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
                            '-i', 'nullsrc=s=320x240:d=0.2', '-vf', 'format=yuv420p',
                            '-c:v', 'h264_nvenc', '-f', 'null', '-'],
                           capture_output=True, timeout=20)
        return r.returncode == 0
    except Exception:
        return False


def probe(path):
    """返回 (codec, pix_fmt, has_audio)；解析 ffmpeg -i 的 stderr"""
    r = subprocess.run([FF, '-hide_banner', '-i', path], capture_output=True, text=True, errors='replace')
    codec, pix = '?', '?'
    for line in r.stderr.splitlines():
        if 'Video:' in line and codec == '?':
            seg = line.split('Video:')[1]
            codec = seg.strip().split(',')[0].split('(')[0].strip().split()[0].lower()
            m = re.search(r'\b(yuv\w+|nv12|rgb\w*|gbr\w*)\b', seg)
            if m:
                pix = m.group(1)
    audio = 'Audio:' in r.stderr
    return codec, pix, audio


def playable(path):
    codec, pix, _ = probe(path)
    if codec not in SAFE_CODEC:
        return False, '%s（浏览器不支持）' % codec
    if codec == 'h264' and pix not in SAFE_PIX:
        return False, 'h264/%s（4:4:4 之类的 profile 浏览器不支持）' % pix
    if codec in ('vp8', 'vp9') and not path.lower().endswith(('.webm', '.mp4')):
        return False, '%s 装在 %s 里' % (codec, os.path.splitext(path)[1])
    return True, '%s/%s' % (codec, pix)


CUVID = {'vp9': 'vp9_cuvid', 'vp8': 'vp8_cuvid', 'h264': 'h264_cuvid', 'hevc': 'hevc_cuvid',
         'av1': 'av1_cuvid', 'mpeg4': 'mpeg4_cuvid', 'mpeg2video': 'mpeg2_cuvid',
         'mjpeg': 'mjpeg_cuvid', 'vc1': 'vc1_cuvid'}


def convert(path, crf='20', hw=False, cq='26'):
    """就地转 H.264；返回 (ok, 说明)。
       hw=True 走全 GPU：cuvid 解码 → nvenc 编码；该源没有 cuvid 解码器时回退软解。"""
    codec, pix, audio = probe(path)
    stem, ext = os.path.splitext(path)
    out = stem + '.mp4'
    tmp = stem + '.__conv.mp4'

    def build(use_gpu):
        dec = CUVID.get(codec) if use_gpu else None
        pre = ['-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda', '-c:v', dec] if dec else []
        a = [FF, '-y', '-hide_banner', '-loglevel', 'error'] + pre + ['-i', path]
        if use_gpu and dec:
            # cuvid 出的 cuda 帧不能直连 nvenc（格式协商失败、报 -22），必须过一道 scale_cuda；
            # 这里用恒等缩放，不改分辨率，只是把帧格式对齐成 nv12。
            # 另注意：GPU 路**不能**加 -pix_fmt yuv420p——对硬件帧指定 CPU 像素格式会让 nvenc 报 -22。
            a += ['-vf', 'scale_cuda=w=iw:h=ih:format=nv12']
            a += ['-c:v', 'h264_nvenc', '-preset', 'p5', '-tune', 'hq', '-rc', 'vbr',
                  '-cq', cq, '-b:v', '0']
        else:
            a += ['-c:v', 'libx264', '-crf', crf, '-preset', 'veryfast', '-pix_fmt', 'yuv420p']
        a += ['-c:a', 'aac', '-b:a', '160k'] if audio else ['-an']
        a += ['-movflags', '+faststart', tmp]
        return a

    def try_run(args):
        r = subprocess.run(args, capture_output=True)
        return r.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 1000

    ok = False
    if hw and codec in CUVID:
        ok = try_run(build(True))
        if not ok and os.path.exists(tmp):
            os.remove(tmp)
        mode = 'gpu' if ok else 'cpu-fallback'
    else:
        mode = 'cpu'
    if not ok:
        ok = try_run(build(False))
    if not ok:
        if os.path.exists(tmp):
            os.remove(tmp)
        return False, 'ffmpeg 失败'
    os.replace(tmp, out)
    if os.path.normcase(out) != os.path.normcase(path) and os.path.exists(path):
        os.remove(path)          # 原文件是 mkv/ogv/webm：转好后删掉，免得图库里出现两条
    return True, '%s/%s → h264/yuv420p（%s）' % (codec, pix, mode)


def collect(roots):
    out = []
    for cg in roots:
        for dp, dns, fns in os.walk(cg):
            dns[:] = [d for d in dns if d not in ('assets', '_poster', '_thumbs')]
            for fn in sorted(fns):
                if os.path.splitext(fn)[1].lower() in VID:
                    out.append(os.path.join(dp, fn))
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = [a for a in sys.argv[1:] if a.startswith('--')]
    if not args:
        print(__doc__)
        sys.exit(1)
    crf = '20'
    cq = '26'
    for f in flags:
        if f.startswith('--crf'):
            crf = f.split('=')[1] if '=' in f else crf
        if f.startswith('--cq'):
            cq = f.split('=')[1] if '=' in f else cq
    dry = '--dry' in flags
    hw = ('--hw' in flags or '--nvenc' in flags)
    if hw and not nvenc_ok():
        print('提示: 没检测到可用的 NVENC，回退 CPU（libx264）', flush=True)
        hw = False
    files = collect(args)
    print('视频 %d 个，开始探测（%s%s）' % (
        len(files), 'dry-run' if dry else 'ffmpeg=' + FF,
        '' if dry else ('，编码器=NVENC(GPU) cq=' + cq if hw else '，编码器=libx264 crf=' + crf)), flush=True)

    todo = []
    for p in files:
        ok, why = playable(p)
        if ok:
            continue
        todo.append((p, why, os.path.getsize(p)))
    print('需要转换: %d 个' % len(todo), flush=True)
    for p, why, sz in todo[:5]:
        print('  · %-58s %-46s %.1fMB' % (os.path.relpath(p, args[0])[:58], why, sz / 1048576), flush=True)
    if dry or not todo:
        return

    stat = collections.Counter()
    total = 0
    workers = 8 if hw else 4      # 消费级卡 NVENC 并发会话上限=8
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, res in enumerate(ex.map(lambda t: convert(t[0], crf, hw, cq), todo)):
            ok, info = res
            stat['ok' if ok else 'fail'] += 1
            if not ok:
                print('  ✗ %s: %s' % (todo[i][0], info))
            if (i + 1) % 20 == 0 or i + 1 == len(todo):
                print('进度 %d/%d 成功 %d 失败 %d' % (i + 1, len(todo), stat['ok'], stat['fail']), flush=True)
    print('完成：成功 %d / 失败 %d' % (stat['ok'], stat['fail']))


if __name__ == '__main__':
    main()
