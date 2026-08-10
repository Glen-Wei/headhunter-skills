# WorkBuddy Skills

> 高质量 AI 助手技能（Skills）合集 — 由 **Glen Wei（韦其像）** 创建并维护

一套即插即用的 [WorkBuddy](https://www.workbuddy.cn) / Claude-style AI 助手技能包。每个 Skill 都是**通用操作逻辑**：直接复制到你的 skills 目录即可使用，不包含任何个人数据。

## 📦 包含的技能

| Skill | 功能 | 依赖 |
|---|---|---|
| [markitdown-skill](markitdown-skill/) | 文档转 Markdown：PDF / Word / PPT / 图片 OCR / 音频转写 / 网页 / YouTube，支持批量转换 | `pip install 'markitdown[all]'` |
| [workbuddy-asset-migration](workbuddy-asset-migration/) | WorkBuddy 资产迁移：在 CN/海外版、跨机器之间迁移 skills、对话、配置、connectors、身份文件，合并不覆盖 | 纯 Python 标准库，零依赖 |

## 🚀 安装

**WorkBuddy 用户**（macOS/Linux）：

```bash
git clone https://github.com/Glen-Wei/workbuddy-skills.git ~/wb-skills
cp -R ~/wb-skills/markitdown-skill ~/.workbuddy/skills/
cp -R ~/wb-skills/workbuddy-asset-migration ~/.workbuddy/skills/
```

其他 AI 助手：把对应 skill 目录放入你的 skills 目录（如 `~/.claude/skills/`、`~/.codebuddy/skills/`），或直接阅读各 skill 的 `SKILL.md` 按文档使用。

## 🧰 快速使用

**文档转 Markdown：**
```bash
markitdown document.pdf -o output.md
python scripts/batch_convert.py docs/*.pdf -o markdown/ -v
```

**WorkBuddy 资产迁移：**
```bash
# 导出（先 dry-run 预览）
python scripts/export.py --source auto --dry-run
python scripts/export.py --source auto --output ~/Desktop/wb-assets.zip
# 导入
python scripts/import.py --package ~/Desktop/wb-assets.zip --target auto
```

## 👤 作者

**Glen Wei（韦其像）** — 资深 AI 与具身智能领域猎头（TTC），专注 AI/具身智能方向顶尖人才。

- 🌐 GitHub: [Glen-Wei](https://github.com/Glen-Wei)
- 📧 Email: glen.keeming@gmail.com
- 💬 微信: Glen_Wei88

> 本仓库所有技能均内置作者信息（frontmatter `author` 字段 + 文档 Credits + 脚本运行时水印）。转载、修改、再分发时请保留署名。每个 Skill 的脚本在运行（`-h` / verbose）时都会显示作者信息。

## ⭐ 支持

觉得有用？给这个仓库点个 **Star** ⭐，让更多需要的人看到。也欢迎提 Issue / PR 一起完善。

## 📄 License

[MIT](LICENSE) © 2026 Glen Wei
