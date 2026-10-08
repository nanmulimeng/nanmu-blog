/* 3D 场景加载器:检测 WebGL → 动态导入场景模块 → 用画布替换海报。
   失败路径全部静默回退到海报图,页面内容与链接不受影响。 */
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

  import('./courtyard.js').then(function(mod){
    var dark = document.documentElement.dataset.theme === 'dark' ||
      (!document.documentElement.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches);
    var host = document.createElement('div');
    host.style.cssText = 'position:absolute;inset:0;opacity:0;transition:opacity .6s ease';
    var scene = mod.createCourtyard(host, {});
    scene.setTheme(dark, true);
    box.appendChild(host);
    /* 就绪后淡入画布、撤下海报 */
    requestAnimationFrame(function(){ requestAnimationFrame(function(){
      host.style.opacity = '1';
      box.querySelectorAll('img.poster').forEach(function(poster){
        poster.style.transition = 'opacity .6s ease'; poster.style.opacity = '0';
        setTimeout(function(){ poster.remove(); }, 700);
      });
    });});
    /* HUD:复位视角 */
    var hud = document.createElement('div');
    hud.className = 'scene-hud';
    hud.appendChild(document.createElement('span'));
    var btns = document.createElement('span'); btns.className = 'btns';
    var reset = document.createElement('button');
    reset.type = 'button'; reset.textContent = '复位视角';
    reset.addEventListener('click', function(){ scene.resetView(); });
    btns.appendChild(reset); hud.appendChild(btns);
    box.appendChild(hud);
    window.__courtyard = scene;   // 供验收脚本读取 stats()
  }).catch(function(err){
    box.classList.add('no-webgl');
    if (window.console) console.warn('3D 场景加载失败,已回退静态图:', err);
  });
})();
