# 2026-10-25 批 3 完成:发布/撤下/Git 双远端与恢复(待用户复核)

## 交付(workbench-batch2 分支,批 3 与批 2 同分支连续实施)

| 件 | 提交 | 内容 |
|---|---|---|
| operations.js 核心 | 4548d1c | 七内部态状态机;先落骨架再动 git;窗口①(分支 HEAD 补记,不判 failed)/窗口②(幂等键);闸门(a) 未终态拒新发布/(b) github 领先或分叉转人工(差异列表);slug 占用拒绝;双跳 push(github→deploy),deploy 拒=部分成功保留分支;retryDeploy 同 SHA;确认=内容身份核对(release 树 blob==本 op 内容/撤下=路径不存在),180s→pending_confirm 不判失败;git 统一 60s 超时 |
| API 层 | bbebed3 | POST /api/publish(读草稿+幂等键)/withdraw/GET /api/operations(界面态)/POST /api/operations/:id/confirm(手动重查);错误透传 409/400/404/503;server.js 生产 env 组装(WB_GIT_* /WB_REMOTE_* /WB_RELEASE_URL) |
| release 兜底 | (随本 session 提交) | getRelease 未配置/失败时退化 deploy main(开发/演练默认;生产=HTTP release.txt) |

## 验证(全部实跑)

- **单测 12**:operations.test.js 8 场景(成功链/幂等/闸门 a+b(afterBackupPush 注入构造部分成功)/窗口①恢复/撤下/替代判定/slug 占用)+ operations_api.test.js 4(鉴权链/撤下链/闸门透传 409/未配置 503)
- **全量 71/71**;批 1/2 回归无破坏
- **双远端演练 8/8**(server.js 真进程+临时裸双远端,不碰生产):存草稿→发布双跳→内容身份核对确认→双远端 main 一致=本操作 SHA→撤下→确认(路径不存在)→界面态(发布 superseded/撤下 withdrawn)→日志无口令

## 过程坑(留痕)

1. `git hash-object --stdin` 无输入流挂起(测试全挂根因)——git 调用统一 60s 超时;
2. light-my-request 的 set-cookie 可能返回字符串,`[0]` 直取拿到首字符 'w' 致 401——此前 chain/内联多轮 401 之谜同根因,批 1 的兼容写法才是对的;
3. fetch 更新本地 ref 非 ff 需 `+` 前缀;update-ref 引用他库对象需先 fetch;
4. 测试闸门(a) 场景:op 基准=创建时 fetch 的 deploy main,构造 deploy 拒须在双跳之间注入(afterBackupPush)。

## 与 DESIGN 契约的对齐说明

- §2.1 六场景:反例 1/2/3(闸门 a/同 op 重试/取消)由闸门+retryDeploy 覆盖(取消=前端动作,终态语义已留 cancelled);4/5(领先/分叉)闸门 b 覆盖;6(slug 占用)覆盖。
- §4.4 五中断:前四行由状态机+recover 覆盖;「后续版本已上线」由 listView 动态 superseded 覆盖;四反例(1/2/3/4)分别在替代判定/撤下/窗口①/幂等测试中。
- 前端界面(编辑器上的发布/撤下按钮+状态显示+二次确认+撤下影响面明示)**未做**——批 4 真实写作验收时按需补(API 已全就绪,e2e_browser.py 亦未扩)。

## 停止点

批 3 机器侧+演练完成,**待用户复核**;批 4(部署 write.nanmu.xyz/备份恢复/资源实测/真实写作验收)需服务器操作逐项授权。生产发布授权另行获得。
