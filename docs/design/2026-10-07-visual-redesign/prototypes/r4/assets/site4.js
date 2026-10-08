/* ═══════════════════════════════════════════════════════════
   R4「纸筑」全站原型 · 共用渐进增强脚本
   全部为增强:无 JS 时内容、导航、链接完整可用。
   与 R3 差异:图片展开改用原生 <dialog>.showModal(),
   背景隔离(inert)与焦点约束由浏览器保证,而非 aria-modal 声明。
   ═══════════════════════════════════════════════════════════ */
(function(){
"use strict";
/* 标记 JS 可用:CSS 据此把移动导航从「常显」切换为「按钮开合」 */
document.documentElement.classList.add('js');

/* ── 1. 三态主题:跟随系统 / 昼 / 夜 ── */
var KEY='nm-theme', root=document.documentElement;
function getTheme(){try{return localStorage.getItem(KEY)||'auto';}catch(e){return 'auto';}}
function setTheme(v){try{localStorage.setItem(KEY,v);}catch(e){}}
function applyTheme(){
  var m=getTheme();
  if(m==='auto'){delete root.dataset.theme;}else{root.dataset.theme=m;}
  document.querySelectorAll('#theme-btn').forEach(function(b){
    b.textContent=m==='auto'?'跟随系统':(m==='light'?'昼览':'夜览');
  });
  /* 通知 3D 场景等订阅者 */
  document.dispatchEvent(new CustomEvent('nm-theme',{detail:{mode:m,
    dark:m==='dark'||(m==='auto'&&matchMedia('(prefers-color-scheme: dark)').matches)}}));
}
document.querySelectorAll('#theme-btn').forEach(function(b){
  b.addEventListener('click',function(){
    var m=getTheme(); setTheme(m==='auto'?'light':(m==='light'?'dark':'auto')); applyTheme();
  });
});
matchMedia('(prefers-color-scheme: dark)').addEventListener('change',applyTheme);
applyTheme();

/* ── 2. 移动菜单(.js 类已由本脚本加上;无 JS 时导航常显) ── */
var mt=document.querySelector('.menu-toggle'), nav=document.querySelector('nav.main');
if(mt&&nav){
  mt.addEventListener('click',function(){
    var open=nav.classList.toggle('open');
    mt.setAttribute('aria-expanded',open?'true':'false');
    mt.textContent=open?'收起':'目录';
  });
  document.addEventListener('keydown',function(e){
    if(e.key==='Escape'&&nav.classList.contains('open')){
      nav.classList.remove('open'); mt.setAttribute('aria-expanded','false');
      mt.textContent='目录'; mt.focus();
    }
  });
}

/* ── 3. 进入视口动效(默认全显,JS 才加遮蔽类) ── */
if('IntersectionObserver' in window &&
   !matchMedia('(prefers-reduced-motion: reduce)').matches){
  document.body.classList.add('reveal-ready');
  var io=new IntersectionObserver(function(es){
    es.forEach(function(en){
      if(en.isIntersecting){en.target.classList.add('in'); io.unobserve(en.target);}
    });
  },{rootMargin:'0px 0px -8% 0px'});
  document.querySelectorAll('[data-reveal]').forEach(function(el){io.observe(el);});
}

/* ── 4. 阅读进度 + 目录定位 ── */
var bar=document.querySelector('.progress-bar');
var article=document.querySelector('.prose');
if(bar&&article){
  var onScroll=function(){
    var r=article.getBoundingClientRect();
    var total=r.height-innerHeight;
    var done=Math.min(Math.max(-r.top,0),Math.max(total,1));
    bar.style.width=(total>0?(done/total*100):0)+'%';
  };
  addEventListener('scroll',onScroll,{passive:true}); onScroll();
}
var tocLinks=document.querySelectorAll('.toc a[href^="#"]');
if(tocLinks.length&&'IntersectionObserver' in window){
  var heads=[].map.call(tocLinks,function(a){return document.getElementById(a.getAttribute('href').slice(1));});
  var tio=new IntersectionObserver(function(es){
    es.forEach(function(en){
      if(en.isIntersecting){
        tocLinks.forEach(function(a){a.classList.toggle('active',
          a.getAttribute('href')==='#'+en.target.id);});
      }
    });
  },{rootMargin:'-10% 0px -70% 0px'});
  heads.forEach(function(h){h&&tio.observe(h);});
}

/* ── 5. 代码复制 ── */
document.querySelectorAll('.prose pre').forEach(function(pre){
  var btn=document.createElement('button');
  btn.className='copy-btn'; btn.type='button'; btn.textContent='复制';
  btn.addEventListener('click',function(){
    var text=pre.querySelector('code')?pre.querySelector('code').textContent:pre.textContent;
    function ok(){btn.textContent='已复制'; btn.classList.add('done');
      setTimeout(function(){btn.textContent='复制'; btn.classList.remove('done');},1600);}
    function fail(){btn.textContent='复制失败,请手动选择';
      setTimeout(function(){btn.textContent='复制';},2000);}
    if(navigator.clipboard&&navigator.clipboard.writeText){
      navigator.clipboard.writeText(text).then(ok,fail);
    }else{fail();}
  });
  pre.appendChild(btn);
});

/* ── 6. 复制链接(RSS 等) ── */
document.querySelectorAll('[data-copy]').forEach(function(btn){
  btn.addEventListener('click',function(){
    var v=btn.getAttribute('data-copy');
    function ok(){var t=btn.textContent; btn.textContent='已复制'; btn.classList.add('done');
      setTimeout(function(){btn.textContent=t; btn.classList.remove('done');},1600);}
    function fail(){var t=btn.textContent; btn.textContent='失败,请手动复制';
      setTimeout(function(){btn.textContent=t;},2000);}
    if(navigator.clipboard&&navigator.clipboard.writeText){
      navigator.clipboard.writeText(v).then(ok,fail);
    }else{fail();}
  });
});

/* ── 7. 图片展开:原生 <dialog>.showModal() ──
   showModal 自带背景 inert(背景不可点击、Tab 焦点约束在对话框内)
   与 Esc 关闭;cancel 事件清理状态,close 后焦点归还触发按钮。
   无 JS 时不生成按钮,图片保持原样可读。 */
document.querySelectorAll('[data-zoom]').forEach(function(img){
  var btn=document.createElement('button');
  btn.className='img-expand'; btn.type='button';
  btn.setAttribute('aria-label','展开图片: '+(img.alt||''));
  img.parentNode.insertBefore(btn,img); btn.appendChild(img);
  btn.addEventListener('click',function(){
    var dlg=document.createElement('dialog');
    dlg.className='lightbox';
    var big=new Image(); big.src=img.src; big.alt=img.alt||'';
    dlg.appendChild(big);
    if(img.dataset.cap){var c=document.createElement('div'); c.className='lb-cap';
      c.textContent=img.dataset.cap; dlg.appendChild(c);}
    var x=document.createElement('button');
    x.className='lb-close'; x.type='button'; x.textContent='关闭 ✕';
    x.addEventListener('click',function(){dlg.close();});
    dlg.appendChild(x);
    /* 点图片外的半透明背板区域关闭 */
    dlg.addEventListener('click',function(e){ if(e.target===dlg){dlg.close();} });
    dlg.addEventListener('close',function(){ btn.focus(); });
    document.body.appendChild(dlg);
    dlg.showModal();
  });
});

})();
