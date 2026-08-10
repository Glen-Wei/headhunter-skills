#!/usr/bin/env python3
"""
Fast arXiv search + classification only (no email finding/sending).
Runs standalone, imports core modules from main.py.

Created & maintained by Glen Wei (韦其像) — https://github.com/Glen-Wei
Email: glen.keeming@gmail.com | WeChat: Glen_Wei88
Part of headhunter-skills: https://github.com/Glen-Wei/headhunter-skills"""

AUTHOR_EPILOG = (
    "Author: Glen Wei (韦其像) | GitHub: https://github.com/Glen-Wei "
    "| Email: glen.keeming@gmail.com | WeChat: Glen_Wei88 | "
    "Part of headhunter-skills: https://github.com/Glen-Wei/headhunter-skills"
)

import os, sys, json, time
from datetime import datetime, date, timedelta

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, WORK_DIR)

# Import from main.py
from main import (
    ArxivScraper, PaperTracker, JDGenerator, EmailSender,
    is_robotics_relevant, extract_highlight,
    ARXIV_CATEGORIES, VENUE_KEYWORDS, DIRECTION_MAP,
    MAX_PAPERS_PER_RUN, DB_PATH, SUMMARY_DIR,
)

def generate_summary(results, run_date, total_found):
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    # Filter: papers with Chinese authors
    from main import is_chinese_name
    with_cn = [r for r in results if any(is_chinese_name(a) for a in r['paper']['authors'][:2])]
    no_cn = [r for r in results if not any(is_chinese_name(a) for a in r['paper']['authors'][:2])]

    lines = []
    lines.append(f"# 🤖 机器人顶会论文推送小结 — {run_date}\n")
    lines.append(f"📅 执行时间：{now}\n")
    lines.append("---\n")
    lines.append("## 📊 今日概况\n")
    lines.append(f"- arXiv命中论文：**{total_found}** 篇（4个类别搜索）")
    lines.append(f"- 机器人相关：**{len(results)}** 篇")
    lines.append(f"- 有华人一作/二作：**{len(with_cn)}** 篇")
    lines.append(f"- 无华人一作/二作：**{len(no_cn)}** 篇")
    lines.append(f"- 本次推送邮件：**本次跳过邮箱查找和发送**（需Glen确认后单独处理）\n")

    lines.append("---\n## 📋 论文总览\n")
    for i, r in enumerate(results):
        p = r['paper']
        cn_flag = "🇨🇳" if any(is_chinese_name(a) for a in p['authors'][:2]) else ""
        lines.append(f"### {i+1}. {cn_flag} {p['title'][:100]}")
        lines.append(f"- **方向**: {r.get('direction', '未知')}")
        lines.append(f"- **会议**: {p.get('venue', 'unknown')}")
        lines.append(f"- **作者**: {', '.join(p['authors'][:5])}")
        lines.append(f"- **arXiv**: {p['url']}")
        lines.append(f"- **发布日期**: {p.get('published', '')}")
        abs_short = p['abstract'][:200].replace('\n', ' ')
        lines.append(f"- **摘要**: {abs_short}...\n")

    lines.append("---\n## 📈 方向分布\n")
    dirs = {}
    for r in results:
        d = r.get('direction', '未知')
        dirs[d] = dirs.get(d, 0) + 1
    for d, c in sorted(dirs.items(), key=lambda x: -x[1]):
        lines.append(f"- {d}: {'█' * c} {c}篇")

    lines.append("\n---\n*快速扫描模式 — 仅搜索与分类，未进行邮箱查找与邮件发送*")
    return "\n".join(lines)


def main():
    today = date.today()
    run_date = today.isoformat()
    date_from = (today - timedelta(days=3)).isoformat()
    date_to = today.isoformat()

    print(f"🤖 Robot Paper Campaign — Fast Scan")
    print(f"📅 Range: {date_from} → {date_to}\n")

    # ── Step 1: arXiv Search ──
    print("🔍 Searching arXiv (bypassing proxy)...")
    scraper = ArxivScraper()
    all_papers = scraper.search(VENUE_KEYWORDS, ARXIV_CATEGORIES, date_from, date_to)
    print(f"\n   Total matching: {len(all_papers)} papers")

    # Filter by robotics relevance
    relevant = [p for p in all_papers if is_robotics_relevant(p)]
    print(f"   Robotics-relevant: {len(relevant)} papers (filtered out {len(all_papers)-len(relevant)})")

    if not relevant:
        print("   ✅ No relevant papers found.")
        os.makedirs(SUMMARY_DIR, exist_ok=True)
        sp = os.path.join(SUMMARY_DIR, f"{run_date}.md")
        with open(sp, 'w') as f:
            f.write(f"# 🤖 机器人顶会论文推送小结 — {run_date}\n\n今日无新增匹配论文。\n📅 搜索范围: {date_from} → {date_to}\n")
        print(f"📋 {sp}")
        return

    # ── Step 2: Classify ──
    print(f"\n📝 Classifying {len(relevant)} papers...\n")
    jd_gen = JDGenerator()
    results = []

    for idx, paper in enumerate(relevant):
        direction = jd_gen.classify(paper['title'], paper['abstract'])
        jd_info = jd_gen.generate(direction, paper)
        highlight = extract_highlight(paper['title'], paper['abstract'])
        print(f"   [{idx+1}/{len(relevant)}] {direction['name']} — {paper['title'][:60]}...")

        from main import is_chinese_name
        cn_authors = [a for a in paper['authors'][:2] if is_chinese_name(a)]
        cn_info = f"🇨🇳{', '.join(cn_authors)}" if cn_authors else "无华人作者"

        results.append({
            'paper': paper, 'direction': direction['name'],
            'emails_sent': [], 'highlight': highlight,
            'skipped': False,
            'cn_authors': cn_info,
        })

    # ── Step 3: Summary ──
    print("\n📋 Writing summary...")
    os.makedirs(SUMMARY_DIR, exist_ok=True)
    summary_text = generate_summary(results, run_date, len(all_papers))
    summary_path = os.path.join(SUMMARY_DIR, f"{run_date}.md")
    with open(summary_path, 'w') as f:
        f.write(summary_text)

    print(f"\n{'='*50}")
    print(f"✅ Done!")
    print(f"   Found: {len(all_papers)} | Robotics-relevant: {len(relevant)}")
    print(f"   Summary: {summary_path}")
    print(f"{'='*50}")

    # Print summary
    print("\n\n=== SUMMARY START ===")
    print(summary_text)
    print("=== SUMMARY END ===")


if __name__ == '__main__':
    print(AUTHOR_EPILOG, file=sys.stderr)
    main()
