/* ═══════════════════════════════════════════════════════════
   R5「字场 · 碑页」首页脚本
   全部为增强:无 JS 时内容、导航、链接完整可用。
   与 site4 差异:新增朱砂装订线(滚动延伸 + 节点点亮);
   图片 lightbox / 代码复制等内页能力不属首页,不重复装载。
   ═══════════════════════════════════════════════════════════ */
(function(){
"use strict";
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

/* ── 2. 移动菜单 ── */
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

/* ── 3. 进入视口(默认全显,JS 才加遮蔽类) ── */
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

/* ── 4. 朱砂装订线:碑页装订线落入正文,随滚动延伸;节点对应各节 ──
   reduced-motion:线全显、节点全亮,不做滚动动画;节点定位两种模式都执行。 */
var thread=document.querySelector('.thread');
if(thread){
  var line=thread.querySelector('.line');
  var knots=[].slice.call(thread.querySelectorAll('.knot'));
  var reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  var flow=document.querySelector('main.flow');
  /* 各 knot 纵向定位到对应节标题;初始、resize、字体就绪(版式重排)后都要重算 */
  function layoutKnots(){
    if(!flow)return;
    knots.forEach(function(k){
      var target=document.querySelector(k.dataset.for);
      if(target){
        k.style.top=(target.getBoundingClientRect().top+scrollY-flow.offsetTop+8)+'px';
      }
    });
  }
  var onScroll=function(){
    var r=flow.getBoundingClientRect();
    var total=r.height-innerHeight*0.4;
    var done=Math.min(Math.max(-r.top+innerHeight*0.55,0),Math.max(total,1));
    var p=total>0?done/total:1;
    line.style.transform='scaleY('+p+')';
    knots.forEach(function(k){
      var ky=parseFloat(k.style.top)||0;
      k.classList.toggle('lit', p*r.height>=ky);
    });
  };
  layoutKnots();
  if(document.fonts&&document.fonts.ready)document.fonts.ready.then(layoutKnots);
  if(reduced){
    line.style.transform='scaleY(1)';
    knots.forEach(function(k){k.classList.add('lit');});
    addEventListener('resize',layoutKnots);
  }else{
    addEventListener('scroll',onScroll,{passive:true});
    addEventListener('resize',function(){layoutKnots();onScroll();});
    onScroll();
  }
}

/* ── 5. 复制链接(RSS) ── */
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

})();
