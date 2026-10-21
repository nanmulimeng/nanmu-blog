// 登录页交互(任务 1.1:仅前端接线;/api/login 由任务 1.2 落地,未就绪时如实提示)
const form = document.getElementById('login-form');
const statusEl = document.getElementById('login-status');
const btn = document.getElementById('login-btn');

form.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  statusEl.className = 'wb-status';
  statusEl.textContent = '';
  btn.disabled = true;
  try {
    const res = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      body: JSON.stringify({ password: document.getElementById('password').value }),
    });
    if (res.ok) {
      window.location.assign('/');
      return;
    }
    if (res.status === 401) {
      statusEl.className = 'wb-status err';
      statusEl.textContent = '口令不正确,或稍后再试(有次数限制)。';
    } else if (res.status === 429) {
      statusEl.className = 'wb-status err';
      statusEl.textContent = '失败次数过多,已锁定,请 15 分钟后再试。';
    } else {
      // 404 = 认证服务尚未接入(批 1 任务 1.2),如实显示,不伪装成功
      statusEl.className = 'wb-status err';
      statusEl.textContent = `登录服务未就绪(${res.status}),认证在批 1 后续任务接入。`;
    }
  } catch {
    statusEl.className = 'wb-status err';
    statusEl.textContent = '网络请求失败,请检查连接后重试。';
  } finally {
    btn.disabled = false;
  }
});
