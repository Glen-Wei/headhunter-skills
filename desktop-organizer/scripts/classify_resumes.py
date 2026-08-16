#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""简历职位分类预演/合并脚本 v4

用法:
    classify_resumes.py <目录...> --out report.json          预演（不移动）
    classify_resumes.py <目录...> --apply --target <根目录>  实际合并

流程（判断方向 → 统一命名 → 归类，一步完成）：
    1. 按文件名解析职位关键词，归一化为职位类目（= 判断方向）；
    2. 移动落盘时按「姓名-方向.pdf」规约命名（复用 rename_to_convention.propose_rename，
       方向 = 目标类目文件夹名；无法提取姓名的保持原名并计入汇报）；
    3. 移入 ~/Desktop/简历库/<类目>/；重复文件（同名同大小）移至「_待确认重复/」；
       非简历资料（xlsx/xmind等）移至根目录。

Created & maintained by Glen Wei (韦其像) — https://github.com/Glen-Wei
Email: glen.keeming@gmail.com | WeChat: Glen_Wei88
Part of headhunter-skills: https://github.com/Glen-Wei/headhunter-skills"""
import os, re, sys, json, hashlib, shutil

AUTHOR_EPILOG = (
    "Author: Glen Wei (韦其像) | GitHub: https://github.com/Glen-Wei "
    "| Email: glen.keeming@gmail.com | WeChat: Glen_Wei88 | "
    "Part of headhunter-skills: https://github.com/Glen-Wei/headhunter-skills"
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rename_to_convention import propose_rename

# 职位关键词 → 标准类目（顺序敏感，长的优先；中文与英文缩写粘连时 \b 会失效，缩写直接子串匹配）
RULES = [
    (r"3dgs|3D[_-]?算法|三维重建|重建算法|3D[_-]?场景|3D:4D|3D/4D|点云|NeRF|Gaussian|渲染引擎|3D$|3d$", "3D重建与算法"),
    (r"灵巧操作|灵巧手", "灵巧手"),
    (r"技术美术|TA$|TA[-_ ]|作品集|3d资产|设计师", "技术美术"),
    (r"PR专家|PR$|PR[-_ ]|公关|媒介|舆情|党央媒|新华社", "公关PR"),
    (r"强化学习|运控|具身算法|强化", "强化学习运控"),
    (r"机器人部署|部署落地", "机器人部署"),
    (r"机器人运维测试|运维测试|测试开发|测试负责人|测试lead|测试$", "测试"),
    (r"PMO|CPM|PM$|PM[-_ ]|TPM|项目经理|项目负责人|产品经理|项目交付|技术产品|产品技术", "项目经理"),
    (r"供应链", "供应链"),
    (r"NPI|量产|工艺|可靠性|质量", "量产与工艺"),
    (r"嵌入式|嵌软", "嵌入式"),
    (r"机械设计|结构工程师|结构设计|结构负责人|机械$", "机械设计"),
    (r"SLAM专家|SLAM$|SLAM[-_ ]|定位建图|激光", "SLAM"),
    (r"VLA算法|VLA$|VLA[-_ ]|视觉语言|VLM|视频理解|视频生成", "VLA"),
    (r"LLM|大模型|NLP|语言模型|AIGC|基模|基础模型", "LLM大模型"),
    (r"仿真", "仿真"),
    (r"多模态", "多模态"),
    (r"自动驾驶|自驾", "自动驾驶"),
    (r"视觉感知|感知算法|端到端感知|视觉算法|动捕|DLO", "感知与运动"),
    (r"控制算法|控制规划|控制器|运动规划|运动控制|规划控制", "控制规划"),
    (r"位姿估计|姿态估计|抓取|人体姿态|运动建模", "感知与运动"),
    (r"世界模型|world[ -]?model", "世界模型"),
    (r"数据|标注|清洗|数采", "数据"),
    (r"解决方案|售前|方案", "解决方案"),
    (r"战略|生态|拓展|合作|KA|高校业务|交付负责人|事业部", "战略生态"),
    (r"商业|商务|BD|销售|市场|品牌", "商业运营"),
    (r"运营", "运营"),
    (r"评测", "评测"),
    (r"Agent|智能体", "Agent"),
    (r"研究员", "具身研究员"),
    (r"算法工程师|算法专家|算法负责人|算法$|算法[-_ ]", "算法"),
    (r"Momenta|百度|阿里|华为|腾讯|字节|智元", "大厂算法"),
    (r"硬件|电子", "硬件"),
    (r"软件|全栈|后端|前端|开发", "软件开发"),
    (r"CEO|CTO|创始人|合伙人|VP|首席|总裁|executive|助理", "高管"),
    (r"导师|教授|博士|科学家", "学术研究"),
    (r"SRE|云原生|Infra|基础设施|工具链|运维", "基础设施SRE"),
    (r"信息安全|AI安全|安全管理|安全工程师|安全$", "信息安全"),
    (r"机器人|机械臂", "机器人"),
]

# 脚本类目名 → 具身现有方向类目 映射（合并进既有文件夹）
CATEGORY_MAP = {
    "LLM大模型": "LLM",
    "强化学习运控": "强化学习",
    "商业运营": "商业管理",
}

STRIP_PREFIX = re.compile(r"^ATCH\d+[_-]?")
CAREER_HINT = re.compile(r"工程师|负责人|经理|专家|总监|主管|顾问|研究员|算法|设计|师$|员$|Lead|leader|\bPM\b|\bPR\b|\bTA\b|\bVP\b|\bCEO\b|\bCTO\b|技术|运营|销售|市场|开发|硬件|软件|结构|算法|仿真|测试|数据|战略|生态|商务|供应链|嵌入式|总监|总裁|首席|博士后")

# 简历文件名常以「-机构/公司品牌名」结尾（如「姓名-职位-XX公司.pdf」），归类前剥离末尾品牌后缀。
# 词表按使用者业务自行配置（匹配时自动忽略大小写），无需修改其它代码。
BRAND_SUFFIXES = []  # 例如 ["XX招聘", "TalentCo", "Agency"]，留空则跳过品牌后缀剥离
_BRAND_RE = re.compile(r"[-_ ]*(?:" + "|".join(map(re.escape, BRAND_SUFFIXES)) + r")\d*$", flags=re.I)

def clean_name(filename):
    name = os.path.splitext(filename)[0]
    name = STRIP_PREFIX.sub("", name)
    if BRAND_SUFFIXES:
        name = _BRAND_RE.sub("", name)
    name = re.sub(r"[-_]*\d{2,}$", "", name)
    name = re.sub(r"[（(].*?[)）]", "", name)
    name = re.sub(r"[-_]{2,}", "-", name)
    return name.strip(" -_")

def classify(filename):
    name = clean_name(filename)
    for pattern, cat in RULES:
        if re.search(pattern, name, flags=re.I):
            return cat
    parts = re.split(r"[-_]", name)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) >= 2:
        first, rest = parts[0], parts[1]
        # 「职位-姓名」反向
        if CAREER_HINT.search(first):
            for pattern, cat in RULES:
                if re.search(pattern, first, flags=re.I):
                    return cat
            return first[:14]
        # 「姓名-职位」正向
        if CAREER_HINT.search(rest):
            for pattern, cat in RULES:
                if re.search(pattern, rest, flags=re.I):
                    return cat
            return rest[:14]
    return "未分类"

def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def scan(dirs, dedup_target=None):
    results, seen = {}, {}
    if dedup_target:
        for root, _, files in os.walk(dedup_target):
            for f in files:
                if f.startswith("~$") or f == ".DS_Store":
                    continue
                p = os.path.join(root, f)
                seen[(f, os.path.getsize(p))] = p
    for d in dirs:
        for root, _, files in os.walk(d):
            for f in files:
                if f.startswith("~$") or f == ".DS_Store":
                    continue
                ext = os.path.splitext(f)[1].lower()
                path = os.path.join(root, f)
                if ext in (".xlsx", ".xls", ".xmind", ".csv") or "联系方式" in f:
                    results.setdefault("__非简历__", []).append({"file": f, "from": root})
                    continue
                cat = classify(f)
                key = (f, os.path.getsize(path))
                if key in seen:
                    results.setdefault("__重复__", []).append({"file": f, "from": root, "dup_of": seen[key]})
                    continue
                seen[key] = path
                p = propose_rename(CATEGORY_MAP.get(cat, cat), f) if not cat.startswith("__") else None
                new = p["new"] if (p and p["status"] in ("rename", "noop") and p["new"]) else None
                results.setdefault(cat, []).append({"file": f, "from": root, "new": new})
    return results

def apply_moves(results, target_root):
    moved = renamed = 0
    for cat, items in results.items():
        if cat == "__非简历__":
            dest = target_root
        elif cat == "__重复__":
            dest = os.path.join(target_root, "_待确认重复")
        else:
            dest = os.path.join(target_root, CATEGORY_MAP.get(cat, cat))
        os.makedirs(dest, exist_ok=True)
        for it in items:
            src = os.path.join(it["from"], it["file"])
            newname = it["file"]
            if not cat.startswith("__"):
                # 简历：判断方向(类目)后，按 姓名-方向 规约命名再落盘（先命名后归类）
                p = propose_rename(CATEGORY_MAP.get(cat, cat), it["file"])
                if p and p["status"] in ("rename", "noop") and p["new"]:
                    newname = p["new"]
                    if newname != it["file"]:
                        renamed += 1
                # skip（无法提取姓名）保持原名，汇报时列入待人工处理
            dst = os.path.join(dest, newname)
            if os.path.exists(dst):
                base, ext = os.path.splitext(newname)
                dst = os.path.join(dest, f"{base}_2{ext}")
            shutil.move(src, dst)
            moved += 1
    return moved, renamed

def main():
    args, opts = [], {}
    i = 1
    while i < len(sys.argv):
        a = sys.argv[i]
        if a.startswith("--"):
            if i + 1 < len(sys.argv) and not sys.argv[i + 1].startswith("--"):
                opts[a[2:]] = sys.argv[i + 1]
                i += 2
            else:
                opts[a[2:]] = True
                i += 1
        else:
            args.append(a)
            i += 1
    apply_move = "--apply" in sys.argv or opts.get("apply")
    out = opts.get("out")
    target = opts.get("target")
    dedup = opts.get("dedup-target")
    if not args:
        print(__doc__); return
    results = scan(args, dedup_target=dedup)
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(results, fh, ensure_ascii=False, indent=1)
    order = sorted(results.items(), key=lambda kv: (kv[0].startswith("__"), -len(kv[1])))
    for c, items in order:
        tag = "资料/重复" if c.startswith("__") else "职位类目"
        print(f"[{c}] {len(items)}  ({tag})")
        for it in items[:5]:
            dup = f"  ⚠重复→{it['dup_of']}" if "dup_of" in it else ""
            nn = f"  → 新名: {it['new']}" if it.get("new") else ""
            print(f"   {it['file']}{dup}{nn}")
        if len(items) > 5:
            print(f"   ... 共 {len(items)} 个")
    total = sum(len(v) for k, v in results.items() if not k.startswith("__"))
    print(f"\n# 简历 {total} 份 / 类目 {sum(1 for k in results if not k.startswith('__'))} 个 / 重复 {len(results.get('__重复__', []))} / 非简历 {len(results.get('__非简历__', []))}")
    if apply_move:
        assert target, "--target 必填"
        n, rn = apply_moves(results, target)
        print(f"✔ 已移动 {n} 个文件到 {target}（其中按「姓名-方向」规约重命名 {rn} 个）")

if __name__ == "__main__":
    print(AUTHOR_EPILOG)
    main()
