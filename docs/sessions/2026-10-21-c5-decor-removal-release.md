# 2026-10-21 C5 装饰删除轮:首页装订线+页签线绳,发布上线

## 背景

用户使用反馈两处装饰多余,逐条删除后授权发布:

1. **首页左缘贯穿竖线**(装订线三段链):探针实证 hero 段(x=12/24, y=80–1000)命中 3D canvas,即碑页线装几何,非 CSS;整链 = 3D 线装(addBinding 订环/订线+纹理订眼+seal 材质+projectBindingBottom)→ boot6 落线转接(dropV/dropH)→ main.flow 正文 .thread(line+4 knot)。三段全删才不留残线(tris 4351→295)。
2. **页签选中态顶部线绳**:`.ptab.on::before`(挂牌上方垂 9px 朱砂线)。

## 变更(均在 main)

- 69e3398 装订线:scene6.js/boot6.js/index.astro/home.css/home.js + poster-stack 昼夜重拍(147.6/144.1 KiB ≤450KiB)+ verify_browser(knots/pbb→threadN==0)
- 1e8fc2c 线绳:home.css `.ptab.on::before` 删除+注释同步 + verify_browser(ptOnBefore=="none")
- 两处均 TDD:RED(home/static FAIL:threadN=1 / ptOnBefore="")→ GREEN 86/86;npm run verify 全绿;dev 实测+像素/视觉复查

## Git / 部署状态(实况)

- `git push origin main`:67cba35..1e8fc2c(GitHub)
- `git push server main`:17d008c..1e8fc2c,hook 构建,release.txt 首次轮询(5s)即=1e8fc2c
- 线上 https://nanmu.xyz = 1e8fc2c,零回滚(9120bf3 及更早仍不作回滚目标)

## 线上验收 21/21(复用 C4 脚本,EXPECTED 改 1e8fc2c + 新增断言 11)

release.txt SHA / 四页 200+乱路径 404 / 被撤 URL 404 / rss items=0=本地 / digest items=0=本地 / 零被撤残留+poster stack 200×2 / **断言 11:threadN=0+ptOnBefore=none+3D 就绪** / 主题循环 / 零新增 404 / 几何三档+页签 resize / 手机 390 / 无JS / WebGL 禁用 / 模块失败降级。证据:shots/c5-release-*(6 图)+ logs/c5-release-live-accept.log。

## 用户报「线上线下不一致」排查结论

关于页实测 dev=dist=live 正文逐字相同(main 内文本全等);全页截图唯一像素差异 bbox=(626,881,814,953)=**Astro Dev Toolbar**(dev 模式注入的开发工具条,HTML 中 astro-dev-toolbar dev=1/live=0),非网站内容。首页同理:本地 dev/线上均无装饰(断言 11 双侧过)。若浏览器仍见旧样式,为浏览器缓存(线上无 Cache-Control,仅 Etag/Last-Modified,强刷即新)。

## 停止点

发布完成;workbench 批 1 定点修正仍待用户审计复核,批 2–4 未授权。
