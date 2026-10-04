# ADR-0006: RAG 自建 sqlite-vec + bge-m3;PowerContext 评估后不采用

- 状态:已接受;事实/数学依据见文末2026-10-02勘误,当前契约以spec为准
- 日期:2026-10-02
- 关联:spec §6 / M2;调研结论 2026-10-02

> 2026-10-04有效口径:当前接受:轻量自建、独立rag.db、双通道与可重建索引。下文版本/免费档/内存/延迟/无成本平滑切换不作实施事实;Markdown才是语料源,具体核查见[spec §6](../superpowers/specs/2026-10-02-nanmu-blog-design.md#6-rag-知识库m2)。

## 背景

M2 要"博客内容 → 个人知识库问答(自用)"。候选:自建(sqlite-vec + FastAPI)/ OceanBase PowerContext / Chroma / LanceDB。

## 决策

- **向量存储 sqlite-vec v0.1.9**:vec0 虚拟表 `float[1024]` 暴力 KNN(万级向量毫秒级、~50MB 内存);requirements 锁版本(pre-v1)
- **检索双通道混合**:FTS5(bm25)+ 向量独立检索融合,命中标注 `matched_by`,embedding 失败自动降级纯 FTS(PowerContext 模式)
- **embedding**:SiliconFlow `BAAI/bge-m3`(免费、1024 维)主用;阿里百炼 text-embedding-v4(¥0.5/M)备胎
- **独立 rag.db**:向量库与 engine.db 解耦,可随时删除全量重建;EmbeddingProfile(model+dim+distance+normalization)整体身份 + 内容 hash 陈旧检测;**索引是可重建投影,chunk 行表是唯一真相**
- **PowerContext 不采用**(评估结论):问题域是 agent 跨会话交接而非知识库问答;server 栈常驻 150-250MB(自建 50-100MB);六周三版 breaking change;其内部检索底座恰是 FTS5+sqlite-vec 同款积木,反向验证自建选型

## 后果(代价)

- 自维护检索融合与重建逻辑(M2 计划范围)
- bge-m3 免费档限速未实测(备胎阿里 v4 可平滑切换,换模型全量重建已内建)

## 被否决的替代方案

1. PowerContext——理由见上,否决(其 handoff 模式已在 spec §8.1 借鉴)
2. Chroma——~800MB 常驻内存,1.8G 机器出局
3. LanceDB——数十万向量以上才值得换,当前量级万级
4. SQLite 官方 vec1 扩展——真 ANN 但仅源码编译、无 Python 生态,观望

## 2026-10-02证据边界修订

轻量自建与双通道的决策保留。0.1.9稳定版、免费额度、各方案内存和延迟不作为当前已验证结论;安装前查官方发布/账户并在目标机验证。上文“平滑切换”必须包括维数变更和全量重建成本。Markdown为语料真相源,chunk/FTS/向量均可重建;当前设计见spec §6。
