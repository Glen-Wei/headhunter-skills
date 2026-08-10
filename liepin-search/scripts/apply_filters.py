"""
猎聘前置条件设置 (apply_filters.py)
====================================
在猎聘"找简历"搜索条件页，提前设置好 年龄/工作年限/学历/期望城市/性别 等筛选项，
然后再输入关键词搜索 —— 保证搜索出来的就是符合硬性条件的人，减少无效打开。

用法:
  python apply_filters.py --max-age 35 --min-years 8 --min-edu 本科 --city 上海 --gender 男
  # 所有参数可选；不传的保持"不限"

注意: 猎聘某些筛选为单行（同排互斥，如工作年限的"10年以上"与"5-10年"），
      设置前会先点击同组"不限"复位，再点目标项。

Created & maintained by Glen Wei (韦其像) — https://github.com/Glen-Wei
Email: glen.keeming@gmail.com | WeChat: Glen_Wei88
Part of headhunter-skills: https://github.com/Glen-Wei/headhunter-skills"""
import sys, time, json, argparse
from browser_harness.helpers import list_tabs, cdp, switch_tab

AUTHOR_EPILOG = (
    "Author: Glen Wei (韦其像) | GitHub: https://github.com/Glen-Wei "
    "| Email: glen.keeming@gmail.com | WeChat: Glen_Wei88 | "
    "Part of headhunter-skills: https://github.com/Glen-Wei/headhunter-skills"
)

def connect():
    tabs = list_tabs()
    for t in tabs:
        if "h.liepin.com" in t.get("url",""):
            switch_tab(t["targetId"]); time.sleep(1)
            return cdp("Target.attachToTarget", targetId=t["targetId"], flatten=True).get("sessionId")
    nt = cdp("Target.createTarget", url="https://h.liepin.com/")
    switch_tab(nt.get("targetId")); time.sleep(4)
    return cdp("Target.attachToTarget", targetId=nt.get("targetId"), flatten=True).get("sessionId")

def js(sid, expr):
    r = cdp("Runtime.evaluate", session_id=sid, expression=expr, returnByValue=True, awaitPromise=False)
    return r.get("result",{}).get("value")

def click_text(sid, text, group_cls=None):
    """点击页面中可见的、文本完全匹配的元素（可指定所在容器 class）"""
    return js(sid, """
    (function(txt, grp) {
        var scope = grp ? Array.from(document.querySelectorAll(grp)) : [document];
        for (var s of scope) {
            var els = s.querySelectorAll ? s.querySelectorAll('span,label,div,li,button,a') : [];
            for (var el of els) {
                var t = (el.textContent||'').trim();
                if (t === txt && el.offsetParent !== null && el.querySelector('span,label') === null) {
                    el.click(); return true;
                }
            }
        }
        return false;
    })('%s', %s)
    """ % (text, "'%s'" % group_cls if group_cls else 'null'))

def set_age(sid, max_age):
    """年龄：填最小年龄(留空) + 最大年龄 = max_age"""
    js(sid, """
    (function(mx) {
        var inputs = document.querySelectorAll('input.age-input');
        if (inputs.length >= 2) {
            // [0]=最小年龄 [1]=最大年龄
            var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
            setter.call(inputs[0], '');
            inputs[0].dispatchEvent(new Event('input',{bubbles:true}));
            inputs[0].dispatchEvent(new Event('change',{bubbles:true}));
            setter.call(inputs[1], String(mx));
            inputs[1].dispatchEvent(new Event('input',{bubbles:true}));
            inputs[1].dispatchEvent(new Event('change',{bubbles:true}));
            return true;
        }
        return false;
    })(%d)
    """ % max_age)
    time.sleep(0.5)

def set_years(sid, min_years):
    """工作年限：按 min_years 选择档位；>=10 选【10年以上】"""
    if min_years is None: return
    if min_years >= 10:
        click_text(sid, '10年以上')
    elif min_years >= 8:
        click_text(sid, '10年以上')
    elif min_years >= 5:
        click_text(sid, '5-10年')
    elif min_years >= 3:
        click_text(sid, '3-5年')
    elif min_years >= 1:
        click_text(sid, '1-3年')
    time.sleep(0.5)

def set_edu(sid, min_edu):
    """学历：本科/硕士/博士"""
    if min_edu is None: return
    click_text(sid, min_edu)
    time.sleep(0.3)

def set_city(sid, city):
    """期望城市：上海等"""
    if city is None: return
    click_text(sid, city)
    time.sleep(0.3)

def set_gender(sid, gender):
    """性别：男/女（ant-select 下拉）"""
    if gender is None: return
    # 点击性别下拉框
    ok = js(sid, """
    (function() {
        var sel = document.querySelector('.sexSelectStyle');
        if (sel) { sel.click(); return true; }
        return false;
    })()
    """)
    time.sleep(0.8)
    # 在下拉选项里点 男/女
    click_text(sid, gender)
    time.sleep(0.5)

def apply_all(sid, max_age=None, min_years=None, min_edu=None, city=None, gender=None):
    """依次设置所有前置条件（先导航到搜索条件页）"""
    cdp("Page.navigate", session_id=sid, url="https://h.liepin.com/search/getConditionItem?searchType=1")
    time.sleep(3.5)
    if max_age is not None:
        set_age(sid, max_age)
    if min_years is not None:
        set_years(sid, min_years)
    if min_edu is not None:
        set_edu(sid, min_edu)
    if city is not None:
        set_city(sid, city)
    if gender is not None:
        set_gender(sid, gender)
    return True

def main():
    ap = argparse.ArgumentParser(description='猎聘前置条件设置', epilog=AUTHOR_EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--max-age', type=int)
    ap.add_argument('--min-years', type=int)
    ap.add_argument('--min-edu', choices=['本科','硕士','博士'])
    ap.add_argument('--city')
    ap.add_argument('--gender', choices=['男','女'])
    args = ap.parse_args()
    sid = connect()
    apply_all(sid, args.max_age, args.min_years, args.min_edu, args.city, args.gender)
    print("✅ 前置条件已设置")

if __name__ == '__main__':
    main()
