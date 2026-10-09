/* ═══════════════════════════════════════════════════════════
   R6「字场 · 换页碑」全站脚本(生产版)
   源:prototypes/r6/assets/site6.js,按 ADR-0010 白名单裁剪:
   W2 三态主题 / W3 移动菜单 / W4 reveal / W9 复制盖印 /
   W10 阅读进度+目录书签 / W11 代码复制 / W12 图片展开。
   首页专属段(§4-6,W5-W8)批次 2 接入首页时再入。
   全部为增强:无 JS 时内容、导航、链接完整可用;
   首帧主题引导(W1)是 Base.astro 里的内联脚本,不在此文件。
   与原型的实现适配:§10 扫 .prose img(生产 Markdown 无 data-zoom
   通道),说明文字取 figcaption。
   ═══════════════════════════════════════════════════════════ */
(function(){
"use strict";
document.documentElement.classList.add('js');

/* ── W2. 三态主题:跟随系统 / 昼 / 夜 ── */
var KEY='nm-theme', root=document.documentElement;
function getTheme(){try{return localStorage.getItem(KEY)||'auto';}catch(e){return 'auto';}}
function setTheme(v){try{localStorage.setItem(KEY,v);}catch(e){}}
function applyTheme(){
  var m=getTheme();
  if(m==='auto'){delete root.dataset.theme;}else{root.dataset.theme=m;}
  document.querySelectorAll('#theme-btn').forEach(function(b){
    b.textContent=m==='auto'?'跟随系统':(m==='light'?'昼览':'夜览');
    b.setAttribute('data-mode',m);
  });
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

/* ── W3. 移动菜单 ── */
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

/* ── W4. 进入视口(默认全显,JS 才加遮蔽类) ── */
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

/* ── W9. 复制链接(RSS):成功后盖「已录」小印 ── */
document.querySelectorAll('[data-copy]').forEach(function(btn){
  btn.addEventListener('click',function(){
    var v=btn.getAttribute('data-copy');
    function ok(){
      btn.classList.add('stamped');
      var t=btn.textContent; btn.textContent='已复制';
      setTimeout(function(){btn.textContent=t; btn.classList.remove('stamped');},1600);
    }
    function fail(){var t=btn.textContent; btn.textContent='失败,请手动复制';
      setTimeout(function(){btn.textContent=t;},2000);}
    if(navigator.clipboard&&navigator.clipboard.writeText){
      navigator.clipboard.writeText(v).then(ok,fail);
    }else{fail();}
  });
});

/* ── W10. 阅读进度条 + 目录书签(文章页) ──
   进度条随正文滚动;目录以 aria-current 标记当前节(无 JS 时仍是普通锚链) */
var bar=document.querySelector('.progress-bar');
var article=document.querySelector('.prose');
if(bar&&article){
  var onRead=function(){
    var r=article.getBoundingClientRect();
    var total=r.height-innerHeight;
    var done=Math.min(Math.max(-r.top,0),Math.max(total,1));
    bar.style.width=(total>0?(done/total*100):0)+'%';
  };
  addEventListener('scroll',onRead,{passive:true}); onRead();
}
var tocLinks=[].slice.call(document.querySelectorAll('.toc a[href^="#"]'));
if(tocLinks.length&&'IntersectionObserver' in window){
  var heads=tocLinks.map(function(a){return document.getElementById(a.getAttribute('href').slice(1));});
  var cur=null;
  function markToc(id){
    if(id===cur)return; cur=id;
    tocLinks.forEach(function(a){
      if(a.getAttribute('href')==='#'+id)a.setAttribute('aria-current','true');
      else a.removeAttribute('aria-current');
    });
  }
  var tio=new IntersectionObserver(function(es){
    es.forEach(function(en){ if(en.isIntersecting) markToc(en.target.id); });
  },{rootMargin:'-15% 0px -70% 0px'});
  heads.forEach(function(h){h&&tio.observe(h);});
}

/* ── W11. 代码块复制(文章页 pre) ── */
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

/* ── W12. 图片展开:原生 <dialog>.showModal() ──
   showModal 自带背景 inert 与焦点约束、Esc 关闭;close 后焦点归还触发按钮。
   无 JS 时不生成按钮,图片保持原样可读。 */
document.querySelectorAll('.prose img').forEach(function(img){
  var btn=document.createElement('button');
  btn.className='img-expand'; btn.type='button';
  btn.setAttribute('aria-label','展开图片: '+(img.alt||''));
  img.parentNode.insertBefore(btn,img); btn.appendChild(img);
  btn.addEventListener('click',function(){
    var dlg=document.createElement('dialog');
    dlg.className='lightbox';
    var big=new Image(); big.src=img.src; big.alt=img.alt||'';
    dlg.appendChild(big);
    var fig=img.closest('figure'), capEl=fig&&fig.querySelector('figcaption');
    if(capEl&&capEl.textContent.trim()){var c=document.createElement('div'); c.className='lb-cap';
      c.textContent=capEl.textContent.trim(); dlg.appendChild(c);}
    var x=document.createElement('button');
    x.className='lb-close'; x.type='button'; x.textContent='关闭 ✕';
    x.addEventListener('click',function(){dlg.close();});
    dlg.appendChild(x);
    dlg.addEventListener('click',function(e){ if(e.target===dlg){dlg.close();} });
    dlg.addEventListener('close',function(){ btn.focus(); });
    document.body.appendChild(dlg);
    dlg.showModal();
  });
});

})();
