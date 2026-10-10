# 会话交接:R6 批次 3 TBT 重测轮——v1 勘误撤回+Event Timing 重测(2026-10-10)

- **recorded_at**: 2026-10-10 16:40 Asia/Shanghai
- **continues**: [修正轮 session](2026-10-10-r6-batch03-fixround.md)(e19b50d)
- **repository**: 起点 HEAD = e19b50d;分支 `codex/r6-interaction`(仅本地,未推送/未合并/未部署)。本轮单提交见 Git 实况
- **objective**: 用户审计裁决:修正轮四项中①②④通过关闭,**③性能结论暂不通过**——v1 探针从 click 处理函数起测,遗漏输入排队延迟,「交互可用性已证无影响」撤回并保留勘误痕迹。本轮只修正测量与报告,不调视觉、不拆 3D、不改移动端策略:①Event Timing 记 startTime/processingStart/processingEnd/duration/interactionId,未收到条目不填 0;②独立测试页仪器自检(400–600ms 长任务+渲染线程之外真实输入),自检结果不混入项目数据;③项目对照记录输入时间与长任务区间,确认是否真正采到长任务期间输入;④两组用一致服务/压缩/视口/节流(按归档配置实际参数对齐);⑤采样覆盖场景就绪/poster 退出/稳定期,明确截止,超时如实登记;⑥分别报告 Lighthouse TBT、长任务总时长、输入排队延迟、输入到绘制、重叠样本,保留原始日志,修正 INTEGRATION-PLAN 与 session 过度结论。**单个独立测量修正提交,工作区干净;不合并/推送/部署,不进其他优化任务**

## v1 勘误(撤回什么,为什么)

- **计时口径**:v1 PROBE_JS 在 click 处理函数首行 `performance.now()`+rAF——只覆盖「处理开始→下一帧」,**输入排队延迟(startTime→processingStart)全部不可见**(自检判据 6 实证:v1 口径对排队 377ms 的点击测得 dt=0ms,失明)。
- **点击方式**:v1 用 pg.click() 的 actionability 自动等待,渲染线程忙时挂起,恰好掩盖要测的阻塞。
- **撤回的结论**:「操作响应两组无差异(5/8/1 vs 4/8/1ms)」「无一次点击落入长任务(最近间隔 115ms)」「操作可用性无影响/交互可用性已证无影响」——全部不成立。v1 数据与日志(logs/r6-b3-tbt-compare-*)保留为痕迹不删。
- **勘误落点**:INTEGRATION-PLAN §5 P2 行撤回标注+§7 3c 行+§8 重写、fixround session tbt_compare 节标注、AGENTS.md 第七轮段③,本文档即重测记录。

## 仪器自检(前置门槛,两轮 FAIL→PASS)

- **独立测试页**(C:/tmp/b3-selfcheck.{html,py},一次性不入库):block 按钮 500ms 同步忙等;点击 block 后 120ms 点击 target(排队受害者);`__marks`(capture 阶段 e.timeStamp,与 Event Timing startTime 同源)+`__raf`(v1 口径复刻);import tbt_probe 的 EVENT_TIMING_JS/LONGTASK_JS——**自检的仪器=上项目的仪器**。
- **两轮勘误(方法演进,证据都在自检 log)**:
  - R1:`wait_for_timeout` 是协议往返,渲染线程忙时被排队拉长——target 输入实际发生在阻塞后(marks: block=809→target=1463,长任务 833–1335)。改 python 侧 sleep+预取坐标仍 FAIL 4/6。
  - R2(根因):**sync API 的 mouse.click 等 CDP ack,而 Input ack 要等渲染线程空闲——target 的 dispatch 命令从未在阻塞期上线**(串行化把输入推迟到阻塞后,排队被整个掩盖)。解法=async + create_task 并发:block 点击不 await 完成,120ms 后 target 的 dispatch 即写入协议管道,事件在渲染线程忙时入队。
- **终态判据 6/6 两轮复现**(logs/r6-b3-eventtiming-selfcheck.log):baseline inputDelay 1.0/1.6ms;block processing 500ms 入条目;longtask 500ms 捕获;**target inputDelay=375.5/377.6ms、processing≤0.1ms(排队实证)**;target.startTime 落在 longtask 窗口内(重叠判定成立);**v1 口径 rAF dt=0ms(失明实证)**。自检数据独立归档,不与项目数据混读。

## tbt_probe v2(重写要点)

- **Event Timing**:durationThreshold=16(Chromium 下限);派生 inputDelay/processing/presentation;`pair_clicks` 按 hook timeStamp×条目 startTime ±5ms 配对,未配上登记 missing **不填 0**;重叠=条目 [startTime, processingStart) × longtask 区间相交。
- **条件对齐**(归档 r6-b3-lh-after-home.excerpt.json 逐项):视口 412×823 DSF1.75 is_mobile;节流 latency 562.5ms/下行 184320B/s/上行 84375B/s/4×CPU(**v1 误用 RTT150/1.6Mbps/390×844 属独立条件,一并勘误**);full/static 共用内置 gzip-6 静态服务(同 8982 规则,text 压缩/woff2/png 直传/no-store)。
- **async 并发派发**(自检 R2 同一机理)+**三轮探针自身勘误**:
  - gzip 服务 else 分支先 send_header 再 super().do_GET,headers buffer 顺序颠倒→`ERR_INVALID_HTTP_RESPONSE`,重写 do_GET;
  - read 按钮在首屏外(中心 y≈933>823),视口外 mouse.click 无页面事件——首改滚动后取盒(往返被长任务挂起+坐标错位),定稿=**wheel 滚 200→click(顶位 y−200)→wheel 回**三连纯 Input,零协议往返;
  - v2.0/v2.1 两轮 overlap=0 的根因:轮内任何协议往返(read 取盒、轮末 gather 等 ack)在渲染线程忙时挂起,把击点**弹开**到长任务窗口之外(点击序列在窗口两侧出现 ~0.9s 空隙,正常节拍 150–250ms)——定稿=**击任务 fire-and-forget 跨轮累积不 gather**,击点命令上线即返回,长任务期间照常入队。
- **采样**:P1 加载与场景窗口(t≈6s 起,击点节拍 150/175/250/250ms,轮距 1s)→P2 poster 退场→P3 稳定 3 轮;DEADLINE 45s;sceneTimeout/posterTimeout/deadlineHit 如实登记;Lighthouse TBT 引用归档值不重跑。

## 项目对照结果(logs/r6-b3-tbt2-compare-{full,static}.json + .log)

六类数字分别报告(用户指令第 6 项):

| 指标 | full(正常 3D) | static(abort 3D) |
|---|---|---|
| Lighthouse TBT home | 846.4ms(引用归档摘录,两组同基准) | 同左 |
| 长任务总时长 | **Σ954ms**:446@9.8s+362@14.9s+146@15.3s(attribution unknown) | **0** |
| inputDelay 中位(窗口外) | menu 2 / tab 5 / read 5ms(max 均 ≤40ms) | menu 2 / tab 5 / read 6ms |
| 输入到绘制中位 | menu 16 / tab 24 / read 16ms | menu 16 / tab 24 / read 16ms |
| **实际重叠样本** | **2 发**:tab@9888ms inputDelay=**409ms**、tab@10148ms inputDelay=**163ms**(均在 446ms 场景构建长任务窗口内;前者输入到绘制 448ms) | 0(无长任务) |
| LCP/FCP | poster-light 2712ms / ≈2256ms | poster-light 2712ms / ≈2240ms |

- 过程登记:full scene@13.9s/poster@15.1s 均在 45s 内(deadlineHit=False);static scene/poster 超时=abort 走失败清理 poster 常显的设计路径,45s 截止如实登记(deadlineHit=True,采样轮更多系窗口跑满,两组数据分列不互换);missing(条目 duration<16 未上报)按入口分列未计 0。
- 连续两轮(v2.2 迭代过程中)overlap 复现:409/163 与 424/177,量级一致。
- **修正后结论**:3D 场景构建长任务期间(加载后 ~10s/15s 两个窗口合计 ~0.95s)点击输入排队 163–409ms,输入到绘制最长 448ms;窗口外输入延迟中位 2–5ms 与静态组无差;静态组无长任务无排队。**是否优化仍属性能取舍,选项 A 接受现状/B 分帧切片/C 移动端仅 poster 更新于 INTEGRATION-PLAN §8,数据提交用户裁决,未动 3D、未放宽任何标准**。

- **change_scope**:
  - `site/scripts/tbt_probe.py`:v2 全量重写(sync→async;Event Timing+归档配置+gzip 共享服务+阶段采样+重叠判定;三轮探针勘误见上)
  - `docs/design/2026-10-07-visual-redesign/logs/`:r6-b3-eventtiming-selfcheck.log(自检 6/6 两轮)、r6-b3-tbt2-compare.log、r6-b3-tbt2-compare-{full,static}.json
  - `docs/design/2026-10-07-visual-redesign/INTEGRATION-PLAN.md`:状态行③、§5 P2 行撤回标注+P2-v2 新段、§7 3c 行、§8 TBT 裁决行重写
  - `docs/sessions/2026-10-10-r6-batch03-fixround.md`:tbt_compare 节勘误标注(原文保留)
  - `AGENTS.md`:第七轮段③勘误+接手入口加本文档
  - `docs/sessions/2026-10-10-r6-batch03-tbt-remeasure.md`:本文档
  - 外部操作:未执行(无推送/合并/部署/付费/服务器访问);C:/tmp 自检两文件与探针中间产物不入库

- **verification**:

| 工作目录/环境 | 实际命令或操作 | 结果及证据边界 |
|--------------|--------------------------------|---|
| C:/tmp(独立测试页) | `python -I b3-selfcheck.py`(async 版,两轮) | **SELF-CHECK PASS 6/6** 两轮复现;第一轮 R1/R2 勘误过程 FAIL 4/6 两次(勘误记录在案);log 归档 logs/r6-b3-eventtiming-selfcheck.log |
| site/ | `npm run build` | 6 页构建完成,探针用 dist 为最新产物 |
| site/(内置 8945 gzip 服务+CDP 节流) | `python -I scripts/tbt_probe.py`(v2.2 定稿轮) | full/static 两组成形,六类数字见上表;stdout 归档 logs/r6-b3-tbt2-compare.log;探针三轮迭代勘误(ERR_INVALID_HTTP_RESPONSE/read 首屏外/击点弹开)全记录在脚本注释与本档 |
| 仓库根 | `python scripts/check_docs.py` | 提交前跑,见 Git 实况(要求零错误) |

- **pending_runtime**: C:/tmp/b3-selfcheck.{html,py} 与 b3-lh 旧目录(一次性,不入库);本地 8945/8946 服务随探针进程退出已停
- **decisions_needed**: **TBT 取舍**(§8 选项 A/B/C,本轮数据=场景构建窗口内排队 163–409ms 的实测证据,不构成任何选项的自动执行授权);合并 main/推送/部署仍待用户明确授权
- **disposition**: complete(六项指令全部交付;v1 结论撤回留痕;单提交;未动 3D/视觉/移动端策略)
- **next_action**: 用户复核本报告并裁决 TBT 取舍;若选 B/C 另开任务(实现后须以 tbt_probe v2 同口径重跑对照)。本文档不自动授予任何提交外权限
- **omissions**:
  - 长任务 attribution 仍 unknown(Chromium longtask API 不给调用栈);3D 归因靠 static 对照(0 长任务)+Lighthouse long-tasks audit url(scene6/three.module)旁证
  - 重叠样本仅 2 发(命中场景构建第一个窗口;第二/三窗口采样未撞上)——击点密度已三轮加密,窗口占比 ~4% 下 2 发为实际采样结果,如实报告不外推
  - missing 条目(duration<16 未上报)为 Event Threshold 仪器边缘特性,按入口分列未深究
  - 真机(触摸/Safari/帧率)仍无设备登记待验(沿批次 3b 口径)
