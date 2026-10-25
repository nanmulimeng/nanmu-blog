# 2026-10-25 C6 favicon 上线轮:用户图标改动入库+部署(含一次漏提交勘误)

## 背景

全量检验轮(五域,A 86/86 / B 330 / C 10/10 / D 34+22 / E 一致)发现用户 2026-10-22 未提交改动:Base.astro favicon 三行 link + favicon.ico/apple-touch-icon.png/favicon.svg。用户指示按推荐处理(提交+部署),GitHub 用 MCP 重连核实。

## 过程(实况)

1. **GitHub MCP 核实**:远端已含 257d364(此前「网络失败」实为推送成功后收尾断连误报)。
2. 86fda2b 提交 favicon 三件套(Base.astro+ico+png),推 origin(257d364..86fda2b)+推 server(1e8fc2c..86fda2b),15s 切版。
3. **线上验收发现漏项**:/favicon.svg 404。根因=svg 未入库——上轮 `git status --short | head -3` 截断,untracked 第 4 行(svg)丢失,误以为只有两个新文件。【教训:否定性结论必须确认完整输出】
4. 230db76 补提交 svg,推 server(86fda2b..230db76),5s 切版。
5. 复验 5/5:favicon 三件 200(268B/3032B/4490B)、页头 link×3、装饰断言无回归(首轮 FAIL 系 3D 3s 未就绪时序,等就绪后全过;86fda2b/230db76 未触碰装饰代码)。

## Git 状态

- 线上 release.txt = **230db76**;server/main = 230db76
- origin/main = 86fda2b(**230db76 git 通道两次失败待补推**;GitHub MCP 通道正常,网络恢复后 `git push origin main` 一条补齐)
- 零回滚;9120bf3 及更早仍不作回滚目标

## 停止点

favicon 上线完成;workbench 批 1 仍停「待审计复核」(用户未授权合并);origin 补推待网络。
