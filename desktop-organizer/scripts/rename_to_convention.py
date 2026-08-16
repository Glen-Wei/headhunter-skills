#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rename_to_convention.py — 简历文件名统一规约工具

规约（Glen 确认，2026-08-13）：
  方向 = 文件所在「类目文件夹名」（如 VLA / 算法 / 商业管理 / 技术美术 / 公关PR）
  文件名格式 = 姓名-方向.pdf
  清理：去掉 Copy of / 公司品牌后缀 / 数字序号 / (2) / _1 等多余后缀
  英文名：保留（点号转下划线），如 Dylan-VLA.pdf、Jesse_Wu-商业管理.pdf
  无法从文件名提取姓名的：保持原名不动

用法：
  # 仅预览（默认，不改动任何文件），生成 rename_preview.csv
  python3 rename_to_convention.py [--root ~/Desktop/简历库]

  # 实际改名（先确认预览无误；可选 --backup 自动整机备份）
  python3 rename_to_convention.py --apply [--backup] [--root ...]

  # 作为模块调用（供其他脚本嵌入）
  from rename_to_convention import normalize_name, propose_rename

安全：默认 dry-run；--apply 才真改；同文件夹目标名已存在时自动加 _2/_3 避免覆盖。

Created & maintained by Glen Wei (韦其像) — https://github.com/Glen-Wei
Email: glen.keeming@gmail.com | WeChat: Glen_Wei88
Part of headhunter-skills: https://github.com/Glen-Wei/headhunter-skills"""
import os
import re
import csv
import argparse
import shutil
import datetime

AUTHOR_EPILOG = (
    "Author: Glen Wei (韦其像) | GitHub: https://github.com/Glen-Wei "
    "| Email: glen.keeming@gmail.com | WeChat: Glen_Wei88 | "
    "Part of headhunter-skills: https://github.com/Glen-Wei/headhunter-skills"
)

# ---------- 复用已验证的姓名提取逻辑（与 2026-08-13 批量改名一致）----------

# 分隔符（含全角）
SPLIT_RE = r'[-_ —–·]'

# 中文职位/方向 关键词（多字符，用于子串匹配，不会误中英文名）
CJK_ROLE_SUBSTR = {
    "算法","工程师","总监","经理","专家","负责人","开发","研究","设计","运营","销售","产品",
    "架构","顾问","咨询","媒介","资深","高级","初级","实习","助理","管培","代表","专员","主管",
    "主任","部长","总裁","副总","总经理","合伙人","创始","技术","业务","市场","财务","人事","行政",
    "法务","采购","供应链","质量","生产","制造","工艺","测试","运维","实施","交付","客户","用户",
    "增长","战略","商业","品牌","公关","内容","社区","渠道","商务","项目","研究员","学者","讲师",
    "导师","博士","硕士","本科","安全","分析","工程","招聘","培训","数据","平台","策略","智能",
    "具身","仿真","控制","规划","感知","运动","嵌入","硬件","软件","机械","通信","网络","系统",
    "模型","世界","多模态","强化","自动驾驶","灵巧","机器人","自动化","人工智能","大模型","leader",
}
# 职位/方向 关键词（命中即认为该段是「职位」而非「姓名」）
ROLE_KEYWORDS = {
    # 中文职位/方向词
    "算法","工程师","总监","经理","专家","负责人","开发","研究","设计","运营","销售",
    "产品","架构","顾问","咨询","媒介","资深","高级","初级","实习","助理","管培","代表",
    "专员","主管","主任","部长","总裁","副总","总经理","合伙人","创始","技术","业务","市场",
    "财务","人事","行政","法务","采购","供应链","质量","生产","制造","工艺","测试","运维",
    "实施","交付","客户","用户","增长","战略","商业","品牌","公关","内容","社区","渠道","商务",
    "项目","研究员","学者","讲师","导师","博士","硕士","本科","安全","分析","工程","招聘",
    "培训","数据","平台","策略","智能","具身","仿真","控制","规划","感知","运动","嵌入","硬件",
    "软件","机械","通信","网络","系统","模型","世界","多模态","强化","嵌入","自动驾驶","灵巧",
    "机器人","自动化","人工智能","大模型","leader","lead","ta","agent","pr","sre","infra",
    # 英文职位/方向词
    "ai","ml","cv","nlp","data","pm","qa","hr","bd","ae","ui","ux","api","genai","vla","llm",
    "sla","ceo","cto","cfo","coo","founder","architect","scientist","engineer","manager",
    "director","principal","staff","senior","junior","intern","researcher","professor","phd",
    "dr","mr","mrs","ms","dev","triage","triageload","support","specialist","expert",
}
# 英文名拼接时的停止词（遇到即不再拼接）
EN_STOP = ROLE_KEYWORDS | {"cv","final","resume","ttc","pdf","report","for","of",
                           "and","the","at","share","reel","portfolio","work","demo"}

def strip_prefixes(s):
    s = s.strip()
    s = re.sub(r'(?i)^copy\s+of\s+', '', s)
    s = re.sub(r'(?i)^(ttc|品牌名|品牌名)[-_]\s*', '', s)
    s = re.sub(r'(?i)^cv[-_]', '', s)
    return s

def strip_suffixes(s):
    s = re.sub(r'(?i)[-_ ]?(ttc|品牌名|品牌名)\s*$', '', s)
    s = re.sub(r'[-_ ]\(\d{1,3}\)\s*$', '', s)            # (2)
    s = re.sub(r'[-_ ]1\s*$', '', s)                     # 仅去 _1 / -1（Copy of 产物）；保留 _2/_3 冲突标记
    s = re.sub(r'(?i)[-_ ]?(report|分享|final|cv)\s*$', '', s)
    s = re.sub(r'(?i)[-_]?resume[_]?\d*\s*$', '', s)
    s = re.sub(r'(?i)[-_]?pdf\s*$', '', s)
    return s

def is_cjk_name(seg):
    seg = seg.strip()
    if not seg:
        return False
    cjk = re.findall(r'[\u4e00-\u9fff]', seg)
    return 1 <= len(cjk) <= 4 and len(seg) <= 6 and not any(k in seg for k in ROLE_KEYWORDS)

def is_ascii_name(seg):
    seg = seg.strip()
    if not seg:
        return False
    return bool(re.fullmatch(r'[A-Za-z][A-Za-z ._\-]*', seg)) and len(seg) <= 30

def first_is_role(seg, folder):
    seg_l = seg.strip().lower()
    if seg_l in ROLE_KEYWORDS:
        return True
    # 仅对多字符中文职位词做子串匹配，避免 "ta"/"pr" 误中 Si-ta-s、Tan-g 等英文名
    if any(k in seg_l for k in CJK_ROLE_SUBSTR):
        return True
    # 文件名以文件夹名(方向)开头 -> 那是方向不是姓名
    f = folder.lower().replace(" ", "")
    if seg_l == f or seg_l.startswith(f) or f.startswith(seg_l):
        return True
    return False

def build_en_name(segments):
    parts = []
    for p in segments:
        p = p.strip()
        if not p:
            continue
        if re.search(r'\d', p):      # 含数字(如 4DLabel, 2026) 停止
            break
        if p.lower() in EN_STOP:
            break
        if re.fullmatch(r'[A-Za-z]+', p):
            parts.append(p)
        else:
            break
        if len(parts) >= 3:
            break
    return "_".join(parts) if parts else ""

def fallback_name(s):
    """主逻辑失败后的兜底：处理 简历/作品集/博士/中英文混合/英文名 等明显可提取的情况"""
    s = s.strip()
    m = re.match(r'^([\u4e00-\u9fff]+?)的?(中文)?简历$', s)
    if m: return m.group(1)
    m = re.match(r'^([\u4e00-\u9fff]+?)作品集', s)
    if m: return m.group(1)
    m = re.match(r'简历([\u4e00-\u9fff]{1,4})$', s)
    if m: return m.group(1)
    m = re.match(r'^(.+?)博士$', s)
    if m and re.search(r'[\u4e00-\u9fff]', m.group(1)): return m.group(1)
    m = re.match(r'^([\u4e00-\u9fff]{2,4})[A-Za-z]+$', s)        # 陈展彬Chris
    if m: return m.group(1)
    m = re.match(r'^[A-Za-z]+([\u4e00-\u9fff]{1,3})$', s)        # Sienna王
    if m: return s
    m = re.match(r'^[\u4e00-\u9fff]{1,2}[A-Za-z]+$', s)         # 黄Valley
    if m: return s
    m = re.match(r'^([A-Za-z]+)\.([A-Za-z]+)$', s)             # Jesse.Wu
    if m: return m.group(1) + "_" + m.group(2)
    m = re.match(r"^(.+?)['’]s\s*CV$", s, re.I)                # Chen's CV
    if m: return m.group(1)
    m = re.match(r'^([A-Za-z]+?)(\d+)?(reel|portfolio|share|demo)$', s, re.I)
    if m and m.group(1): return m.group(1)
    m = re.match(r'^([A-Za-z]+\.[A-Za-z]+)', s)                 # Jesse.Wu
    if m: return m.group(1).replace(".", "_")
    m = re.match(r'^[A-Za-z]+([\u4e00-\u9fff]{2,4})$', s)        # Jackie陈泽江
    if m: return m.group(1)
    return ""

def normalize_name(s, folder):
    """从文件名 base 提取「姓名」。返回 (name, conf, reason)。conf: high/review；name 为空表示无法提取。"""
    raw = s
    s = strip_prefixes(s)
    s = strip_suffixes(s)
    s = s.strip()
    if not s:
        return ("", "review", "提取后为空")

    # 开头长ID：ATCH2082..._姓名
    m = re.match(r'^([A-Za-z0-9]{10,})[-_](.*)$', s)
    if m:
        nm, conf, reason = normalize_name(m.group(2), folder)
        if nm:
            return (nm, "high" if conf == "high" else "review", reason + "(去ID前缀)")
        return ("", "review", "开头为长ID且后续无法提取")

    segs = [x for x in re.split(SPLIT_RE, s) if x.strip() != ""]
    if not segs:
        return ("", "review", f"无法切分: {raw!r}")

    first = segs[0].strip()

    # 姓名在前
    if is_cjk_name(first):
        return (first, "high", "中文姓名段(姓名在前)")
    if is_ascii_name(first) and not first_is_role(first, folder):
        en = build_en_name(segs)
        if en:
            return (en, "high", "英文名")

    # 可能是「职位/方向在前，姓名在后」
    if first_is_role(first, folder) or not (is_cjk_name(first) or (is_ascii_name(first) and not first_is_role(first, folder))):
        # 在后续段里找姓名
        for seg in segs[1:]:
            seg = seg.strip()
            if is_cjk_name(seg):
                return (seg, "high", "姓名在末尾(职位在前)")
        for seg in segs[1:]:
            seg = seg.strip()
            if is_ascii_name(seg) and not first_is_role(seg, folder):
                en = build_en_name(segs[segs.index(seg):])
                if en:
                    return (en, "high", "英文名在末尾(职位在前)")
        fb = fallback_name(s)
        if fb:
            return (fb, "review", f"兜底规则提取: {raw!r}")
        return ("", "review", f"职位在前但找不到姓名: {raw!r}")

    fb = fallback_name(s)
    if fb:
        return (fb, "review", f"兜底规则提取: {raw!r}")
    return ("", "review", f"无法识别姓名: {raw!r}")

def propose_rename(folder, filename):
    """给定类目文件夹名 folder 与文件名 filename，返回建议结果 dict。"""
    ext = os.path.splitext(filename)[1]
    if ext.lower() not in (".pdf", ".docx", ".doc"):
        return None
    base = os.path.splitext(filename)[0]
    # 已合规：文件名本身就是 姓名-方向 形式（方向==文件夹名，可带 _N 冲突标记）。
    # 命中即视为已整齐，直接 no-op，避免把 SLAM/VLA 等方向词误当姓名拼接，也不动 _2/_3 冲突文件。
    esc = re.escape(folder)
    if re.search(r'[-_]' + esc + r'(_\d+)?$', base, re.I):
        return {"folder": folder, "old": filename, "new": filename, "status": "noop",
                "conf": "high", "reason": "已符合 姓名-方向 规约"}
    name, conf, reason = normalize_name(base, folder)
    if not name:
        return {"folder": folder, "old": filename, "new": "", "status": "skip",
                "conf": "review", "reason": reason}
    new = f"{name}-{folder}{ext}"
    if new == filename:
        return {"folder": folder, "old": filename, "new": new, "status": "noop",
                "conf": conf, "reason": reason + " (已合规)"}
    return {"folder": folder, "old": filename, "new": new, "status": "rename",
            "conf": conf, "reason": reason}

# ---------- 目录扫描与执行 ----------

def scan(root):
    items = []
    for folder in sorted(os.listdir(root)):
        fpath = os.path.join(root, folder)
        if not os.path.isdir(fpath):
            continue
        for fn in sorted(os.listdir(fpath)):
            full = os.path.join(fpath, fn)
            if not os.path.isfile(full):
                continue
            p = propose_rename(folder, fn)
            if p:
                items.append(p)
    return items

def resolve_target(folder_path, new_name):
    """若目标名已存在，返回带 _2/_3 的不冲突名。"""
    if not os.path.exists(os.path.join(folder_path, new_name)):
        return new_name
    base, ext = os.path.splitext(new_name)
    i = 2
    while True:
        cand = f"{base}_{i}{ext}"
        if not os.path.exists(os.path.join(folder_path, cand)):
            return cand
        i += 1

def backup_root(root):
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(os.path.expanduser("~/.workbuddy/backups"),
                       f"rename_convention_backup_{ts}")
    shutil.copytree(root, dst)
    return dst

def run_apply(root, items):
    # 同文件夹目标名冲突预检（本次映射内部）
    from collections import defaultdict
    seen = defaultdict(list)
    for it in items:
        if it["status"] == "rename":
            seen[(it["folder"], it["new"])].append(it["old"])
    reverts = []
    done = 0
    for it in items:
        if it["status"] != "rename":
            continue
        folder_path = os.path.join(root, it["folder"])
        target = resolve_target(folder_path, it["new"])
        src = os.path.join(folder_path, it["old"])
        # 再次确认目标不是源本身
        if os.path.abspath(src) == os.path.abspath(os.path.join(folder_path, target)):
            continue
        os.rename(src, os.path.join(folder_path, target))
        reverts.append([it["folder"], target, it["old"]])
        done += 1
    return done, reverts

def main():
    ap = argparse.ArgumentParser(description="简历文件名统一为 姓名-方向.pdf", epilog=AUTHOR_EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=os.path.expanduser("~/Desktop/简历库"),
                    help="根目录（默认 ~/Desktop/简历库）")
    ap.add_argument("--apply", action="store_true", help="实际改名（默认仅预览）")
    ap.add_argument("--backup", action="store_true", help="--apply 前自动整机备份")
    args = ap.parse_args()

    root = os.path.expanduser(args.root)
    if not os.path.isdir(root):
        print(f"✗ 目录不存在: {root}")
        return

    items = scan(root)
    total = len(items)
    noop = sum(1 for i in items if i["status"] == "noop")
    rename = sum(1 for i in items if i["status"] == "rename")
    skip = sum(1 for i in items if i["status"] == "skip")
    review = sum(1 for i in items if i["conf"] == "review" and i["status"] == "rename")

    print(f"根目录: {root}")
    print(f"扫描文件: {total}  已合规(no-op): {noop}  将改名: {rename}  跳过(无法提取姓名): {skip}")
    if review:
        print(f"  ⚠ 其中需复核(兜底提取)的: {review} 个，改名前请确认预览")

    # 预览 CSV
    preview_csv = os.path.join(os.getcwd(), "rename_preview.csv")
    with open(preview_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["分类文件夹", "原文件名", "建议新名", "状态", "置信度", "说明"])
        for it in items:
            w.writerow([it["folder"], it["old"], it["new"] or "(保持原名)",
                        it["status"], it["conf"], it["reason"]])
    print(f"预览CSV: {preview_csv}")

    if not args.apply:
        print("\n（dry-run）未改动任何文件。确认无误后加 --apply 执行；可加 --backup 自动备份。")
        # 打印前若干条改名样例
        sample = [i for i in items if i["status"] == "rename"][:15]
        for it in sample:
            print(f"  {it['folder']}/  {it['old']}  ->  {it['new']}")
        return

    # --apply
    backup_dir = ""
    if args.backup:
        backup_dir = backup_root(root)
        print(f"✅ 已备份至: {backup_dir}")

    done, reverts = run_apply(root, items)
    revert_csv = os.path.join(os.getcwd(), "rename_revert.csv")
    with open(revert_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["分类文件夹", "改名后文件名", "原文件名"])
        w.writerows(reverts)
    print(f"✅ 实际改名: {done} 个（冲突自动加 _2/_3 避免覆盖）")
    print(f"回退映射: {revert_csv}")

if __name__ == "__main__":
    print(AUTHOR_EPILOG)
    main()
