// 批 3 发布/撤下/双远端/恢复:TDD 先行测试(RED)
// 契约:DESIGN §2.1(闸门/恢复表/六场景)+§4.4(七态/幂等/五中断/内容身份核对)
// +§4.5(撤下)。测试远端=临时 bare 双远端,绝不碰生产。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createGitOps } from '../src/operations.js';

const G = (args, cwd, extraEnv = {}) =>
  execFileSync('git', args, { cwd, env: { ...process.env, ...extraEnv } });

function mkEnv() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'wbops-'));
  const env = {
    GIT_AUTHOR_NAME: 't', GIT_AUTHOR_EMAIL: 't@t',
    GIT_COMMITTER_NAME: 't', GIT_COMMITTER_EMAIL: 't@t',
  };
  const mkBare = (name, withSeed) => {
    const b = path.join(dir, name);
    G(['init', '--bare', '-b', 'main', b], dir, env);
    if (withSeed) {
      const s = path.join(dir, name + '-seed');
      G(['clone', b, s], dir, env);
      fs.mkdirSync(path.join(s, 'site', 'src', 'content', 'posts'), { recursive: true });
      fs.writeFileSync(path.join(s, 'site', 'README'), 'x');
      G(['add', '-A'], s, env); G(['commit', '-m', 'seed'], s, env);
      G(['push', 'origin', 'HEAD:main'], s, env);
      fs.rmSync(s, { recursive: true, force: true });
    }
    return b;
  };
  const deploy = mkBare('deploy.git', true);
  const github = mkBare('github.git', false);
  github && G(['push', github, deploy && 'main:main'], deploy, env); // github 从 deploy 同步初始
  const repo = path.join(dir, 'repo.git');
  const wt = path.join(dir, 'repo.wt');
  const opsDir = path.join(dir, 'ops');
  const ops = createGitOps({ repoPath: repo, wtPath: wt, opsDir,
    remotes: { github, deploy }, now: () => T, getRelease: () => ({
      sha: G(['rev-parse', 'main'], deploy, env).toString().trim(),
    }) },
    env);
  return { dir, deploy, github, repo, wt, ops, env };
}
let T = 1_000_000_000;

const MD = (title, body = '正文') =>
  `---\ntitle: ${title}\npubDate: 2026-10-25\ntags: []\n---\n\n${body}\n`;

async function okPublish(ops, slug, title, idemKey) {
  const r = await ops.publish({ slug, idemKey, content: MD(title) });
  return r;
}

test('3.x 发布成功链:骨架→commit→双跳 push→身份核对确认→草稿转已发布', async () => {
  const e = mkEnv();
  try {
    const op = await e.ops.publish({ slug: 'first-post', idemKey: 'k1', content: MD('第一篇') });
    assert.equal(op.status, 'deploy_received'); // 态 4(push 双跳完成)
    assert.ok(op.commit_sha, 'commit_sha 已落盘');
    // github 与 deploy main 都 == commit_sha
    for (const b of [e.github, e.deploy]) {
      assert.equal(G(['rev-parse', 'main'], b, e.env).toString().trim(), op.commit_sha);
    }
    const conf = await e.ops.confirm(op.id);
    assert.equal(conf.status, 'confirmed');          // 态 5
    assert.equal(conf.release_sha, op.commit_sha);
    // op 分支已清理,repo main 快进
    const mainSha = G(['rev-parse', 'main'], e.repo, e.env).toString().trim();
    assert.equal(mainSha, op.commit_sha);
    const branches = G(['branch', '--list', 'op/*'], e.repo, e.env).toString();
    assert.equal(branches.trim(), '');
    // 草稿 md 已在树中,内容身份一致
    const blob = G(['rev-parse', `${op.commit_sha}:site/src/content/posts/first-post.md`], e.repo, e.env).toString().trim();
    assert.ok(blob);
  } finally { fs.rmSync(e.dir, { recursive: true, force: true }); }
});

test('3.x 幂等键:首次创建响应丢失后同键重试→同一 operation 不重复', async () => {
  const e = mkEnv();
  try {
    const a = await e.ops.publish({ slug: 'idem', idemKey: 'same-key', content: MD('幂等') });
    const b = await e.ops.publish({ slug: 'idem', idemKey: 'same-key', content: MD('幂等') });
    assert.equal(a.id, b.id);
    assert.equal(a.commit_sha, b.commit_sha);
    // 只产生一个提交
    const log = G(['log', '--oneline', 'main'], e.deploy, e.env).toString().trim().split('\n');
    assert.equal(log.length, 2); // seed + 1
  } finally { fs.rmSync(e.dir, { recursive: true, force: true }); }
});

test('3.x 闸门(a):未终态 operation 阻止新发布(409 语义)', async () => {
  const e = mkEnv();
  try {
    // 制造部分成功:github 收到、deploy 拒(让 deploy 领先制造非 ff)
    const first = await e.ops.publish({ slug: 'a', idemKey: 'a1', content: MD('A') });
    assert.equal(first.status, 'deploy_received');
    await e.ops.confirm(first.id);
    // 部分成功构造:op 创建基准=当时 deploy;github 推送成功后、deploy 推送前,
    // 第三方使 deploy 前进→本 op 的 deploy push 非 ff 被拒
    const s = path.join(e.dir, 'hand');
    G(['clone', e.deploy, s], e.dir, e.env);
    e.ops.testHooks().afterBackupPush = () => {
      fs.writeFileSync(path.join(s, 'hand.txt'), 'manual');
      G(['add', '-A'], s, e.env); G(['commit', '-m', 'manual'], s, e.env);
      G(['push', 'origin', 'HEAD:main'], s, e.env);
    };
    const second = await e.ops.publish({ slug: 'b', idemKey: 'b1', content: MD('B') });
    e.ops.testHooks().afterBackupPush = null;
    assert.equal(second.status, 'deploy_rejected');
    // 未终态(second)→新发布被闸门拒绝
    await assert.rejects(
      () => e.ops.publish({ slug: 'c', idemKey: 'c1', content: MD('C') }),
      (err) => err.code === 'OPERATION_OPEN' && /b1|pending|未/.test(err.message));
    // 恢复:重试同 op push deploy 同一 SHA——人工收敛(测试模拟:deploy 对齐
    // github main,manual 提交被人工弃置,ff 重新成立)
    G(['fetch', e.github, '+main:main'], e.deploy, e.env);
    const retried = await e.ops.retryDeploy(second.id);
    assert.equal(retried.status, 'deploy_received');
    assert.equal(retried.commit_sha, second.commit_sha, '同 SHA 不重做 commit');
  } finally { fs.rmSync(e.dir, { recursive: true, force: true }); }
});

test('3.x 闸门(b):github 领先→停止转人工,不自动收敛', async () => {
  const e = mkEnv();
  try {
    // github 侧加一个 deploy 没有的提交(领先)
    const s = path.join(e.dir, 'gh-only');
    G(['clone', e.github, s], e.dir, e.env);
    fs.writeFileSync(path.join(s, 'gh.txt'), 'x');
    G(['add', '-A'], s, e.env); G(['commit', '-m', 'github-only'], s, e.env);
    G(['push', 'origin', 'HEAD:main'], s, e.env);
    await assert.rejects(
      () => e.ops.publish({ slug: 'x', idemKey: 'x1', content: MD('X') }),
      (err) => err.code === 'REMOTES_DIVERGED' && /github-only/.test((err.message || '') + (err.detail || '')));
  } finally { fs.rmSync(e.dir, { recursive: true, force: true }); }
});

test('3.x 窗口①:commit 后落盘前中断→按 op 分支 HEAD 补记同一 SHA', async () => {
  const e = mkEnv();
  try {
    const hooks = e.ops.testHooks();
    // 注入:commit 之后、落盘 commit_sha 之前抛出(模拟中断)
    hooks.afterCommit = () => { throw new Error('crash-before-persist'); };
    await assert.rejects(() => e.ops.publish({ slug: 'w1', idemKey: 'w1', content: MD('W') }),
      /crash-before-persist/);
    // op 分支存在,HEAD=新提交;落盘记录 commit_sha 仍 null
    const list = e.ops.listInternal();
    const rec = list.find((o) => o.idem_key === 'w1');
    assert.ok(rec);
    assert.equal(rec.commit_sha, null);
    const head = G(['rev-parse', `op/${rec.id}`], e.repo, e.env).toString().trim();
    // 恢复:补记分支 HEAD 为 commit_sha,不产生第二个同义提交
    const healed = await e.ops.recover();
    const rec2 = e.ops.listInternal().find((o) => o.idem_key === 'w1');
    assert.equal(rec2.commit_sha, head);
    assert.ok(healed >= 1);
  } finally { fs.rmSync(e.dir, { recursive: true, force: true }); }
});

test('3.x 撤下:git rm→双跳→确认=目标路径不存在', async () => {
  const e = mkEnv();
  try {
    const p = await e.ops.publish({ slug: 'gone', idemKey: 'g1', content: MD('将撤') });
    await e.ops.confirm(p.id);
    const w = await e.ops.withdraw({ slug: 'gone', idemKey: 'g2' });
    assert.equal(w.status, 'deploy_received');
    const c = await e.ops.confirm(w.id);
    assert.equal(c.status, 'confirmed');
    // deploy 树中该路径不存在
    const sha = G(['rev-parse', 'main'], e.deploy, e.env).toString().trim();
    let exists = true;
    try { G(['rev-parse', `${sha}:site/src/content/posts/gone.md`], e.repo, e.env); } catch { exists = false; }
    assert.equal(exists, false);
  } finally { fs.rmSync(e.dir, { recursive: true, force: true }); }
});

test('3.x 替代判定:A 上线后 B 改同篇→A=已被替代,B=已上线', async () => {
  const e = mkEnv();
  try {
    const a = await e.ops.publish({ slug: 'same', idemKey: 's1', content: MD('v1') });
    await e.ops.confirm(a.id);
    const b = await e.ops.publish({ slug: 'same', idemKey: 's2', content: MD('v2') });
    await e.ops.confirm(b.id);
    const view = await e.ops.listView();
    const va = view.find((o) => o.idem_key === 's1');
    const vb = view.find((o) => o.idem_key === 's2');
    assert.equal(va.state, 'superseded');
    assert.equal(vb.state, 'published');
  } finally { fs.rmSync(e.dir, { recursive: true, force: true }); }
});

test('3.x slug 占用:远端已有同 slug 手工文章→发布拒绝不覆盖', async () => {
  const e = mkEnv();
  try {
    const s = path.join(e.dir, 'hand2');
    G(['clone', e.deploy, s], e.dir, e.env);
    const posts = path.join(s, 'site', 'src', 'content', 'posts');
    fs.mkdirSync(posts, { recursive: true });
    fs.writeFileSync(path.join(posts, 'taken.md'), MD('别人的'));
    G(['add', '-A'], s, e.env); G(['commit', '-m', 'hand post'], s, e.env);
    G(['push', 'origin', 'HEAD:main'], s, e.env);
    G(['push', e.github, 'HEAD:main'], s, e.env); // 两端同步,别触发闸门(b)
    await assert.rejects(
      () => e.ops.publish({ slug: 'taken', idemKey: 't1', content: MD('我的') }),
      (err) => err.code === 'SLUG_TAKEN');
  } finally { fs.rmSync(e.dir, { recursive: true, force: true }); }
});
