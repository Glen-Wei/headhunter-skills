"""
猎聘超级搜索脚本 - 批量搜索、提取、评分候选人
用法: python liepin_search.py -k "关键词1,关键词2,关键词3" [--output <文件>]
"""
import sys, time, json, re, argparse
# browser-harness should be pip installed - no manual path needed
from browser_harness.helpers import list_tabs, cdp

def js(expr, sid=None):
    r = cdp("Runtime.evaluate", session_id=sid, expression=expr, returnByValue=True, awaitPromise=False)
    return r.get("result",{}).get("value")

def wait_for(sid, expr, timeout=12, interval=0.3):
    """轮询等待 JS 表达式返回真值（DOM就绪检测，替代固定sleep）。
    返回 True=已就绪；False=超时。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = cdp("Runtime.evaluate", session_id=sid, expression=expr,
                    returnByValue=True, awaitPromise=False)
            if r.get("result", {}).get("value"):
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False

def search_kw_direct(kw, sid, filters=None, pages=1, max_per_page=20):
    """搜索单一关键词（支持前置筛选+翻页），DOM就绪检测替代固定sleep。
    返回候选列表 [{cid, text, name, age, edu, years, city, cur}]。"""
    cdp("Page.navigate", session_id=sid,
        url="https://h.liepin.com/search/getConditionItem?searchType=1")
    # 等页面加载 + 搜索框出现（旧代码固定 sleep 3s）
    wait_for(sid, "document.readyState==='complete' && document.querySelectorAll('input[type=search]').length >= 2", timeout=15)
    apply_pre_filters(sid, filters)

    # 设置搜索框
    js("""
    var input = document.querySelectorAll('input[type=search]')[1];
    if (input) {
        input.focus();
        var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(input, arguments[0]);
        input.dispatchEvent(new Event('input', {bubbles: true}));
        input.dispatchEvent(new Event('change', {bubbles: true}));
    }
    """, sid)
    js("""
    var input = document.querySelectorAll('input[type=search]')[1];
    if (input) {
        input.focus();
        var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(input, '""" + kw + """');
        input.dispatchEvent(new Event('input', {bubbles: true}));
        input.dispatchEvent(new Event('change', {bubbles: true}));
    }
    """, sid)
    time.sleep(0.4)

    # 点击搜索
    js("var btn = document.querySelector('.search-btn'); if (btn) btn.click();", sid)
    # 等结果卡片出现（旧代码固定 sleep 5s）
    wait_for(sid, "document.querySelectorAll('[data-tlg-scm]').length > 0", timeout=12)
    time.sleep(1.0)  # 等首屏渲染稳定

    # 收集当前页
    all_raw = extract_cards(sid, max_per_page)
    # 翻页
    for _ in range(max(0, pages - 1)):
        clicked = js("""
        (function(){
            var btns = document.querySelectorAll('.ant-pagination-next, .ant-pagination-item');
            var next = null;
            for (var b of btns) {
                if (b.className.indexOf('next') >= 0) { next = b; break; }
            }
            if (next && next.className.indexOf('disabled') < 0) {
                next.click();
                return true;
            }
            return false;
        })()
        """, sid)
        if not clicked:
            break
        wait_for(sid, "document.querySelectorAll('[data-tlg-scm]').length > 0", timeout=10)
        time.sleep(0.8)
        more = extract_cards(sid, max_per_page)
        if not more:
            break
        all_raw.extend(more)
    # 去重
    seen, uniq = set(), []
    for d in all_raw:
        if d['cid'] not in seen:
            seen.add(d['cid']); uniq.append(d)
    return uniq

def extract_cards(sid, max_per_page=20, text_limit=2000):
    """从搜索列表页提取候选人卡片。text_limit 默认取 2000 字符（旧版只取400，
    粗筛/初判信息不足）。"""
    raw = js("""
    (function() {
        var results = [];
        var els = document.querySelectorAll('[data-tlg-scm]');
        var seen = {};
        for (var i = 0; i < els.length; i++) {
            var scm = els[i].getAttribute('data-tlg-scm');
            var m = scm && scm.match(/cid=([a-zA-Z0-9]+)/);
            if (!m || seen[m[1]]) continue;
            seen[m[1]] = true;
            results.push({
                cid: m[1],
                text: (els[i].textContent || '').trim().substring(0, %d)
            });
            if (results.length >= %d) break;
        }
        return JSON.stringify(results);
    })()
    """ % (text_limit, max_per_page), sid)
    return json.loads(raw) if raw else []

def connect():
    """连接到猎聘tab（静默：只 attach 不激活，不抢焦点、不弹窗）。
    禁用 switch_tab：其内部 Target.activateTarget 会把 tab 切到前台，打断用户。"""
    tabs = list_tabs()
    for t in tabs:
        if "h.liepin.com" in t.get("url",""):
            # 直接 attach 获取 sessionId，不激活该 tab
            sid = cdp("Target.attachToTarget", targetId=t["targetId"], flatten=True).get("sessionId")
            time.sleep(1)
            return sid
    # 没有猎聘 tab：后台创建（background=True 不抢焦点），不激活
    try:
        tid = cdp("Target.createTarget", url="https://h.liepin.com/", background=True).get("targetId")
    except Exception:
        tid = cdp("Target.createTarget", url="about:blank").get("targetId")
    time.sleep(4)
    return cdp("Target.attachToTarget", targetId=tid, flatten=True).get("sessionId")

def apply_pre_filters(sid, filters=None):
    """在猎聘搜索条件页设置前置筛选（年龄/年限/学历/城市/性别）。
    必须在关键词搜索前调用（页面刚导航到 getConditionItem 之后）。"""
    if not filters:
        return
    time.sleep(1.0)  # 等筛选区渲染
    # 年龄: 输入上限
    if filters.get('max_age'):
        js("""
        (function(mx) {
            var inputs = document.querySelectorAll('input.age-input');
            if (inputs.length >= 2) {
                var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
                setter.call(inputs[1], String(mx));
                inputs[1].dispatchEvent(new Event('input',{bubbles:true}));
                inputs[1].dispatchEvent(new Event('change',{bubbles:true}));
                return true;
            }
            return false;
        })(%d)
        """ % filters['max_age'], sid)
        time.sleep(0.6)
    # 工作年限: 点对应档位
    if filters.get('min_years'):
        opts = {1:'1-3年', 3:'3-5年', 5:'5-10年', 8:'10年以上', 10:'10年以上'}
        opt = None
        for thr in sorted(opts, reverse=True):
            if filters['min_years'] >= thr:
                opt = opts[thr]; break
        if opt:
            js("""
            (function(txt){
                var els = document.querySelectorAll('label.tag-item');
                for (var el of els) {
                    if ((el.textContent||'').trim()===txt) { el.click(); return true; }
                }
                return false;
            })('%s')
            """ % opt, sid)
            time.sleep(0.6)
    # 学历: 点 本科/硕士/博士
    if filters.get('min_edu'):
        js("""
        (function(txt){
            var els = document.querySelectorAll('label.tag-item');
            for (var el of els) {
                if ((el.textContent||'').trim()===txt) { el.click(); return true; }
            }
            return false;
        })('%s')
        """ % filters['min_edu'], sid)
        time.sleep(0.6)
    # 期望城市: 点标签
    if filters.get('city'):
        js("""
        (function(txt){
            var els = document.querySelectorAll('label.tag-item');
            for (var el of els) {
                if ((el.textContent||'').trim()===txt) { el.click(); return true; }
            }
            return false;
        })('%s')
        """ % filters['city'], sid)
        time.sleep(0.6)
    # 性别: ant-select 下拉
    if filters.get('gender'):
        js("""
        (function(){
            var sel = document.querySelector('.sexSelectStyle');
            if (sel) { sel.click(); return true; }
            return false;
        })()
        """, sid)
        time.sleep(0.8)
        js("""
        (function(txt){
            var opts = document.querySelectorAll('.ant-select-item, .ant-select-item-option, li[role=option]');
            for (var el of opts) {
                if ((el.textContent||'').trim()===txt) { el.click(); return true; }
            }
            return false;
        })('%s')
        """ % filters['gender'], sid)
        time.sleep(0.5)

def search_keyword(kw, sid, filters=None, pages=1, max_per_page=20):
    """搜索单一关键词（兼容旧接口，转发到 DOM就绪检测版）"""
    return search_kw_direct(kw, sid, filters=filters, pages=pages, max_per_page=max_per_page)

def parse_candidates(raw_list, max_age=40):
    """解析候选人信息并评分（默认过滤40岁以上）"""
    parsed = []
    for d in raw_list:
        text = d.get('text','')
        link = 'https://h.liepin.com/resume/showresumedetail/?res_id_encode=' + d['cid']
        
        name_m = re.search(r'([\u4e00-\u9fa5]{2,3})\*', text)
        name = name_m.group(1) if name_m else "?"
        age_m = re.search(r'(\d+)岁', text)
        age = int(age_m.group(1)) if age_m else 99
        edu_m = re.search(r'(博士(?:后)?|硕士|本科)', text)
        edu = edu_m.group(1) if edu_m else "?"
        school_m = re.search(r'([\u4e00-\u9fa5]{2,8}(?:大学|学院))', text)
        school = school_m.group(1) if school_m else ""
        company_m = re.search(r'·\s*([^·\n]{5,80})', text)
        company = company_m.group(1).strip() if company_m else ""
        
        in_sh = '上海' in text
        is_hr = any(w in text for w in ['HR','人力','人力资源','招聘','人事','组织','薪酬'])
        is_robotics = any(w in text for w in ['机器人','AI','人工智能','智能','硬科技','自动化','机器'])
        is_physics = any(w in text for w in ['物理','Physic','模型','深度学习','机器学习','算法'])
        
        # 年龄过滤：默认排除40岁以上
        if age > max_age:
            continue
        
        score = 0
        if is_hr: score += 3
        if is_physics: score += 3
        if in_sh: score += 3
        if is_robotics: score += 2
        if edu in ['硕士','博士']: score += 1
        
        parsed.append({
            'name': name, 'age': age, 'edu': edu, 'school': school,
            'company': company, 'link': link,
            'in_sh': in_sh, 'is_hr': is_hr, 'is_physics': is_physics,
            'score': score, 'text': text[:200]
        })
    
    return parsed

def print_table(candidates, title="TOP10候选人"):
    """打印候选人的表格"""
    print(f"\n{'='*100}")
    print(f"📋 {title}")
    print(f"{'='*100}")
    print(f"\n{'#':<3} {'姓名':<8} {'年龄':<4} {'学历':<5} {'学校':<20} {'公司/职位':<35} {'匹配'}")
    print(f"{'-'*100}")
    for i, c in enumerate(candidates[:10]):
        tags = []
        if c.get('in_sh'): tags.append('上海')
        if c.get('is_hr'): tags.append('HR')
        if c.get('is_physics'): tags.append('物理/AI')
        tag_str = '|'.join(tags) if tags else str(c['score'])
        
        print(f"  {i+1:<2} {c['name']:<8} {c['age']:<4} {c['edu']:<5} {c['school'][:18]:<20} {c['company'][:33]:<35} {tag_str}")
        print(f"     🔗 {c['link']}")

def save_md(candidates, filename, keywords=""):
    """保存为Markdown"""
    with open(filename, 'w', encoding='utf-8') as f:
        f.write("# 猎聘搜索报告\n\n")
        if keywords:
            f.write(f"**搜索词:** {keywords}\n\n")
        f.write(f"**总候选人:** {len(candidates)}\n\n")
        f.write("| # | 姓名 | 年龄 | 学历 | 学校 | 公司/职位 | 标签 | 简历链接 |\n")
        f.write("|---|------|:---:|:---:|------|-----------|:----:|----------|\n")
        for i, c in enumerate(candidates[:10]):
            tags = []
            if c.get('in_sh'): tags.append('上海')
            if c.get('is_hr'): tags.append('HR')
            if c.get('is_physics'): tags.append('物理/AI')
            tag_str = ' '.join(tags) if tags else str(c['score'])
            f.write(f"| {i+1} | {c['name']} | {c['age']} | {c['edu']} | {c['school']} | {c['company'][:25]} | {tag_str} | [👉直达]({c['link']}) |\n")

def main():
    parser = argparse.ArgumentParser(description='猎聘超级搜索')
    parser.add_argument('-k', '--keywords', required=True, help='搜索关键词，逗号分隔')
    parser.add_argument('-o', '--output', default='liepin_search_results.md', help='输出文件')
    parser.add_argument('--pages', type=int, default=1, help='每关键词翻页数（每页约20人）')
    parser.add_argument('--max-age', type=int, default=40, help='年龄上限（默认40岁）')
    parser.add_argument('--no-age-filter', action='store_true', help='关闭年龄过滤')
    parser.add_argument('--pre-max-age', type=int, help='前置筛选: 年龄上限（在猎聘页面设置）')
    parser.add_argument('--pre-min-years', type=int, help='前置筛选: 工作年限下限')
    parser.add_argument('--pre-min-edu', choices=['本科','硕士','博士'], help='前置筛选: 学历下限')
    parser.add_argument('--pre-city', help='前置筛选: 期望城市（如 上海）')
    parser.add_argument('--pre-gender', choices=['男','女'], help='前置筛选: 性别')
    args = parser.parse_args()
    
    keywords = [k.strip() for k in args.keywords.split(',')]
    
    sid = connect()
    if not sid:
        print("❌ 未找到猎聘页面，请先在Chrome中打开猎聘并登录")
        return
    
    filters = {}
    if args.pre_max_age: filters['max_age'] = args.pre_max_age
    if args.pre_min_years: filters['min_years'] = args.pre_min_years
    if args.pre_min_edu: filters['min_edu'] = args.pre_min_edu
    if args.pre_city: filters['city'] = args.pre_city
    if args.pre_gender: filters['gender'] = args.pre_gender
    
    all_raw = []
    for kw in keywords:
        print(f"🔍 搜索: {kw}")
        data = search_keyword(kw, sid, filters=filters or None, pages=args.pages)
        all_raw.extend(data)
        print(f"   → {len(data)} 条")
    
    # 去重
    seen = set()
    unique = []
    for d in all_raw:
        if d['cid'] not in seen:
            seen.add(d['cid'])
            unique.append(d)
    
    print(f"\n📊 去重后: {len(unique)} 条")
    
    max_age = 999 if args.no_age_filter else args.max_age
    candidates = parse_candidates(unique, max_age=max_age)
    candidates.sort(key=lambda x: -x['score'])
    
    # 如果过滤后不足5人，放宽至45岁
    if len(candidates) < 5 and not args.no_age_filter:
        print(f"⚠️ ≤{args.max_age}岁仅{len(candidates)}人，放宽至45岁")
        candidates = parse_candidates(unique, max_age=45)
        candidates.sort(key=lambda x: -x['score'])
    
    print_table(candidates)
    save_md(candidates, args.output, args.keywords)
    print(f"\n✅ 已保存: {args.output}")

if __name__ == '__main__':
    main()
