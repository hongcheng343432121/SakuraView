(function(){
const FAV_KEY='demo_favs',NOTE_KEY='demo_notes';
let favOrder=[],notes={};
try{favOrder=JSON.parse(localStorage.getItem(FAV_KEY)||'[]')}catch(e){}
let favSet=new Set(favOrder);
try{notes=JSON.parse(localStorage.getItem(NOTE_KEY)||'{}')}catch(e){}
function saveFav(){try{localStorage.setItem(FAV_KEY,JSON.stringify(favOrder))}catch(e){}}
function saveNotes(){try{localStorage.setItem(NOTE_KEY,JSON.stringify(notes))}catch(e){}}
const TAGS_KEY='demo_tags';
let tags={};
try{tags=JSON.parse(localStorage.getItem(TAGS_KEY)||'{}')}catch(e){}
function saveTags(){try{localStorage.setItem(TAGS_KEY,JSON.stringify(tags))}catch(e){}}
const RECENT_KEY='demo_recent_'+location.pathname;
let recentRel='';
try{recentRel=localStorage.getItem(RECENT_KEY)||''}catch(e){}
/* 最近查看：图片灯箱 / 视频播放器共用同一状态，退出后仍保留高亮 */
function markRecent(rel){
if(!rel||rel===recentRel)return;
recentRel=rel;
try{localStorage.setItem(RECENT_KEY,rel)}catch(e){}
if(!grid)return;
grid.querySelectorAll('figure.item').forEach(function(f){
f.classList.toggle('seen',f.dataset.rel===rel);});
}
/* 目录树折叠：显式设置过的分类记住用户选择，未动过的默认收起（当前页/当前过滤所在分类默认展开） */
const CAT_KEY='demo_catopen';
const DUP_KEY='demo_dupv2';   /* 差分是否叠起（0/缺省=平铺直接看图，1=叠成一张），跨页记住 */
var catState={};
try{catState=JSON.parse(localStorage.getItem(CAT_KEY)||'{}')}catch(e){}
function catOpen(name,isActive){return (name in catState)?!!catState[name]:!!isActive}
function saveCatState(){try{localStorage.setItem(CAT_KEY,JSON.stringify(catState))}catch(e){}}
function catHead(name,label,count,open){
return '<div class="cat'+(open?' open':'')+'" data-cat="'+esc(name)+'">'
+'<div class="cat-h"><span class="ch">&#9656;</span><span class="ct2">'+esc(label)+'</span><em>'+count+'</em></div>'
+'<div class="cat-body"><div class="cat-in">';
}
var CAT_END='</div></div></div>';
const PAGE=window.PAGE||{items:[]};
const items=PAGE.items||[];
const grid=document.getElementById('grid');
const lb=document.getElementById('lb'),lbImg=document.getElementById('lbImg');
const lbName=document.getElementById('lbName'),lbIdx=document.getElementById('lbIdx');
const lbFav=document.getElementById('lbFav');
const noteModal=document.getElementById('noteModal'),noteInput=document.getElementById('noteInput');
const tagInput=document.getElementById('tagInput');
const modalThumb=document.getElementById('modalThumb');
const q=document.getElementById('q');
let noteRel=null,cur=[],pos=-1;
const KIND=document.querySelector('.cards')?'index':(/fav\.html$/.test(location.pathname)?'fav':'group');
function esc(s){return String(s).replace(/[&<>"]/g,function(c){
return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];})}
function encPath(p){return String(p).split('/').map(encodeURIComponent).join('/')}
/* 视频海报帧：与视频同目录的 _poster/<名称>.jpg（由 gen_posters.py 批量生成） */
function posterFor(rel){var i=rel.lastIndexOf('/');
var b=rel.slice(i+1).replace(/\.[^.]+$/,'');
return (i<0?'_poster/':rel.slice(0,i)+'/_poster/')+b+'.jpg'}
/* 缩略图：同目录 _thumbs/<名称>.jpg（gen_thumbs.py 生成），缺失时 onerror 回退原图 */
function thumbFor(rel){var i=rel.lastIndexOf('/');
var b=rel.slice(i+1).replace(/\.[^.]+$/,'');
return (i<0?'_thumbs/':rel.slice(0,i)+'/_thumbs/')+b+'.jpg'}
/* 轻提示：复用右下角 #ztoast，不新增按钮 */
var toastT=null;
function toast(t){
var el=document.getElementById('ztoast');
if(!el){el=document.createElement('div');el.id='ztoast';document.body.appendChild(el)}
el.textContent=t;el.classList.add('show');
clearTimeout(toastT);toastT=setTimeout(function(){el.classList.remove('show')},1300);
}
/* 收藏页：数量 / 副标题 / 空状态统一刷一次，避免分批渲染时数不准 */
var favFilter=null,favQ='';
function relDir(rel){var i=rel.lastIndexOf('/');return i<0?'':rel.slice(0,i)}
/* 收藏页增强：随机看图 + 按目录分组视图（跨库场景在总收藏 Hub 里按库分组） */
var favGrouped=false;
function groupFavByDir(on){
if(KIND!=='fav'||!grid)return;
var olds=grid.querySelectorAll('.grphead');
for(var i=0;i<olds.length;i++)olds[i].remove();
if(!on){favGrouped=false;return}
favGrouped=true;
var fs=Array.prototype.slice.call(grid.querySelectorAll('figure.item'));
var map={},order=[];
fs.forEach(function(f){
var p=f.dataset.rel.split('/'),d=p.slice(0,p.length-1).join('/')||'（根目录）';
if(!map[d]){map[d]=[];order.push(d)}map[d].push(f)});
order.sort();
order.forEach(function(d){
var h=document.createElement('div');h.className='grphead';
h.innerHTML='<span>'+esc(d)+'</span><em>'+map[d].length+' 张</em>';
grid.appendChild(h);
map[d].forEach(function(f){grid.appendChild(f)})});
}
if(KIND==='fav'&&grid){
var bRandom=document.getElementById('favRandom'),bGroup=document.getElementById('favGroup');
if(bRandom)bRandom.onclick=function(e){e.preventDefault();
var list=visible();if(!list.length){toast('当前没有可看的收藏');return}
openLb(list[Math.floor(Math.random()*list.length)])};
if(bGroup)bGroup.onclick=function(e){e.preventDefault();
groupFavByDir(!favGrouped);
bGroup.innerHTML=favGrouped?'&#9776; 平铺':'&#9776; 分组';
toast(favGrouped?'已按目录分组':'已切回平铺')};
}
function refreshFavUI(){
if(KIND!=='fav'||!grid)return;
if(favFilter||favQ){applyFavFilters();return}
var n=grid.querySelectorAll('figure.item').length;
var c=document.getElementById('fcnt');if(c)c.textContent=n;
var em=document.getElementById('favEmpty');if(em)em.style.display=n?'none':'';
var s=document.getElementById('fsub');
if(s)s.textContent=n?('共 '+n+' 个收藏 · 最近收藏在最前'):'还没有收藏，回目录挑几张点 ♡';
buildFavNav();
}
/* 收藏页目录导航：只列出「实际有收藏的目录」，与图片实时联动 */
function applyFavFilters(){
if(KIND!=='fav'||!grid)return;
if(favFilter){var ok=false;items.forEach(function(it){if(relDir(it[0])===favFilter)ok=true});
if(!ok)favFilter=null;}
var shown=0,total=items.length;
grid.querySelectorAll('figure.item').forEach(function(f){
var hit=true;
if(favFilter)hit=relDir(f.dataset.rel)===favFilter;
if(hit&&favQ){var t=(f.dataset.name+' '+f.dataset.rel).toLowerCase();hit=t.indexOf(favQ)>=0}
if(hit&&tagFilter)hit=(tags[f.dataset.rel]||[]).indexOf(tagFilter)>=0;
f.style.display=hit?'':'none';if(hit)shown++;
});
fixStacks();
var e=document.getElementById('emp');
if(!shown&&total){ensureEmp(favFilter?'该目录下暂无匹配的收藏':'没有匹配的内容','换个关键词，或点左侧「全部」')}
else if(e){e.style.display='none'}
var c=document.getElementById('fcnt');if(c)c.textContent=shown;
var s=document.getElementById('fsub');
if(s)s.textContent=!total?'还没有收藏，回目录挑几张点 ♡':(shown===total?('共 '+total+' 个收藏 · 最近收藏在最前'):('筛选出 '+shown+' / '+total+' 个收藏'));
buildFavNav();
}
function buildFavNav(){
if(KIND!=='fav'||!navbox)return;
var st=navbox.scrollTop;
/* 取消收藏后以 DOM 为准；初始构建时 render 还没跑，退回 items */
var src=[];
if(grid&&grid.children.length){
grid.querySelectorAll('figure.item').forEach(function(f){src.push(f.dataset.rel)});
}else{
items.forEach(function(it){src.push(it[0])});
}
var m={};
src.forEach(function(rel){
var d=relDir(rel);if(!d)return;
var c=d.split('/')[0];
(m[c]=m[c]||{})[d]=(m[c][d]||0)+1;
});
var nh='<a class="nav-item" href="index.html">&#9776; 目录总览</a>';
nh+='<a class="nav-item'+(favFilter?'':' on')+'" data-g="">&#9825; 全部 <em>'+items.length+'</em></a>';
var activeCat=favFilter?favFilter.split('/')[0]:null;
Object.keys(m).map(function(c){
var gs=m[c],tot=0;Object.keys(gs).forEach(function(k){tot+=gs[k]});
return {c:c,gs:gs,tot:tot};
}).sort(function(a,b){return b.tot-a.tot||a.c.localeCompare(b.c)}).forEach(function(o){
nh+=catHead(o.c,o.c,o.tot,catOpen(o.c,o.c===activeCat));
Object.keys(o.gs).map(function(g){return {g:g,k:o.gs[g]}})
.sort(function(a,b){return b.k-a.k||a.g.localeCompare(b.g)}).forEach(function(gi){
var short=gi.g.split('/').slice(1).join('/')||gi.g;
nh+='<a class="nav-item'+(favFilter===gi.g?' on':'')+'" data-g="'+esc(gi.g)+'" title="'+esc(gi.g)+'">'
+esc(short)+'<em>'+gi.k+'</em></a>';
});
nh+=CAT_END;
});
navbox.innerHTML=nh;navbox.scrollTop=st;
buildTagNav();
}
/* 侧栏标签维度：列出当前页出现过的标签，点选过滤（与搜索/横竖图/收藏目录叠加） */
var tagFilter='';
function buildTagNav(){
if(!navbox||(KIND!=='group'&&KIND!=='fav'))return;
var counts={};
Object.keys(tags).forEach(function(rel){
(tags[rel]||[]).forEach(function(t){counts[t]=(counts[t]||0)+1})});
var old=document.getElementById('tagcat');if(old)old.remove();
var names=Object.keys(counts).sort(function(a,b){return counts[b]-counts[a]||a.localeCompare(b)});
if(!names.length)return;
var st=navbox.scrollTop;
/* 开关状态尊重用户：显式设置过按用户来，没动过默认展开 */
var d=document.createElement('div');d.id='tagcat';
d.className='cat'+(catOpen('__tags__',true)?' open':'');d.dataset.cat='__tags__';
var h='<div class="cat-h"><span class="ch">&#9656;</span><span class="ct2">标签</span><em>'+names.length+'</em></div><div class="cat-body"><div class="cat-in">';
names.forEach(function(t){
h+='<a class="nav-item'+(tagFilter===t?' on':'')+'" data-tag="'+esc(t)+'">'+esc(t)+'<em>'+counts[t]+'</em></a>'});
d.innerHTML=h+'</div></div>';
navbox.appendChild(d);navbox.scrollTop=st;
}
function syncFavNav(rel){
if(KIND!=='fav'||!navbox||!rel)return;
var d=relDir(rel);if(!d)return;
navbox.querySelectorAll('a[data-g]').forEach(function(a){
var hit=a.dataset.g===d;
a.classList.toggle('on',hit);
if(hit){var cat=a.closest('.cat');
/* 联动到的分类若收起则自动展开，保证高亮可见 */
if(cat&&!cat.classList.contains('open')){cat.classList.add('open');
if(cat.dataset.cat){catState[cat.dataset.cat]=true;saveCatState()}}}
});
}
function ensureEmp(msg,sub,hint){
var host=grid?grid.parentNode:document.querySelector('.wrap');
if(!host)return null;
var e=document.getElementById('emp');
if(!e){e=document.createElement('div');e.id='emp';e.className='empty';
e.innerHTML='<div class="big">&#9825;</div><b></b><span></span>';host.appendChild(e)}
e.querySelector('b').textContent=msg;
e.querySelector('span').textContent=sub||'';
e.style.display='';
var fe=document.getElementById('favEmpty');if(fe)fe.style.display='none';
return e;
}
/* 差分折叠：同一场景的差分（y09_05_001/002/003…）叠成一张卡，右下角标数量。
   被叠起来的 figure 仍留在 DOM 里（只是 opacity:0），所以灯箱里 ←→ 照样能翻到每一张差分。
   判断依据：去掉末尾数字后的“基名”相同且相邻。立绘那种 001活01/002活02 基名不同，不会误折叠。 */
function baseOf(rel){
var b=rel.slice(rel.lastIndexOf('/')+1).replace(/\.[^.]+$/,'');
var s=b.replace(/[_\-\s.]?\d+$/,'');
var core=s.replace(/[\s_\-]+$/,'');
/* 只有「去掉序号后还剩至少两段」才当差分折叠。
   否则 dd 1..243 / 1..456 / cg1..cg999 这种顺序命名会被整页叠成一张（实测 Ripples 456→1）。 */
if(!core||!/[\s_\-]/.test(core))return b;
return s;
}
function itemHTML(it){
var rel=it[0],w=it[1],hh=it[2],isv=it[3];
var nm=rel.split('/').pop(),qq=encPath(rel);
var fav=favSet.has(rel),nt=notes[rel]||'';
var oc=isv?'v':(w&&hh?(w>=hh?'l':'p'):'l');
var h=[];
h.push('<figure class="item'+(isv?' item-v':'')+(fav?' fav':'')+(nt?' has-note':'')+(rel===recentRel?' seen':'')+'"'+(isv?'':' data-src="'+esc(qq)+'"')+' data-rel="'+esc(rel)+'" data-o="'+oc+'" data-name="'+esc(nm)+'">');
h.push('<div class="acts"><button class="act act-fav" title="收藏">'+(fav?'&#9829;':'&#9825;')+'</button>');
h.push('<button class="act act-note" title="备注">&#128172;</button></div>');
if(isv){h.push('<video preload="none" muted playsinline poster="'+esc(encPath(posterFor(rel)))+'" src="'+qq+'"></video>');}
else{var wh=(w&&hh)?' width="'+w+'" height="'+hh+'"':'';
h.push('<img loading="lazy" decoding="async" src="'+esc(encPath(thumbFor(rel)))+'" data-orig="'+esc(qq)+'" onerror="this.onerror=null;this.src=this.dataset.orig"'+wh+' alt="">');}
h.push('<figcaption title="'+esc(rel)+'">'+esc(nm)+'</figcaption>');
if(nt)h.push('<div class="note" title="'+esc(nt)+'">&#128172; '+mdInline(nt)+'</div>');
const tl=tags[rel]||[];
if(tl.length)h.push('<div class="tagrow">'+tl.map(function(x){return '<span class="tagchip" data-tag="'+esc(x)+'">'+esc(x)+'</span>'}).join('')+'</div>');
h.push('</figure>');
return h.join('');
}
/* 过滤/搜索后修正叠层：让「栈里第一个可见的」显形，整栈都没了就收起。
   已摊开（.flat）的栈不参与——它的每张都要正常显示。 */
function fixStacks(){
document.querySelectorAll('.stack').forEach(function(s){
if(s.classList.contains('flat')){
[].forEach.call(s.children,function(f){if(f.tagName==='FIGURE'){f.style.opacity='1';f.style.pointerEvents=''}});
s.style.display='';return;
}
var kids=[].slice.call(s.children).filter(function(f){return f.tagName==='FIGURE'}),vis=null,rec=null;
kids.forEach(function(f){
if(f.style.display==='none'||f.classList.contains('hide'))return;
if(!vis)vis=f;
if(recentRel&&f.dataset.rel===recentRel)rec=f;
});
/* 顶层优先显示「最近看过的那张」：看完第 7 张退出来，卡片就停在第七张，不用满栈找 */
var top=rec||vis;
/* 必须显式写 1：清空内联样式的话，CSS 里 .stack>figure:not(:first-of-type){opacity:0} 依旧生效 */
kids.forEach(function(f){
f.style.opacity=(f===top?'1':'0');
f.style.pointerEvents=(f===top?'':'none');
});
s.style.display=vis?'':'none';
var n=kids.filter(function(f){return f.style.display!=='none'&&!f.classList.contains('hide')}).length;
s.dataset.n=n||kids.length;
});
}
/* 最近查看变了（关灯箱 / 翻页）时重算 .seen 标记，并让对应的栈浮到顶层 */
function refreshSeen(){
document.querySelectorAll('figure.item').forEach(function(f){
f.classList.toggle('seen',!!recentRel&&f.dataset.rel===recentRel);
});
fixStacks();
}
/* 差分「平铺/叠起」：**默认平铺**（每张都显示，直接看图）；点导航栏 chip 才叠起来。
   切换要重建网格（plan 结构变了），所以直接 render()，并把状态按库记住。 */
function applyDupMode(expand,btn){
dupExpand=!!expand;
if(btn){
btn.classList.toggle('on',dupExpand);
var n=btn.getAttribute('data-n')||'';
btn.textContent=dupExpand?'平铺显示':('叠起差分'+(n?(' '+n+' 组'):''));
btn.title=dupExpand?'当前：同一场景的差分叠成一张。点这里恢复平铺（每张都显示）'
                   :'当前：每张都平铺显示。点这里把同一场景的差分叠成一张（右下角会标 +N）';
}
try{localStorage.setItem(DUP_KEY,dupExpand?'1':'0')}catch(e){}
}
var dupChip=document.getElementById('dupChip'),dupExpand=false;
try{dupExpand=localStorage.getItem(DUP_KEY)==='1'}catch(e){}
if(dupChip){
if(!dupChip.getAttribute('data-n')){
var mm=(dupChip.textContent||'').match(/(\d+)/);
if(mm)dupChip.setAttribute('data-n',mm[1]);
}
applyDupMode(dupExpand,dupChip);
dupChip.addEventListener('click',function(e){
e.preventDefault();
applyDupMode(!dupExpand,dupChip);
if(typeof render==='function')render();
toast(dupExpand?'差分已叠起（点角标可看整组）':'已恢复平铺');
});
}
if(grid){
grid.addEventListener('click',function(e){
var b=e.target.closest&&e.target.closest('.dupbadge');
if(!b)return;
e.preventDefault();e.stopPropagation();
openDup(b.parentNode);
},true);
}
/* 差分速览弹层：列出这一组每一张的小缩略图，点哪张就进灯箱看哪张 */
var dupPanel=document.getElementById('dupPanel'),dpGrid=document.getElementById('dpGrid');
function stackFigs(s){return [].slice.call(s.children).filter(function(f){return f.tagName==='FIGURE'})}
function openDup(stack){
if(!dupPanel||!stack)return;
var figs=stackFigs(stack);
document.getElementById('dpTitle').textContent='差分速览 · '+figs.length+' 张';
document.getElementById('dpSub').textContent=(figs[0].dataset.name||'')+' —— 点任意一张直接全屏查看，←→ 继续翻这一组';
dpGrid.innerHTML=figs.map(function(f,i){
var rel=f.dataset.rel;
return '<div class="dp-item" data-i="'+i+'" title="'+esc(rel)+'">'
+'<img loading="lazy" decoding="async" src="'+esc(encPath(thumbFor(rel)))+'" data-orig="'+esc(encPath(rel))+'" '
+'onerror="this.onerror=null;this.src=this.dataset.orig" alt=""><b>'+(i+1)+'</b></div>';
}).join('');
dupPanel.classList.add('open');
dupPanel._stack=stack;
}
function closeDup(){if(!dupPanel)return;dupPanel.classList.remove('open');dupPanel._stack=null}
if(dupPanel){
dpGrid.addEventListener('click',function(e){
var it=e.target.closest&&e.target.closest('.dp-item');if(!it)return;
var s=dupPanel._stack;if(!s)return;
var idx=+it.dataset.i,f=stackFigs(s)[idx];
closeDup();
if(f)openLb(f);
});
dupPanel.addEventListener('click',function(e){if(e.target===dupPanel)closeDup()});
var dpc=document.getElementById('dpClose');if(dpc)dpc.addEventListener('click',closeDup);
document.addEventListener('keydown',function(e){
if(e.key==='Escape'&&dupPanel.classList.contains('open')){
e.stopImmediatePropagation();e.preventDefault();closeDup();
}
},true);
}
function render(){
if(!grid)return;
grid.innerHTML='';
if(!items.length)return;
/* 差分默认**不折叠**——用户明确要求「我要直接看图」，所以每张都平铺。
   想叠起来看再点导航栏的「叠起差分」，这时才按基名聚合（收藏页永远不聚合）。 */
var plan=[];
if(KIND==='fav'||!dupExpand){
items.forEach(function(it){plan.push([it])});
}else{
var byBase={};
items.forEach(function(it){
var b=baseOf(it[0]);
if(!byBase[b]){byBase[b]=[];plan.push(byBase[b])}
byBase[b].push(it);
});
}
var pi=0;
function flush(){
var h=[],cnt=0;
while(pi<plan.length&&cnt<70){
var g=plan[pi++];cnt+=g.length;
if(g.length>1){
h.push('<div class="stack" data-n="'+g.length+'"><span class="dupbadge" title="点这里看这一组的所有差分">+'+g.length+' 差分</span>');
for(var k=0;k<g.length;k++)h.push(itemHTML(g[k]));
h.push('</div>');
}else h.push(itemHTML(g[0]));
}
grid.insertAdjacentHTML('beforeend',h.join(''));
if(pi<plan.length)requestAnimationFrame(flush);else refreshSeen();
}
flush();
}
if(q){
q.addEventListener('input',function(){
const v=q.value.trim().toLowerCase();let n=0;
/* 目录页：按分组卡片过滤，整块分类空了就一起收起 */
if(KIND==='index'){
document.querySelectorAll('.catblock').forEach(function(blk){
var any=false;
blk.querySelectorAll('.card').forEach(function(c){
var hit=!v||c.textContent.toLowerCase().indexOf(v)>=0;
c.style.display=hit?'':'none';if(hit){any=true;n++}
});
blk.style.display=any?'':'none';
});
var e0=document.getElementById('emp');
if(!n){ensureEmp('没有匹配的分组','换个关键词，或清空搜索框')}
else if(e0){e0.style.display='none'}
var sb=document.getElementById('isub');
if(sb)sb.textContent=v?('筛选出 '+n+' 个分组'):sb.dataset.all;
return;
}
if(KIND==='fav'){favQ=v;applyFavFilters();return}
gq=v;applyGroupFilters();
});}
/* 分组页：关键词 + 横竖图 + 标签筛选叠加 */
var gq='',curOrient='',tagFilter='';
function applyGroupFilters(){
if(KIND!=='group'||!grid)return;
var n=0;
grid.querySelectorAll('figure.item').forEach(function(f){
var hit=true;
if(gq){var t=(f.dataset.name+' '+f.dataset.rel).toLowerCase();hit=t.indexOf(gq)>=0}
if(hit&&curOrient)hit=f.dataset.o===curOrient;
if(hit&&tagFilter)hit=(tags[f.dataset.rel]||[]).indexOf(tagFilter)>=0;
f.style.display=hit?'':'none';if(hit)n++;});
fixStacks();
var e=document.getElementById('emp');
if(!n&&items.length){ensureEmp('没有匹配的内容','换个关键词或切换筛选')}
else if(e){e.style.display='none'}
buildTagNav();
}
var orientChips=document.getElementById('orientChips');
if(orientChips){orientChips.addEventListener('click',function(e){
var c=e.target.closest&&e.target.closest('.chip');if(!c)return;
curOrient=c.dataset.o||'';
orientChips.querySelectorAll('.chip').forEach(function(x){x.classList.toggle('on',x===c)});
applyGroupFilters();
});}
/* 收藏页：导出 / 导入收藏与备注 + 显示设置（JSON，跨设备迁移用） */
if(KIND==='fav'){
var expBtn=document.getElementById('expBtn');
if(expBtn)expBtn.onclick=function(){
toast('导出中…');
var K=FAV_KEY.replace('_favs','');
var data={app:'SakuraView',v:1,key:K,
exported:new Date().toISOString().slice(0,10),favs:favOrder.slice(),notes:notes,tags:tags,
settings:{zm:localStorage.getItem(K+'_zm'),zn:localStorage.getItem(K+'_zn'),
cat:localStorage.getItem(CAT_KEY)}};
try{var blob=new Blob([JSON.stringify(data,null,1)],{type:'application/json'});
var a=document.createElement('a');a.href=URL.createObjectURL(blob);
a.download='sakuraview-'+data.key+'-'+data.exported+'.json';
document.body.appendChild(a);a.click();
setTimeout(function(){URL.revokeObjectURL(a.href);a.remove()},800);
toast('已导出 '+favOrder.length+' 个收藏 / '+Object.keys(notes).length+' 条备注');
}catch(x){toast('导出失败：'+x.message)}};
var impBtn=document.getElementById('impBtn'),impFile=document.getElementById('impFile');
if(impBtn&&impFile){impBtn.onclick=function(){impFile.click()};
impFile.onchange=function(){
var f=impFile.files&&impFile.files[0];impFile.value='';if(!f)return;
var r=new FileReader();
r.onload=function(){var d;try{d=JSON.parse(r.result)}catch(x){toast('导入失败：不是有效的 JSON');return}
if(!d||!Array.isArray(d.favs)){toast('导入失败：文件里缺少 favs');return}
var addF=0,addN=0,addS=0,addT=0;
d.favs.forEach(function(rel){if(rel&&!favSet.has(rel)){favSet.add(rel);favOrder.push(rel);addF++}});
if(d.notes)Object.keys(d.notes).forEach(function(k){
if(d.notes[k]&&!(k in notes)){notes[k]=String(d.notes[k]).slice(0,200);addN++}});
if(d.tags)Object.keys(d.tags).forEach(function(k){
var arr=(d.tags[k]||[]).filter(function(x){return typeof x==='string'&&x}).slice(0,8);
if(arr.length&&!(k in tags)){tags[k]=arr;addT++}});
if(d.settings){var K=FAV_KEY.replace('_favs','');
['zm','zn'].forEach(function(s){if(d.settings[s]){try{localStorage.setItem(K+'_'+s,d.settings[s]);addS++}catch(x){}}});
if(d.settings.cat){try{localStorage.setItem(CAT_KEY,d.settings.cat);addS++}catch(x){}}}
saveFav();saveNotes();saveTags();
toast('导入 '+addF+' 个收藏 / '+addN+' 条备注'+(addT?' / '+addT+' 组标签':'')+(addS?' / '+addS+' 项设置':'')+'，刷新中…');
setTimeout(function(){location.reload()},800);};
r.onerror=function(){toast('读取文件失败')};
r.readAsText(f)};
}
}
function toggleFav(rel){
const on=!favSet.has(rel);
if(on){favSet.add(rel);favOrder.push(rel)}else{favSet.delete(rel);favOrder=favOrder.filter(function(r){return r!==rel})}
saveFav();
const drop=(KIND==='fav'&&!on);
grid.querySelectorAll('figure.item').forEach(function(f){
if(f.dataset.rel!==rel)return;
if(!drop){
f.classList.toggle('fav',on);
const b=f.querySelector('.act-fav');if(b)b.innerHTML=on?'&#9829;':'&#9825;';return;
}
/* 收藏页取消收藏：直接撤掉这张卡，别留着让人以为还收藏着 */
if(lb.classList.contains('open')){if(f.parentNode)f.remove();return}
f.style.transition='opacity .16s,transform .16s,box-shadow .16s';
f.style.opacity='0';f.style.transform='scale(.97)';
setTimeout(function(){if(f.parentNode){f.remove();refreshFavUI()}},160);
});
if(drop){
if(lb.classList.contains('open')){
refreshFavUI();cur=visible();
if(!cur.length){closeLb();return}
if(pos>cur.length-1)pos=cur.length-1;
show();return;
}
toast('已取消收藏 · 从收藏夹移除');
return;
}
if(lb.classList.contains('open'))syncLb();
}
function openNote(rel){
slideStop();noteRel=rel;noteInput.value=notes[rel]||'';
tagInput.value=(tags[rel]||[]).join(' ');
const f=grid.querySelector('figure.item[data-rel="'+rel.replace(/"/g,'\\"')+'"]');
if(f&&!f.querySelector('video')){modalThumb.src=f.dataset.src;modalThumb.style.display=''}
else{modalThumb.removeAttribute('src');modalThumb.style.display='none'}
noteModal.classList.add('open');setTimeout(function(){noteInput.focus()},60);
}
function closeNote(){noteModal.classList.remove('open');noteRel=null}
function parseTags(s){return s.split(/[\s,，、]+/).map(function(t){return t.trim().slice(0,20)})
.filter(function(t,i,a){return t&&a.indexOf(t)===i}).slice(0,8)}
/* 备注的 Markdown 简写：**粗体** / `代码` / #标签（渲染前先 esc，安全）
   存储仍是原始文本，标签只做展示 + 保存时把 #xxx 合并进 tags（不改变导出格式） */
function mdInline(t){
var s=esc(String(t||''));
s=s.replace(/\*\*([^*]+)\*\*/g,'<b>$1</b>');
s=s.replace(/`([^`]+)`/g,'<code>$1</code>');
s=s.replace(/(^|[\s，。,.!?！？])#([^\s#<>]{1,16})/g,'$1<span class="mdtag">#$2</span>');
return s.replace(/\s+/g,' ');}
function hashTags(t){
var out=[],m,re=/(^|[\s，。,.!?！？])#([^\s#<>]{1,16})/g;
while((m=re.exec(String(t||''))))out.push(m[2]);
return out.filter(function(x,i,a){return a.indexOf(x)===i})}
function commitNote(){
const t=noteInput.value.trim();
if(t)notes[noteRel]=t;else delete notes[noteRel];
var tg=parseTags(tagInput.value);
/* 备注里写的 #标签 自动并入标签表（渲染仍按原文） */
hashTags(t).forEach(function(x){if(tg.indexOf(x)<0&&tg.length<8)tg.push(x)});
if(tg.length)tags[noteRel]=tg;else delete tags[noteRel];
saveNotes();saveTags();
const rel=noteRel;
grid.querySelectorAll('figure.item').forEach(function(f){
if(f.dataset.rel!==rel)return;
let el=f.querySelector('.note');
if(!t){if(el)el.remove();f.classList.remove('has-note');return}
if(!el){el=document.createElement('div');el.className='note';f.appendChild(el)}
el.innerHTML='&#128172; '+mdInline(t);el.title=t;f.classList.add('has-note');
let tr=f.querySelector('.tagrow');
const list=tags[rel]||[];
if(list.length){if(!tr){tr=document.createElement('div');tr.className='tagrow';f.appendChild(tr)}
tr.innerHTML=list.map(function(x){return '<span class="tagchip">'+esc(x)+'</span>'}).join('')}
else if(tr)tr.remove();});
buildTagNav();closeNote();
}
if(document.getElementById('noteSave')){
document.getElementById('noteSave').onclick=commitNote;
document.getElementById('noteCancel').onclick=closeNote;
document.getElementById('noteDel').onclick=function(){
delete notes[noteRel];saveNotes();
delete tags[noteRel];saveTags();
const rel=noteRel;
grid.querySelectorAll('figure.item').forEach(function(f){
if(f.dataset.rel!==rel)return;
const el=f.querySelector('.note');if(el)el.remove();f.classList.remove('has-note');
const tr=f.querySelector('.tagrow');if(tr)tr.remove();});
buildTagNav();closeNote();};
noteModal.addEventListener('click',function(e){if(e.target===noteModal)closeNote()});
noteInput.addEventListener('keydown',function(e){
if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();commitNote()}});
}
/* ---------- 批量选择：Shift 点选 / 空白处拖框 / 批量收藏 · 批量加标签 ---------- */
var selSet=new Set(),selAnchor=null,bandEl=document.getElementById('selBand'),bandOn=false,bandStart=null;
var selBar=document.getElementById('selBar');
function figs(){return Array.prototype.slice.call(grid.querySelectorAll('figure.item')).filter(function(f){return f.style.display!=='none'})}
function applySelClasses(){if(!grid)return;
grid.querySelectorAll('figure.item').forEach(function(f){f.classList.toggle('sel',selSet.has(f.dataset.rel))})}
function refreshSel(){if(!selBar)return;
document.getElementById('selN').textContent=selSet.size;
selBar.classList.toggle('open',selSet.size>0);
var b=document.getElementById('selFav');
if(b)b.innerHTML=(KIND==='fav'?'&#9825; 取消收藏':'&#9829; 收藏');}
function clearSel(){selSet.clear();selAnchor=null;applySelClasses();refreshSel()}
function selAdd(f){if(!f)return;selSet.add(f.dataset.rel);f.classList.add('sel')}
function selToggle(f){if(!f)return;var r=f.dataset.rel;
if(selSet.has(r)){selSet.delete(r);f.classList.remove('sel')}else{selSet.add(r);f.classList.add('sel')}}
if(grid){
grid.addEventListener('click',function(e){
var f=e.target.closest('figure.item');
if(!f||e.target.closest('.acts')||e.target.closest('.note'))return;
if(!e.shiftKey)return;
e.preventDefault();e.stopPropagation();
if(selAnchor&&selAnchor!==f&&selAnchor.isConnected){
var list=figs(),a=list.indexOf(selAnchor),b=list.indexOf(f);
if(a>=0&&b>=0){for(var i=Math.min(a,b);i<=Math.max(a,b);i++)selAdd(list[i])}
else selToggle(f);
}else selToggle(f);
selAnchor=f;refreshSel();
},true);
/* 空白处拖出选框（触摸/鼠标通用） */
grid.addEventListener('pointerdown',function(e){
if(e.button!==0||!bandEl)return;
if(e.target.closest('figure.item'))return;
bandOn=true;bandStart={x:e.clientX,y:e.clientY};
bandEl.style.display='block';
bandEl.style.left=e.clientX+'px';bandEl.style.top=e.clientY+'px';
bandEl.style.width='0px';bandEl.style.height='0px';});
document.addEventListener('pointermove',function(e){
if(!bandOn)return;
var x=Math.min(bandStart.x,e.clientX),y=Math.min(bandStart.y,e.clientY);
var w=Math.abs(e.clientX-bandStart.x),h=Math.abs(e.clientY-bandStart.y);
bandEl.style.left=x+'px';bandEl.style.top=y+'px';
bandEl.style.width=w+'px';bandEl.style.height=h+'px';});
document.addEventListener('pointerup',function(e){
if(!bandOn)return;
bandOn=false;bandEl.style.display='none';
var x1=Math.min(bandStart.x,e.clientX),y1=Math.min(bandStart.y,e.clientY);
var x2=Math.max(bandStart.x,e.clientX),y2=Math.max(bandStart.y,e.clientY);
if(x2-x1<8&&y2-y1<8)return;
figs().forEach(function(f){var r=f.getBoundingClientRect();
if(r.right>x1&&r.left<x2&&r.bottom>y1&&r.top<y2)selAdd(f)});
refreshSel();});
}
if(selBar){
document.getElementById('selAll').onclick=function(){figs().forEach(selAdd);refreshSel()};
document.getElementById('selClear').onclick=clearSel;
document.getElementById('selFav').onclick=function(){
var n=0;
if(KIND==='fav'){/* 收藏页：批量取消收藏 */
selSet.forEach(function(rel){if(favSet.has(rel)){favSet.delete(rel);favOrder=favOrder.filter(function(r){return r!==rel});n++}});
saveFav();toast('已取消收藏 '+n+' 张');setTimeout(function(){location.reload()},600);return}
selSet.forEach(function(rel){if(!favSet.has(rel)){favSet.add(rel);favOrder.push(rel);n++}});
saveFav();
grid.querySelectorAll('figure.item').forEach(function(f){
if(!selSet.has(f.dataset.rel))return;
f.classList.add('fav');var b=f.querySelector('.act-fav');if(b)b.innerHTML='&#9829;'});
toast('已收藏 '+n+' 张');clearSel()};
function applyBatchTags(){
var inp=document.getElementById('selTag');var list=parseTags(inp.value||'');
if(!list.length){toast('先输入标签，空格分隔');return}
var n=0;
selSet.forEach(function(rel){
var cur=tags[rel]||[];var add=false;
list.forEach(function(t){if(cur.indexOf(t)<0&&cur.length<8){cur.push(t);add=true}});
if(add){tags[rel]=cur;n++}});
saveTags();buildTagNav();
grid.querySelectorAll('figure.item').forEach(function(f){
if(!selSet.has(f.dataset.rel))return;
var tr=f.querySelector('.tagrow'),l=tags[f.dataset.rel]||[];
if(!l.length)return;
if(!tr){tr=document.createElement('div');tr.className='tagrow';f.appendChild(tr)}
tr.innerHTML=l.map(function(x){return '<span class="tagchip">'+esc(x)+'</span>'}).join('')});
inp.value='';toast('已给 '+n+' 张加标签');}
document.getElementById('selTagApply').onclick=applyBatchTags;
document.getElementById('selTag').addEventListener('keydown',function(e){
if(e.key==='Enter'){e.preventDefault();applyBatchTags()}});
refreshSel();
}

/* 视频卡：单击延迟 230ms 再开（给双击留窗口），双击第一击排队、第二击直接开+全屏 */
var vCardT=null;
function openVCard(rel,e){
if(e&&e.detail>1){clearTimeout(vCardT);vCardT=null;openVlb(rel);goFullV();return}
clearTimeout(vCardT);
vCardT=setTimeout(function(){vCardT=null;openVlb(rel)},230);
}
document.addEventListener('click',function(e){
const ntEl=e.target.closest('.note');
if(ntEl){e.stopPropagation();openNote(ntEl.closest('figure').dataset.rel);return}
const fav=e.target.closest('.act-fav');
if(fav){e.stopPropagation();e.preventDefault();toggleFav(fav.closest('figure').dataset.rel);return}
const nt=e.target.closest('.act-note');
if(nt){e.stopPropagation();e.preventDefault();openNote(nt.closest('figure').dataset.rel);return}
const vcard=e.target.closest('figure.item-v[data-rel]');
if(vcard){e.stopPropagation();openVCard(vcard.dataset.rel,e);return}
const item=e.target.closest('figure.item[data-src]');
if(item&&!e.target.closest('.acts')){
if(e.shiftKey)return;   /* Shift 点选交给批量选择逻辑 */
openLb(item)}
});
var pageY=0;
function visible(){return Array.prototype.slice.call(grid.querySelectorAll('figure.item[data-src]')).filter(function(f){return f.style.display!=='none'})}
function openLb(f){pageY=window.scrollY;cur=visible();pos=cur.indexOf(f);if(pos<0)return;
markRecent(f.dataset.rel);lb.classList.add('open');show();hideChrome();lbHintOnce();enterFs()}
/* 点缩略图直接进全屏（真全屏，浏览器地址栏/标签一起隐藏）；不支持或被拒就退化成整屏遮罩 */
function enterFs(){try{
if(document.fullscreenElement||!lb.requestFullscreen)return;
var p=lb.requestFullscreen();if(p&&p.catch)p.catch(function(){})}catch(e){}}
function exitFs(){try{
if(document.fullscreenElement===lb&&document.exitFullscreen)document.exitFullscreen().catch(function(){})}catch(e){}}
/* 首次打开给一句操作提示（点左右半屏翻页 / 底部才浮出操作条），只提示一次 */
var LB_HINT_KEY='demo_lbhint';
function lbHintOnce(){
try{if(localStorage.getItem(LB_HINT_KEY)==='1')return;localStorage.setItem(LB_HINT_KEY,'1')}catch(e){}
toast('点左右半屏翻页 · 底部是收藏/幻灯/备注 · Esc 关闭')}
/* 底部操作条：靠屏幕下方才浮现，离开即隐藏；顶栏/箭头/关闭由 ui-on 控制（2.4s 后自动淡出） */
var actsHideT=null,chromeT=null;
function showChrome(){lb.classList.add('ui-on');clearTimeout(chromeT);
chromeT=setTimeout(function(){lb.classList.remove('ui-on')},2400)}
function hideChrome(){lb.classList.remove('ui-on');clearTimeout(chromeT)}
function showActs(){lb.classList.add('show-acts');showChrome();clearTimeout(actsHideT);
if(matchMedia('(hover:none)').matches)actsHideT=setTimeout(hideActs,3200)}
function hideActs(){lb.classList.remove('show-acts');clearTimeout(actsHideT)}
/* 退出预览后定位：把刚看的那张滚到视口上部约 1/6 处；目标不在（如已取消收藏）则回原位置 */
function scrollToFig(f){
if(!f||!f.isConnected)return;
var off=Math.max(56,Math.round(window.innerHeight*0.16));
function jump(){
/* html 上有 scroll-behavior:smooth，长距离程序化滚动会变成动画，这里强制即时 */
var de=document.documentElement,prev=de.style.scrollBehavior;
de.style.scrollBehavior='auto';
var r=f.getBoundingClientRect();
window.scrollTo(0,Math.max(0,Math.round(window.scrollY+r.top-off)));
de.style.scrollBehavior=prev;
}
jump();
/* 图片懒加载/布局稳定后再校正一次 */
setTimeout(function(){if(!f.isConnected)return;
var r=f.getBoundingClientRect();
if(Math.abs(r.top-off)>4)jump()},90);
}
/* 幻灯片放映：速率 200ms~2s 五档可调（记忆在 <key>_slide），主按钮开停、旁边小按钮选速率 */
const SLIDES=[16,100,200,500,1000,1500,2000];
const SLIDE_KEY='demo_slide';
var slideMs=16;
try{slideMs=parseInt(localStorage.getItem(SLIDE_KEY),10)||16;
if(SLIDES.indexOf(slideMs)<0)slideMs=16}catch(e){}
var slideT=null,slideOn=false;
function slideArm(){clearTimeout(slideT);
if(slideOn)slideT=setTimeout(function(){step(1);slideArm()},slideMs)}
function slideLabel(){
var b=document.getElementById('lbPlay'),m=document.getElementById('lbSpdMs');
if(b)b.innerHTML=(slideOn?'&#9208;':'&#9654;')+' 幻灯';
if(m)m.textContent=slideMs<1000?slideMs+'ms':(slideMs/1000)+'s'}
function slideStart(){slideOn=true;
var b=document.getElementById('lbPlay');if(b)b.classList.add('on');
slideLabel();slideArm()}
function slideStop(){slideOn=false;clearTimeout(slideT);
var b=document.getElementById('lbPlay');if(b){b.classList.remove('on');b.innerHTML='&#9654; 幻灯'}
var m=document.getElementById('spdMenu');if(m)m.classList.remove('open')}
function closeLb(){var f=cur[pos];if(f)markRecent(f.dataset.rel);
saveCurView();viewRel=null;exitFs();resetView();rotQ=0;
lb.classList.remove('open');lb.classList.remove('ui-on');hideActs();slideStop();
if(f&&f.isConnected)scrollToFig(f);
else window.scrollTo(0,pageY);
refreshSeen()}
/* ---------- 全图视图：缩放 / 旋转 / 拖拽 / 滑动翻页 ----------
   坐标模型：图片按 contain 摆进视口（fitW×fitH），再用 translate+scale+rotate 变换。
   zS=1 即"整屏 contain"，是缩放下限；上限保证能放大到原始像素的 2 倍以上（长图看细节）。
   每张图的缩放/旋转按 rel 记在 <key>_imgstate，退出再进能回到上次的位置。 */
var zS=1,zTx=0,zTy=0,rotQ=0,fitW=0,fitH=0,maxScaleNow=6;
var IMG_STATE_KEY='demo_imgstate',imgState={};
try{imgState=JSON.parse(localStorage.getItem(IMG_STATE_KEY)||'{}')||{}}catch(e){imgState={}}
function saveImgState(){try{localStorage.setItem(IMG_STATE_KEY,JSON.stringify(imgState))}catch(e){}}
var viewRel=null;   /* 当前内存里的 zS/rotQ 属于哪张图（换图前要存回它） */
function saveCurView(){var r=viewRel;if(!r)return;
if(zS<=1.001&&rotQ===0){delete imgState[r]}
else imgState[r]={z:Math.round(zS*100)/100,r:rotQ};
saveImgState()}
function layoutFit(){
var nw=lbImg.naturalWidth||0,nh=lbImg.naturalHeight||0;if(!nw||!nh)return;
var swap=(rotQ%2===1),w=swap?nh:nw,h=swap?nw:nh;
var k=Math.min(innerWidth/w,innerHeight/h);
fitW=Math.max(1,Math.round(w*k));fitH=Math.max(1,Math.round(h*k));
lbImg.style.width=fitW+'px';lbImg.style.height=fitH+'px';
maxScaleNow=Math.max(3,Math.min(16,Math.max(nw/fitW,nh/fitH)*2));}
function applyT(){
var vw=innerWidth,vh=innerHeight,bw=fitW*zS,bh=fitH*zS;
if(bw<=vw+0.5)zTx=0;else zTx=Math.max((vw-bw)/2,Math.min((bw-vw)/2,zTx));
if(bh<=vh+0.5)zTy=0;else zTy=Math.max((vh-bh)/2,Math.min((bh-vh)/2,zTy));
lbImg.style.transform='translate('+zTx+'px,'+zTy+'px) scale('+zS+') rotate('+(rotQ*90)+'deg)';
lbImg.classList.toggle('zoomed',zS>1.001);}
function resetView(){zS=1;zTx=0;zTy=0;applyT()}
function zoomAt(px,py,factor){
var ns=Math.max(1,Math.min(maxScaleNow,zS*factor));
if(Math.abs(ns-zS)<0.0008)return;
var cx=innerWidth/2+zTx,cy=innerHeight/2+zTy;
var dx=(px-cx)/zS,dy=(py-cy)/zS;
zS=ns;zTx=px-innerWidth/2-dx*zS;zTy=py-innerHeight/2-dy*zS;
applyT();}
function rotateCur(){rotQ=(rotQ+1)%4;zS=1;zTx=0;zTy=0;layoutFit();applyT();saveCurView();
toast('旋转 '+(rotQ*90)+'° · 已按此图记住')}
function show(){const f=cur[pos];if(!f)return;
saveCurView();
var src=f.dataset.src,rel=f.dataset.rel;
lbName.textContent=f.dataset.name;
lbIdx.textContent=(pos+1)+' / '+cur.length;syncLb();syncFavNav(rel);
var st=imgState[rel]||{};
rotQ=st.r||0;
viewRel=rel;
/* 换图：原图未就绪时先淡到 22% 再淡入，避免上一张残影停留 */
function ready(){
lbImg.classList.remove('loading');
layoutFit();
zS=(slideOn?1:(st.z||1));zTx=0;zTy=0;
if(zS>maxScaleNow)zS=maxScaleNow;
applyT();}
if(lbImg.getAttribute('src')!==src){lbImg.classList.add('loading');
lbImg.onload=ready;
lbImg.onerror=function(){lbImg.classList.remove('loading')};
lbImg.src=src}else ready();
/* 预取左右各一张：点半屏翻页时不再等原图 */
[1,-1].forEach(function(d){var n=cur[(pos+d+cur.length)%cur.length];
if(!n)return;var im=new Image();im.src=n.dataset.src});
hideActs();}
function syncLb(){const f=cur[pos];if(!f)return;
const on=favSet.has(f.dataset.rel);
lbFav.classList.toggle('on',on);
lbFav.innerHTML=on?'&#9829; 已收藏':'&#9825; 收藏';}
function step(d){if(!cur.length)return;pos=(pos+d+cur.length)%cur.length;show()}
if(lbFav){
lbFav.onclick=function(e){e.stopPropagation();const f=cur[pos];if(f)toggleFav(f.dataset.rel)};
/* 幻灯片：主按钮开停，旁边小按钮弹出院内速率菜单（200ms~2s 五档） */
var lbPlay=document.getElementById('lbPlay'),lbSpd=document.getElementById('lbSpd'),
spdMenu=document.getElementById('spdMenu');
lbPlay.onclick=function(e){e.stopPropagation();slideOn?slideStop():slideStart()};
lbSpd.onclick=function(e){e.stopPropagation();
var r=lbSpd.getBoundingClientRect();
spdMenu.style.left=Math.max(8,Math.round(r.left+r.width/2-48))+'px';
spdMenu.style.bottom=Math.round(window.innerHeight-r.top+12)+'px';
spdMenu.classList.toggle('open')};
SLIDES.forEach(function(ms){var b=document.createElement('button');
b.textContent=ms<1000?ms+'ms':(ms/1000)+'s';
if(ms===slideMs)b.classList.add('on');
b.onclick=function(e){e.stopPropagation();slideMs=ms;
try{localStorage.setItem(SLIDE_KEY,ms)}catch(x){}
[].slice.call(spdMenu.querySelectorAll('button')).forEach(function(x){x.classList.toggle('on',x===b)});
slideLabel();spdMenu.classList.remove('open');if(slideOn)slideArm()};
spdMenu.appendChild(b)});
slideLabel();
document.getElementById('lbNote').onclick=function(e){e.stopPropagation();const f=cur[pos];if(f)openNote(f.dataset.rel)};
document.getElementById('lbPrev').onclick=function(e){e.stopPropagation();step(-1)};
document.getElementById('lbNext').onclick=function(e){e.stopPropagation();step(1)};
document.getElementById('lbClose').onclick=function(e){e.stopPropagation();closeLb()};
/* 全图模式：点右半侧=下一张、左半侧=上一张；底部 120px 只负责浮出操作条；✕ / Esc 关闭。
   放大状态（zS>1）下点击不翻页，避免拖拽看细节时误触。 */
lb.addEventListener('click',function(e){
if(Date.now()<suppressClickUntil)return;
if(e.detail>1)return;
if(e.target.closest('.lb-acts')||e.target.closest('.lb-btn')||e.target.closest('.lb-close')
||e.target.closest('.spdmenu')||e.target.closest('.lb-bar'))return;
if(e.clientY>window.innerHeight-120){showActs();return}
if(zS>1.001)return;
if(e.clientX<window.innerWidth/2)step(-1);else step(1);});
lb.addEventListener('mousemove',function(e){
if(e.pointerType==='touch')return;
showChrome();
if(e.clientY>window.innerHeight-120)showActs();else hideActs();});
lb.addEventListener('touchstart',function(e){
var t=e.touches&&e.touches[0];if(!t)return;
if(t.clientY>window.innerHeight-140)showActs();},{passive:true});

/* 缩放：滚轮（桌面）/ 双指（触屏）；拖拽平移；zS=1 时横向滑动翻页 */
var ptrs={},pinchD0=0,pinchZ0=1,swipe=null,dragging=false,suppressClickUntil=0,dragO=null;
function pDist(a,b){return Math.sqrt((a.x-b.x)*(a.x-b.x)+(a.y-b.y)*(a.y-b.y))}
function pMid(a,b){return{x:(a.x+b.x)/2,y:(a.y+b.y)/2}}
function pCount(){var n=0;for(var k in ptrs)if(ptrs.hasOwnProperty(k))n++;return n}
function setZoomAbs(ns,px,py){
ns=Math.max(1,Math.min(maxScaleNow,ns));
if(Math.abs(ns-zS)<0.0008)return;
var cx=innerWidth/2+zTx,cy=innerHeight/2+zTy;
var dx=(px-cx)/zS,dy=(py-cy)/zS;
zS=ns;zTx=px-innerWidth/2-dx*zS;zTy=py-innerHeight/2-dy*zS;applyT();}
lb.addEventListener('wheel',function(e){
if(!lb.classList.contains('open'))return;
e.preventDefault();
zoomAt(e.clientX,e.clientY,e.deltaY<0?1.16:1/1.16);
if(slideOn)slideStop();
},{passive:false});
lb.addEventListener('pointerdown',function(e){
if(!lb.classList.contains('open'))return;
if(e.target.closest('.lb-acts,.lb-btn,.lb-close,.lb-bar,.spdmenu'))return;
if(e.pointerType==='mouse'&&e.button!==0)return;
ptrs[e.pointerId]={x:e.clientX,y:e.clientY};
var n=pCount();
if(n>=2){var ks=[];for(var k in ptrs)if(ptrs.hasOwnProperty(k))ks.push(ptrs[k]);
pinchD0=Math.max(1,pDist(ks[0],ks[1]));pinchZ0=zS;swipe=null;dragging=false}
else{swipe={x0:e.clientX,y0:e.clientY,t:Date.now(),moved:0};
if(zS>1.001){dragging=true;lbImg.classList.add('dragging')}}
});
lb.addEventListener('pointermove',function(e){
var p=ptrs[e.pointerId];if(!p)return;
var dxm=e.clientX-p.x,dym=e.clientY-p.y;p.x=e.clientX;p.y=e.clientY;
if(pCount()>=2){
var ks=[];for(var k in ptrs)if(ptrs.hasOwnProperty(k))ks.push(ptrs[k]);
var d=pDist(ks[0],ks[1]),m=pMid(ks[0],ks[1]);
if(pinchD0>8)setZoomAbs(pinchZ0*(d/pinchD0),m.x,m.y);
suppressClickUntil=Date.now()+600;swipe=null;return}
if(dragging&&zS>1.001){zTx+=dxm;zTy+=dym;applyT();suppressClickUntil=Date.now()+420;return}
if(swipe)swipe.moved+=Math.abs(dxm)+Math.abs(dym);
});
function ptrEnd(e){
if(!ptrs[e.pointerId])return;
delete ptrs[e.pointerId];
if(pCount()===0){
lbImg.classList.remove('dragging');dragging=false;
if(swipe&&zS<=1.001){
var dx=e.clientX-swipe.x0,dy=e.clientY-swipe.y0,dt=Date.now()-swipe.t;
if(swipe.moved>=14&&Math.abs(dx)>55&&Math.abs(dx)>Math.abs(dy)*1.35&&dt<900){
suppressClickUntil=Date.now()+520;hideActs();step(dx<0?1:-1)}
else if(swipe.moved>=14&&Math.abs(dy)>70&&Math.abs(dy)>Math.abs(dx)*1.2&&e.clientY>innerHeight*0.7){
showActs();suppressClickUntil=Date.now()+400}
}
swipe=null}}
lb.addEventListener('pointerup',ptrEnd);
lb.addEventListener('pointercancel',ptrEnd);
/* 视口变化（进出全屏 / 转屏）后重新算 contain 尺寸 */
function relayoutView(){if(!lb.classList.contains('open'))return;layoutFit();applyT()}
window.addEventListener('resize',relayoutView);
document.addEventListener('fullscreenchange',relayoutView);
var lbRotBtn=document.getElementById('lbRot');
if(lbRotBtn)lbRotBtn.onclick=function(e){e.stopPropagation();rotateCur();showActs()};
/* 键盘：←/→ 与 J/K 翻页、空格开停幻灯、F 收藏、R 旋转、0 复位、Esc 逐层退出
   层级：提示弹窗 → 备注弹窗 → 批量选择 → 真全屏 → 全图模式，一层一个 Esc */
document.addEventListener('keydown',function(e){
var k=e.key;
if(k==='Escape'){
var tip=document.getElementById('shotTip');
if(tip&&tip.classList.contains('open')){tip.classList.remove('open');return}
if(noteModal&&noteModal.classList.contains('open')){closeNote();return}
if(selSet.size){clearSel();return}
if(document.fullscreenElement){exitFs();return}
if(lb.classList.contains('open')){closeLb();return}
return}
if(!lb.classList.contains('open'))return;
if(k==='ArrowLeft'||k==='k'||k==='K'){step(-1);if(slideOn)slideArm();return}
if(k==='ArrowRight'||k==='j'||k==='J'){step(1);if(slideOn)slideArm();return}
if(k===' '){e.preventDefault();slideOn?slideStop():slideStart();return}
if(k==='f'||k==='F'){const f=cur[pos];if(f)toggleFav(f.dataset.rel);return}
if(k==='r'||k==='R'){rotateCur();return}
if(k==='0'){resetView();return}
});
}
/* 页面滚动位置记忆：切页面回来自动回到原位 */
var SCROLL_KEY='demo_scroll_'+location.pathname;
try{
var sy0=parseInt(sessionStorage.getItem(SCROLL_KEY)||'0')||0;
if(sy0>0){
window.addEventListener('load',function(){
setTimeout(function(){window.scrollTo(0,sy0)},50);
});
}
}catch(e){}
window.addEventListener('scroll',function(){
try{sessionStorage.setItem(SCROLL_KEY,window.scrollY)}catch(e){}
});

/* 侧边导航 */
var navbox=document.getElementById('navbox');
if(navbox&&window.NAV){
var curF=(location.pathname.split('/').pop()||'index.html');
var nh='';
/* 分类标题点击 → 展开/收起该分类的子目录，各分类状态独立并按库记忆 */
navbox.addEventListener('click',function(e){
var h=e.target.closest&&e.target.closest('.cat-h');
if(!h)return;
var cat=h.closest('.cat');if(!cat)return;
var open=!cat.classList.contains('open');
cat.classList.toggle('open',open);
if(cat.dataset.cat){catState[cat.dataset.cat]=open;saveCatState()}
});
/* 标签点击 → 过滤网格（再点同标签取消） */
navbox.addEventListener('click',function(e){
var tg=e.target.closest&&e.target.closest('a[data-tag]');
if(!tg)return;e.preventDefault();
tagFilter=(tagFilter===tg.dataset.tag)?'':tg.dataset.tag;
buildTagNav();
if(KIND==='fav')applyFavFilters();else applyGroupFilters();
});
if(KIND==='fav'){
/* 收藏页：目录条由收藏项动态生成，只列「实际有收藏」的目录 */
buildFavNav();
navbox.addEventListener('click',function(e){
var a=e.target.closest&&e.target.closest('a[data-g]');
if(!a)return;e.preventDefault();
favFilter=a.dataset.g||null;applyFavFilters();
});
}else{
var activeCat=null;
window.NAV.groups.forEach(function(g){g.items.forEach(function(it){if(it.f===curF)activeCat=g.c})});
if(curF==='index.html')nh+='<a class="nav-item on" href="index.html">&#9776; 目录总览</a>';
window.NAV.groups.forEach(function(g){
nh+=catHead(g.c,g.c,g.tc,catOpen(g.c,g.c===activeCat));
g.items.forEach(function(it){
nh+='<a class="nav-item'+(it.f===curF?' on':'')+'" href="'+it.f+'">'+esc(it.n)+'<em>'+it.k+'</em></a>';
});
nh+=CAT_END;
});
navbox.innerHTML=nh;
buildTagNav();
}
/* 侧栏滚动位置记忆：切页后停在原位，不自动跳 */
try{
var nsKey='demo_navscroll';
var nsY=parseInt(sessionStorage.getItem(nsKey)||'0')||0;
if(nsY>0)requestAnimationFrame(function(){navbox.scrollTop=nsY});
navbox.addEventListener('scroll',function(){
try{sessionStorage.setItem(nsKey,navbox.scrollTop)}catch(e){}
});
}catch(e){}
}
/* 视频播放器（B 站式控制条） */
var vlb=document.getElementById('vlb'),vPlayer=document.getElementById('vPlayer');
var vBar=document.getElementById('vBar'),vBarWrap=document.getElementById('vBarWrap');
var vPlay=document.getElementById('vPlay'),vTime=document.getElementById('vTime');
var vPrev=document.getElementById('vPrev'),vNext=document.getElementById('vNext');
var vRate=document.getElementById('vRate'),vMenu=document.getElementById('vMenu');
var vFull=document.getElementById('vFull'),vClose=document.getElementById('vClose');
var vName=document.getElementById('vName');
var vlist=[],vpos=-1,rate=1,hideT=null;
/* 播放位置记忆：按视频 rel 记录观看进度，下次打开自动续播（仅记 3s<t<d-3s，避免记忆"已看完"） */
var vposMap={};
try{vposMap=JSON.parse(localStorage.getItem('demo_vpos')||'{}')||{}}catch(e){vposMap={}}
function saveVpos(){
  if(vpos<0||!vlist[vpos])return;
  var rel=vlist[vpos];
  try{var t=vPlayer.currentTime||0,d=vPlayer.duration||0;
    if(d>0&&t>3&&t<d-3)vposMap[rel]=t;else delete vposMap[rel];
    localStorage.setItem('demo_vpos',JSON.stringify(vposMap));}catch(e){}
}
function applyVpos(){
  if(vpos<0||!vlist[vpos])return;
  var rel=vlist[vpos],t=vposMap[rel];
  if(t&&t>0){try{vPlayer.currentTime=t;
    if(vTime)vTime.textContent=fmt(t)+' / '+fmt(vPlayer.duration||0);
    toast('↺ 续播 '+fmt(t));}catch(e){}}
}
/* 目录页没有播放器 DOM（无 EXTRA 块）→ 必须判空，否则整段顶层代码从这里断掉，
   后面的 Ctrl+滚轮缩放 / Ctrl+0 全部注册不上（第二十五轮修复） */
if(vPlayer)vPlayer.addEventListener('loadedmetadata',applyVpos);
var RATES=[0.5,0.75,1,1.25,1.5,2];
try{rate=parseFloat(localStorage.getItem('demo_rate')||'1')||1}catch(e){}
function fmt(s){s=Math.floor(s||0);var m=Math.floor(s/60);var q=s%60;
return m+':'+(q<10?'0':'')+q}
function setRate(r){
rate=r;
try{vPlayer.playbackRate=r}catch(e){}
try{localStorage.setItem('demo_rate',r)}catch(e){}
if(vRate)vRate.textContent=r+'x';
if(vMenu)vMenu.querySelectorAll('button').forEach(function(b){
b.classList.toggle('on',parseFloat(b.dataset.r)===r);});
}
if(vMenu){
RATES.forEach(function(r){
var b=document.createElement('button');
b.textContent=r+'x';b.dataset.r=r;
if(r===rate)b.className='on';
b.onclick=function(){setRate(r);vMenu.classList.remove('open')};
vMenu.appendChild(b);});
}
function showUI(){
if(!vlb)return;
vlb.classList.add('show-ui');
clearTimeout(hideT);
hideT=setTimeout(function(){
if(!vPlayer.paused&&!(vMenu&&vMenu.classList.contains('open')))
vlb.classList.remove('show-ui');
},2400);
}
/* 播放/暂停图标：以 vPlayer 的媒体事件为唯一真相（按钮、空格、点画面、切集、播完都走这里），
   不再靠 onplay 里改 innerHTML——那样 pause/ended 之后图标永远停在暂停符号 */
function syncPlayIcon(){
if(!vPlay)return;
var on=!vPlayer.paused&&!vPlayer.ended;
vPlay.classList.toggle('playing',on);
vPlay.title=on?'暂停':'播放';}
function openVlb(rel){
vlist=items.filter(function(it){return it[3]===1}).map(function(it){return it[0]});
var np=vlist.indexOf(rel);
if(np<0)return;
/* 同一个视频已经在播：不重开（否则双击进全屏会把进度清零） */
if(vlb.classList.contains('open')&&np===vpos){showUI();return}
if(!vlb.classList.contains('open'))pageY=window.scrollY;
vpos=np;markRecent(rel);playV();vlb.classList.add('open');showUI();
}
/* 双击视频卡：直接进全屏播放（桌面双击 / 移动端双击即双击手势，见下方 touchend） */
function goFullV(){showUI();
if(!document.fullscreenElement&&vlb.requestFullscreen)vlb.requestFullscreen().catch(function(){})}
function playV(){
spriteRel=null;hideSprite();preloadSprite(vlist[vpos]);
vPlayer.src=encPath(vlist[vpos]);
setRate(rate);
try{vPlayer.play().catch(function(){})}catch(e){}
vPrev.disabled=vpos<=0;
vNext.disabled=vpos>=vlist.length-1;
if(vName)vName.textContent=vlist[vpos].split('/').pop()+'  ·  '+(vpos+1)+' / '+vlist.length;
vTime.textContent='0:00 / 0:00';
syncFavNav(vlist[vpos]);showUI();
}
function stepV(d){var n=vpos+d;if(n<0||n>=vlist.length)return;vpos=n;playV()}
function closeV(){
if(vpos>=0&&vlist[vpos]){markRecent(vlist[vpos]);saveVpos();}
var f=null;
if(vpos>=0&&vlist[vpos]&&grid){
f=grid.querySelector('figure.item[data-rel="'+vlist[vpos].replace(/"/g,'\\"')+'"]')}
vlb.classList.remove('open');vPlayer.pause();syncPlayIcon();hideSprite();
/* 全屏退出是异步的：先退全屏，等布局恢复再定位，否则 rect 全错 */
var wasFs=!!(document.fullscreenElement&&document.exitFullscreen);
if(wasFs)document.exitFullscreen().catch(function(){});
if(f){
if(wasFs){var h=function(){document.removeEventListener('fullscreenchange',h);scrollToFig(f)};
document.addEventListener('fullscreenchange',h);
setTimeout(function(){document.removeEventListener('fullscreenchange',h)},800);
}else scrollToFig(f);
}else window.scrollTo(0,pageY);
}
if(vlb){
vPlay.onclick=function(){vPlayer.paused?vPlayer.play():vPlayer.pause()};
vPrev.onclick=function(){stepV(-1)};
vNext.onclick=function(){stepV(1)};
vClose.onclick=closeV;
/* 连播/单曲循环：单按钮三态循环切换（关→连播→单曲循环），状态持久化（<key>_vplay） */
var vPM=document.getElementById('vPlayMode');
var vplayMode='off';
try{vplayMode=localStorage.getItem('demo_vplay')||
(localStorage.getItem('demo_vcont')==='1'?'cont':(localStorage.getItem('demo_vloop')==='1'?'loop':'off'))}catch(e){}
if(['off','cont','loop'].indexOf(vplayMode)<0)vplayMode='off';
var VLBL={off:'单集',cont:'连播',loop:'循环'};
function applyMode(){if(!vPM)return;
vPlayer.loop=(vplayMode==='loop');
vPM.textContent=VLBL[vplayMode];
vPM.classList.toggle('on',vplayMode!=='off');
vPM.title={off:'连播/循环：关（点击开启连播）',
cont:'连播：开（点击切换为单曲循环）',
loop:'单曲循环：开（点击关闭）'}[vplayMode]}
if(vPM){applyMode();
vPM.onclick=function(e){e.stopPropagation();
vplayMode=vplayMode==='off'?'cont':(vplayMode==='cont'?'loop':'off');
try{localStorage.setItem('demo_vplay',vplayMode)}catch(x){}applyMode()}}
vPlayer.addEventListener('ended',function(){
if(vplayMode==='cont'&&vpos<vlist.length-1)stepV(1)});
['play','playing','pause','ended','emptied','seeking','loadedmetadata'].forEach(function(n){
vPlayer.addEventListener(n,function(){syncPlayIcon();if(n==='play')showUI()})});
syncPlayIcon();
/* 双击视频画面 → 全屏切换；单击 → 播放/暂停（延迟 260ms 区分单双击） */
var vclickT=null;
vPlayer.addEventListener('click',function(e){e.stopPropagation();
if(vclickT){clearTimeout(vclickT);vclickT=null;
showUI();
if(!document.fullscreenElement){if(vlb.requestFullscreen)vlb.requestFullscreen().catch(function(){})}
else if(document.exitFullscreen)document.exitFullscreen().catch(function(){});
return}
vclickT=setTimeout(function(){vclickT=null;
vPlayer.paused?vPlayer.play():vPlayer.pause()},260)});
vPlayer.ontimeupdate=function(){
var d=vPlayer.duration||0,c=vPlayer.currentTime||0;
vBar.style.width=(d?c/d*100:0)+'%';
vTime.textContent=fmt(c)+' / '+fmt(d);
};
vBarWrap.onclick=function(e){
var r=vBarWrap.getBoundingClientRect();
var p=Math.max(0,Math.min(1,(e.clientX-r.left)/r.width));
if(vPlayer.duration)vPlayer.currentTime=vPlayer.duration*p;
};
/* 进度条帧预览：本地库没法用 canvas 抓帧（file:// 污染），改用 gen_sprites.py 预生成的
   「10 帧雪碧图」(_sprite/<名>.jpg，10×160×90)，悬停/拖动时按位置换 background-position。 */
var SPRITE_TILES=10;
var vSprite=document.getElementById('vSprite'),vSpriteT=document.getElementById('vSpriteT');
var spriteRel=null,spriteLoaded={};
function spriteURL(rel){
var i=rel.lastIndexOf('/'),dir=i<0?'':rel.slice(0,i)+'/';
return dir+'_sprite/'+encodeURIComponent(rel.slice(i+1).replace(/\.[^.]+$/,''))+'.jpg';}
function preloadSprite(rel){
var u=spriteURL(rel);if(u in spriteLoaded)return;
spriteLoaded[u]=null;
var im=new Image();
im.onload=function(){spriteLoaded[u]=true};
im.onerror=function(){spriteLoaded[u]=false};
im.src=u;}
function showSprite(e){
if(!vSprite||!vPlayer.duration)return;
var rel=vlist[vpos]||'',sp=spriteURL(rel);
if(spriteLoaded[sp]!==true){preloadSprite(rel);return}
var r=vBarWrap.getBoundingClientRect();
var p=Math.max(0,Math.min(0.999,(e.clientX-r.left)/r.width));
var idx=Math.floor(p*SPRITE_TILES);
if(spriteRel!==sp){spriteRel=sp;
vSprite.style.backgroundImage='url("'+sp+'")';
vSprite.style.backgroundSize=(160*SPRITE_TILES)+'px 90px';}
vSprite.style.backgroundPosition=(-idx*160)+'px 0';
vSprite.classList.add('on');
vSprite.style.left=Math.max(8,Math.min(innerWidth-170,r.left+r.width*p-80))+'px';
vSprite.style.top=Math.max(8,r.top-104)+'px';
if(vSpriteT)vSpriteT.textContent=fmt(vPlayer.duration*p);
}
function hideSprite(){if(vSprite)vSprite.classList.remove('on')}
vBarWrap.addEventListener('mousemove',showSprite);
vBarWrap.addEventListener('mouseleave',hideSprite);
vBarWrap.addEventListener('pointerdown',function(e){
showSprite(e);
var mv=function(ev){showSprite(ev)};
window.addEventListener('pointermove',mv);
window.addEventListener('pointerup',function(){window.removeEventListener('pointermove',mv);hideSprite()},{once:true});
});
vRate.onclick=function(e){e.stopPropagation();vMenu.classList.toggle('open');showUI()};
/* 音量：滑块拖动调节（0-100），图标随音量显示 🔇/🔉/🔊，状态存 <key>_vvol；
   旧版只有「点一下静音」，这里读不到 _vvol 时用旧的 _vmute 当初始值，保证设置不丢 */
var vVol=document.getElementById('vVol'),vVolIcon=document.getElementById('vVolIcon');
var vol=1;
try{
var _vv=localStorage.getItem('demo_vvol');
vol=(_vv===null||_vv==='')?((localStorage.getItem('demo_vmute')==='1')?0:1):parseFloat(_vv);
}catch(e){}
if(!isFinite(vol))vol=1;
function volGlyph(v){return v<=0.001?'&#128263;':(v<0.5?'&#128265;':'&#128266;')}
function applyVol(){if(!vVol)return;
vol=Math.max(0,Math.min(1,vol));
vPlayer.volume=vol;vPlayer.muted=vol<=0.001;
vVol.value=Math.round(vol*100);
vVol.style.setProperty('--vp',(vol*100)+'%');
if(vVolIcon)vVolIcon.innerHTML=volGlyph(vol);
vVol.title='音量 '+Math.round(vol*100)+'%'+(vol<=0.001?'（静音）':'');
vVol.setAttribute('aria-valuetext',Math.round(vol*100)+'%')}
if(vVol){applyVol();
vVol.addEventListener('input',function(e){
vol=parseInt(vVol.value,10)/100;applyVol();
try{localStorage.setItem('demo_vvol',String(vol))}catch(x){}showUI()});
/* 拖滑块别顺手触发播放器/画面上的其它点击逻辑 */
['click','pointerdown','mousedown'].forEach(function(n){
vVol.addEventListener(n,function(e){e.stopPropagation()})});
/* 滚轮在滑块上也能调音量（桌面小便利） */
vVol.addEventListener('wheel',function(e){e.preventDefault();e.stopPropagation();
vol=Math.max(0,Math.min(1,vol+(e.deltaY<0?0.05:-0.05)));applyVol();
try{localStorage.setItem('demo_vvol',String(vol))}catch(x){}},{passive:false});
}
/* 截图：抓当前帧存 PNG。
   file:// 下浏览器把本地视频判为跨源资源，canvas 会被污染、
   toBlob/toDataURL 抛 SecurityError（captureStream / VideoFrame 同样被拒），
   这不是 bug 而是安全策略 —— 这里做两件事：给出明确原因 + 引导用 http:// 打开。 */
var vShot=document.getElementById('vShot');
function shotName(){
var b=vlist[vpos].split('/').pop().replace(/\.[^.]+$/,'');
var t=Math.round(vPlayer.currentTime||0);
return b+'_'+Math.floor(t/60)+'m'+(t%60)+'s.png'}
function shotTipOnce(){
var m=document.getElementById('shotTip');if(!m)return;
m.classList.add('open');
var ok=document.getElementById('shotTipOk');
if(ok)ok.onclick=function(){m.classList.remove('open')};
m.onclick=function(e){if(e.target===m)m.classList.remove('open')}}
function shotFail(msg){
var tainted=/taint|security/i.test(msg);
toast(tainted?'截图失败：浏览器禁止读取本地视频画面（file:// 安全限制）':'截图失败：'+msg);
if(tainted)setTimeout(shotTipOnce,900)}
function shotFrame(){
if(!vPlayer.videoWidth){toast('画面还没解码出来，等一秒再点');return}
var c=document.createElement('canvas');
c.width=vPlayer.videoWidth;c.height=vPlayer.videoHeight;
var ctx=c.getContext('2d');
try{ctx.drawImage(vPlayer,0,0)}catch(x){shotFail(x.message);return}
var name=shotName();
function done(blob){
if(!blob){toast('截图失败：浏览器无法导出画面');return}
var url=URL.createObjectURL(blob);
var a=document.createElement('a');
a.href=url;a.download=name;
document.body.appendChild(a);a.click();a.remove();
setTimeout(function(){URL.revokeObjectURL(url)},15000);
toast('已截图：'+name)}
if(c.toBlob){try{c.toBlob(done,'image/png')}catch(x){shotFail(x.message)}}
else{try{var u=c.toDataURL('image/png');
var a2=document.createElement('a');a2.href=u;a2.download=name;
document.body.appendChild(a2);a2.click();a2.remove();toast('已截图：'+name)}
catch(x){shotFail(x.message)}}}
if(vShot){
vShot.onclick=function(e){e.stopPropagation();shotFrame()};
/* file:// 下必然失败，直接把按钮标题说清楚，别让人反复点 */
if(location.protocol==='file:')vShot.title='截图（file:// 下浏览器禁止读取视频画面，需用 http:// 打开）';
}
/* 画中画：不支持的环境自动隐藏 */
var vPip=document.getElementById('vPip');
if(vPip){
if('requestPictureInPicture' in HTMLVideoElement.prototype){
vPip.onclick=function(e){e.stopPropagation();
if(document.pictureInPictureElement){document.exitPictureInPicture().catch(function(){})}
else vPlayer.requestPictureInPicture().catch(function(){toast('无法进入画中画')})};
}else vPip.style.display='none'}
vFull.onclick=function(){
showUI();
if(!document.fullscreenElement){
if(vlb.requestFullscreen)vlb.requestFullscreen().catch(function(){});
}else if(document.exitFullscreen){document.exitFullscreen().catch(function(){})}
};
vlb.addEventListener('mousemove',showUI);
vlb.addEventListener('click',function(e){if(e.target===vlb)closeV()});
document.addEventListener('keydown',function(e){
if(!vlb.classList.contains('open'))return;
if(e.key==='Escape'){
if(document.fullscreenElement&&document.exitFullscreen){document.exitFullscreen();return}
closeV();return;
}
if(e.key==='ArrowLeft'){stepV(-1);return}
if(e.key==='ArrowRight'){stepV(1);return}
if(e.key===' '){e.preventDefault();vPlayer.paused?vPlayer.play():vPlayer.pause();return}
if(e.key==='f'||e.key==='F'){vFull.click();return}
});
}

/* 卡片悬停预览：鼠标移上去播，移开暂停并回到开头 */
if(grid){
grid.addEventListener('mouseover',function(e){
var f=e.target.closest&&e.target.closest('figure.item-v');
if(!f)return;
var v=f.querySelector('video');
if(!v||v.dataset.hov==='1')return;
v.dataset.hov='1';v.muted=true;
try{v.currentTime=0;v.play().catch(function(){})}catch(x){}
});
grid.addEventListener('mouseout',function(e){
var f=e.target.closest&&e.target.closest('figure.item-v');
if(!f)return;
if(e.relatedTarget&&f.contains(e.relatedTarget))return;
var v=f.querySelector('video');
if(!v)return;
v.dataset.hov='0';
try{v.pause();v.currentTime=0}catch(x){}
});
/* 双击视频卡 = 直接全屏播放（桌面 dblclick；移动端用 340ms 内的二次 tap 兜底，保证两端一致） */
grid.addEventListener('dblclick',function(e){
var f=e.target.closest&&e.target.closest('figure.item-v[data-rel]');
if(!f)return;
openVlb(f.dataset.rel);goFullV();
});
var vTapLast=0,vTapFig=null;
grid.addEventListener('touchend',function(e){
var f=e.target.closest&&e.target.closest('figure.item-v[data-rel]');
if(!f)return;
var now=Date.now();
if(vTapFig===f&&now-vTapLast<340){
vTapLast=0;vTapFig=null;e.preventDefault();
openVlb(f.dataset.rel);goFullV();
return}
vTapLast=now;vTapFig=f;
},{passive:false});
}

/* 分区独立缩放：Ctrl+滚轮，鼠标在哪边缩哪边 */
(function(){
var zn=1,zm=1;
try{zn=parseFloat(localStorage.getItem('demo_zn')||'1')||1}catch(e){}
try{zm=parseFloat(localStorage.getItem('demo_zm')||'1')||1}catch(e){}
var root=document.documentElement;
function applyZ(){root.style.setProperty('--z-nav',zn);root.style.setProperty('--z-main',zm)}
document.addEventListener('wheel',function(e){
if(!e.ctrlKey)return;
e.preventDefault();
var inNav=!!(e.target.closest&&e.target.closest('aside'));
var d=e.deltaY<0?0.05:-0.05;
if(inNav){
zn=Math.min(1.9,Math.max(0.8,zn+d));
try{localStorage.setItem('demo_zn',zn)}catch(x){}
}else{
zm=Math.min(2.4,Math.max(0.5,zm+d));
try{localStorage.setItem('demo_zm',zm)}catch(x){}
}
applyZ();
toast((inNav?'导航栏 ':'内容区 ')+Math.round((inNav?zn:zm)*100)+'%');
},{passive:false});
document.addEventListener('keydown',function(e){
if(e.ctrlKey&&(e.key==='0'||e.code==='Digit0')){
e.preventDefault();zn=1;zm=1;applyZ();
try{localStorage.setItem('demo_zn',1);localStorage.setItem('demo_zm',1)}catch(x){}
toast('两边已重置');
}
});
applyZ();
})();

render();
/* 深链：#open=<rel> 直接打开某张（总收藏 Hub 的卡片、随机看图都靠它）
   分批渲染，目标可能还没插入 DOM → 最多重试 ~12 次（4s） */
(function(){
var m=location.hash.match(/open=([^&]+)/);if(!m)return;
var rel=decodeURIComponent(m[1]);
if(!rel)return;
var tries=0;
(function find(){
if(!grid)return;
var f=null;
grid.querySelectorAll('figure.item[data-rel]').forEach(function(x){if(x.dataset.rel===rel)f=x});
if(f){
if(f.classList.contains('item-v'))openVlb(rel);else openLb(f);
history.replaceState&&history.replaceState(null,'',location.pathname);
return}
if(++tries>12)return;
setTimeout(find,320)})();
})();
})();
