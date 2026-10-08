# 会话交接:视觉改版第一批——三方向视觉稿与推荐方案(2026-10-07)

- **recorded_at**: 2026-10-07 22:50 Asia/Shanghai
- **continues**: 无(本主题为 M2 前前端改版首轮;仓库前序见 [2026-10-06 M1 审计修复轮](2026-10-06-m1-audit-fix-round.md))
- **repository**: HEAD `734c47f`(main,本轮无提交);本轮全部产出为**未提交**新文件 `docs/design/2026-10-07-visual-redesign/`(README + prototypes + shots);接手时已有未跟踪目录 `.audit-plan-a-v_rqz2td/` 与本轮无关,未触及
- **objective**: M2 开发前的前端视觉与交互改版第一批——三个可比较的视觉方向、推荐方案的首页+文章页四态视觉稿、主视觉与微交互设计、动效实现与降级说明、分批实施计划。不改 site/ 正式页面
- **change_scope**:
  - 本轮新增:`docs/design/2026-10-07-visual-redesign/README.md`(设计说明)、`prototypes/`(index + direction-a/a-article/b/c 共 5 个独立 HTML + 本地字体子集 fonts/*.woff2 8 个文件共约 560KB + fonts.css)、`shots/`(11 张浏览器核对截图)
  - 未触及:site/、engine/、spec、ADR、内容文件;原型中的内联脚本仅演示主题切换,已在文件内标注"原型专用"
  - 外部操作:未执行(无提交/推送/部署)
- **state**:
  - 三方向视觉稿完成并可双击查看:A「营造·本站施工图」(推荐,含首页+文章页 × 桌面/手机 × 浅/深)、B「蓝晒·工程底图」(首页双主题)、C「活字·一色印刷」(首页双主题) [verified: Playwright/Chromium 实机渲染逐页核对,截图在 shots/;渲染修复记录见下]
  - 主视觉定案:轴测 SVG 小院(正房=文章/东厢=AI 日报虚线工地/留白=检索),静止/悬停/分镜/降级齐备 [verified: shots/a-home-* 四态 + reduced-motion 完成态]
  - 字体方案验证:思源宋体/黑体/IBM Plex Mono 按原型用字子集化,单中文字重约 68–90KB,woff2 本地化、无外网依赖 [verified: d:/tmp/subset-fonts.py 运行输出,fonts/ 文件大小]
  - 设计说明含:三方向构图/字色/明暗/动效/适配理由、推荐理由、页面规格、分镜表、微交互清单、降级矩阵、真实状态核对、规则调整提案(主题切换内联脚本 ADR / 字体子集化)、四批实施计划 [verified: README.md 全文;check_docs 通过]
- **verification**:

  | 工作目录/环境 | 实际命令或操作 | 结果及证据边界 |
  |--------------|----------------|----------------|
  | 仓库根 | `python scripts/check_docs.py` | 通过,errors/warnings 均为 0 |
  | Chromium(Playwright,本地 http.server 8931) | 逐页渲染 5 个原型 × 桌面 1440/手机 390 × 浅/深 + reduced-motion | 通过;证据 shots/ 11 张。已知修复:翼注超出版心(viewBox 扩至 704)、活字翻面动画覆盖 rotate(改格子落盘)、backface 3D 文字镂空(改透明度过渡)、B 修订戳图文分离(整组旋转)、移动端导航折行/日报图签键值堆叠 |
  | site/ | 未运行 verify(本轮不改 site) | 不适用 |

- **decisions_needed**:
  1. 方向选择:推荐 A「营造」;B/C 为备选,评审后可弃可融
  2. ADR-0002 增补提案:手动主题切换需唯一内联脚本(约 20 行);或保持跟随系统(零改动)
  3. 字体自托管:构建期子集化(运行时零新依赖);或降级系统字体栈
- **disposition**: continuable
- **next_action**: 用户评审 prototypes/(入口 index.html)→ 定方向与规则调整 → 按 README §7 批次 1(排版与骨架)开工;实施前先按 README §6 落 ADR
- **omissions**:
  - 日报详情页、归档/列表页、404 页仅有规格文字,未建原型;M2 的 RAG 入口位置未设计(spec 也尚未定其形态)
  - 原型未测真实移动设备(仅 390px 视口模拟);楷体回退在未装 Kaiti 的环境降为宋体,未多平台核对
  - 方向 B/C 的深色文章页未建(推荐后再补)
  - 施工图 SVG 几何为一次性脚本(d:/tmp/gen-house.mjs,在临时目录,未入库)生成后手工微调;生产实现需决定构建期生成还是手工维护
  - 原型链接为 # 占位,未接真实路由;文章页"排版样张"块为演示内容,已在页面内标注
  - README 未挂入 docs/README.md 索引与 AGENTS 状态快照——方向未定稿,待评审后随实施批次一起更新入口,避免把未定稿设计写成项目状态
