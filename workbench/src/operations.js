// 发布/撤下/双远端操作(DESIGN §2.1/§4.4/§4.5,批 3)
// 状态机七内部态:created→commit_created→backup_received→deploy_received
// →confirmed(终) | github_rejected/deploy_rejected(未终,待恢复) | failed(终)
// 铁律:绝 force push;部分成功阻止新发布;github→deploy 领先转人工;
// 确认=内容身份核对(不是 release.txt 等值)。
import { execFile } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { promisify } from 'node:util';

const execFileP = promisify(execFile);
const TERMINAL = new Set(['confirmed', 'failed', 'cancelled']);
const POSTS = 'site/src/content/posts';

export function createGitOps({ repoPath, wtPath, opsDir, remotes, now = Date.now,
                                 getRelease, commitEnv }, gitEnv = {}) {
  const E = { ...gitEnv, ...(commitEnv || {}) };
  const git = (args, cwd) => execFileP('git', args,
    { cwd, env: { ...process.env, ...E }, maxBuffer: 16 * 1024 * 1024, timeout: 60_000 });
  const hooks = { afterCommit: null, afterBackupPush: null };

  /* ── 初始化:repo.git(裸克隆自 deploy)+ github remote + 固定 repo.wt ── */
  function init() {
    fs.mkdirSync(opsDir, { recursive: true });
    if (!fs.existsSync(path.join(repoPath, 'HEAD'))) {
      // execFile 同步语义:用 execFileSync 场景由调用方保证首次;此处 throw 前先做轻克隆
      throw new Error('repo_not_initialized');
    }
  }

  async function ensureInit() {
    if (fs.existsSync(path.join(repoPath, 'HEAD'))) return;
    fs.mkdirSync(path.dirname(repoPath), { recursive: true });
    await git(['clone', '--bare', remotes.deploy, repoPath], path.dirname(repoPath));
    await git(['remote', 'add', 'github', remotes.github], repoPath);
    if (!fs.existsSync(path.join(wtPath, '.git'))) {
      await git(['worktree', 'add', wtPath, 'main'], repoPath);
    }
  }

  /* ── 记录读写(每 op 一个 JSON,先落骨架再动 git) ── */
  const opFile = (id) => path.join(opsDir, `${id}.json`);
  function readAll() {
    init0();
    return fs.readdirSync(opsDir).filter((f) => f.endsWith('.json'))
      .map((f) => JSON.parse(fs.readFileSync(path.join(opsDir, f), 'utf8')));
  }
  function init0() { fs.mkdirSync(opsDir, { recursive: true }); }
  function save(rec) { fs.writeFileSync(opFile(rec.id), JSON.stringify(rec, null, 2), 'utf8'); }
  const byIdem = (key) => readAll().find((o) => o.idem_key === key);

  async function fetchRefs() {
    await git(['fetch', remotes.deploy, 'main:refs/remotes/deploy/main'], repoPath);
    await git(['fetch', remotes.github, 'main:refs/remotes/github/main'], repoPath);
  }
  async function ref(name) {
    try { return (await git(['rev-parse', name], repoPath)).stdout.trim(); }
    catch { return null; }
  }
  /* 当前 release:优先注入的 getRelease(生产=HTTP release.txt);
     未配置/失败时退化为 deploy main(开发/演练默认,与测试同口径) */
  async function currentRelease() {
    if (getRelease) {
      try { const r = await getRelease(); if (r && r.sha) return r; } catch { /* 落到兜底 */ }
    }
    await git(['fetch', remotes.deploy, 'main:refs/remotes/deploy/main'], repoPath);
    return { sha: await ref('refs/remotes/deploy/main') };
  }

  /* ── 闸门(a):未终态存在→拒;闸门(b):github 领先/分叉→转人工 ── */
  function gateA() {
    const open = readAll().filter((o) => !TERMINAL.has(o.status));
    if (open.length) {
      const err = new Error(`操作 ${open[0].idem_key}(${open[0].id}) 尚未终态(${open[0].status}),先按恢复表处理`);
      err.code = 'OPERATION_OPEN';
      throw err;
    }
  }
  async function gateB() {
    const d = await ref('refs/remotes/deploy/main');
    const g = await ref('refs/remotes/github/main');
    if (!d) throw new Error('deploy_main_missing');
    if (!g || g === d) return { base: d };
    let gIsAncestor = false;
    try { await git(['merge-base', '--is-ancestor', g, d], repoPath); gIsAncestor = true; }
    catch { gIsAncestor = false; }
    if (gIsAncestor) return { base: d }; // github 落后=常态
    const diff = (await git(['log', '--oneline', `${d}..${g}`], repoPath)).stdout.trim();
    const err = new Error('github 领先或分叉,转人工处理(不自动收敛)');
    err.code = 'REMOTES_DIVERGED';
    err.detail = diff;
    throw err;
  }

  async function treeHasBlob(sha, relPath, content) {
    let blob;
    try { blob = (await git(['rev-parse', `${sha}:${relPath}`], repoPath)).stdout.trim(); }
    catch { return false; }
    if (content === undefined) return true;
    const tmp = path.join(opsDir, `.hash-${crypto.randomBytes(4).toString('hex')}`);
    fs.writeFileSync(tmp, content, 'utf8');
    const want = (await git(['hash-object', tmp], repoPath)).stdout.trim();
    fs.rmSync(tmp, { force: true });
    return blob === want;
  }

  function extractTitle(content) {
    const m = /^title:\s*(.+)$/m.exec(content || '');
    return m ? m[1].trim() : '';
  }

  /* ── 核心执行:骨架→分支→变更→commit→落 sha→双跳 push→清理 ── */
  async function runOp({ kind, slug, idemKey, content, draftRev }) {
    await ensureInit();
    const existing = byIdem(idemKey);
    if (existing) return existing; // 幂等:同键同记录(§4.4 窗口②)
    gateA();
    await fetchRefs();
    const { base } = await gateB();

    // slug 占用(§2.1 反例6):远端已有同 slug 且本工作台从未发布过它→拒绝
    const mine = readAll().some((o) => o.slug === slug && o.status === 'confirmed');
    const takenRemote = await treeHasBlob(base, `${POSTS}/${slug}.md`);
    if (kind === 'publish' && takenRemote && !mine) {
      const err = new Error(`slug "${slug}" 已被远端文章占用,请改 slug`);
      err.code = 'SLUG_TAKEN';
      throw err;
    }
    if (kind === 'withdraw' && !takenRemote) {
      const err = new Error(`slug "${slug}" 不存在于远端,无可撤下`);
      err.code = 'NOT_FOUND';
      throw err;
    }

    const id = crypto.randomUUID().slice(0, 8);
    const rec = { id, idem_key: idemKey, kind, slug, draft_rev: draftRev ?? null,
      content: kind === 'publish' ? (content ?? null) : null,  // 供内容身份核对
      commit_sha: null, base_sha: base, status: 'created',
      created_at: now(), pushed_backup_at: null, pushed_deploy_at: null,
      confirmed_at: null, failed_at: null, release_sha: null };
    save(rec); // 先落骨架再动 git

    const branch = `op/${id}`;
    await git(['branch', branch, base], repoPath);
    await git(['checkout', '-q', branch], wtPath);
    try {
      const file = path.join(wtPath, POSTS, `${slug}.md`);
      if (kind === 'publish') {
        fs.mkdirSync(path.dirname(file), { recursive: true });
        fs.writeFileSync(file, content, 'utf8');
      } else {
        fs.rmSync(file, { force: true });
      }
      const title = kind === 'publish' ? extractTitle(content) || slug : slug;
      const msg = kind === 'publish' ? `post(site): 发布〈${title}〉` : `post(site): 撤下〈${title}〉`;
      await git(['add', '-A'], wtPath);
      const ce = { GIT_AUTHOR_NAME: 'nanmu', GIT_AUTHOR_EMAIL: 'workbench@nanmu.xyz',
        GIT_COMMITTER_NAME: 'nanmu', GIT_COMMITTER_EMAIL: 'workbench@nanmu.xyz' };
      await git(['commit', '-m', msg], wtPath);
      if (hooks.afterCommit) hooks.afterCommit(rec);
      rec.commit_sha = (await git(['rev-parse', 'HEAD'], wtPath)).stdout.trim();
      rec.status = 'commit_created';
      save(rec); // 窗口①恢复锚:分支名即操作身份

      try {
        await git(['push', remotes.github, `${branch}:main`], repoPath);
        rec.status = 'backup_received'; rec.pushed_backup_at = now(); save(rec);
      } catch (e) {
        rec.status = 'github_rejected'; rec.error = String(e.message).slice(0, 300); save(rec);
        return rec;
      }
      if (hooks.afterBackupPush) hooks.afterBackupPush(rec);
      try {
        await git(['push', remotes.deploy, `${branch}:main`], repoPath);
        rec.status = 'deploy_received'; rec.pushed_deploy_at = now(); save(rec);
      } catch (e) {
        rec.status = 'deploy_rejected'; rec.error = String(e.message).slice(0, 300); save(rec);
        return rec; // 部分成功:保留 op 分支为恢复证据
      }
      await cleanup(branch, rec.commit_sha);
      return rec;
    } catch (e) {
      // 窗口①(commit 已产生、sha 未落盘)不判 failed:分支名即身份锚,
      // recover() 按分支 HEAD 补记;commit 前失败则 status 停在 created,
      // 闸门(a)拦新发布直至人工处理
      rec.error = String(e.message).slice(0, 300);
      save(rec);
      try { await git(['checkout', '-q', 'main'], wtPath); } catch { /* 尽力 */ }
      throw e;
    }
  }

  async function cleanup(branch, sha) {
    try {
      await git(['update-ref', 'refs/heads/main', sha], repoPath);
      await git(['update-ref', '-d', `refs/heads/${branch}`], repoPath);
      await git(['checkout', '-q', 'main'], wtPath);
    } catch { /* 清理尽力而为,记录已完整 */ }
  }

  /* ── 确认:内容身份核对(当前 release 树中目标路径) ── */
  async function confirm(opId) {
    const rec = readAll().find((o) => o.id === opId);
    if (!rec) throw new Error('op_not_found');
    if (!rec.commit_sha) return rec;
    const rel = `${POSTS}/${rec.slug}.md`;
    const release = await currentRelease();
    if (!release || !release.sha) return rec;
    const okNow = rec.kind === 'publish'
      ? await treeHasBlob(release.sha, rel, rec.content ?? undefined)
      : !(await treeHasBlob(release.sha, rel));
    if (okNow) {
      rec.status = 'confirmed'; rec.confirmed_at = now(); rec.release_sha = release.sha;
      save(rec);
    } else if (rec.status === 'deploy_received' && now() - rec.created_at > 180_000) {
      rec.status = 'pending_confirm'; save(rec); // 180s 未确认≠失败(§4.4)
    }
    return rec;
  }

  /* ── 部分成功恢复:同 SHA 重试 push deploy(不重做 commit) ── */
  async function retryDeploy(opId) {
    const rec = readAll().find((o) => o.id === opId);
    if (!rec || !rec.commit_sha) throw new Error('op_not_found');
    const d = await ref('refs/remotes/deploy/main');
    await git(['fetch', remotes.deploy, 'main:refs/remotes/deploy/main'], repoPath);
    await git(['push', remotes.deploy, `${rec.commit_sha}:main`], repoPath);
    rec.status = 'deploy_received'; rec.pushed_deploy_at = now(); save(rec);
    await cleanup(`op/${rec.id}`, rec.commit_sha);
    return rec;
  }

  /* ── 重启恢复:窗口①(commit_sha 未落盘)按分支 HEAD 补记 ── */
  async function recover() {
    let healed = 0;
    await ensureInit();
    for (const rec of readAll()) {
      if (!rec.commit_sha && rec.status !== 'failed') {
        const head = await ref(`refs/heads/op/${rec.id}`);
        if (head && head !== rec.base_sha) {
          rec.commit_sha = head; rec.status = 'commit_created'; save(rec); healed++;
        }
      }
    }
    return healed;
  }

  function listInternal() { return readAll(); }
  /* 界面态:confirmed 的 publish 动态复核当前 release——内容不一致(被改写/
     撤下)=superseded(§4.4 替代判定),不静态缓存 */
  async function listView() {
    const all0 = readAll();
    if (!all0.length) return [];  // 无操作不触发 git(repo 未初始化时不 500)
    const release = await currentRelease();
    const out = [];
    for (const o of readAll()) {
      const v = { ...o, state: o.status };
      if (o.status === 'confirmed' && release && release.sha) {
        const rel = `${POSTS}/${o.slug}.md`;
        const cur = o.kind === 'publish'
          ? await treeHasBlob(release.sha, rel, o.content ?? undefined)
          : !(await treeHasBlob(release.sha, rel));
        v.state = cur ? (o.kind === 'publish' ? 'published' : 'withdrawn') : 'superseded';
      }
      out.push(v);
    }
    return out;
  }

  return {
    publish: (a) => runOp({ ...a, kind: 'publish' }),
    withdraw: (a) => runOp({ ...a, kind: 'withdraw' }),
    confirm, retryDeploy, recover, listInternal, listView,
    testHooks: () => hooks,
  };
}
