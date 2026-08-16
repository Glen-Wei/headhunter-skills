---
name: liepin-search
description: 猎聘超级搜索——输入JD/关键词，自动搜索、提取、评分候选人，输出TOP10含直达链接的表格。适用场景：Glen给出任一JD或搜索要求时。
author: Glen Wei
author_email: glen.keeming@gmail.com
author_wechat: Glen_Wei88
author_github: https://github.com/Glen-Wei
agent_created: true
---

# 猎聘超级搜索 Skill

## 概述

在猎聘（h.liepin.com）上搜索并深度筛选候选人。**唯一交付模式：深度审查模式**（`scripts/liepin_deep_review.py`）——逐个打开候选人简历详情页，提取完整简历，按 JD 维度深度评分，输出带证据的判定结论。

> `scripts/liepin_search.py` 仅作为内部搜索库被复用（提供 `search_keyword`/`connect`），不单独作为交付模式。

## 前置条件

- 浏览器已通过 browser-harness 连接到用户 Chrome（已登录猎聘）
- `data-tlg-scm` 属性包含 `cid=` 参数（简历ID）
- 简历直达链接格式：`https://h.liepin.com/resume/showresumedetail/?res_id_encode={cid}`

## 硬规则（Glen固定偏好）

- **直达链接必须在聊天窗口表格中展示**：每个候选人的简历链接必须以 `[👉打开](url)` 形式直接嵌入在每一行的最后一列。不允许仅保存到文件而不在聊天窗口展示链接。链接必须可点击（markdown格式）。
- **硬性条件可叠加**：`--max-age`（年龄）、`--city`（城市）、`--gender`（性别）——不满足条件的候选人自动标记排除，不出现在推荐名单
- **JD硬性要求必须从JD自动解析**：学历下限/统招/工作年限/必备方向/落地项目数——用 `parse_jd.py` 从JD文档自动提取，禁止人工拍脑袋定
- **默认深度审查**：候选人必须逐个打开简历详情页判断，不能只看搜索卡片文本
- **总结完自动发消息（2026-08-16 固化）**：深度审查+人工研判产出合适候选人名单后，**自动向名单中的候选人发送猎聘站内建联消息**（无需等 Glen 逐条确认话术，按下文话术规范自动生成）。除非 Glen 明确说"先别发"，否则每次搜索交付都自动带发。
- **发消息不抢焦点 + 发完即关**：发消息用后台标签页（`Target.createTarget(background=True)`），**禁止弹前台/抢焦点**；**每发完一人立即 `Target.closeTarget` 关闭标签**，不允许堆积标签页。

## 提速机制（2026-08-16 改造，v2）

三处提速，不依赖外部服务、不增加登录风险：

1. **DOM就绪检测替代固定sleep（搜索+审查）**：搜索时等搜索框/结果卡片出现即继续，审查时等"工作经历/求职意向"区块渲染即提取——不再死等。实测：搜索每词 12-15s → **5.5s**；深度审查每人 6-10s → **3.6s**。
2. **翻页拿更多候选人**：新增 `--pages N`，每关键词翻 N 页（每页约20人）。实测 pages=2 拿 40 人仅 6.4s。
3. **卡片粗筛**（默认开启）：开详情页前先用搜索卡片文本（姓名/年龄/学历/年限/城市）保守筛掉明确不符者（超龄/年限不足/学历不足），信息不足一律保留不误杀。可用 `--no-card-filter` 关闭。实测50人场景可省约1/3详情页打开。

> 注：猎头端 h.liepin.com 是 SPA+hash 路由，**不支持**求职端那种 URL 参数直连（实测 keyword 参数不生效），搜索交互流程必须保留。

---

## 标准流程（每次搜索必须走完）

```
1. 读JD → 2. parse_jd.py 自动解析硬性要求 → 3. 前置大搜索（关键词×多组）
→ 4. 前100人深度审查（逐个打开简历） → 5. 硬性过滤+JD评分+人工研判
→ 6. 输出全量通过者（按合适度排序，附直达链接）+ 自动向合适候选人发建联消息
```

### ⭐ 一键入口（用户发JD时的默认用法）

用户提供JD文件后，**执行一条命令即可全流程自动完成**：
```bash
python <skill_dir>/scripts/run_jd_search.py "<JD文件路径>" [--limit 30] [--max-age 35] [--city 上海] [--gender 男]
```
内部自动完成：parse_jd解析 → 生成关键词 → 猎聘前置筛选 → 搜索 → 深度审查 → 报告+直达链接。
- `--limit` 默认20（分批跑），要全量用 `--limit 100`
- 年龄/城市/性别等不传时默认从JD解析（年龄默认≤40）
- 人数不足或中断后用 `--resume` 续跑

**注意**：一键脚本通过 subprocess 调用，必须在 **browser-harness 管道环境** 下运行
（`browser-harness <<'PYEOF' ... PYEOF`），或确保 daemon 已连接 Chrome。

### Step 0: 读取JD并自动解析硬性要求（新增）
```bash
python <skill_dir>/scripts/parse_jd.py "<JD文件路径>" -o <jd.json>
```
自动提取（输出JSON的 `hard` 字段）：
- `min_edu`：学历下限（本科/硕士/博士）
- `tongzhao`：是否要求统招/全日制
- `min_years`：工作年限下限
- `core_skills_any`：必备方向词（至少命中其一）
- `landing_min`：落地/量产证据最低命中数
- 同时生成 `core/skills/industry/landing/cities` 评分配置

**人工复核**：解析结果必须人工核对，确认与JD原文一致（正则可能漏网/误判）。

### 前置筛选（猎聘页面源头过滤，Glen硬性要求）
搜索前必须在猎聘"找简历"页设置筛选，避免无效候选人混入：
```bash
--pre-max-age 35     # 年龄上限（input.age-input）
--pre-min-years 8    # 工作年限下限（label.tag-item 点选档位）
--pre-min-edu 本科    # 学历下限（label.tag-item）
--pre-city 上海       # 期望城市（label.tag-item）
--pre-gender 男       # 性别（.sexSelectStyle 下拉）
```
猎聘筛选控件结构见 `references/data-tlg-scm.md` 附注。

### 后台标签页（不打断用户）
简历深度审查用 **单个复用后台标签页**（`Target.createTarget(background=True)` + 全局 `_bg_tab()`），
不在用户浏览器前台弹新标签。禁止每份简历 createTarget 新开前台标签。

### Step 1-4: 深度审查
```bash
python <skill_dir>/scripts/liepin_deep_review.py \
  --keywords "关键词1,关键词2,关键词3,关键词4,关键词5,关键词6" \
  --jd-json <jd.json> \
  --max-age 35 --city 上海 --gender 男 \
  --pre-max-age 35 --pre-min-years 8 --pre-min-edu 本科 --pre-city 上海 --pre-gender 男 \
  --pages 2 --limit 30 --resume \
  --output <前缀>
```
- `--limit 30` 分批跑，每批完成后用 `--resume` 续跑（断点不丢）
- `--pages N` 每关键词翻 N 页（每页约20人），想覆盖全量用 `--pages 5`
- `--no-card-filter` 关闭卡片粗筛（默认开启）
- 大数据量（100人）分 3-4 批执行
- 支持入口：`--keywords` / `--cids` / `--cids-file` / `--from-json`

1. **打开简历页**：显式 CDP 控制（后台标签页复用），**不依赖隐式"当前tab"状态**（旧实现会因 switch_tab 干扰而失败）
2. **展开折叠**：循环点击 `.rd-info-other-link`（"显示其他N段项目经历"）
3. **有效性判定**：`len(text) > 800` 且含"工作经历/求职意向"区块（**短简历也接受**，避免误杀）
4. **解析**：基本信息（姓名/年龄/学历/城市/年限/当前职位公司）、求职意向（职位/薪资/城市/行业）、工作经历/项目/教育/自我评价切块

5. **评分**：核心方向词（电主轴/末端执行器/灵巧手/打磨/力控等，每词最多累计2次）+ 技能词（"学习中"扣半）+ 行业词 + 落地证据 + 年限 + 学历（统招/机械专业/硕博）+ 长三角 + 可谈性；反向信号（维修向/非统招/学习中/教师）扣分；总分归一化 0-100
6. **节奏控制**：每人间隔 1-2s，每 8 人暂停 6s，防风控

### 已知限制与应对

| 情况 | 表现 | 应对 |
|---|---|---|
| 浏览器 CDP 连接中断 | "no close frame received" | 用 `browser-harness` CLI 唤醒连接后重跑（`--resume`） |
| 短简历（内容<1500字） | 早期版本误判失败 | 已修复：>800字且含核心区块即接受，注意短简历机器分偏低，需人工研判 |
| 公司名无"·"分隔 | current_company 解析为空 | 从最后一个"市"字回溯切分（覆盖多数带城市前缀公司名），无"市"则留空，以 current_role 为准 |
| 求职意向含"索要附件"等噪声 | intent 字段污染 | 已过滤导航行；纯城市名单行（如"东莞"）正确归入 cities |
| 机器评分 ≠ 真实匹配 | 短简历/软件方向误判 | **人工研判不可省**：最终名单必须人工复核高分者完整简历 + 修正误判（例：软件算法方向 57 分但方向不符应排除；短简历 44 分但灵巧手负责人方向对口应上调） |
| 大批量审查超时 | 100人一次跑不完 | 分批跑：`--limit 30` + `--resume` 续跑，每批之间等待通知 |
| 简历编号异常 | "抱歉，简历编号异常" | 简历被下架/无效，脚本已判失败记录 status=failed，重跑自动跳过 |
| 卡片粗筛误杀（理论风险） | 卡片文本截断导致年龄/学历误判 | 粗筛逻辑**保守**：仅明确不符才跳过，信息不足一律保留；仍不放心可 `--no-card-filter` |

---

## Step 6: 自动发建联消息（2026-08-16 新增，Glen要求固化）

深度审查 + 人工研判产出合适名单后，**自动向名单候选人发猎聘站内消息**（不再等逐条确认）。

### 用法
```bash
python <skill_dir>/scripts/send_chat.py <cid> "<消息内容>" [--dry] [--shot]
```
- 必选：`cid`（简历ID）+ 消息内容
- `--dry`：只跑到"消息已输入输入框"，不点发送（流程验证用）
- `--shot`：发完截图存 `<工作目录>/sent_<cid>.png`（默认不截）

### 话术规范（Glen 2026-08-16 指示）
- **禁止出现"我是 Sherry，TTC 猎头"等身份介绍**——Glen 明确删掉，直入主题
- 格式：`<称呼>您好，<北京一家 AI 公司在找 XX>，<点出该候选人最硬的一个亮点>。方便聊聊吗/了解一下吗？`
- 每条 40-60 字，点出对方简历最亮眼的具体战绩（如"RT6无人车招聘完成率100%""石头科技1000→3800人扩张期操盘"），拒绝空话套话
- 落款：不加个人署名（Glen 要求）

### 流程（脚本内置，全程后台标签）
1. `Target.createTarget(background=True)` 后台开简历页（**禁止弹前台/抢焦点**）
2. 点「立即沟通」/「继续沟通」（旧版按钮文案，自动兼容两种）
3. 弹窗模式 → 点「不选择职位开聊」；无弹窗 → 直接进入聊天抽屉（自动识别）
4. `textarea.ant-im-input` 写入消息 → 点「发送」
5. **发完立即 `Target.closeTarget` 关闭标签**（`finally` 块，出错也关，不堆积标签）

### 批量发送
- 名单确认后逐条调用，**每人间隔 ≥6 秒**，防风控
- 完成后在聊天窗口报告：每人 `SENT`/失败原因
- 提醒 Glen 到猎聘「我的消息」看回复，优先跟进高意向+已读未回者

### 注意事项
- **猎聘风控是真实风险**：批量搜索+审查+实发叠加极易触发风控。发消息批次要小、间隔要长；触发风控立即停止等冷却
- 若浏览器 CDP 连接中断（"no close frame received"），唤醒连接后补发未成功者
- 脚本已复制至 skill 目录：`scripts/send_chat.py`（2026-08-16 加入自动关标签逻辑）

---

## 交付规范

1. **聊天窗口表格必须包含直达链接**（`[👉打开](url)` 为最后一列）
2. 深度模式报告需包含：对比说明（快速 vs 深度）、最终排名表、**逐人研判**（匹配证据/疑虑/建议）、行动建议
3. 完整简历文本存 JSON 供建联邮件个性化使用
4. 用 `present_files` 展示报告

---

## Credits / 作者

**Glen Wei（韦其像）** 创建并维护 — 资深 AI 与具身智能领域猎头（TTC）。

- GitHub: [Glen-Wei](https://github.com/Glen-Wei)
- Email: glen.keeming@gmail.com
- 微信: Glen_Wei88
- 所属合集: [headhunter-skills](https://github.com/Glen-Wei/headhunter-skills)

觉得好用？欢迎去 GitHub 上 ⭐ Star [headhunter-skills](https://github.com/Glen-Wei/headhunter-skills) 支持持续维护。转载或修改本 Skill 时，请保留作者信息。
