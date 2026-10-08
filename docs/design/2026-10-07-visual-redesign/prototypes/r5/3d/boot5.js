/* R5 场景加载器:WebGL 检测 → 动态导入 → 画布替换海报;失败静默回退。
   与 boot4 差异:createScene 返回 Promise(碑页文字纹理等分片字体就绪)。
   HUD:复位视角 / 暂停动态;初始主题立即同步;nm-theme 事件联动。 */
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

  import('./scene5.js').then(function(mod){
    var dark = document.documentElement.dataset.theme === 'dark' ||
      (!document.documentElement.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches);
    var host = document.createElement('div');
    host.className = 'scene-host';   // 定位交给 CSS(桌面满幅/手机 56dvh),不动内联样式
    host.style.opacity = '0'; host.style.transition = 'opacity .6s ease';
    box.appendChild(host);   // 先入 DOM,createScene 内部量取的尺寸才有效
    var links = {};
    if (box.dataset.linkPost) links.post = box.dataset.linkPost;
    if (box.dataset.linkDigest) links.digest = box.dataset.linkDigest;
    return mod.createScene(host, {links: links}).then(function(scene){
      scene.setTheme(dark, true);   // 初始主题:立即应用并绘制(reduced-motion 同样生效)
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
        /* 主题联动 */
        document.addEventListener('nm-theme', function(ev){ scene.setTheme(!!(ev.detail && ev.detail.dark)); });
        window.__bookscene = scene;   // 验收脚本读取(沿用 R4 全局名)

        /* 落线:碑页装订线底部 → 正文朱砂线的可见转接(装饰,无它内容完整)。
           直角两段(竖落 + 沿 main.flow 顶横走),取线装走线的工艺语义;
           斜线会横穿 hero 按钮区,故不取。仅 hero 在视口内时随帧更新。 */
        var threadEl = document.querySelector('.thread');
        if (threadEl && scene.projectBindingBottom){
          var dropV = document.createElement('div');
          dropV.className = 'thread-drop v'; dropV.setAttribute('aria-hidden', 'true');
          var dropH = document.createElement('div');
          dropH.className = 'thread-drop h'; dropH.setAttribute('aria-hidden', 'true');
          document.body.appendChild(dropV); document.body.appendChild(dropH);
          var heroVisible = true, dropTicking = false;
          function updDrop(){
            if (!heroVisible){ dropTicking = false; dropV.style.opacity = '0'; dropH.style.opacity = '0'; return; }
            dropTicking = true;
            var p = scene.projectBindingBottom();
            if (!p){ dropV.style.opacity = '0'; dropH.style.opacity = '0'; }
            else {
              var r = host.getBoundingClientRect();
              var ax = r.left + window.scrollX + p.x, ay = r.top + window.scrollY + p.y;
              var tr = threadEl.getBoundingClientRect();
              var bx = tr.left + window.scrollX + 1.5, by = tr.top + window.scrollY;
              if (by > ay + 8){
                dropV.style.opacity = '0.9'; dropH.style.opacity = '0.9';
                dropV.style.left = (ax - 1.5) + 'px'; dropV.style.top = ay + 'px';
                dropV.style.height = (by - ay) + 'px';
                dropH.style.left = bx + 'px'; dropH.style.top = (by - 1.5) + 'px';
                dropH.style.width = (ax - bx) + 'px';
              } else { dropV.style.opacity = '0'; dropH.style.opacity = '0'; }
            }
            requestAnimationFrame(updDrop);
          }
          if ('IntersectionObserver' in window){
            new IntersectionObserver(function(en){
              var vis = en[0].isIntersecting;
              if (vis && !dropTicking){ heroVisible = true; requestAnimationFrame(updDrop); }
              heroVisible = vis;
            }, {threshold: 0.05}).observe(box);
          }
          requestAnimationFrame(updDrop);
        }
      });
    });
  }).catch(function(err){
    box.classList.add('no-webgl');
    if (window.console) console.warn('R5 场景加载失败,已回退静态图:', err);
  });
})();
