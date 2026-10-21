/* R6 场景加载器(生产,/3d/boot6.js,仅首页引用)。
   触发顺序契约(批次 2):poster 是 HTML img,首包即请求并先行呈现;
   WebGL 探测通过后,等浏览器空闲(requestIdleCallback,2s 超时兜底)
   才动态 import 场景——3D 字节请求的发起序始终晚于 poster(由验收
   脚本按 CDP 请求时间线断言),idle 前零 3D 请求。
   失败终态:WebGL 不可用/模块加载失败 → .no-webgl,poster 常显,
   页签(HTML 面板)照常工作,无空白/遮罩/永久加载。
   内容同源:article/digest/site 从 #scene3d data-* JSON(构建期生成)
   解析传入 scene6,解析失败按无数据排默认态;HUD/主题/页签同步/落线同原型。 */
(function(){
  var box = document.getElementById('scene3d');
  if (!box) return;

  function webglOK(){
    try{
      var c = document.createElement('canvas');
      return !!(window.WebGLRenderingContext && (c.getContext('webgl2') || c.getContext('webgl')));
    }catch(e){ return false; }
  }
  if (!webglOK()){ box.classList.add('no-webgl'); return; }

  /* 最新有效主题(data-theme 优先,缺省看系统);场景就绪时按它首显,
     不用加载开始时的旧快照 */
  function nowDark(){
    return document.documentElement.dataset.theme === 'dark' ||
      (!document.documentElement.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches);
  }
  var bookScene = null;
  /* 主题联动提前注册:场景就绪前的 nm-theme 切换不再丢失;
     bookScene 为空时忽略,由就绪时的 setTheme(nowDark()) 兜住 */
  document.addEventListener('nm-theme', function(ev){
    if (bookScene) bookScene.setTheme(!!(ev.detail && ev.detail.dark));
  });

  var started = false;
  function boot(){
    if (started) return; started = true;
    import('./scene6.js').then(function(mod){
    var host = document.createElement('div');
    host.className = 'scene-host';   // 定位交给 CSS(桌面满幅/手机 56dvh),不动内联样式
    host.style.opacity = '0'; host.style.transition = 'opacity .6s ease';
    box.appendChild(host);   // 先入 DOM,createScene 内部量取的尺寸才有效
    box.classList.add('has-scene');   // 手机端 poster 转叠加布局(home.css),交接区恒一格 56dvh
    var links = {};
    if (box.dataset.linkPost) links.post = box.dataset.linkPost;
    if (box.dataset.linkDigest) links.digest = box.dataset.linkDigest;
    if (box.dataset.linkAbout) links.about = box.dataset.linkAbout;
    /* 内容同源:data-article/data-digest/data-site 为空串=无该数据;
       JSON 损坏按无数据处理(终态明确),不中断场景 */
    var article = null;
    try{ article = box.dataset.article ? JSON.parse(box.dataset.article) : null; }
    catch(e){ article = null; }
    var digest = null;
    try{ digest = box.dataset.digest ? JSON.parse(box.dataset.digest) : null; }
    catch(e){ digest = null; }
    var site = null;
    try{ site = box.dataset.site ? JSON.parse(box.dataset.site) : null; }
    catch(e){ site = null; }
    /* 3D 内点选后排页 → 通知页面页签(home.js 监听 nm-page) */
    var onSelect = function(pid){
      document.dispatchEvent(new CustomEvent('nm-page', {detail: {pid: pid}}));
    };
    return mod.createScene(host, {links: links, onSelect: onSelect, article: article, digest: digest, site: site}).then(function(scene){
      bookScene = scene;
      scene.setTheme(nowDark(), true);   // 初始主题:立即应用并绘制(reduced-motion 同样生效)
      /* 等碑页文字纹理就绪再替换 poster(否则访客会看到素纸突然变文字页);
         3.5s 超时保护:字体挂起不致 poster 永不退场;
         纹理失败:素纸仍成立(纸质感在,无文字),继续替换并告警。 */
      var guarded = Promise.race([
        scene.texReady,
        new Promise(function(res){ setTimeout(res, 3500); })
      ]).catch(function(err){
        if (window.console) console.warn('碑页文字纹理失败,回退素纸:', err);
      });
      return guarded.then(function(){
        requestAnimationFrame(function(){ requestAnimationFrame(function(){
          host.style.opacity = '1';
          box.querySelectorAll('img.poster').forEach(function(p){
            p.style.transition = 'opacity .6s ease'; p.style.opacity = '0';
            setTimeout(function(){ p.remove(); }, 700);
          });
        });});
        /* HUD */
        var hud = document.createElement('div');
        hud.className = 'scene-hud';
        var btns = document.createElement('span'); btns.className = 'btns';
        var ambBtn = document.createElement('button');
        ambBtn.type = 'button';
        function syncAmb(){ ambBtn.textContent = scene.isAmbientOn() ? '暂停动态' : '恢复动态';
          ambBtn.setAttribute('aria-pressed', String(!scene.isAmbientOn())); }
        ambBtn.addEventListener('click', function(){ scene.setAmbient(!scene.isAmbientOn()); syncAmb(); });
        syncAmb();
        var reset = document.createElement('button');
        reset.type = 'button'; reset.textContent = '复位视角';
        reset.addEventListener('click', function(){ scene.resetView(); });
        btns.appendChild(ambBtn); btns.appendChild(reset); hud.appendChild(btns);
        box.appendChild(hud);
        window.__bookscene = scene;   // 验收脚本读取(沿用 R4 全局名)

        /* 场景就绪前的页签选择在此同步(用户在 3D 加载期间已点过别的栏目) */
        var curTab = document.querySelector('.ptab.on');
        if (curTab && curTab.dataset.pid && curTab.dataset.pid !== scene.current()){
          scene.select(curTab.dataset.pid);
        }
      });
    });
    }).catch(function(err){
      /* 半成品容器清理:残留的空 scene-host 会在手机端多撑一格
         56dvh,静态首页不留额外空白 */
      var dead = box.querySelector('.scene-host');
      if (dead) dead.remove();
      box.classList.remove('has-scene');
      box.classList.add('no-webgl');
      if (window.console) console.warn('R6 场景加载失败,已回退静态图:', err);
    });
  }
  /* idle 调度:空闲才拉 3D 字节;2s 超时兜底保证慢机器/无空闲信号
     (后台标签页等)下加载仍会发生;不支持 rIC 的环境退定时器 */
  if ('requestIdleCallback' in window) requestIdleCallback(boot, {timeout: 2000});
  else setTimeout(boot, 300);
})();
