/* ═══════════════════════════════════════════════════════════
   R6「字场 · 换页碑」首页脚本
   全部为增强:无 JS 时内容、导航、链接完整可用。
   与 site5 差异:页签目录与 3D 页叠双向联动(nm-page 事件);
   「这个站」三层可展开说明;复制 RSS 盖印反馈。
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

/* ── 4. 页签目录 ↔ 3D 页叠(双向联动) ──
   页签点击 → scene.select(pid) 换页 + 面板切换;
   3D 内点选后排页 → nm-page 事件 → 页签/面板同步。
   场景未加载(WebGL 失败/无 module)时,页签仍切换 HTML 面板,不空转。 */
var tabs=[].slice.call(document.querySelectorAll('.ptab'));
var panels=[].slice.call(document.querySelectorAll('.tpanel'));
function showPanel(pid){
  tabs.forEach(function(t){
    var on=t.dataset.pid===pid;
    t.classList.toggle('on',on);
    t.setAttribute('aria-selected',String(on));
    t.tabIndex=on?0:-1;   /* 漫游 tabindex:Tab 只进当前页签,方向键在页签间移动 */
  });
  panels.forEach(function(p){
    var on=p.id==='panel-'+pid;
    p.classList.toggle('on',on);
    if(on){p.removeAttribute('hidden');}else{p.setAttribute('hidden','');}
  });
}
function activateTab(t,focus){
  var pid=t.dataset.pid;
  showPanel(pid);
  if(window.__bookscene&&window.__bookscene.select)window.__bookscene.select(pid);
  if(focus)t.focus();
}
tabs.forEach(function(t){
  t.tabIndex=t.classList.contains('on')?0:-1;
  t.addEventListener('click',function(){activateTab(t);});
});
/* 键盘:方向键/Home/End 移动并选中(自动激活,与点击行为一致) */
var tablist=document.querySelector('.page-tabs');
if(tablist)tablist.addEventListener('keydown',function(ev){
  var i=tabs.indexOf(document.activeElement);
  if(i<0)return;
  var j=-1;
  if(ev.key==='ArrowRight'||ev.key==='ArrowDown')j=(i+1)%tabs.length;
  else if(ev.key==='ArrowLeft'||ev.key==='ArrowUp')j=(i-1+tabs.length)%tabs.length;
  else if(ev.key==='Home')j=0;
  else if(ev.key==='End')j=tabs.length-1;
  if(j>=0){ev.preventDefault();activateTab(tabs[j],true);}
});
document.addEventListener('nm-page',function(ev){
  if(ev.detail&&ev.detail.pid)showPanel(ev.detail.pid);
});

/* ── 4b. 封面→正文跨页过渡的挂名策略(渐进增强;reduced-motion 下 VT 整体禁用,以下为空操作) ──
   CSS 不常驻封面名,按入口分别定义转场:
   - 点击可见封面卡:点击时挂名,旧页快照在点击后采集,封面 morph 进文章页头;
   - 「读全文」按钮 / 3D 前景页入口:不挂名,只走根过渡(屏幕外封面不无关飞入);
   - 返回:文章页头常驻 latest-cover;本页 pagereveal 若处于 VT 中(即回程),补挂封面名接住 morph。 */
var coverCard=document.querySelector('.cover-card');
if(coverCard){
  coverCard.addEventListener('click',function(){
    coverCard.style.viewTransitionName='latest-cover';
  });
  addEventListener('pagereveal',function(ev){
    if(ev.viewTransition)coverCard.style.viewTransitionName='latest-cover';
  });
}

/* ── 5. 朱砂装订线:前景页装订线落入正文,随滚动延伸;节点对应各节 ──
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

/* ── 6. 「这个站」三层展开:手风琴 + 分层图联动;键盘可操作 ── */
var layerItems=[].slice.call(document.querySelectorAll('.layer-item'));
var layerFig=[].slice.call(document.querySelectorAll('.layers-fig .ly'));
function openLayer(name){
  layerItems.forEach(function(it){
    var on=it.dataset.layer===name;
    it.classList.toggle('on',on);
    var head=it.querySelector('.li-head'), body=it.querySelector('.li-body');
    head.setAttribute('aria-expanded',String(on));
    if(on){body.removeAttribute('hidden');}else{body.setAttribute('hidden','');}
  });
  layerFig.forEach(function(ly){
    var on=ly.dataset.layer===name;
    ly.classList.toggle('on',on);
    ly.setAttribute('aria-pressed',String(on));
  });
}
layerItems.forEach(function(it){
  it.querySelector('.li-head').addEventListener('click',function(){
    openLayer(it.dataset.layer);
  });
});
/* 双向:分层图纸卡本身是按钮,点击/键盘(原生 Enter/Space)同样展开对应说明 */
layerFig.forEach(function(ly){
  ly.addEventListener('click',function(){openLayer(ly.dataset.layer);});
});

/* ── 7. 复制链接(RSS):成功后盖「已录」小印,与版面语言一致 ── */
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

})();
