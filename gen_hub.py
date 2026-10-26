# -*- coding: utf-8 -*-
"""生成 SakuraView 总收藏页（Hub）：聚合多个本地图库的收藏
用法:
  python gen_hub.py [输出.html] [--lib "显示名|相对路径|key" ...]
缺省读同目录 hub_libs.json（output / libs）。

约定（与 gen_site_generic.py 一致）:
  · file:// 下所有页面共用 localStorage → 每库数据键一律带 <key>_ 前缀
  · 收藏 <key>_favs（数组，末尾最新）/ 备注 <key>_notes（rel→文本）/ 标签 <key>_tags（rel→数组）
  · 卡片点击走 <base>/fav.html#open=<rel> 深链（图片开灯箱、视频开播放器）
  · 路径按段 encodeURIComponent（文件名带 # ? & 也不会裂图）
  · 缩略图 <dir>/_thumbs/<stem>.jpg，视频海报 <dir>/_poster/<stem>.jpg；缺失自动回退原图
生成期会读各库 assets/nav.js 统计「图片数/分组数」，并探测 _thumbs 是否存在。
"""
import os, sys, json, argparse, re

TPL = r"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>🌸 SakuraView · 总收藏</title>
<style>
:root{--bg:#0a0b0f;--card:#151821;--line:#222733;--text:#e9ecf3;--muted:#79839a;--pink:#ffb7c5}
*{box-sizing:border-box;margin:0;padding:0}
html{color-scheme:dark;scrollbar-gutter:stable}
body{background:var(--bg);color:var(--text);font:14px/1.6 "Segoe UI","PingFang SC","Microsoft YaHei",system-ui,sans-serif;padding:26px 30px 90px}
h1{font-size:21px;font-weight:800;font-style:italic;display:flex;align-items:baseline;gap:10px}
h1 .mk{color:var(--pink);font-size:12.5px;letter-spacing:2.4px;font-style:normal}
h1 em{font-style:normal;color:var(--muted);font-size:13px;font-weight:600}
.stats{color:var(--muted);font-size:12.5px;margin:7px 0 0;line-height:1.9}
.stats b{color:#c8d0e2;font-weight:700}
.bar{position:sticky;top:0;z-index:30;display:flex;align-items:center;gap:10px;flex-wrap:wrap;
padding:12px 0 13px;margin:16px 0 22px;background:linear-gradient(#0a0b0f 72%,rgba(10,11,15,.82));
border-bottom:1px solid var(--line)}
.search{display:flex;align-items:center;gap:8px;background:var(--card);border:1px solid var(--line);
border-radius:9px;padding:7px 11px;width:330px;max-width:100%;transition:border-color .16s}
.search:focus-within{border-color:rgba(255,183,197,.55)}
.search input{background:none;border:0;outline:none;color:var(--text);font-size:13px;width:100%;font-family:inherit}
.search input::placeholder{color:#5b6478}
.search .clr{display:none;color:var(--muted);cursor:pointer;font-size:15px;line-height:1;padding:0 2px}
.search.has .clr{display:block}
.vsw{padding:7px 14px;border-radius:9px;border:1px solid var(--line);background:var(--card);
color:#c8d0e2;font-size:12.5px;font-weight:600;cursor:pointer;font-family:inherit;transition:.16s}
.vsw:hover{background:#232a3a;color:#fff}
.vsw.on{background:rgba(255,91,140,.18);border-color:rgba(255,183,197,.68);color:#ffb7c5}
#fcount{color:var(--pink);font-size:12.5px}
#tagbar{display:flex;align-items:center;gap:7px;flex-wrap:wrap;width:100%}
#tagbar.hide{display:none}
#tagbar .tl{color:var(--muted);font-size:12px;margin-right:2px}
.chip{border:1px solid var(--line);background:#12151d;color:#9aa4b8;font-size:11.5px;
border-radius:20px;padding:2px 10px;cursor:pointer;font-family:inherit;transition:.15s}
.chip:hover{color:#fff;border-color:#3a4358}
.chip.on{background:rgba(255,183,197,.16);border-color:rgba(255,183,197,.65);color:#ffb7c5}
section.slib{margin-bottom:32px}
.lh{display:flex;align-items:baseline;gap:12px;border-left:3px solid var(--pink);
padding:7px 14px;margin-bottom:14px;background:linear-gradient(100deg,#22305a,#1a2338 55%,#151b28);
border-radius:2px 8px 8px 2px;flex-wrap:wrap}
.lh b{font-size:15px}
.lh .cnt{color:#c8d0e2;font-size:12.5px;font-weight:700}
.lh .cnt i{color:var(--muted);font-weight:400;font-style:normal}
.lh .meta{color:var(--muted);font-size:12px}
.lh .acts{margin-left:auto;display:flex;gap:15px}
.lh a{color:var(--pink);font-size:12.5px;text-decoration:none}
.lh a:hover{text-decoration:underline}
.hgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(196px,1fr));gap:16px 12px;align-items:start}
.hc{position:relative;display:block;min-width:0}
.hc .th{display:block;position:relative;border-radius:10px;overflow:hidden;background:var(--card);
border:1px solid var(--line);aspect-ratio:4/3}
.hc .th img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .26s}
.hc:hover .th img{transform:scale(1.045)}
.hc.dead .th{display:grid;place-items:center;border-style:dashed;background:#131720}
.hc.dead .th::after{content:"文件缺失";color:#6b7488;font-size:12px;letter-spacing:1px}
.hc.dead .play,.hc.dead .lt,.hc.dead .lbn{display:none}
.hc .play{position:absolute;inset:0;display:grid;place-items:center;font-size:23px;color:#fff;
text-shadow:0 2px 10px #000;pointer-events:none;opacity:.88}
.hc .lt{position:absolute;left:6px;right:6px;bottom:6px;font-size:10px;color:#fff;background:rgba(6,8,12,.74);
border-radius:5px;padding:1px 6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
opacity:0;transition:opacity .18s}
.hc:hover .lt{opacity:1}
.hc .lbn{position:absolute;top:6px;left:6px;font-size:10.5px;background:rgba(10,11,15,.8);
border:1px solid rgba(255,183,197,.45);color:#ffb7c5;padding:0 6px;border-radius:5px;
max-width:calc(100% - 12px);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cap{margin-top:6px}
.cap .nt{font-size:11.5px;color:#9aa4b8;line-height:1.45;display:-webkit-box;-webkit-line-clamp:2;
-webkit-box-orient:vertical;overflow:hidden;word-break:break-word}
.cap .tg{display:flex;gap:5px;flex-wrap:wrap;margin-top:5px}
.cap .tg span{font-size:10.5px;color:#ffb7c5;background:rgba(255,183,197,.12);border-radius:4px;padding:0 5px}
.elibs{display:flex;gap:8px;flex-wrap:wrap}
.elibs a{font-size:12px;color:#9aa4b8;text-decoration:none;border:1px solid var(--line);
background:#12151d;border-radius:7px;padding:3px 10px}
.elibs a:hover{color:#ffb7c5;border-color:rgba(255,183,197,.5)}
.big{color:#5b6478;font-size:13.5px;padding:26px 4px;line-height:2}
.big b{color:#c8d0e2}
.hide{display:none!important}
#toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);background:#20242f;color:#f2f5fa;
border:1px solid #333a4a;border-radius:9px;padding:8px 16px;font-size:13px;opacity:0;
transition:opacity .2s,transform .2s;pointer-events:none;z-index:99}
#toast.on{opacity:1;transform:translateX(-50%) translateY(-4px)}
@media(max-width:640px){body{padding:18px 14px 70px}.bar{gap:8px}.search{width:100%}}
</style></head><body>
<h1><span class="mk">🌸 SAKURAVIEW</span>总收藏<em id="hint">按 / 搜索 · R 随机</em></h1>
<div class="stats" id="stats"></div>
<div class="bar">
  <div class="search" id="sbox">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#8892a6" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
    <input id="q" placeholder="搜图库 / 文件名 / 备注 / 标签…" autocomplete="off" spellcheck="false">
    <span class="clr" id="clr" title="清空">×</span>
  </div>
  <button class="vsw on" id="vGroup" type="button">按库分组</button>
  <button class="vsw" id="vMix" type="button">混合时间线</button>
  <button class="vsw" id="vRand" type="button">🎲 随机一张</button>
  <span id="fcount"></span>
  <div id="tagbar" class="hide"></div>
</div>
<div id="libs"></div>
<div id="toast"></div>
<script>window.LIBS=__LIBS__;</script>
<script>
(function(){
'use strict';
var LIBS=window.LIBS||[];
var IMGV=/\.(png|jpe?g|webp|gif|bmp)$/i, VIDV=/\.(mp4|webm|ogv|mkv)$/i;
var $=function(s){return document.querySelector(s)};
function encSeg(s){return encodeURIComponent(s)}
function encPath(p){return String(p).split('/').map(encSeg).join('/')}
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'})[c]})}
function lsGet(k,d){try{var v=localStorage.getItem(k);return v==null?d:JSON.parse(v)}catch(e){return d}}
var toastEl=$('#toast'),toastT=0;
function toast(m){toastEl.textContent=m;toastEl.classList.add('on');clearTimeout(toastT);
toastT=setTimeout(function(){toastEl.classList.remove('on')},1600)}

/* ── 数据：按库读 localStorage（<key>_favs / _notes / _tags） ── */
var DATA=[];
function mk(L,rel){
  var i=rel.lastIndexOf('/'),dir=i<0?'':rel.slice(0,i),bn=rel.slice(i+1);
  var nt=(L.notes&&L.notes[rel])||'';
  var tg=(L.tags&&L.tags[rel])||[];
  if(!Array.isArray(tg))tg=[];
  return {L:L,rel:rel,dir:dir,bn:bn,stem:bn.replace(/\.[^.]+$/,''),isV:VIDV.test(rel),
          note:String(nt||''),tags:tg,
          key:(L.name+' '+rel+' '+nt+' '+tg.join(' ')).toLowerCase()};
}
LIBS.forEach(function(L){
  var favs=lsGet(L.key+'_favs',[]),notes=lsGet(L.key+'_notes',{}),tags=lsGet(L.key+'_tags',{});
  if(!Array.isArray(favs))favs=[];
  L.notes=(notes&&typeof notes==='object')?notes:{};
  L.tags=(tags&&typeof tags==='object')?tags:{};
  /* 收藏页约定为倒序（最近收藏在最前）→ 这里同样反转 */
  L.favs=favs.slice().reverse().filter(function(r){return typeof r==='string'&&r});
  L.items=[];
  L.favs.forEach(function(rel){var d=mk(L,rel);L.items.push(d);DATA.push(d)});
});

/* ── 卡片 ── */
function srcOf(d,kind){
  var pre=d.dir?encPath(d.dir)+'/':'';
  if(kind==='thumb')return d.L.base+'/'+pre+'_thumbs/'+encSeg(d.stem)+'.jpg';
  if(kind==='poster')return d.L.base+'/'+pre+'_poster/'+encSeg(d.stem)+'.jpg';
  return d.L.base+'/'+pre+encSeg(d.bn);
}
function card(d){
  var L=d.L;
  var fig=document.createElement('figure');
  fig.className='hc'+(d.isV?' vid':'');
  var a=document.createElement('a');
  a.className='th';
  a.href=L.base+'/fav.html#open='+encSeg(d.rel);
  a.title=L.name+' · '+d.rel;
  var chain;
  if(d.isV)chain=[srcOf(d,'poster')];
  else chain=L.thumbs?[srcOf(d,'thumb'),srcOf(d,'full')]:[srcOf(d,'full')];
  var img=document.createElement('img');
  img.loading='lazy';img.decoding='async';img.alt='';
  var ci=0;
  img.addEventListener('error',function(){
    ci++;
    if(ci<chain.length){img.src=chain[ci];return}
    fig.classList.add('dead');if(img.parentNode)img.parentNode.removeChild(img);
  });
  img.src=chain[0];
  a.appendChild(img);
  if(d.isV){var pl=document.createElement('span');pl.className='play';pl.textContent='▶';a.appendChild(pl)}
  var lt=document.createElement('span');lt.className='lt';lt.textContent=d.bn;a.appendChild(lt);
  fig.appendChild(a);
  if(d.lb){var b=document.createElement('span');b.className='lbn';b.textContent=L.name;fig.appendChild(b)}
  if(d.note||d.tags.length){
    var cap=document.createElement('div');cap.className='cap';
    if(d.note){var p=document.createElement('p');p.className='nt';p.textContent=d.note;p.title=d.note;cap.appendChild(p)}
    if(d.tags.length){var tw=document.createElement('div');tw.className='tg';
      d.tags.slice(0,4).forEach(function(t){var s=document.createElement('span');s.textContent='#'+t;tw.appendChild(s)});
      cap.appendChild(tw)}
    fig.appendChild(cap);
  }
  fig._d=d;
  return fig;
}

/* ── 渲染 ── */
function grid(ds){var g=document.createElement('div');g.className='hgrid';
  ds.forEach(function(d){g.appendChild(card(d))});return g}
function head(name,cntTxt,meta,acts){
  var h=document.createElement('div');h.className='lh';
  var left='<b>'+esc(name)+'</b><span class="cnt">'+cntTxt+'</span>'+(meta?'<span class="meta">'+esc(meta)+'</span>':'');
  var right=acts?'<span class="acts">'+acts+'</span>':'';
  h.innerHTML=left+right;
  return h;
}
function renderGroup(){
  var host=$('#libs');host.innerHTML='';
  var has=[],none=[];
  LIBS.forEach(function(L){(L.items.length?has:none).push(L)});
  has.forEach(function(L){
    var sec=document.createElement('section');sec.className='slib';sec.dataset.n=L.items.length;
    var meta=L.files?('全库 '+L.files+' 张图 / '+L.groups+' 组'):'';
    sec.appendChild(head(L.name,('<i>'+L.items.length+' 张收藏</i>'),meta,
      '<a href="'+L.base+'/index.html">目录</a><a href="'+L.base+'/fav.html">收藏 →</a>'));
    sec.appendChild(grid(L.items));
    host.appendChild(sec);
  });
  if(none.length){
    var sec=document.createElement('section');sec.className='slib empty';
    sec.appendChild(head('暂无收藏','<i>'+none.length+' 个库</i>','',''));
    var wrap=document.createElement('div');wrap.className='elibs';
    none.forEach(function(L){var a=document.createElement('a');a.href=L.base+'/index.html';a.textContent=L.name;wrap.appendChild(a)});
    sec.appendChild(wrap);host.appendChild(sec);
  }
  if(!DATA.length){
    var b=document.createElement('div');b.className='big';
    b.innerHTML='还没有任何收藏。<br>去任意图库<b>悬停卡片点 ♡</b>，或在分组页<b>框选多张</b>批量收藏，回到这里就会汇总。';
    host.appendChild(b);
  }
}
function renderMix(){
  var host=$('#libs');host.innerHTML='';
  DATA.forEach(function(d){d.lb=true});
  var sec=document.createElement('section');sec.className='slib';sec.dataset.n=String(DATA.length);
  sec.appendChild(head('全部收藏','<i>'+DATA.length+' 张</i>','按各库收藏顺序平铺，最近收藏在前',''));
  sec.appendChild(grid(DATA));
  host.appendChild(sec);
}
var mode='group';
function setMode(m,silent){
  mode=m;
  $('#vGroup').classList.toggle('on',m==='group');
  $('#vMix').classList.toggle('on',m==='mix');
  DATA.forEach(function(d){d.lb=(m==='mix')});
  if(m==='group')renderGroup();else renderMix();
  apply();
  if(!silent){try{localStorage.setItem('sakuraview_hub_view',m)}catch(e){}}
}
$('#vGroup').onclick=function(){setMode('group')};
$('#vMix').onclick=function(){setMode('mix')};

/* ── 过滤：关键词（库名/路径/备注/标签） × 标签 ── */
var tagSel='';
var sbox=$('#sbox'),qEl=$('#q'),fcount=$('#fcount');
function apply(){
  var q=(qEl.value||'').trim().toLowerCase();
  sbox.classList.toggle('has',!!q);
  var shown=0;
  var secs=document.querySelectorAll('#libs section.slib');
  for(var i=0;i<secs.length;i++){
    var sec=secs[i];
    if(sec.classList.contains('empty')){
      var eh=!!(q||tagSel);
      sec.classList.toggle('hide',eh);continue;
    }
    var figs=sec.querySelectorAll('figure.hc'),n=0;
    for(var j=0;j<figs.length;j++){
      var f=figs[j],d=f._d;
      var ok=(!q||d.key.indexOf(q)>=0)&&(!tagSel||d.tags.indexOf(tagSel)>=0);
      f.classList.toggle('hide',!ok);if(ok)n++;
    }
    sec.classList.toggle('hide',(!!(q||tagSel))&&n===0);
    var c=sec.querySelector('.cnt');
    if(c){
      var total=sec.dataset.n;
      c.innerHTML=(q||tagSel)?('<i>'+n+' / '+total+' 张</i>'):('<i>'+total+' 张'+(mode==='group'?'收藏':'')+'</i>');
    }
    shown+=n;
  }
  var on_=!!(q||tagSel);
  fcount.textContent=on_?('筛选出 '+shown+' 张'):'';
  return shown;
}
function renderTagState(){
  var chips=document.querySelectorAll('#tagbar .chip');
  for(var i=0;i<chips.length;i++)chips[i].classList.toggle('on',chips[i].dataset.tag===tagSel);
}
function buildTags(){
  var bar=$('#tagbar'),counts={};
  DATA.forEach(function(d){d.tags.forEach(function(t){if(typeof t==='string'&&t)counts[t]=(counts[t]||0)+1})});
  var keys=Object.keys(counts).sort(function(a,b){return counts[b]-counts[a]});
  if(!keys.length){bar.classList.add('hide');return}
  bar.classList.remove('hide');
  bar.innerHTML='<span class="tl">标签</span>';
  keys.forEach(function(t){
    var b=document.createElement('button');
    b.type='button';b.className='chip';b.dataset.tag=t;b.textContent='#'+t+' '+counts[t];
    b.onclick=function(){tagSel=(tagSel===t?'':t);renderTagState();apply()};
    bar.appendChild(b);
  });
}

/* ── 随机：从当前筛选结果里抽（没有筛选就全量） ── */
function randomOne(){
  var pool=[];
  var figs=document.querySelectorAll('#libs figure.hc');
  for(var i=0;i<figs.length;i++){if(!figs[i].classList.contains('hide')&&!figs[i].classList.contains('dead'))pool.push(figs[i]._d)}
  if(!pool.length)pool=DATA.slice();
  if(!pool.length){toast('还没有任何收藏');return}
  var d=pool[Math.floor(Math.random()*pool.length)];
  location.href=d.L.base+'/fav.html#open='+encSeg(d.rel);
}
$('#vRand').onclick=randomOne;

/* ── 统计 ── */
var total=0,on=0,allFiles=0,allGroups=0;
LIBS.forEach(function(L){
  allFiles+=L.files||0;allGroups+=L.groups||0;
  total+=L.items.length;if(L.items.length)on++;
});
$('#stats').innerHTML='共 <b>'+total+'</b> 张收藏 · <b>'+on+'</b> / '+LIBS.length+' 个图库有收藏 · 全库 <b>'+allFiles+'</b> 张图 / <b>'+allGroups+'</b> 组 · 数据只存本浏览器，迁移用各库收藏页的导出/导入';

qEl.addEventListener('input',apply);
$('#clr').addEventListener('click',function(){qEl.value='';apply();qEl.focus()});
document.addEventListener('keydown',function(e){
  var tag=(e.target.tagName||'').toLowerCase();
  var typing=tag==='input'||tag==='textarea'||e.target.isContentEditable;
  if(e.key==='/'&&!typing){e.preventDefault();qEl.focus();qEl.select();return}
  if(e.key==='Escape'){
    if(qEl.value){qEl.value='';apply()}
    else if(tagSel){tagSel='';renderTagState();apply()}
    else if(document.activeElement===qEl)qEl.blur();
    return;
  }
  if(!typing&&(e.key==='r'||e.key==='R')){e.preventDefault();randomOne()}
});

buildTags();
var saved='group';
try{saved=localStorage.getItem('sakuraview_hub_view')||'group'}catch(e){}
setMode(saved==='mix'?'mix':'group',true);
if(!DATA.length){$('#hint').textContent='还没有收藏';}
})();
</script></body></html>"""

def _nav_stats(out_dir, base):
    """读 <lib>/assets/nav.js 里的 window.NAV，汇总图片数与分组数（读不到返回 0,0）"""
    p = os.path.join(out_dir, base.replace('/', os.sep), 'assets', 'nav.js')
    try:
        with open(p, encoding='utf-8') as f:
            txt = f.read()
        m = re.search(r'window\.NAV=(\{.*\});?\s*$', txt, re.S)
        if not m:
            return 0, 0
        nav = json.loads(m.group(1))
        groups = sum(len(g.get('items', [])) for g in nav.get('groups', []))
        files = sum(int(i.get('k', 0)) for g in nav.get('groups', []) for i in g.get('items', []))
        return files, groups
    except Exception:
        return 0, 0

def _has_dir(root, name, cap=6000):
    """root 下是否存在名为 name 的目录（缩略图/海报按子目录分散存放，命中即返回）"""
    if not os.path.isdir(root):
        return False
    n = 0
    for dp, dns, _ in os.walk(root):
        if name in dns:
            return True
        n += 1
        if n > cap:
            return False
    return False

def _load_cfg():
    cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hub_libs.json')
    if os.path.exists(cfg):
        with open(cfg, encoding='utf-8') as f:
            return json.load(f)
    return None

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('output', nargs='?')
    ap.add_argument('--lib', action='append',
                    help='格式: 显示名|相对路径|key （可多次；缺省读 hub_libs.json）')
    a = ap.parse_args()
    cfg = _load_cfg()
    if a.lib:
        libs = []
        for spec in a.lib:
            name, base, key = spec.split('|')
            libs.append({'name': name, 'base': base.rstrip('/'), 'key': key})
    elif cfg:
        libs = cfg['libs']
    else:
        print('未找到 hub_libs.json，且未给 --lib'); sys.exit(1)
    output = a.output or (cfg or {}).get('output') or 'SakuraView-hub.html'
    out_dir = os.path.dirname(os.path.abspath(output))
    for L in libs:
        L['base'] = L['base'].rstrip('/')
        absbase = os.path.join(out_dir, L['base'].replace('/', os.sep))
        f, g = _nav_stats(out_dir, L['base'])
        L['files'], L['groups'] = f, g
        L['thumbs'] = _has_dir(absbase, '_thumbs')
    html = TPL.replace('__LIBS__', json.dumps(libs, ensure_ascii=False))
    os.makedirs(out_dir, exist_ok=True)
    with open(output, 'w', encoding='utf-8') as f:
        f.write(html)
    print('已生成:', output)
    tf = sum(L.get('files', 0) for L in libs)
    tg = sum(L.get('groups', 0) for L in libs)
    print('  合计 %d 张图 / %d 组' % (tf, tg))
    for L in libs:
        print('  库: %-26s → %-44s (%s) %s %s' % (
            L['name'], L['base'], L['key'],
            ('%d 图/%d 组' % (L['files'], L['groups'])) if L.get('files') else '无 nav.js 统计',
            '缩略图✓' if L['thumbs'] else '缩略图✗(回退原图)'))
