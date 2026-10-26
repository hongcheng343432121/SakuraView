# -*- coding: utf-8 -*-
"""给示例库截图（README 用）——自动找 Edge/Chrome，用无头模式截三张

用法: python make_screenshots.py
输出: docs/screenshots/01-index.png  02-group.png  03-video.png
说明:
  · 全图模式（灯箱）必须点一下图片才出现，无头模式截不到；想要就手动截一张丢进同目录。
  · 如果一台机器上截出来是空白，多半是浏览器被策略拦了，换 `python serve_site.py` 起 http
    再用普通窗口手动截。
"""
import os, sys, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CG = os.path.join(ROOT, 'demo', 'CG')
OUT = os.path.join(HERE, 'screenshots')

BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def find_browser():
    for p in BROWSERS:
        if os.path.exists(p):
            return p
    return None


def shot(exe, page, out_png, size='1440,900'):
    url = page.as_uri() if hasattr(page, 'as_uri') else page
    cmd = [exe, '--headless=new', '--disable-gpu', '--hide-scrollbars',
           '--no-first-run', '--no-default-browser-check',
           '--user-data-dir=' + os.path.join(os.environ.get('TEMP', HERE), 'sv-shot-profile'),
           '--window-size=' + size, '--virtual-time-budget=5000',
           '--screenshot=' + out_png, url]
    r = subprocess.run(cmd, capture_output=True, text=True, errors='replace')
    ok = os.path.exists(out_png) and os.path.getsize(out_png) > 2000
    return ok, (r.stderr or '')[-200:]


def main():
    import pathlib
    exe = find_browser()
    if not exe:
        print('没找到 Edge / Chrome，请手动截图放进', OUT)
        return 1
    if not os.path.isdir(os.path.join(CG)):
        print('没有示例库：先跑 python make_demo.py')
        return 1
    os.makedirs(OUT, exist_ok=True)
    jobs = [('index.html', '01-index.png', '目录页'),
            ('p01.html', '02-group.png', '分组页'),
            ('p08.html', '03-video.png', '视频页')]
    fail = 0
    for page, name, desc in jobs:
        dst = os.path.join(OUT, name)
        ok, err = shot(exe, pathlib.Path(os.path.join(CG, page)), dst)
        print('%-14s %s  %s' % (desc, 'OK' if ok else '失败', name if ok else err.strip()[:80]))
        if not ok:
            fail += 1
    print('完成，输出目录:', OUT)
    if fail:
        print('有 %d 张失败：说明这台机器上无头浏览器被拦了。手动方式：双击 demo\\CG\\index.html，' % fail)
        print('用 Win+Shift+S 截图后另存到上面的目录，文件名对齐 01-index / 02-group / 03-video 即可。')
    return 1 if fail else 0


if __name__ == '__main__':
    sys.exit(main())
