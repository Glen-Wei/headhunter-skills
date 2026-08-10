"""
猎聘深度简历审查脚本 (liepin_deep_review.py)
=============================================
核心思路：不再依赖搜索结果卡片的截断文本，而是逐个打开候选人简历详情页，
提取【完整简历】后按 JD 维度深度评分，输出带证据的判定结论。

入口（三选一）：
  1. 直接搜索:  python liepin_deep_review.py --keywords "电主轴,末端执行器" [--limit 15]
  2. 指定简历:  python liepin_deep_review.py --cids "cid1,cid2"
  3. 复用搜索结果: python liepin_deep_review.py --from-json enhanced_all.json --top 15

通用参数:
  --jd-json <file>   JD维度配置JSON（缺省用内置"末端执行系统"配置）
  --max-age <n>      年龄上限（默认40）
  --output <prefix>  输出前缀（默认 liepin_deep）
  --resume           断点续跑（读取 progress.json）
  --limit <n>        最多审查人数（默认全部）

输出:
  <prefix>_results.json     每人完整简历文本 + 结构化字段 + 评分 + 证据
  <prefix>_report.md        判定报告（评分排名 + 匹配理由 + 疑虑点）
  progress.json             断点进度

Created & maintained by Glen Wei (韦其像) — https://github.com/Glen-Wei
Email: glen.keeming@gmail.com | WeChat: Glen_Wei88
Part of headhunter-skills: https://github.com/Glen-Wei/headhunter-skills"""
import sys, os, time, json, re, argparse, random, datetime
from browser_harness.helpers import list_tabs, cdp, switch_tab, new_tab, goto_url, close_tab, wait_for_load

AUTHOR_EPILOG = (
    "Author: Glen Wei (韦其像) | GitHub: https://github.com/Glen-Wei "
    "| Email: glen.keeming@gmail.com | WeChat: Glen_Wei88 | "
    "Part of headhunter-skills: https://github.com/Glen-Wei/headhunter-skills"
)

# ---------------------------------------------------------------- JD 配置
DEFAULT_JD = {
    "title": "资深机械设计工程师【末端执行系统方向】",
    "core": {   # 核心方向词: 权重(每处出现累计)
        "电主轴": 14, "主轴": 10, "末端执行器": 12, "末端执行机构": 12,
        "灵巧手": 12, "电动工具": 12, "打磨头": 10, "打磨": 6,
        "力控": 8, "恒力": 8, "柔顺": 8, "浮动执行器": 8, "执行机构": 6,
        "抓取": 4, "欠驱动": 4, "联动机构": 4,
    },
    "skills": {  # 技能词: 权重
        "ansys": 8, "abaqus": 8, "有限元": 5, "仿真": 3,
        "GD&T": 8, "公差": 6, "尺寸链": 6, "3DCS": 6,
        "solidworks": 3, "catia": 3, "ug": 3, "pro/e": 3, "creo": 3,
    },
    "industry": {"机器人": 4, "人形机器人": 5, "具身智能": 5, "自动化": 2,
                 "工业机器人": 5, "非标": 3, "医疗": 2, "机床": 4, "磨削": 4},
    "landing": ["量产", "落地", "工程化", "导入", "交付", "一次验证", "样机", "0-1", "从0到1", "上市"],
    "years_min": 8,
    "cities": ["上海", "苏州", "杭州", "南京", "无锡", "常州", "昆山"],  # 长三角加分
}

# 反向/疑虑信号（命中则记录，扣分并在报告标注）
WARN_PATTERNS = [
    ("学习中", "技能标注\"学习中\"（未达到熟练）", -3),
    ("非统招", "学历非统招", -4),
    ("维修", "偏维修/售后方向，非研发设计", -6),
    ("培训讲师", "偏培训/讲师", -5),
    ("语文教师", "求职意向偏离机械方向", -6),
]

def load_jd(path=None):
    if path and os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return DEFAULT_JD

# ---------------------------------------------------------------- 浏览器操作
def get_session():
    tabs = list_tabs()
    for t in tabs:
        if "h.liepin.com" in t.get("url", ""):
            switch_tab(t["targetId"])
            time.sleep(0.5)
            return True
    # 没有猎聘tab则新建
    new_tab("https://h.liepin.com/")
    time.sleep(3)
    return True

# 全局后台标签页（复用，避免每份简历都弹新标签打断用户）
_BG_TAB_ID = None
_BG_SID = None

def _bg_tab():
    """获取（或创建）后台标签页 session。background=True 不抢焦点，不打断用户。"""
    global _BG_TAB_ID, _BG_SID
    if _BG_SID:
        return _BG_SID
    try:
        tid = cdp("Target.createTarget", url="about:blank", background=True).get("targetId")
        _BG_TAB_ID = tid
        _BG_SID = cdp("Target.attachToTarget", targetId=tid, flatten=True).get("sessionId")
    except Exception:
        # 某些环境不支持 background 参数，退回普通创建
        tid = cdp("Target.createTarget", url="about:blank").get("targetId")
        _BG_TAB_ID = tid
        _BG_SID = cdp("Target.attachToTarget", targetId=tid, flatten=True).get("sessionId")
    return _BG_SID

def open_resume_text(cid, max_retry=2):
    """显式CDP控制：在后台标签页打开简历详情页 → 展开折叠区块 → 提取完整innerText。
    复用单个后台标签页（background=True），全程不抢焦点、不弹窗，不打断用户。"""
    url = f"https://h.liepin.com/resume/showresumedetail/?res_id_encode={cid}"
    for attempt in range(max_retry):
        try:
            sid = _bg_tab()
            cdp("Page.navigate", session_id=sid, url=url)
            # 等待页面加载完成
            for _ in range(40):
                try:
                    st = cdp("Runtime.evaluate", session_id=sid,
                             expression="document.readyState", returnByValue=True)
                    if st.get("result", {}).get("value") == "complete":
                        break
                except Exception:
                    pass
                time.sleep(0.5)
            time.sleep(random.uniform(2.5, 3.5))  # 等详情渲染
            # 展开所有折叠区块（"显示其他N段..."）
            for _ in range(4):
                r = cdp("Runtime.evaluate", session_id=sid, returnByValue=True, expression="""
                (function(){
                    var el = document.querySelector('.rd-info-other-link');
                    if (el && el.offsetParent !== null) { el.click(); return true; }
                    return false;
                })()""")
                if not r.get("result", {}).get("value"):
                    break
                time.sleep(1.2)
            time.sleep(0.8)
            r = cdp("Runtime.evaluate", session_id=sid, returnByValue=True,
                    expression="document.body.innerText || ''")
            text = r.get("result", {}).get("value") or ""
            # 有效简历判定：正文包含基本信息+工作经历/求职意向区块（短简历也接受）
            if len(text) > 800 and ('工作经历' in text or '求职意向' in text):
                return text
            # 可能加载失败/空白，刷新重试
            if attempt < max_retry - 1:
                time.sleep(2)
        except Exception as e:
            print(f"(attempt {attempt+1}: {type(e).__name__}: {e})")
            if attempt < max_retry - 1:
                time.sleep(2)
    return None

# ---------------------------------------------------------------- 解析
def clean_body(text):
    """去掉页面导航噪声，取"中文简历"为正文起点"""
    idx = text.find("中文简历")
    body = text[idx:] if idx >= 0 else text
    # 去掉底部版权/备案
    for marker in ["简历备注", "津ICP备"]:
        i = body.find(marker)
        if i > 0:
            body = body[:i]
    return body

def parse_basic(body):
    """基本信息: 姓名/性别/年龄/城市/学历/工作年数/当前职位/当前公司"""
    info = {}
    # 姓名: "查看大图\n杨**\n" 或首现 "X**"
    m = re.search(r'查看大图\n([\u4e00-\u9fa5]{1,4})\*{1,2}', body)
    if not m:
        m = re.search(r'([\u4e00-\u9fa5]{1,4})\*{1,2}', body)
    info['name'] = m.group(1) if m else "?"
    # 性别/年龄/城市/学历/年限: "男40岁东莞本科工作15年保密..."
    m = re.search(r'(男|女)(\d+)岁([\u4e00-\u9fa5A-Za-z\-]{1,12}?)(本科|硕士|博士|大专|高中|中专)(?:[统非]*)\s*(?:工作(\d+)年)?', body)
    if m:
        info['gender'] = m.group(1); info['age'] = int(m.group(2))
        info['city'] = m.group(3); info['edu'] = m.group(4)
        info['years'] = int(m.group(5) or 0)
    else:
        m2 = re.search(r'(男|女)(\d+)岁', body)
        if m2:
            info['gender'] = m2.group(1); info['age'] = int(m2.group(2))
        m3 = re.search(r'工作(\d+)年', body)
        if m3: info['years'] = int(m3.group(1))
        m4 = re.search(r'(本科|硕士|博士|大专)', body)
        if m4: info['edu'] = m4.group(1)
    # 当前职位/公司: "查看大图"到"立即沟通"之间；最后一行通常为"职位·公司"或"职位公司"
    m = re.search(r'查看大图\n(.*?)\n立即沟通', body, re.S)
    if m:
        header_lines = [l.strip() for l in m.group(1).split('\n') if l.strip()]
        # 最后一行一般是当前职位行（前面可能有活跃状态行/姓名/状态/基本信息行）
        if header_lines:
            cur = header_lines[-1]
            if '·' in cur:
                parts = cur.split('·')
                info['current_role'] = parts[0].strip()
                info['current_company'] = parts[1].strip()
            else:
                info['current_role'] = cur
                # 公司名通常带城市前缀（如"深圳市XX有限公司"）：从"市"往前回溯城市名起点
                ci = cur.rfind('市')
                if ci > 0:
                    start = ci - 1
                    if start >= 1 and cur[start-1] in '深上北广苏杭东佛成武南无昆宁甬锡通扬泰嘉绍温青济郑大天重西长厦珠中惠常':
                        start -= 1
                    cand = cur[start:]
                    if re.search(r'(股份有限公司|有限公司|集团|股份公司)$', cand):
                        info['current_company'] = cand
    return info

def parse_intent(body):
    """求职意向: 期望职位/薪资/城市/行业（取"求职意向"到"工作经历"之间）"""
    intent = {}
    m = re.search(r'\n求职意向\n(.*?)(?=\n工作经历\n|附件简历|$)', body, re.S)
    seg = m.group(1).strip() if m else ""
    lines = [l.strip() for l in seg.split('\n') if l.strip()]
    # 去掉导航/噪声行
    lines = [l for l in lines if not l.startswith(('对方近期沟通', '索要附件', '查看全部', '我们已参考'))]
    if not lines:
        return intent
    intent['position'] = lines[0]
    CITY_SET = set('上海 北京 深圳 广州 杭州 苏州 南京 东莞 佛山 无锡 常州 昆山 宁波 合肥 武汉 成都 重庆 天津 西安 长沙 厦门 珠海 中山 惠州 南通 扬州 泰州 嘉兴 绍兴 温州 青岛 济南 郑州 大连'.split())
    city_lines = []
    for l in lines[1:]:
        if re.search(r'\d+k', l, re.I):
            intent['salary'] = l
        elif '、' in l and len(l) < 40:
            intent['cities'] = l
        elif l in CITY_SET:
            city_lines.append(l)
        elif '索要' not in l and '全部行业' not in l:
            intent.setdefault('industry', l)
    if city_lines:
        intent['cities'] = intent.get('cities', '') + ('、'.join(city_lines) if not intent.get('cities') else '、' + '、'.join(city_lines))
    if 'industry' not in intent and '全部行业' in seg:
        intent['industry'] = '全部行业'
    return intent

def extract_sections(body):
    """按标题精确切块（\n标题\n 行首匹配，避免"工作经历内容"等干扰）"""
    sections = {}
    anchors = [('work', '工作经历'), ('project', '项目经历'), ('edu', '教育经历'),
               ('self_eval', '自我评价'), ('lang', '语言能力')]
    for key, title in anchors:
        idx = body.find(f"\n{title}\n")
        if idx < 0:
            idx = body.find(title)
        if idx >= 0:
            start = idx + len(title) + 1
            nxt = len(body)
            for _, t2 in anchors:
                j = body.find(f"\n{t2}\n", start)
                if 0 < j < nxt:
                    nxt = j
            sections[key] = body[start:nxt].strip()
    return sections

# ---------------------------------------------------------------- JD 评分
def jd_score(body, jd):
    """基于完整简历文本的JD评分，返回 (总分, 明细, 证据列表)"""
    low = body.lower()
    details = {}
    evidence = []
    total = 0

    # 核心方向（每个词最多累计2次，避免长文本重复词刷分）
    for kw, w in jd['core'].items():
        cnt = low.count(kw.lower())
        if cnt:
            gain = w + min(cnt - 1, 1) * (w // 2)   # 出现2次内追加半权重，之后封顶
            total += gain
            details[f'core:{kw}'] = gain
            # 收集证据（每个词最多2条上下文）
            n = 0
            for mm in re.finditer(re.escape(kw), low, re.I):
                s = max(0, mm.start() - 40); e = min(len(low), mm.end() + 60)
                snippet = body[s:e].replace('\n', ' ').strip()
                evidence.append((kw, snippet))
                n += 1
                if n >= 2:
                    break
    # 技能
    for kw, w in jd['skills'].items():
        if kw.lower() in low:
            gain = w
            # 若标注"学习中"扣半
            for mm in re.finditer(re.escape(kw), low, re.I):
                ctx = low[max(0, mm.start()-20):mm.end()+20]
                if '学习' in ctx:
                    gain = max(1, w // 2)
                    evidence.append((kw, body[max(0,mm.start()-40):mm.end()+60].replace('\n',' ').strip() + " [⚠学习中]"))
                    break
            total += gain
            details[f'skill:{kw}'] = gain
    # 行业
    for kw, w in jd['industry'].items():
        if kw in body:
            total += w
            details[f'industry:{kw}'] = w
    # 落地证据
    land_cnt = 0
    for w in jd['landing']:
        if w in body:
            land_cnt += 1
    total += min(land_cnt, 6) * 3
    if land_cnt: details['landing'] = min(land_cnt, 6) * 3
    # 年限
    years = parse_basic(body).get('years', 0)
    if years >= jd['years_min']:
        total += 6; details['years'] = 6
    elif years >= jd['years_min'] - 2:
        total += 3; details['years'] = 3
    # 学历
    edu_txt = body
    is_tongzhao = '统招' in edu_txt
    mech_major = any(x in edu_txt for x in ['机械', '机电', '车辆', '材料', '自动化', '机器人'])
    if '硕士' in edu_txt: total += 3; details['edu_master'] = 3
    elif '博士' in edu_txt: total += 4; details['edu_phd'] = 4
    if is_tongzhao and ('本科' in edu_txt or '硕士' in edu_txt or '博士' in edu_txt):
        total += 3; details['edu_tongzhao'] = 3
    if mech_major:
        total += 2; details['edu_mech'] = 2
    # 长三角
    city_hit = [c for c in jd['cities'] if c in body[:2000]]
    if city_hit:
        total += 3; details['city'] = 3
    # 可谈性
    if '在职' in body and ('看看新机会' in body or '看机会' in body):
        total += 3; details['open_to_move'] = 3

    # 反向信号
    warnings = []
    for pat, msg, penalty in WARN_PATTERNS:
        if pat in body:
            total += penalty
            warnings.append(msg)
            details[f'warn:{pat}'] = penalty

    total = max(0, min(100, total))  # 归一化 0-100
    return total, details, evidence, warnings

def verdict(score):
    if score >= 60: return 'A 强匹配'
    if score >= 40: return 'B 中匹配'
    return 'C 弱匹配'

# ---------------------------------------------------------------- JD 硬性要求检查
EDU_RANK = {'大专': 1, '本科': 2, '硕士': 3, '博士': 4}

def check_hard_requirements(body, basic, jd):
    """根据 JD 的 hard 配置做硬性筛选，返回不满足项列表（空=全部通过）。
    支持: exclude / min_edu / tongzhao / min_years / core_skills_any / landing_min / current_role_keywords
    """
    hard = jd.get('hard', {})
    fails = []
    low = body.lower()

    # 0. 反向排除（命中任一即排除）——如热门赛道标签
    exclude = hard.get('exclude', [])
    if exclude:
        hit_ex = [w for w in exclude if w.lower() in low]
        if hit_ex:
            fails.append(f"命中排除标签({'/'.join(hit_ex[:3])})")

    # 0.5 当前职位必须是设计岗（最近一段工作经历做机械设计）
    role_kw = hard.get('current_role_keywords')
    if role_kw:
        cur_role = basic.get('current_role') or ''
        if cur_role:
            if not any(k in cur_role for k in role_kw):
                fails.append(f"当前职位非设计岗({cur_role[:16]})")
        else:
            # 解析不出职位时，从简历文本找设计岗信号（工作经历/自我评价中的"机械设计"）
            design_signal = any(k in body for k in role_kw)
            if not design_signal:
                fails.append("无机械设计岗位证据")

    # 1. 学历下限
    min_edu = hard.get('min_edu')
    if min_edu:
        edu = basic.get('edu', '')
        cand_rank = EDU_RANK.get(edu, 0)
        if cand_rank < EDU_RANK.get(min_edu, 0):
            fails.append(f"学历不符({edu or '未知'}<{min_edu})")

    # 2. 统招要求
    if hard.get('tongzhao') and ('非统招' in body or '非全日制' in body):
        fails.append("非统招/非全日制")

    # 3. 工作年限下限
    min_years = hard.get('min_years')
    if min_years:
        years = basic.get('years') or 0
        if years < min_years:
            fails.append(f"年限不足({years}年<{min_years}年)")

    # 4. 必备方向词（至少命中其一）
    core_any = hard.get('core_skills_any')
    if core_any:
        hit = [w for w in core_any if w.lower() in low]
        if not hit:
            fails.append(f"无必备方向经验({'/'.join(core_any[:3])}等)")

    # 5. 落地/量产证据最低数量
    landing_min = hard.get('landing_min')
    if landing_min:
        land_words = jd.get('landing', ['量产', '落地', '工程化', '导入', '交付', '验证', '样机', '上市'])
        cnt = sum(1 for w in land_words if w in body)
        if cnt < landing_min:
            fails.append(f"落地/量产证据不足({cnt}<{landing_min})")

    return fails

# ---------------------------------------------------------------- 主流程
def collect_candidates(args):
    """返回候选 cid 列表（按给定顺序）"""
    if args.cids:
        return [c.strip() for c in args.cids.split(',') if c.strip()]
    if args.cids_file:
        with open(args.cids_file, encoding='utf-8') as f:
            content = f.read().replace('\n', ',')
        return [c.strip() for c in content.split(',') if c.strip()]
    if args.from_json:
        with open(args.from_json, encoding='utf-8') as f:
            data = json.load(f)
        data.sort(key=lambda x: -x.get('score', 0))
        cids = [d['cid'] for d in data if d.get('age', 99) <= args.max_age]
        return cids[:args.top] if args.top else cids
    # 搜索
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from liepin_search import search_keyword, connect
    sid = connect()
    if not sid:
        print("ERROR: 未找到猎聘页面"); sys.exit(1)
    all_raw = []
    # 前置筛选参数（在猎聘页面设置，减少无效候选人）
    pre_filters = {}
    if args.pre_max_age: pre_filters['max_age'] = args.pre_max_age
    if args.pre_min_years: pre_filters['min_years'] = args.pre_min_years
    if args.pre_min_edu: pre_filters['min_edu'] = args.pre_min_edu
    if args.pre_city: pre_filters['city'] = args.pre_city
    if args.pre_gender: pre_filters['gender'] = args.pre_gender
    for kw in args.keywords.split(','):
        kw = kw.strip()
        print(f"搜索: {kw}")
        try:
            data = search_keyword(kw, sid, filters=pre_filters or None)
            all_raw.extend(data)
            print(f"  -> {len(data)}")
        except Exception as e:
            print(f"  搜索失败: {e}")
    seen, uniq = set(), []
    for d in all_raw:
        if d['cid'] not in seen:
            seen.add(d['cid']); uniq.append(d['cid'])
    return uniq[:args.top] if args.top else uniq

def main():
    ap = argparse.ArgumentParser(description='猎聘深度简历审查', epilog=AUTHOR_EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--keywords', help='搜索关键词(逗号分隔)')
    ap.add_argument('--cids', help='直接审查指定简历cid(逗号分隔)')
    ap.add_argument('--cids-file', help='从文件读取cid列表（每行一个或逗号分隔）')
    ap.add_argument('--from-json', help='复用之前搜索结果JSON')
    ap.add_argument('--top', type=int, default=0, help='最多取前N个')
    ap.add_argument('--max-age', type=int, default=40)
    ap.add_argument('--jd-json', help='JD维度配置')
    ap.add_argument('--output', default='liepin_deep')
    ap.add_argument('--resume', action='store_true', help='断点续跑')
    ap.add_argument('--limit', type=int, default=0, help='最多审查人数')
    ap.add_argument('--city', help='硬性城市条件（如 上海），命中求职意向/现居任一即通过')
    ap.add_argument('--gender', help='硬性别条件（男/女）')
    # 前置筛选（在猎聘搜索页直接设置，从源头过滤）
    ap.add_argument('--pre-max-age', type=int, help='前置筛选: 年龄上限')
    ap.add_argument('--pre-min-years', type=int, help='前置筛选: 工作年限下限')
    ap.add_argument('--pre-min-edu', choices=['本科','硕士','博士'], help='前置筛选: 学历下限')
    ap.add_argument('--pre-city', help='前置筛选: 期望城市（如 上海）')
    ap.add_argument('--pre-gender', choices=['男','女'], help='前置筛选: 性别')
    args = ap.parse_args()

    if not (args.keywords or args.cids or args.cids_file or args.from_json):
        print("必须提供 --keywords / --cids / --cids-file / --from-json 之一"); sys.exit(1)

    jd = load_jd(args.jd_json)
    cids = collect_candidates(args)
    print(f"待审查候选人: {len(cids)} 人")

    if not get_session():
        print("ERROR: 无法连接浏览器"); sys.exit(1)

    progress_file = 'progress.json'
    done = {}
    if args.resume and os.path.exists(progress_file):
        done = json.load(open(progress_file, encoding='utf-8'))
        print(f"断点续跑，已完成 {len(done)} 人")

    # 断点续跑时，把之前完成的完整记录合并进结果（旧版精简记录视为未完成，重新处理）
    results = []
    for cid in cids:
        rec = done.get(cid)
        if rec and rec.get('status') == 'ok' and all(k in rec for k in ('score', 'age', 'name', 'link')):
            results.append(rec)
    todo = [c for c in cids if not (done.get(c) and done.get(c).get('status') == 'ok'
            and all(k in done[c] for k in ('score', 'age', 'name', 'link')))]
    if args.limit and len(todo) > args.limit:
        todo = todo[:args.limit]
    print(f"本次审查 {len(todo)} 人")

    for i, cid in enumerate(todo):
        print(f"[{i+1}/{len(todo)}] 打开简历 {cid} ...", end=' ', flush=True)
        text = open_resume_text(cid)
        if not text:
            print("❌ 提取失败")
            done[cid] = {"status": "failed"}
            json.dump(done, open(progress_file, 'w', encoding='utf-8'), ensure_ascii=False)
            continue
        body = clean_body(text)
        basic = parse_basic(body)
        intent = parse_intent(body)
        sections = extract_sections(body)
        score, details, evidence, warnings = jd_score(body, jd)

        rec = {
            'cid': cid, 'name': basic.get('name', '?'),
            'age': basic.get('age', '?'), 'gender': basic.get('gender', ''),
            'city': basic.get('city', ''), 'edu': basic.get('edu', ''),
            'years': basic.get('years', 0),
            'current_role': basic.get('current_role', ''),
            'current_company': basic.get('current_company', ''),
            'intent': intent, 'score': score, 'verdict': verdict(score),
            'details': details, 'warnings': warnings,
            'work_history': sections.get('work', '')[:1500],
            'project_history': sections.get('project', '')[:2000],
            'self_eval': sections.get('self_eval', '')[:1200],
            'link': f"https://h.liepin.com/resume/showresumedetail/?res_id_encode={cid}",
        }
        # 证据去重（同词保留前2条）
        seen_ev = {}
        for kw, snip in evidence:
            seen_ev.setdefault(kw, []).append(snip)
        rec['evidence'] = {k: v[:2] for k, v in seen_ev.items()}
        rec['status'] = 'ok'  # 断点续跑合并判定用

        # 硬性条件筛选（年龄 / 性别 / 城市 / JD硬性要求）
        rejects = []
        if args.max_age < 99:
            age_v = rec['age'] if isinstance(rec['age'], int) else 99
            if age_v > args.max_age:
                rejects.append(f"超龄{age_v}岁")
        if args.gender and rec.get('gender') and rec['gender'] != args.gender:
            rejects.append(f"性别不符({rec.get('gender')})")
        if args.city:
            city_hit = args.city in (rec.get('city') or '')
            intent_city_hit = args.city in json.dumps(rec.get('intent', {}), ensure_ascii=False)
            if not (city_hit or intent_city_hit):
                rejects.append(f"城市不符({rec.get('city','')})")
        # JD 硬性要求（学历/统招/年限/必备技能/落地证据）—— 从 JD JSON 的 hard 字段解析
        jd_hard_fails = check_hard_requirements(body, basic, jd)
        rejects.extend(jd_hard_fails)
        rec['jd_hard'] = jd_hard_fails
        rec['reject'] = rejects
        if rejects:
            print(f"   ✗ 排除: {';'.join(rejects)}")

        results.append(rec)
        done[cid] = rec  # 存完整记录，供断点续跑合并
        json.dump(done, open(progress_file, 'w', encoding='utf-8'), ensure_ascii=False)

        print(f"✅ {basic.get('name','?')} {basic.get('age','?')}岁 得分{score} {verdict(score)}")
        # 节奏控制
        if (i + 1) % 8 == 0:
            print("  ...暂停6秒...")
            time.sleep(6)
        else:
            time.sleep(random.uniform(1.0, 2.0))

    results.sort(key=lambda x: -x['score'])
    out_json = f"{args.output}_results.json"
    json.dump(results, open(out_json, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f"\n✅ 已保存: {out_json}")

    # 生成报告：只列出通过硬性筛选的候选人，数量不限
    passed = [r for r in results if not r.get('reject')]
    rejected = [r for r in results if r.get('reject')]
    from pathlib import Path
    md = Path(f"{args.output}_report.md")
    lines = ["# 猎聘深度简历审查报告", "",
             f"**JD:** {jd.get('title','')}",
             f"**硬性条件:** 年龄≤{args.max_age}岁" + (f" | 城市:{args.city}" if args.city else "") + (f" | 性别:{args.gender}" if args.gender else ""),
             f"**JD硬性要求:** {json.dumps(jd.get('hard',{}), ensure_ascii=False)}",
             f"**审查人数:** {len(results)}（通过 {len(passed)} / 排除 {len(rejected)}）",
             f"**审查时间:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}", "",
             "| # | 姓名 | 年龄 | 学历 | 城市 | 年限 | 当前职位/公司 | 得分 | 判定 | 📎直达链接 |",
             "|---|------|:---:|:---:|:---:|:---:|--------------|:---:|:---:|----------|"]
    for i, r in enumerate(passed):
        cur = f"{r.get('current_role','')}@{r.get('current_company','')}"[:26]
        lines.append(f"| {i+1} | {r['name']} | {r['age']} | {r['edu']} | {r['city']} | {r['years']}年 | {cur} | {r['score']} | {r['verdict']} | [👉打开]({r['link']}) |")
    lines.append("")
    for i, r in enumerate(passed):
        lines += ["---", f"### {i+1}. {r['name']}（{r['age']}岁 | {r['edu']} | {r['city']} | {r['years']}年）",
                  f"**判定:** {r['verdict']}（得分 {r['score']}）",
                  f"**当前:** {r.get('current_role','')} @ {r.get('current_company','')}",
                  f"**求职意向:** {json.dumps(r.get('intent',{}), ensure_ascii=False)}",
                  f"**直达链接:** [打开]({r['link']})"]
        if r['evidence']:
            lines.append("**匹配证据:**")
            for kw, snips in list(r['evidence'].items())[:4]:
                lines.append(f"- `{kw}` → " + " | ".join(s[:70] for s in snips[:1]))
        if r['warnings']:
            lines.append(f"**⚠ 疑虑:** {'；'.join(r['warnings'])}")
        lines.append("")
    if rejected:
        lines += ["---", "## 被硬性条件排除（仅供参考）", ""]
        for r in rejected:
            lines.append(f"- {r['name']} {r['age']}岁 {r.get('city','')} {r.get('gender','')} — {';'.join(r['reject'])}（{r['score']}分）")
    md.write_text("\n".join(lines), encoding='utf-8')
    print(f"✅ 已保存: {md}")

if __name__ == '__main__':
    main()
