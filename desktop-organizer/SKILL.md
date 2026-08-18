---
name: desktop-organizer
description: 整理桌面散落文件（候选人简历 / 职位JD / 图片）并按既定规则归档。简历按文件名职位关键词归类，先判断方向 → 统一命名为「姓名-方向.pdf」→ 归入对应类目文件夹；JD 脱敏转 PDF 后可同步发布猎聘/小红书；图片分析内容后询问处理方式；全程不删除文件。
author: Glen Wei (韦其像)
author_email: glen.keeming@gmail.com
homepage: https://github.com/Glen-Wei/headhunter-skills
agent_created: true
---

# Desktop Organizer — 桌面文件整理（超级桌面）

桌面文件（候选人简历 / 职位 JD / 图片 / 公司资料）的自动化归档流程。核心原则：**不删除任何文件**、移动前确认目标路径合理、`~$` 开头的 Word 临时文件一律忽略。

## 归档体系（桌面路径）

| 文件类型 | 目标位置 | 规则 |
|---|---|---|
| 候选人简历 | `~/Desktop/简历库/<职位类目>/` | 先判断方向 → 统一命名为 `姓名-方向.pdf` → 再归入对应类目文件夹（无该类目则新建）。见「统一文件名规约」 |
| 职位 JD | `~/Desktop/客户/<客户名>/` | 统一转 PDF（docx 原件保留同目录），无客户子文件夹则新建 |
| 图片 | 待定 | 分析内容 → 询问如何处理，等指示后再动 |
| 其他/自有资料 | 原位 | 不处理，汇报中列出提醒 |

**文件来源（每日检查，规则相同）**：
- `~/Desktop`（桌面）
- `~/Downloads`（下载文件夹）——简历→简历库、JD→客户、图片→询问、公司/客户资料→归入 `客户/<客户名>/`、其他（安装包/压缩包等）不处理仅在汇报中列出

## 简历分类规则（按文件名职位提取）

1. 文件名格式通常为 `姓名-职位-公司.pdf` 或 `姓名-职位.pdf`、`姓名_职位_公司.pdf`。职位关键词位于姓名之后、公司后缀/`.pdf` 之前。
2. 提取职位关键词后**按预设类目表归一化**（具体类目基准见 `references/categories.md`）。
3. 完整类目基准（40 个）见 `references/categories.md`，批量分类时以 `scripts/classify_resumes.py` 输出为准。
4. 无法从文件名提取职位的：读简历内容判断方向后归类；仍无法判断的列为「未分类」，汇报并询问。
5. 疑似重复文件（同名/同大小）：移动前校验 md5，重复副本询问或放入废纸篓。

**批量分类使用脚本** `scripts/classify_resumes.py`：输入简历目录，输出 `姓名 → 职位类目 → 目标路径` 清单（不移动文件，先预演）。`--apply --target` 实际归档时**已集成命名**：移动落盘即按 `姓名-方向.pdf` 规约命名（判断方向→命名→归类一步完成），无法提取姓名的保持原名并在汇报中列为待人工处理。

## 统一文件名规约（姓名-方向）

落盘到 `~/Desktop/简历库/<类目>/` 的每份简历，文件名**统一为 `姓名-方向.pdf`**：

- **方向** = 所在「类目文件夹名」（如 `VLA` / `算法` / `商业管理` / `技术美术` / `公关PR` / `灵巧手`）。
- **姓名** 从原文件名提取：中文姓名段、英文名（点号转下划线，如 `Jesse_Wu`）、职位在前时取末尾姓名段。
- **清理**：去掉常见多余后缀与编号标记（具体清理字段在脚本中维护，含客户内部代号、文件副本、数字序号等）；英文名保留。
- **已合规**：文件名本身已是 `姓名-方向`（含 `_2/_3` 冲突标记）直接跳过，不改动。
- **无法提取姓名**（如 `cv.pdf`、`XX公司介绍`）：保持原名不动，列为待人工处理。

**执行**（脚本 `scripts/rename_to_convention.py` 已含完整提取逻辑，先预览后改名；默认 dry-run）：
```bash
# 预览（不改文件），生成 rename_preview.csv 供审阅
python3 scripts/rename_to_convention.py --root ~/Desktop/简历库
# 确认无误后实际改名（可加 --backup 自动整机备份；同文件夹冲突自动加 _2/_3 避免覆盖）
python3 scripts/rename_to_convention.py --root ~/Desktop/简历库 --apply [--backup]
```
**流程顺序**：新简历一律「**判断方向 → 统一命名 → 归类**」：先判定方向，再按 `姓名-方向.pdf` 命名，然后才移入对应类目文件夹。`classify_resumes.py --apply` 已按此顺序集成命名（见上），**定时整理与手动批量归档都走这一条**，落盘即新名。
- `rename_to_convention.py` 保留用于**存量全库归一化与复核**（历史遗留文件名），新文件不再需要事后单独改名。

**docx 原件处理**：简历 docx 若转成 PDF 归档，docx 原件**不要**放类目主层（避免被当第二份简历重复收录）。原件移入类目内 `_原件docx/` 子文件夹保留，不删除。

## JD 处理规则

1. 直接发送 JD 素材并说明客户 → **先脱敏+润色，再生成 PDF** 存入 `~/Desktop/客户/<客户名>/`，文件名保留职位名。
2. **默认同步发布招聘平台（业务约定）**：JD 归档后，除非明确说不用发，否则按「发布职位」流程同步发布；**薪资数值发布前必须向使用者确认**。
3. 桌面上发现 JD 文件 → 读内容判断客户；能确定客户的转 PDF 归档；无法确定的**不移动**，附关键信息询问。
4. 客户文件夹不存在则新建。

### JD 素材脱敏与润色（强制）

JD 素材可能包含客户敏感信息（汇报对象、薪资预算、内部限制条件等），也可能是与客户的通话记录（口语化、零散）。**正式 JD 生成前必须完成脱敏与润色**：

- **必须删除（不出现在正式 JD）**：
  - 汇报对象 / 上级 / 团队内部架构信息（除非客户明确同意公开）
  - 薪资预算具体数字与薪酬谈判信息（对外统一写「面议」或客户授权的范围）
  - 性别、年龄、婚育等任何限制性条件（就业歧视条款，正式 JD 一律剔除）
  - 客户内部代号、未公开战略、竞品敏感信息、商业条款
  - 通话记录中的闲聊、口头禅、内部称呼、不确定/待定信息
- **整理与润色**：
  - 口语化、零散内容 → 规范 JD 语言（岗位定位一句话 + 岗位职责分条 + 任职要求分「必须项/加分项」）
  - 保留：职位名称、核心职责、可公开的任职要求、工作地点、团队背景（可披露部分）
- **敏感筛选条件**（性别/年龄等）不进入正式 JD，仅在内部备注，不外发。
- 生成 PDF 前说明删除了哪些敏感项；若有不确定的信息（如薪资是否可公开），先询问。

**docx → PDF 转换**：使用 Python venv（已装 python-docx + reportlab），逐段提取 docx 文本后排版生成 A4 PDF。注意注册系统中文字体（沙盒下 PingFang.ttc 可能不可用，可尝试 `/Library/Fonts/Arial Unicode.ttf` 等 TrueType 中文字体）。

### 发布职位到猎聘（JD 归档后可顺手发布）

- **焦点授权**：使用者明确授权发布职位操作时可抢焦点（CDP 切到猎聘标签）；其他场景仍保持后台标签红线
- **入口**：h.liepin.com/job/showaddpage/（猎聘「创建职位」）
- **发布流程**（Ant Design 表单，browser-harness + js 事件序列 pointerdown/mousedown/mouseup/click 触发 select）：
  1. 新增代招企业：点「+新增代招企业」→ 填企业全名 → 联想选中 → 确认
  2. 职位名称：`input.search-component-input`（**注意**：职位类别也是同类 input，勿填错位）
  3. 职位类别：自定义 jobs-wrap 联想（非标准下拉），输入关键词后点 `.ant-tag-checkable` 选项
  4. 工作城市：联想城市后仍会弹**区级面板**，需先点左侧省份、再点右侧区 → 最终显示「城市·区」
  5. 职位薪资：三下拉【最低月薪】【最高月薪】【月数】，选项 1k-500k 虚拟滚动（`rc-virtual-list-holder.scrollTop` 定位）
  6. 职位描述：`#detailDuty` textarea（≥60 字），填脱敏后 JD 正文
  7. 发布前必须勾选「已阅读发布规则」checkbox（勾选后校验 `input.checked`，未勾中则循环重试，否则报"请确认已阅读发布规则"）
- **表单选项分隔符**：工作年限等选项用「~」（如 `5~10年`），传值 `5-10年` 时脚本会自动生成变体重试（`_pick_option` 已内置 -/~ 双向变体）
- **薪资必须使用者确认（业务约定）**：薪资数值是使用者的业务决策，即使 JD 写「面议」，发布前也**必须确认对外填多少**，确认后再填表发布。`publish_job.py` 未提供 salary 参数时应停止并提示询问，不得自行定数值。
- **广告法违禁词**：描述含"顶尖/顶级/最好/第一"等会被平台拦截（弹窗"不符合《广告法》"）→ 点「立即修改」替换为"资深/一流"等合规词再发布
- **发布后状态**：平台审核中 → 管理员审核 → 正式发布。汇报时告知后续需管理员审核

### 发布职位笔记到小红书（JD 可同步发图文笔记）

- **平台**：小红书创作服务平台 creator.xiaohongshu.com（登录需扫码/验证码配合）
- **套路**（招聘笔记）：标题 16-22 字（岗位+亮点，禁用夸张词）；封面 1-2 行大字；正文 Slogan→机会→职责→要求→回报→CTA；标签 5-10 个；合规不写具体薪资
- **封面制作**：HTML 设计（简约高级风）→ browser-harness 后台标签打开 file:// → `Emulation.setDeviceMetricsOverride(1080x1440, scale 2)` → 截图 PNG
- **发布流程**（图文模式）：
  1. 上传封面：CDP `DOM.setFileInputFiles` 到 `input[type=file]`（先 `DOM.getDocument` → `DOM.querySelector` 拿 nodeId → `DOM.describeNode` 拿 backendNodeId → 再 setFileInputFiles，缺 backendNodeId 报 -32000）
  2. 标题：placeholder「填写标题」的 input（**≤20 字**，超限可能异常）
  3. 正文：`.tiptap.ProseMirror` contenteditable，`document.execCommand('insertText')` 填入（≤1000 字）
  4. 发布：**发布按钮是 `<xhs-publish-btn>` 自定义 Web Component**（内部 shadow 渲染，普通 DOM 查询找不到其文字）；点击方法：获取组件 getBoundingClientRect，用 CDP `Input.dispatchMouseEvent` 点击组件范围**右侧 60~65%**、垂直中部（`is-publish="true"` 且 `submit-disabled="false"` 表示可发布）
  5. 成功标志：URL 跳 `/publish/success`；笔记管理显示「审核中」
  6. **话题**：点「话题」按钮弹出的 el-overlay 弹窗点选容易把弹窗点关闭、选择不生效 → **不走弹窗**，正文末尾直接 `document.execCommand('insertText')` 插入 `#招聘 #AI ...` 空格分隔标签串，平台自动识别为话题，更稳更快

## 图片处理规则

分析图片内容（画面内容、类型：截图/照片/示意图/证件照/架构图等）→ 说明并询问如何处理（归档到哪/保留/删除）→ 等指示后再操作，不擅自移动删除。

## 扫描件简历处理（无文本层 PDF）

pypdf/pymupdf 提取为空 → 用 pymupdf 渲染页面为 PNG（`page.get_pixmap(dpi=200)`）后做视觉识别判断方向。备选：macOS Vision OCR（`VNRecognizeTextRequest` 支持中英文）。

## 安全红线

- 全程不删除任何文件；确需删除时移入废纸篓，不用 `rm`
- `~$` 开头文件是 Word 锁定临时文件，忽略
- 整理完成后汇报：处理了哪些文件、归入哪里、有哪些待确认事项

## 参考

- `references/categories.md` — 简历职位类目基准
- `scripts/classify_resumes.py` — 简历职位分类预演脚本（集成统一命名）
- `scripts/classify_content.py` — 简历内容分类脚本
- `scripts/rename_to_convention.py` — 简历文件名归一化（姓名-方向.pdf）脚本
- `scripts/publish_job.py` — 猎聘一键发布职位脚本

## Credits / 作者

**Glen Wei（韦其像）** 创建并维护

- Email: glen.keeming@gmail.com
- 所属合集: [headhunter-skills](https://github.com/Glen-Wei/headhunter-skills)

觉得好用？欢迎去 GitHub 上 ⭐ Star [headhunter-skills](https://github.com/Glen-Wei/headhunter-skills) 支持持续维护。转载或修改本 Skill 时，请保留作者信息。
