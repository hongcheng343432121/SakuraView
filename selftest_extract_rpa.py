# 构造一个最小 RPA-3.0 测试归档，验证 extract_rpa.py 端到端可用
# 布局：头行 | 索引(zlib+pickle) | 各文件内容
import pickle, zlib, os

os.makedirs('_rpatest', exist_ok=True)
content = b'\x89PNG fake cg data 0123456789'
key = 0
name = 'images/01/luna_01.png'
idx_off = len(b'RPA-3.0 00000000 00000000\n')      # 头行定长 27

# 内容偏移依赖索引 blob 长度，迭代收敛（2~3 轮即稳定）
content_off = idx_off + 64
for _ in range(5):
    index = {name: [(content_off ^ key, len(content) ^ key, b'')]}
    blob = zlib.compress(pickle.dumps(index))
    new_off = idx_off + len(blob)
    if new_off == content_off:
        break
    content_off = new_off

with open('_rpatest/archive.rpa', 'wb') as f:
    f.write(('RPA-3.0 %08x %08x\n' % (idx_off, key)).encode())
    f.write(blob)
    f.write(content)
print('fake rpa built: idx_off=%d content_off=%d' % (idx_off, content_off))
