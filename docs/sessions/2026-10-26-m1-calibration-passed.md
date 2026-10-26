# 2026-10-26 线 B:真实校准通过(coefficient=1.1)+批 4 资源全部回填

## 真实校准(M1 五步第 2-3 步,用户提供 DeepSeek key 当次授权)

1. **key 入服务器** /etc/nanmu-blog.env(root:nanmu 0640,管道写入不经 shell history;不进任何仓库文件)。
2. **契约核对**:engine llm.py=原生 /chat/completions(Bearer)——用户提供的 /anthropic 兼容端点不适用也不需要;模型 deepseek-flash 原生列表确认存在(DeepSeek-V4.1-Flash,1M ctx);budget.yaml 价目(2026-10-02 快照 ¥2/M 入 ¥8/M 出)与 tokenizer 资源(v4-flash,内容寻址)配置在位。
3. **首跑未通过(校准价值所在)**:HTTP 200 真实链路通;usage.prompt_tokens=665 vs 本地计数 642(**+3.6%**),系数 1.0 不覆盖 → 闸门按设计置 pay_paused 中止(未多花钱)。
4. **人工处置**(契约「否则 pay_paused+人工上调」):calibration_coefficient=1.0→**1.1**(实测+3.6% 留余量,预占冻结而已不虚耗)+pay_paused=0 显式解除,engine_meta 留痕(manual_coefficient_note 含依据与 receipt)。
5. **重跑通过**:`event=passed coefficient=1.1 samples=4`——sample 0 复用既有回执(**零新增付费**,幂等契约实测工作)+3 次新真实调用。校准成本:4 样本均 665 tokens 级输入,合计 <¥0.01(校准预算 ¥0.05 内)。

## 批 4 资源回填(全部实测完成,DESIGN §2.2 已更新)

- 预览构建 ×20:P50=13.6s / P95=14.4s / max=14.7s;
- 构建窗口公开站:100/100@P50 76ms;
- 空闲内存 24h(138 样本):P50=9.6MiB / P95=19.9MiB / max=35.8MiB。

## M1 五步位置与下一步

①替身验证 ✅ →②校准授权 ✅ →③校准执行 ✅(passed 1.1)→ **④正常付费运行授权→首期**(闸门:单期 ≤¥1/月 ≤¥50,rate limit 10/min)→⑤首期人工核验→timer 启用→连续 3 天(M1 交付验收)。

**④须用户明确授权**;批 4 写作验收(用户设口令后)仍开放。

## Git

main=origin=server=e854975(origin 断连两次后已补齐;线上 release.txt 同步)。
