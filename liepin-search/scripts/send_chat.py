# -*- coding: utf-8 -*-
"""猎聘简历页→立即沟通/继续沟通→(进入聊天抽屉)→输入消息→发送
全程后台标签页：创建 background tab，发完消息立即 closeTarget，不激活不抢焦点
两种模式：
  1. 弹窗模式：点击沟通按钮后，弹出"请选择职位开聊"弹窗 → 点击"不选择职位开聊"
  2. 抽屉模式：点击沟通按钮后直接打开聊天抽屉（已有对话或跳过弹窗）
"""
import sys, time, json, base64
from browser_harness.helpers import cdp

def js(expr, sid=None):
    r = cdp("Runtime.evaluate", session_id=sid, expression=expr, returnByValue=True)
    return r.get("result",{}).get("value")

def new_bg_tab(url):
    """后台创建标签页并 attach，返回 (tid, sid)。不 switch/activate，不抢焦点"""
    tid = cdp("Target.createTarget", url="about:blank", background=True)["targetId"]
    time.sleep(0.8)
    sid = cdp("Target.attachToTarget", targetId=tid, flatten=True)["sessionId"]
    time.sleep(0.5)
    cdp("Page.navigate", session_id=sid, url=url)
    return tid, sid

def close_bg_tab(tid):
    """关闭后台标签页（不激活目标，不抢焦点）"""
    try:
        cdp("Target.closeTarget", targetId=tid)
        return True
    except Exception as e:
        print("关闭标签失败:", str(e)[:60])
        return False

def send_message(cid, msg, dry_run=False, screenshot=False, auto_close=True):
    url = f"https://h.liepin.com/resume/showresumedetail/?res_id_encode={cid}"
    tid, sid = new_bg_tab(url)
    try:
        time.sleep(4.5)

        # 1. 点立即沟通/继续沟通
        c1 = js("""
        (function() {
            var btns = document.querySelectorAll('button');
            for (var b of btns) {
                var t = (b.textContent||'').trim();
                if (t.indexOf('继续沟通') >= 0 || t.indexOf('立即沟通') >= 0) { b.click(); return true; }
            }
            return false;
        })()
        """, sid)
        print("1.点击沟通:", c1)
        time.sleep(3.0)

        # 2. 判断模式：看是否有"不选择职位开聊"按钮
        has_dialog = js("""
        (function() {
            var els = document.querySelectorAll('button');
            for (var b of els) {
                var t = (b.textContent||'').trim();
                if (t.indexOf('不选择职位开聊') >= 0) return true;
            }
            return false;
        })()
        """, sid)

        if has_dialog:
            c2 = js("""
            (function() {
                var btns = document.querySelectorAll('button');
                for (var b of btns) {
                    var t = (b.textContent||'').trim();
                    if (t.indexOf('不选择职位开聊') >= 0) { b.click(); return 'DIALOG_CLICKED'; }
                }
                return 'NOT_FOUND';
            })()
            """, sid)
            print("2.不选择职位开聊:", c2)
            time.sleep(3.5)
        else:
            print("2.无弹窗（直接进入聊天抽屉）")
            c2 = 'NO_DIALOG'

        # 3. 输入消息
        msg_json = json.dumps(msg, ensure_ascii=False)
        c3 = js(f"""
        (function() {{
            var ta = document.querySelector('textarea.ant-im-input');
            if (!ta) return 'NO_TEXTAREA';
            var msg = {msg_json};
            var setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
            setter.call(ta, msg);
            ta.dispatchEvent(new Event('input', {{bubbles:true}}));
            ta.dispatchEvent(new Event('change', {{bubbles:true}}));
            return 'INPUT_OK';
        }})()
        """, sid)
        print("3.输入:", c3)
        time.sleep(1.2)

        # 4. 发送（除非 dry_run）
        if dry_run:
            c4 = 'DRY_RUN_SKIPPED'
        else:
            c4 = js("""
            (function() {
                var btns = document.querySelectorAll('button');
                for (var b of btns) {
                    var t = (b.textContent||'').trim();
                    if (t === '发送' && !b.disabled) {
                        var rect = b.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) { b.click(); return 'SENT'; }
                    }
                }
                return 'NO_SEND_BTN';
            })()
            """, sid)
        print("4.发送:", c4)
        time.sleep(2.0)

        if screenshot:
            try:
                shot = cdp("Page.captureScreenshot", session_id=sid, format="png")
                if shot and shot.get("data"):
                    import os
                    out_dir = os.environ.get("LIEpin_SCREENSHOT_DIR", os.getcwd())
                    fn = os.path.join(out_dir, f"sent_{cid}.png")
                    with open(fn, "wb") as f:
                        f.write(base64.b64decode(shot["data"]))
                    print("截图:", fn)
            except Exception as e:
                print("截图失败:", str(e)[:80])

        return {"cid": cid, "open": c1, "dialog": c2, "input": c3, "send": c4}
    finally:
        if auto_close:
            time.sleep(1.0)
            close_bg_tab(tid)
            print("标签已关闭")

if __name__ == "__main__":
    cid = sys.argv[1]
    msg = sys.argv[2]
    dry = "--dry" in sys.argv
    shot = "--shot" in sys.argv
    r = send_message(cid, msg, dry_run=dry, screenshot=shot)
    print(json.dumps(r, ensure_ascii=False))
