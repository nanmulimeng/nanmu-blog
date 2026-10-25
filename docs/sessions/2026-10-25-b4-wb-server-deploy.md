# 2026-10-25 批 4 服务器部署:write.nanmu.xyz 上线(待口令+写作验收)

## 部署实况(用户授权「批 4 服务器部署」,DNS 用户已配)

1. **main 合并部署**:workbench-batch2(批 1-4 全量)merge 入 main(7068186)→ push origin + push server(hook 构建,15s 切版)。公开站随之更新:**导航三轮修复(空态 padding/书页页脚式/收尾)上线**——即此前「main 待部署」挂账项。线上快速验收 6/7:四页 200/404/rss 200;「新导航样式」一项因零文章态无页面承载无法直接断言,**验证顺延至第一篇真实文章发布**(release.txt=7068186 已确认代码在)。
2. **服务器**:sudo 建目录 /opt/nanmu-workbench/{drafts,previews,ops}+clone(/opt/git)→ app@7068186;workbench npm ci --omit=dev(52 包)。
3. **deploy key**:服务器生成 ed25519(~/.ssh/id_ed25519_nwb_deploy+config 指定);公钥待用户贴 GitHub Deploy keys(**用户动作**)。
4. **env**:/etc/nanmu-workbench.env 骨架就位(root:nanmu 0640),WORKBENCH_PASSWORD_HASH=__PENDING__(**用户生成后填入并 systemctl restart nanmu-workbench**)。
5. **systemd**:unit 安装+enable --now,active;MemoryMax=300M。
6. **Caddy**:write.nanmu.xyz 反代段追加(validate 通过+reload);ACME tls-alpn-01 签发完成。
7. **资源采样**:memory-sample.csv 每 5min×24h(cgroup v1/v2 兼容),首值 ≈29.6MiB;24h 后回填 P50/P95 到 DESIGN §2.2。

## 公网验收(全部实跑)

- https://write.nanmu.xyz/login 200+HSTS/nosniff/no-referrer
- 未登录 /api/drafts 401;错误口令登录 401;未登录预览路径 410(鉴权边界全对)
- 服务本机 127.0.0.1:8790 200

## 剩余(批 4 收口条件)

1. **用户**:①公钥贴 GitHub Deploy keys(见下);②服务器生成口令哈希填 env+restart(env.example 有生成命令);
2. GitHub 侧配好后:服务器上验证 `ssh -T git@github.com`(或首跑发布验证);
3. **真实写作验收**(4.4):口令就绪后作者真实走 写→存→预览→发布→撤下 各≥1 轮(此时可顺带验证新导航样式+公开站发布链);
4. 24h 采样回填(明日);预览构建耗时×20 与构建窗口影响实测随写作验收进行。

## 过程坑(留痕)

- ssh 内嵌 heredoc 失败→本地写文件 scp;`pkill -f sample.sh` 自匹配杀 ssh 会话→字符类 [s] 排除/独立 runner;
- cgroup v1 无 memory.current→usage_in_bytes 兼容;
- Caddyfile 检查需 sudo grep(权限),validate/reload 正常。

## Git 状态

main=origin=server=线上=**7068186**;workbench-batch2 已并入(分支保留);本 session 提交后同步推送。
