/* R4 场景加载器:WebGL 检测 → 动态导入 → 画布替换海报;失败静默回退。
   HUD:复位视角 / 暂停动态(环境动效读者可控,对应评审定点 #4)。
   初始主题在建场景后立即同步;setTheme 内部保证 reduced-motion 也重绘(定点 #3)。 */
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

  import('./book.js').then(function(mod){
    var dark = document.documentElement.dataset.theme === 'dark' ||
      (!document.documentElement.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches);
    var host = document.createElement('div');
    host.style.cssText = 'position:absolute;inset:0;opacity:0;transition:opacity .6s ease';
    box.appendChild(host);   // 先入 DOM,createScene 内部量取的尺寸才有效
    var links = {};
    if (box.dataset.linkPost) links.post = box.dataset.linkPost;
    if (box.dataset.linkDigest) links.digest = box.dataset.linkDigest;
    var scene = mod.createScene(host, {links: links});
    scene.setTheme(dark, true);   // 初始主题:立即应用并绘制(reduced-motion 同样生效)
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
    hud.appendChild(document.createElement('span'));
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
    window.__bookscene = scene;   // 验收脚本读取
  }).catch(function(err){
    box.classList.add('no-webgl');
    if (window.console) console.warn('R4 场景加载失败,已回退静态图:', err);
  });
})();
