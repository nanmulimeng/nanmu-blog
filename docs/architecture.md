# nanmu-blog 架构

三件套:site(Astro 5 静态站,git 即 CMS)/ engine(M1,读 topic-digest SQLite 产日报)/ rag(M2,自用问答)。

```
                     ┌─ 个人写作流 ──────────────────────────────┐
                     │ 本地 Markdown → git push → bare repo     │
                     │   (/opt/git/nanmu-blog.git)              │
                     │   post-receive hook → 触发构建           │
                     └──────────────┬───────────────────────────┘
                                    ▼
┌─ AI 引擎(engine)─┐      ┌─ 博客站(site)──────────────┐
│ Python worker     │      │ Astro 5 静态构建            │
│ systemd timer     │─────▶│ content/posts  (个人文章)   │
│  ├ collect:读     │ 写   │ content/digest (AI 日报)    │
│  │  topic-digest  │ digest│        ↓ astro build       │
│  │  SQLite(只读) │ md + │ releases/<sha>/              │
│  ├ 判重/精选/摘要 │ git  │ current symlink 原子切换    │
│  ├ 回执+预算熔断   │ commit│ (topic-digest 已验证模式)  │
│  └ 向量索引 → RAG │      └──────────────┬──────────────┘
└──────┬────────────┘                     ▼
       ▼                          ┌─ 入口(Caddy)──────────────┐
┌─ RAG 服务 ────────┐             │ blog.nanmu.xyz → 静态站    │
│ 轻量 API(FastAPI) │◀────────────│ /api/* → RAG 服务反代      │
│ basicauth 保护     │             │ (443, 主域证书覆盖)        │
└────────────────────┘             └───────────────────────────┘
```

## 数据流

1. **写作流**:人写 markdown → git push → post-receive 后台 flock 构建 → `releases/<sha>/dist` + `mv -T` 原子 symlink → Caddy
2. **AI 流(M1)**:engine 定时读 topic-digest(只读)→ 评分精选 → 摘要 → digest markdown 入库 git → 同一构建链
3. **RAG 流(M2)**:engine 建向量索引(独立 rag.db,可随时重建)→ FastAPI /ask(basicauth)→ Caddy 反代

## 边界不变量

- AI 挂了博客照常在线;engine 崩溃不影响静态站,反之亦然
- topic-digest 保持现状,本项目只读
- 页面永不调模型;读者只读预生成内容
- AI 生成内容必须标注(模型 + 成本)

铁律与详设:[superpowers/specs/2026-10-02-nanmu-blog-design.md](superpowers/specs/2026-10-02-nanmu-blog-design.md) · 决策记录:[decisions/](decisions/)
