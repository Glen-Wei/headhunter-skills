#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""猎聘一键发布职位脚本（browser-harness 管道内运行）

用法：在 browser-harness heredoc 中：
    exec(open('<skill>/scripts/publish_job.py').read())
    publish_job(company='示例科技有限公司', display='示例科技',
                job_name='科学家（物理驱动世界模型方向）', category='数据科学家',
                city='北京', district='海淀区',
                salary_min=50, salary_max=60, months=12,
                edu='博士', years='经验不限', desc='职位描述文本...',
                industry='人工智能', need_admin_approval=True)
流程：新增代招企业→名称→类别联想→城市+区→薪资→学历/年限→行业→描述→同意框→发布→
      广告法违禁词自动替换重试→确认状态。
基于验证过的 selector 与事件序列；页面改版时函数报错并 dump 当前状态。

Created & maintained by Glen Wei (韦其像) — https://github.com/Glen-Wei
Email: glen.keeming@gmail.com | WeChat: Glen_Wei88
Part of headhunter-skills: https://github.com/Glen-Wei/headhunter-skills"""
import time, json, re

AUTHOR_EPILOG = (
    "Author: Glen Wei (韦其像) | GitHub: https://github.com/Glen-Wei "
    "| Email: glen.keeming@gmail.com | WeChat: Glen_Wei88 | "
    "Part of headhunter-skills: https://github.com/Glen-Wei/headhunter-skills"
)

AD_BANNED = ["顶尖", "顶级", "最好", "第一", "最大", "最高", "唯一", "首家", "领先"]

def _setv(sel_or_el, value, is_js=False):
    """React 受控组件填值（input/textarea）"""
    if is_js:
        return sel_or_el
    return js(f"""
    (()=>{{
      function setNativeValue(el, value){{
        const proto = Object.getPrototypeOf(el);
        const desc = Object.getOwnPropertyDescriptor(proto, 'value');
        desc.set.call(el, value);
        el.dispatchEvent(new Event('input', {{bubbles:true}}));
      }}
      const el = {sel_or_el};
      setNativeValue(el, {json.dumps(value)});
      return el.value.length;
    }})()
    """)

def _form_item(label):
    return f"Array.from(document.querySelectorAll('.ant-form-item')).find(f=>(f.querySelector('.ant-form-item-label')||{{}}).innerText?.includes('{label}'))"

def _open_select(label, idx=0):
    return js(f"""
    (()=>{{
      const fi = {_form_item(label)};
      if(!fi) return 'no form item';
      const sel = fi.querySelectorAll('.ant-select')[{idx}];
      if(!sel) return 'no select';
      const target = sel.querySelector('.ant-select-selector') || sel;
      const rect = target.getBoundingClientRect();
      ['pointerdown','mousedown','mouseup','click'].forEach(ev=>{{
        target.dispatchEvent(new MouseEvent(ev, {{bubbles:true, cancelable:true, clientX: rect.x+10, clientY: rect.y+10}}));
      }});
      return 'opened';
    }})()
    """)

def _pick_option(text, contains=True):
    """点击当前打开的标准下拉中的选项（支持 -/~ 变体，如 5-10年 → 5~10年）"""
    variants = {text}
    if '-' in text: variants.add(text.replace('-', '~'))
    if '~' in text: variants.add(text.replace('~', '-'))
    for v in variants:
        hit = js(f"""
        (()=>{{
          const opts = Array.from(document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option'));
          const hit = opts.find(o=>{'o.innerText.trim()==='+json.dumps(v) if not contains else "o.innerText.includes('"+v+"')"});
          if(!hit) return null;
          hit.click();
          return 'selected: ' + hit.innerText.trim().slice(0,20);
        }})()
        """)
        if hit:
            return hit
    return js("""
    (()=>{
      const opts = Array.from(document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option'));
      return 'no option: ' + opts.map(o=>o.innerText.trim()).join(',');
    })()
    """)

def _scroll_salary_to(target_k):
    """薪资虚拟列表滚动到目标档位（1k-500k）"""
    def probe():
        return js("""
        JSON.stringify(
          Array.from(document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option')).map(o=>o.innerText.trim()).filter(Boolean)
        )
        """)
    def set_st(v):
        js(f"""
        (()=>{{
          const dd = Array.from(document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden)')).find(d=>d.innerText.includes('k'));
          if(dd) dd.querySelector('.rc-virtual-list-holder').scrollTop = {v};
          return 'ok';
        }})()
        """)
    lo, hi = 0, 14000  # 上限约 500*20px
    for _ in range(10):
        set_st((lo + hi) // 2)
        time.sleep(0.45)
        opts = json.loads(probe())
        if not opts:
            continue
        nums = [int(o.replace('k', '')) for o in opts if o.endswith('k')]
        if not nums:
            continue
        if target_k < nums[0]:
            hi = (lo + hi) // 2
        elif target_k > nums[-1]:
            lo = (lo + hi) // 2
        else:
            return True
    return False

def _set_salary(mn, mx, months=12):
    """设置薪资：最低/最高/月数"""
    _open_select('职位薪资', 0)
    time.sleep(0.8)
    _scroll_salary_to(mn)
    _pick_option(f'{mn}k')
    time.sleep(0.7)
    _open_select('职位薪资', 1)
    time.sleep(0.8)
    _scroll_salary_to(mx)
    _pick_option(f'{mx}k')
    time.sleep(0.6)
    js("document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true}))")

def _pick_standard(label, value, idx=0, exact=True):
    _open_select(label, idx)
    time.sleep(1.0)
    r = _pick_option(value)
    time.sleep(0.5)
    js("document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true}))")
    return r

def _publish_click():
    pos = js("""
    (()=>{
      const pub = Array.from(document.querySelectorAll('button')).find(b=>b.innerText.trim()==='发布职位');
      if(!pub) return 'no btn';
      pub.scrollIntoView({block:'center'});
      const r = pub.getBoundingClientRect();
      return JSON.stringify({x: Math.round(r.x+r.width/2), y: Math.round(r.y+r.height/2)});
    })()
    """)
    if pos == 'no btn':
        return 'no publish btn'
    p = json.loads(pos)
    cdp("Input.dispatchMouseEvent", type="mousePressed", x=p["x"], y=p["y"], button="left", clickCount=1)
    cdp("Input.dispatchMouseEvent", type="mouseReleased", x=p["x"], y=p["y"], button="left", clickCount=1)
    time.sleep(2.5)
    return 'clicked'

def publish_job(company, display, job_name, category, city, district, salary_min, salary_max,
                months=12, edu='博士', years='经验不限', desc='', industry='', check=True):
    logs = []

    # 0) 薪资必须先经使用者确认（业务约定）
    if not salary_min or not salary_max:
        print("⚠ 薪资未确认：薪资数值是使用者的业务决策，发布前必须向使用者确认对外填多少。请提供 salary_min/salary_max 后再发布。")
        return ["薪资未确认，已停止"]

    # 1) 广告法违禁词预清理（先替换，避免发布拦截返工）
    for w in AD_BANNED:
        desc = desc.replace(w, '资深' if w in ('顶尖', '顶级') else '优秀')
    logs.append(f"[0] 违禁词已预清理: {desc.count('资深')} 处替换")

    # 1) 新增代招企业
    js("document.querySelector('.new-enterprise').click()")
    time.sleep(1.5)
    _setv("document.querySelectorAll('.ant-modal-content input')[0]", company)
    time.sleep(0.8)
    js("""
    (()=>{
      const sels = document.querySelectorAll('.ant-modal-content .ant-select');
      if(sels.length>1){ sels[1].click(); }
      return 'ok';
    })()
    """)
    time.sleep(1.2)
    js("""
    (()=>{
      const opts = Array.from(document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option'));
      if(opts.length) opts[0].click();
      return 'selected display';
    })()
    """)
    time.sleep(0.8)
    js("""
    (()=>{
      const btns = Array.from(document.querySelectorAll('.ant-modal-content button'));
      const ok = btns.find(b=>b.innerText.includes('确'));
      if(ok) ok.click();
      return 'confirmed';
    })()
    """)
    time.sleep(1.5)
    logs.append("[1] 代招企业已添加")

    # 2) 职位名称
    _setv(f"{_form_item('职位名称')}.querySelector('input')", job_name)
    time.sleep(0.5)
    logs.append("[2] 职位名称已填")

    # 3) 职位类别（jobs-wrap 联想）
    js(f"""
    (()=>{{
      function setNativeValue(el, value){{
        const proto = Object.getPrototypeOf(el);
        const desc = Object.getOwnPropertyDescriptor(proto, 'value');
        desc.set.call(el, value);
        el.dispatchEvent(new Event('input', {{bubbles:true}}));
      }}
      const fi = {_form_item('职位类别')};
      const inp = fi.querySelector('input');
      setNativeValue(inp, '{category[:2]}');
      inp.focus();
      return 'typed';
    }})()
    """)
    time.sleep(1.8)
    js(f"""
    (()=>{{
      // 旧结构：EM 精确匹配
      const em = Array.from(document.querySelectorAll('.jobs-wrap *')).find(e=>e.tagName==='EM' && (e.innerText||'').trim()==='{category}');
      if(em){{ const tag = em.closest('.ant-tag') || em.parentElement; tag.click(); return 'category selected (em)'; }}
      // 新结构（08-16 验证）：联想 li，文本可能被 <span>高亮切分（如"数据科学"+家），用 li 整体文本前缀匹配
      const li = Array.from(document.querySelectorAll('.jobs-wrap .suggest-list li')).find(l=>(l.innerText||'').trim().startsWith('{category}'));
      if(li){{ ['pointerdown','mousedown','mouseup','click'].forEach(ev=>li.dispatchEvent(new MouseEvent(ev,{{bubbles:true,cancelable:true}}))); return 'category selected (li)'; }}
      return 'no category option';
    }})()
    """)
    time.sleep(0.8)
    logs.append("[3] 职位类别已选")

    # 4) 工作城市 + 区
    js(f"""
    (()=>{{
      function setNativeValue(el, value){{
        const proto = Object.getPrototypeOf(el);
        const desc = Object.getOwnPropertyDescriptor(proto, 'value');
        desc.set.call(el, value);
        el.dispatchEvent(new Event('input', {{bubbles:true}}));
      }}
      const fi = {_form_item('工作城市')};
      setNativeValue(fi.querySelector('input'), '{city}');
      return 'typed city';
    }})()
    """)
    time.sleep(1.5)
    js(f"""
    (()=>{{
      const opts = Array.from(document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option, .ant-select-dropdown:not(.ant-select-dropdown-hidden) li'));
      const hit = opts.find(o=>o.innerText.includes('{city}'));
      if(hit) hit.click();
      return 'city picked';
    }})()
    """)
    time.sleep(1.5)
    js(f"""
    (()=>{{
      const modal = Array.from(document.querySelectorAll('.ant-modal-content')).pop();
      if(!modal) return 'no district modal';
      // 先点省份（左侧 ant-menu，08-16 验证：先选省右侧才会出现区列表）
      const prov = Array.from(modal.querySelectorAll('span, div, li, a')).find(e=>e.children.length===0 && (e.innerText||'').trim()==='{city}');
      if(prov) prov.click();
      return 'province picked';
    }})()
    """)
    time.sleep(1.2)
    js(f"""
    (()=>{{
      const modal = Array.from(document.querySelectorAll('.ant-modal-content')).pop();
      if(!modal) return 'no district modal';
      const d = Array.from(modal.querySelectorAll('span, div, li, a')).find(e=>e.children.length===0 && (e.innerText||'').trim()==='{district}');
      if(d) d.click();
      return 'district picked';
    }})()
    """)
    time.sleep(1.2)
    logs.append(f"[4] 城市 {city}·{district}")

    # 5) 薪资
    _set_salary(salary_min, salary_max, months)
    logs.append(f"[5] 薪资 {salary_min}k-{salary_max}k·{months}个月")

    # 6) 学历 + 工作年限
    _pick_standard('学历要求', edu)
    _pick_standard('工作年限', years)
    logs.append(f"[6] 学历 {edu} / 年限 {years}")

    # 7) 行业要求（选填）
    if industry:
        _open_select('行业要求')
        time.sleep(1.5)
        js(f"""
        (()=>{{
          const opts = Array.from(document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option'));
          const hit = opts.find(o=>o.innerText.includes('{industry}'));
          if(hit) hit.click();
          return 'industry';
        }})()
        """)
        time.sleep(0.5)

    # 8) 职位描述
    _setv("document.getElementById('detailDuty')", desc)
    logs.append("[8] 职位描述已填")

    # 9) 勾选同意 + 发布（循环处理违禁词弹窗）
    # 勾选后必须校验真实选中（08-17 实测：一次 click 未勾上，顶部黄条"请确认已阅读职位发布规则"）
    agree = js("""
    (()=>{
      function clickCheck(){
        const labels = Array.from(document.querySelectorAll('label, .ant-checkbox-wrapper, span'));
        const hit = labels.find(e=>/发布规则|已阅读|同意/.test(e.innerText||'') && e.innerText.length<80);
        if(!hit) return null;
        const cb = hit.querySelector('.ant-checkbox-input') || hit.closest('label')?.querySelector('.ant-checkbox-input');
        if(cb){ cb.click(); return 'cb'; }
        hit.click(); return 'label';
      }
      const inputs = Array.from(document.querySelectorAll('.ant-checkbox-input'));
      if(inputs.some(i=>i.checked)) return 'already checked';
      for(let k=0;k<3;k++){
        const how = clickCheck();
        const checked = Array.from(document.querySelectorAll('.ant-checkbox-input')).some(i=>i.checked);
        if(checked) return 'checked after try' + (k+1) + ' (' + how + ')';
      }
      const cbs = Array.from(document.querySelectorAll('.ant-checkbox-input'));
      if(cbs.length){ cbs[cbs.length-1].click(); return 'fallback last checkbox'; }
      return 'no checkbox found';
    })()
    """)
    time.sleep(0.8)
    logs.append(f"[9] 勾选发布规则: {agree}")
    for attempt in range(5):
        _publish_click()
        time.sleep(1.5)
        modal = js("(document.querySelector('.ant-modal-content')||{}).innerText?.slice(0,300)||''")
        if '不符合' in modal or '广告法' in modal:
            logs.append(f"[9] 拦截#{attempt+1}: {modal[:60]}")
            js("""
            (()=>{
              const btns = Array.from(document.querySelectorAll('.ant-modal-content button'));
              const fix = btns.find(b=>b.innerText.includes('立即修改'));
              if(fix) fix.click();
              return 'fix clicked';
            })()
            """)
            time.sleep(1.2)
            # 替换违禁词
            cur = js("document.getElementById('detailDuty').value")
            for w in AD_BANNED:
                if w in cur:
                    cur = cur.replace(w, '资深' if w in ('顶尖', '顶级') else '优秀')
            _setv("document.getElementById('detailDuty')", cur)
            time.sleep(0.5)
            continue
        if '职位已提交' in modal or '审核' in modal:
            logs.append(f"[9] ✅ 提交成功: {modal[:120]}")
            js("""
            (()=>{
              const btns = Array.from(document.querySelectorAll('.ant-modal-content button'));
              const v = btns.find(b=>b.innerText.includes('查看职位'));
              if(v) v.click();
              return 'view';
            })()
            """)
            time.sleep(2)
            logs.append("[10] 已跳转职位管理列表")
            break
        time.sleep(2)
    else:
        logs.append("[9] 5 次尝试仍未确认提交，需人工检查")

    if check:
        st = js("JSON.stringify({url: location.href.slice(0,80), title: document.title.slice(0,40)})")
        logs.append("当前页: " + st)
    print("\n".join(logs))
    return logs

if __name__ == "__main__":
    print(AUTHOR_EPILOG)
    print("请在 browser-harness 管道内 exec 本文件后调用 publish_job(...)")
