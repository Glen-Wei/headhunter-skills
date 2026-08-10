<div align="center">

# ⚡ 猎头 Skill（Headhunter Skills）

### AI 猎头工作流技能库 · Skill Arsenal for Headhunters

**由 [Glen Wei（韦其像）](https://github.com/Glen-Wei) 创建并维护** — 资深 AI 与具身智能领域猎头（TTC）

[![Stars](https://img.shields.io/github/stars/Glen-Wei/headhunter-skills?style=for-the-badge&logo=github&color=22d3ee&label=Stars)](https://github.com/Glen-Wei/headhunter-skills)
[![Forks](https://img.shields.io/github/forks/Glen-Wei/headhunter-skills?style=for-the-badge&logo=github&color=a78bfa&label=Forks)](https://github.com/Glen-Wei/headhunter-skills)
[![License](https://img.shields.io/github/license/Glen-Wei/headhunter-skills?style=for-the-badge&color=34d399&label=License)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8%2B-38bdf8?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-WorkBuddy%20%7C%20Claude%20%7C%20通用-0ea5e9?style=for-the-badge)](https://www.workbuddy.cn)

**🌐 展示页: [glen-wei.github.io/headhunter-skills](https://glen-wei.github.io/headhunter-skills)**

> 猎头工作流专用 AI 技能包：文档转 Markdown、资产迁移、猎聘超级搜索、桌面文件整理。
> 每个 Skill 都是**纯通用操作逻辑**——复制到你的 skills 目录即生效，**不含任何个人数据**。

</div>

---

## 🧰 技能库

| Skill | 功能 | 亮点 |
|:---:|---|---|
| 📄 [markitdown-skill](markitdown-skill/) | 文档转 Markdown：PDF / Word / PPT / 图片 OCR / 音频转写 / 网页 / YouTube | 基于微软 MarkItDown，支持批量转换 |
| 📦 [workbuddy-asset-migration](workbuddy-asset-migration/) | WorkBuddy 资产迁移：CN↔海外版 / 跨机器迁移 skills、对话、配置、身份文件 | 纯标准库**零依赖**，合并不覆盖 |
| 🎯 [liepin-search](liepin-search/) | 猎聘超级搜索：输入 JD → 自动搜索 + 深度审查 + 评分候选人 | 输出带直达链接的推荐名单，防误杀 |
| 🗂️ [desktop-organizer](desktop-organizer/) | 桌面文件整理：简历按职位自动分类、JD 脱敏转 PDF | 全程**不删除文件**，安全归档 |

## 🚀 快速开始

```bash
# 克隆
git clone https://github.com/Glen-Wei/headhunter-skills.git ~/wb-skills

# WorkBuddy 用户：全部装入
cp -R ~/wb-skills/* ~/.workbuddy/skills/

# 或按需挑选，例如只要文档转换
cp -R ~/wb-skills/markitdown-skill ~/.workbuddy/skills/
```

其他 AI 助手：把对应 skill 目录放入你的 skills 目录（如 `~/.claude/skills/`），或直接阅读各 skill 的 `SKILL.md` 按文档使用。

## ⚙️ 使用示例

**📄 文档转 Markdown**

```bash
markitdown document.pdf -o output.md          # 单文件
python scripts/batch_convert.py docs/*.pdf -o markdown/ -v   # 批量
```

**📦 资产迁移（先预览后执行）**

```bash
python scripts/export.py --source auto --dry-run            # 预览
python scripts/export.py --source auto --output ~/wb.zip    # 导出
python scripts/import.py --package ~/wb.zip --target auto   # 导入
```

**🎯 猎聘搜索（一条命令全流程）**

```bash
python scripts/run_jd_search.py "JD.pdf" --limit 30 --city 上海
```

**🗂️ 桌面整理（先预演不移动）**

```bash
python scripts/classify_resumes.py ~/Downloads --out report.json
```

## ✨ 特性

- 🔌 **即插即用** — 目录即装即用，无需复杂配置
- 🧩 **纯通用逻辑** — 只含操作流程与方法论，不含任何个人数据
- 🖋️ **作者水印** — 每个 Skill 内置三重作者信息（frontmatter + Credits + 脚本运行时输出），可溯源
- 🛡️ **安全优先** — 全程不删除文件、不触碰凭据、MIT 开源

## 👤 作者

**Glen Wei（韦其像）** — 资深 AI 与具身智能领域猎头（TTC），专注 AI / 具身智能方向顶尖人才。

- 🐙 GitHub: [Glen-Wei](https://github.com/Glen-Wei)
- 📧 Email: glen.keeming@gmail.com
- 💬 微信: Glen_Wei88

> 本仓库所有技能均内置作者信息。转载、修改、再分发时请保留署名。

## ⭐ 支持

觉得有用？点个 **Star** ⭐ 让更多需要的人看到。也欢迎提 [Issue](https://github.com/Glen-Wei/headhunter-skills/issues) / PR 一起完善。

## 📄 License

[MIT](LICENSE) © 2026 Glen Wei
