# 写作与内容维护

> 状态(2026-10-04):site已实现,本地开发/build/verify可运行;M0 Task8a路径与缓存补验、Task9-10服务器/首篇文章上线仍待完成。字段定义以spec §4.1为准;下文区分现在可用的本地预览和完成部署后的发布流程。

## 新建个人文章

在`site/src/content/posts/`中新建单层Markdown文件,名称使用小写英文、数字和短横线,例如`my-first-post.md`。不使用纯数字名称(与分页URL冲突),不放子目录;文件名决定永久URL `/posts/my-first-post/`。

不添加frontmatter `slug`,即使与文件名相同也不允许;不要用大写、空格、点号或下划线等期待框架自动清洗的文件名。当前校验仍存在slug绕过缺口,由Task8a修复;构建通过不能替代这条写作约束。

```yaml
---
title: '我的第一篇文章'
pubDate: 2026-10-03
tags: [随笔]
draft: true
---
```

正文从二级标题开始,页面模板输出文章标题。带冒号、井号等特殊字符的title用引号包裹。tags是简单元数据,没有标签管理平台。日期代表文章日期;未来日期不会自动成为预约发布,未准备公开时必须保留`draft: true`。

字段要求:

| 字段 | 含义 | 约束 |
|------|------|------|
| title | 页面与RSS标题 | 必填,去首尾空白后非空 |
| pubDate | 发布时间 | 必填,可解析日期;展示固定Asia/Shanghai,同日期排序以id稳定打破平局 |
| tags | 简单分类文字 | 字符串数组,默认空 |
| draft | 是否排除公开产物 | 默认false,新草稿必须显式写true |

**draft只控制构建产物,不是保密机制。** Git历史或公开仓库仍可能含原文;文章正文不得存密码、API key或不应进入仓库的材料。

## 预览、发布与确认

现在可在仓库根执行`npm --prefix site run dev`进行本地预览,无需server remote。用Ctrl+C结束;提交前执行`npm --prefix site run verify`。列表/详情/RSS均排除draft,本地查看完整文章时可临时改false,未准备发布就恢复true。

**下面的同步与发布命令仅在M0 Task9完成、server remote已验证后使用。** 写新文章前先同步main,再创建/修改文章并预览;不要写完后才套用要求干净工作区的同步块。已有暂存、未提交修改或分支分叉时先明确归属,不reset或强推。

```bash
(
  set -euo pipefail
  cd "$(git rev-parse --show-toplevel)"
  test -z "$(git status --porcelain)" || { echo '先保存并处理已有修改'; exit 1; }
  git fetch server main
  git merge --ff-only FETCH_HEAD
  npm --prefix site run dev
)
```

用Ctrl+C结束dev服务器后再执行发布步骤。列表和详情都会排除draft,不提供绕过过滤的在线预览。需要看完整文章时可在本地暂改`draft: false`,确认内容后恢复草稿状态;准备发布时才保留false。ff-only失败表示不能直接快进,先检查本地/远端差异并人工合并,完成后重新verify。

正式发布前:

```bash
(
  set -euo pipefail
  cd "$(git rev-parse --show-toplevel)"
  test "$(git branch --show-current)" = main
  git diff --cached --quiet || { echo '已有暂存内容,先核对归属'; exit 1; }
  npm --prefix site run verify
  git add -- site/src/content/posts/my-first-post.md
  # 如文章引用新图片,将确切文件一起加入,例如:
  # git add -- site/public/images/my-first-post.png
  git diff --cached --stat
  git diff --cached
)
```

检查暂存diff仅含预期文章/图片后,在同一工作区执行下面的提交步骤;期间若改了内容或依赖,重新verify。已有暂存会在第一段被拒绝,不是用单个git add掩盖它。

```bash
(
  set -euo pipefail
  cd "$(git rev-parse --show-toplevel)"
  test "$(git branch --show-current)" = main
  git commit -m 'feat(posts): 发布第一篇文章'
  git push server main
)
```

发布者按[部署手册](ops/deploy.md)§6核对线上版本、文章URL与RSS;push成功本身不证明上线。M1以后引擎也会写main,每次写作前同步,冲突时人工合并并重新verify。verify针对整个工作区,拟提交之外若有会影响构建的修改,先隔离或妥善保存后重新验证,不能把未提交依赖当部署输入。

## 修改、撤回与链接

- 改标题/正文可保持文件名不变,既有URL不变。改文件名会改变URL;M0没有自动重定向系统,发布后尽量保持文件名。
- 删除、改名、撤回及清理临时内容后,按[质量门禁](development/quality-gates.md)的内容缓存流程重建,核对旧详情、列表与RSS项全部消失。Task8a尚未完成时,普通verify通过不足以证明旧缓存已清除。
- 撤回文章可将draft改true后重新发布,确认首页、列表、详情、RSS均移除;旧Git历史、旧release和第三方RSS缓存不会因此自动消失。
- 图片放`site/public/images/`后用`/images/...`引用并写替代文本;M0只服务静态文件,不添加上传后台。图片与正文一起提交,不要引用开发机绝对路径。
- 正文链接优先HTTPS;相对站内链接以最终URL核对。`npm run verify`不等于已经检查所有外链可达。
- 如果上一次发布失败,先查部署日志与release.txt,按运维手册重跑既有提交,不用制造空提交触发构建。

## AI日报与人工文章的边界

`site/src/content/digest/YYYY-MM-DD.md`由M1引擎负责,不能当个人文章目录使用。公开时必须有generated/ai_model/成本字段及来源链接;具体模板见[日报管线](engine/pipeline.md)。人工改稿在session记录原因并走发布链;强制纳入或排除条目才修改引擎override。紧急撤回可内容级revert,先暂停该期重试并核对期状态,避免定时任务重新发布。

## 写作验收

M0首篇真实文章要验证:中文标题/正文、明暗主题、图片(如使用)、文章URL、RSS特殊字符与draft排除。只验证实际使用的内容能力;评论、交互组件、标签页、预约发布不属于M0。
