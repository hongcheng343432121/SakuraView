# -*- coding: utf-8 -*-
"""用本地 http 服务打开图库（解决 file:// 才有的浏览器限制）
用法:
  python serve_site.py                 # 默认把「当前目录」开在 http://127.0.0.1:8765/
  python serve_site.py <根目录> [端口]
说明:
  file:// 下浏览器把本地视频当成跨源资源，下面这些能力会被安全策略禁用：
    · 截图（canvas 被污染，toBlob/toDataURL 抛 SecurityError）
    · 画中画（部分版本）、captureStream 相关功能
  用 http:// 打开同一个文件夹即可恢复正常，其它功能（看图/收藏/备注）完全不受影响。
  只监听 127.0.0.1，仅本机可访问；Ctrl+C 停止。
"""
import os, sys, http.server, socketserver, functools

DEFAULT_ROOT = os.getcwd()
DEFAULT_PORT = 8765


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ROOT
    port = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PORT
    if not os.path.isdir(root):
        print('目录不存在: %s' % root)
        sys.exit(1)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=root)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(('127.0.0.1', port), handler) as httpd:
        print('图库根目录: %s' % root)
        print('打开地址  : http://127.0.0.1:%d/' % port)
        hub = 'SakuraView-hub.html'
        if os.path.exists(os.path.join(root, hub)):
            print('总收藏    : http://127.0.0.1:%d/%s' % (port, hub))
        print('（Ctrl+C 停止）')
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\n已停止')


if __name__ == '__main__':
    main()
