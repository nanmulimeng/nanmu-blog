// 审计 P1-8:cost_pending 夹具不得进生产源目录(正常构建会把夹具公开为
// 正式日报页+RSS)。夹具住在 tests/fixtures/,本脚本在临时目录搭站点
// 副本(node_modules 以 junction 复用,不复制),注入夹具后走真实
// astro build + smoke.mjs(含 cost_pending 三处口径标注检查)——夹具的
// 渲染验收用真实构建链,生产构建链(npm run verify)不含夹具。
import { cpSync, existsSync, lstatSync, mkdirSync, mkdtempSync,
         readdirSync, rmSync, rmdirSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const site = dirname(dirname(fileURLToPath(import.meta.url)));
const fixtures = join(site, 'tests', 'fixtures');
const files = existsSync(fixtures)
  ? readdirSync(fixtures).filter((f) => f.endsWith('.md')) : [];
if (!files.length) {
  console.error('FIXTURE FAIL: tests/fixtures 无 .md 夹具(验证素材缺失)');
  process.exit(1);
}

const tmp = mkdtempSync(join(tmpdir(), 'nanmu-fixture-'));
const problems = [];
try {
  // 站点副本:排除 node_modules(junction 复用)、dist、.astro 缓存
  cpSync(site, tmp, {
    recursive: true,
    filter: (src) => {
      const rel = src.slice(site.length + 1).replaceAll('\\', '/');
      return !rel.startsWith('node_modules') && !rel.startsWith('dist')
        && !rel.startsWith('.astro');
    },
  });
  // junction 指向真实 node_modules;清理时必须先 rmdir 摘链接——
  // rmSync(recursive) 会穿过联接递归删除真实 node_modules
  symlinkSync(join(site, 'node_modules'), join(tmp, 'node_modules'),
              'junction');
  mkdirSync(join(tmp, 'src', 'content', 'digest'), { recursive: true });
  for (const f of files) {
    cpSync(join(fixtures, f), join(tmp, 'src', 'content', 'digest', f));
  }
  const build = spawnSync(
    process.execPath, ['node_modules/astro/astro.js', 'build'],
    { cwd: tmp, stdio: 'pipe' });
  if (build.status !== 0) {
    problems.push(`夹具构建失败:\n${build.stdout}\n${build.stderr}`);
  } else {
    const smoke = spawnSync(process.execPath, ['scripts/smoke.mjs'],
                            { cwd: tmp, stdio: 'pipe',
                              env: { ...process.env, NANMU_FIXTURE_BUILD: '1' } });
    if (smoke.status !== 0) {
      problems.push(`夹具构建 smoke 失败:\n${smoke.stdout}\n${smoke.stderr}`);
    }
  }
} finally {
  // 摘链接分平台两步(交界 C1):Windows junction 用 rmdir(只删链接
  // 本身);Linux 上 symlinkSync junction 退化为普通符号链接,rmdir 报
  // ENOTDIR 恒失败,改 rmSync 非递归删链接自身。链接未确认摘除前绝不
  // rmSync(recursive)——Windows 上会穿过 junction 递归删真实 node_modules
  const link = join(tmp, 'node_modules');
  for (const remove of [() => rmdirSync(link), () => rmSync(link)]) {
    if (!lstatSync(link, { throwIfNoEntry: false })) break;
    try { remove(); } catch { /* 换下一种摘法 */ }
  }
  if (lstatSync(link, { throwIfNoEntry: false })) {
    console.error(`FIXTURE CLEANUP:链接 ${link} 未能摘除;为保护真实`
      + ` node_modules 不递归删除 ${tmp},请人工摘除后删除`);
  } else {
    try {
      rmSync(tmp, { recursive: true, force: true });
    } catch (e) {
      console.error(`清理临时目录失败(请手动删除 ${tmp}):`, e.message);
    }
  }
}
if (problems.length) {
  console.error('FIXTURE FAIL:\n' + problems.join('\n'));
  process.exit(1);
}
console.log(`fixture ok: ${files.length} 个夹具经临时构建+smoke 通过(生产构建不含夹具)`);
