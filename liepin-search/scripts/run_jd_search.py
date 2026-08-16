"""
猎聘一键JD搜索 (run_jd_search.py)
================================
【发JD → 出结果】一键入口：读取JD → 自动解析硬性要求 → 猎聘前置筛选 →
多关键词搜索 → 逐个简历深度审查 → 硬过滤+评分 → 输出报告+直达链接。

用法:
  python run_jd_search.py "<JD文件路径>" [--limit 30] [--max-age 35] [--city 上海] [--gender 男]
  可选覆盖: --max-age/--min-years/--min-edu/--city/--gender（默认从JD自动解析）

输出:
  <JD名>_report.md   最终名单（按合适度排序，含直达链接）
  <JD名>_results.json 每人完整简历+评分明细
"""
import sys, os, subprocess, json, argparse, time

SKILL = os.path.dirname(os.path.abspath(__file__))

def parse_jd(jd_file):
    """调用 parse_jd.py 生成 jd.json"""
    jd_json = os.path.splitext(jd_file)[0] + '_jd.json'
    r = subprocess.run(
        [sys.executable, os.path.join(SKILL, 'parse_jd.py'), jd_file, '-o', jd_json],
        capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(jd_json):
        print("❌ JD解析失败:", r.stderr[-500:])
        sys.exit(1)
    with open(jd_json, encoding='utf-8') as f:
        return json.load(f), jd_json

def build_keywords(jd, base=None):
    """基于JD核心方向词生成搜索关键词（6组）"""
    core = list(jd.get('core', {}).keys())
    if not core:
        core = ['机器人', '机械设计']
    # 优先取高权重方向词
    core_sorted = sorted(jd.get('core', {}).items(), key=lambda x: -x[1])
    top = [w for w, _ in core_sorted[:4]]
    keywords = base or []
    for i in range(0, len(top), 2):
        pair = ' '.join(top[i:i+2])
        if pair and pair not in keywords:
            keywords.append(pair)
    # 兜底关键词
    for kw in ['机械设计 工程师', '结构设计 机器人', '资深 机械 设计']:
        if kw not in keywords:
            keywords.append(kw)
    return ','.join(keywords[:6])

def main():
    ap = argparse.ArgumentParser(description='猎聘一键JD搜索')
    ap.add_argument('jd_file', help='JD文件路径 (docx/pdf/txt)')
    ap.add_argument('--limit', type=int, default=20, help='最多深度审查人数（分批，默认20）')
    ap.add_argument('--pages', type=int, default=1, help='每关键词搜索翻页数（每页约20人，默认1页）')
    ap.add_argument('--max-age', type=int, help='覆盖年龄上限')
    ap.add_argument('--min-years', type=int, help='覆盖工作年限下限')
    ap.add_argument('--min-edu', choices=['本科','硕士','博士'], help='覆盖学历下限')
    ap.add_argument('--city', help='覆盖城市（如 上海）')
    ap.add_argument('--gender', choices=['男','女'], help='覆盖性别')
    ap.add_argument('--keywords', help='覆盖搜索关键词（逗号分隔）')
    args = ap.parse_args()

    # 1. 解析JD
    print("="*60)
    print("📄 步骤1/6: 解析JD硬性要求")
    print("="*60)
    jd, jd_json = parse_jd(args.jd_file)
    hard = jd.get('hard', {})
    print(f"  JD: {jd.get('title','')}")
    print(f"  硬性要求: {json.dumps(hard, ensure_ascii=False)}")

    # 2. 合并覆盖参数
    max_age = args.max_age or 40
    min_years = args.min_years or hard.get('min_years')
    min_edu = args.min_edu or hard.get('min_edu')
    city = args.city or jd.get('location', '')[:2] if jd.get('location') else None
    gender = args.gender
    # location 如 "上海徐汇" 取前2字
    if not city and jd.get('location'):
        loc = jd['location'].strip()
        city = loc[:2] if loc and len(loc) >= 2 else None

    print(f"\n  生效筛选: 年龄≤{max_age}" + (f" | 年限≥{min_years}" if min_years else "") +
          (f" | 学历≥{min_edu}" if min_edu else "") + (f" | 城市:{city}" if city else "") +
          (f" | 性别:{gender}" if gender else ""))

    # 3. 生成关键词
    keywords = args.keywords or build_keywords(jd)
    print(f"\n  搜索关键词: {keywords}")

    # 4. 执行深度审查
    print("\n" + "="*60)
    print("🔍 步骤2/6: 猎聘前置筛选 + 搜索")
    print("="*60)
    out_prefix = os.path.join(os.getcwd(), os.path.splitext(os.path.basename(args.jd_file))[0] + '_猎聘名单')
    cmd = [sys.executable, os.path.join(SKILL, 'liepin_deep_review.py'),
           '--keywords', keywords,
           '--jd-json', jd_json,
           '--max-age', str(max_age),
           '--limit', str(args.limit),
           '--pages', str(args.pages),
           '--output', out_prefix]
    if city: cmd += ['--city', city]
    if gender: cmd += ['--gender', gender]
    if min_years: cmd += ['--pre-min-years', str(min_years)]
    if min_edu: cmd += ['--pre-min-edu', min_edu]
    if max_age: cmd += ['--pre-max-age', str(max_age)]
    if city: cmd += ['--pre-city', city]
    if gender: cmd += ['--pre-gender', gender]

    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout[-3000:])
    if r.returncode != 0:
        print("❌ 深度审查失败:", r.stderr[-500:])
        sys.exit(1)

    print("\n" + "="*60)
    print("✅ 完成！最终报告:")
    print("="*60)
    print(f"  {out_prefix}_report.md")
    print(f"  {out_prefix}_results.json")
    print("\n💡 提示: 人数不足或想全量审查，加 --limit 100 重跑即可（支持 --resume 续跑）")

if __name__ == '__main__':
    main()
