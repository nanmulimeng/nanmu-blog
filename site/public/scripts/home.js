/* ═══════════════════════════════════════════════════════════
   R6 首页专属脚本(W5-W8 页面侧,ADR-0010 白名单;仅 index 引用)
   来源:prototypes/r6/assets/site6.js §4/§4b/§5/§6,生产适配:
   §4b 回程来源正则从原型文件名 post-*.html 改为 /posts/<id>/。
   全部为增强:无 JS 时内容、导航、链接完整可用(三层手风琴全展开
   由 home.css 的 html.js 门控承担,本文件只做切换)。
   全站行为(W1-W4/W9-W12)在 site.js,本文件不重复。
   ═══════════════════════════════════════════════════════════ */
(function(){
"use strict";

/* ── W5. 页签目录 ↔ 3D 页叠(双向联动)──
   页签点击 → scene.select(pid) 换页 + 面板切换;
   3D 内点选后排页 → nm-page 事件 → 页签/面板同步。
   场景未加载(boot6 未接入/WebGL 失败)时,页签仍切换 HTML 面板,不空转。 */
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

/* ── W6. 封面→正文跨页过渡的挂名策略(渐进增强;reduced-motion 下 VT 整体禁用,以下为空操作)──
   CSS 不常驻封面名。挂名是有生命周期的临时状态:只在即将发生的这一次
   导航需要时挂上,转场完成/跳过/导航形态改变后恢复默认——否则残留挂名
   会让后续无关入口(「读全文」按钮/3D 前景页)继承封面 morph,屏幕外
   封面飞入文章页头。按入口分别定义:
   - 去程:点击可见封面才挂名(修饰键/非左键=新窗口打开,无同窗 VT,不挂;
     bfcache 往返恢复时摘除);
   - 回程:文章页头常驻 latest-cover;本页新鲜加载、处于 VT 中、且来源是
     文章页时补挂封面名接住 morph——"pagereveal 带 viewTransition"不等于
     "从文章返回"(posts→首页同型导航),来源用 navigation.activation.from
     (无则退 document.referrer,两者都读不到时保守不挂);
     补挂后在该 VT finished(完成或跳过)即摘除。 */
var coverCard=document.querySelector('.cover-card');
if(coverCard){
  function clearCoverName(){coverCard.style.viewTransitionName='';}
  function reducedMotion(){return matchMedia('(prefers-reduced-motion: reduce)').matches;}
  function cameFromArticle(){
    /* 文章页=生产路由 /posts/<id>/(尾部容忍 ?/#) */
    var RE=/\/posts\/[^\/]+\/(\?|#|$)/;
    try{
      if(window.navigation&&navigation.activation&&navigation.activation.from)
        return RE.test(navigation.activation.from.url);
    }catch(e){}
    return RE.test(document.referrer||'');
  }
  coverCard.addEventListener('click',function(e){
    if(reducedMotion())return;                    /* VT 已被 CSS 禁用,不挂名 */
    if(e.defaultPrevented||e.button!==0||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return;
    coverCard.style.viewTransitionName='latest-cover';
  });
  addEventListener('pageshow',function(ev){if(ev.persisted)clearCoverName();});
  addEventListener('pagereveal',function(ev){
    if(!ev.viewTransition)return;                 /* 无 VT(含 reduced-motion 禁用) */
    if(!cameFromArticle())return;                 /* 非文章页来源,不补挂 */
    coverCard.style.viewTransitionName='latest-cover';
    /* 挂名只服务于这一次回程转场:完成或跳过都摘除(0.35s 窗口内再次
       导航属极端边缘,不在生产范围) */
    ev.viewTransition.finished.then(clearCoverName,clearCoverName);
  });
}

/* ── W7. 「这个站」三层展开:手风琴 + 分层图联动;键盘可操作 ──
   初始不隐藏非选中层以外的东西:home.css 在 html.js 下隐藏非选中 .li-body,
   openLayer 统一用 hidden 属性管理(两机制一致,无 JS 时全展开)。 */
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

})();
