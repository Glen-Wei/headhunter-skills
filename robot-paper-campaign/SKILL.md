---
name: robot-paper-campaign
description: "机器人顶会论文推送与建联：每日从 arXiv 搜索顶级 ML/Robotics 会议论文，找一二作者的 GitHub 主页与邮箱，自动发送建联邮件并归档日报。顶会清单与 arXiv 分类在启动时由用户自定义选择（支持 --venues/--categories 参数与交互式输入），不再写死。"
author: Glen Wei (韦其像)
author_email: glen.keeming@gmail.com
author_wechat: Glen_Wei88
author_github: https://github.com/Glen-Wei
homepage: https://github.com/Glen-Wei/headhunter-skills
agent_created: true
---

# Robot Paper Campaign — 顶会论文推送与自动建联

每日从 arXiv 搜索顶级 ML/Robotics 会议论文 → 定位一二作者（华人优先）→ 找 GitHub 主页与邮箱 → 自动发送建联邮件 → 生成日报归档。

> 本 Skill 只包含通用操作逻辑。**顶会清单、arXiv 分类、邮件身份信息全部由使用者在启动前自定义**（交互式选择或命令行参数），不写死任何个人配置。

## 启动前：自定义本次推送（用户选择）

运行 `scripts/main.py` 时，**启动前会让使用者选择本次推送的顶会与 arXiv 分类**：

**方式一：交互式选择（推荐）**

```bash
python scripts/main.py
```

启动时提示（直接回车 = 使用默认）：

```
⚙️  本次推送配置（直接回车 = 使用默认）
  顶会关键词（默认: NeurIPS 2026, ICML 2026, ICLR 2026, ...）: NeurIPS 2026, CoRL 2026
  arXiv 分类（默认: cs.RO, cs.CV, cs.LG, cs.AI）: cs.RO, cs.CV
```

**方式二：命令行参数（适合定时任务/脚本）**

```bash
python scripts/main.py --venues "NeurIPS 2026,CoRL 2026" --categories "cs.RO,cs.CV"
```

**方式三：定时任务/无人值守**

```bash
python scripts/main.py --no-prompt --dry-run        # 用默认顶会，跳过交互
python scripts/main.py --no-prompt                  # 用默认顶会正式运行
```

## 配置（发件身份，由使用者填写）

创建 `~/.workbuddy/gmail_config.json`：

```json
{
  "email": "your@gmail.com",
  "password": "Gmail 应用专用密码",
  "recruiter_name": "你的顾问称呼",
  "wechat": "你的微信号",
  "signature": "你的邮件签名"
}
```

`email` / `password` 必填；`recruiter_name` / `wechat` / `signature` 可选（缺省用中性占位）。

## 完整流程

```
1. arXiv 搜索：按用户选择的顶会关键词 × arXiv 分类 × 日期范围（默认近 3 天）
2. 相关性过滤：仅保留机器人/AI 相关论文（内置相关性关键词）
3. 去重：paper_tracker.db 记录已处理论文，只处理新增
4. 定位作者：取一二作（华人优先），查 GitHub 主页 → 提取邮箱
5. 生成 JD：按论文方向分类（DIRECTION_MAP）→ 生成量身定制的 JD
6. 发送邮件：Gmail SMTP（465, SSL, 代理 CONNECT 隧道支持）
7. 归档：summaries/<日期>.md 日报
```

## 常用命令

```bash
# 预览（不发送、只打印计划）—— 推荐每次先跑这个
python scripts/main.py --dry-run

# 交互选择顶会并正式发送
python scripts/main.py

# 指定日期范围
python scripts/main.py --date-from 2026-08-01

# 限制处理数量
python scripts/main.py --max-papers 20

# 只搜索+分类，不发邮件（快速模式）
python scripts/run_fast.py
```

## 脚本

- `scripts/main.py` — 主流程（搜索/过滤/找邮箱/生成JD/发送/归档）
- `scripts/run_fast.py` — 快速模式：仅 arXiv 搜索 + 分类 + 摘要（不发邮件）

## 依赖

- Python 3.8+
- `requests`
- 能访问 Gmail SMTP（海外网络或本地代理）；配置 `HTTP_PROXY` 环境变量可走代理

## Credits / 作者

**Glen Wei（韦其像）** 创建并维护 — 资深 AI 与具身智能领域猎头（TTC）。

- GitHub: [Glen-Wei](https://github.com/Glen-Wei)
- Email: glen.keeming@gmail.com
- 微信: Glen_Wei88
- 所属合集: [headhunter-skills](https://github.com/Glen-Wei/headhunter-skills)

觉得好用？欢迎去 GitHub 上 ⭐ Star [headhunter-skills](https://github.com/Glen-Wei/headhunter-skills) 支持持续维护。转载或修改本 Skill 时，请保留作者信息。
