# 猎聘 data-tlg-scm 属性提取指南

## 核心发现

猎聘（h.liepin.com）的搜索结果是React SPA，**每个候选人卡片上都有一个 `data-tlg-scm` 属性**，其中包含该候选人的唯一简历ID。

## 属性格式

```
data-tlg-scm="cid=729c9b2b279cPfe42513a3f44&ctype=2&traceId=6801eb56-a559-4c57-8f2d-28657fcb4696"
```

- `cid`：候选人简历唯一ID（类似 `7e9f922825Kff4156363e4b`）
- `ctype`：卡片类型（2=候选人卡片）
- `traceId`：搜索追踪ID

## 简历直达链接

```
https://h.liepin.com/resume/showresumedetail/?res_id_encode={cid}
```

## 候选人卡片文本内容

每个卡片元素的 `textContent` 包含：
- 姓名：如 "周**"（2-3个汉字 + 2个星号，猎聘隐私保护）
- 年龄：如 "24岁"
- 学历：如 "硕士"、"博士"、"博士后"、"本科"
- 学校：如 "哈尔滨工业大学"
- 公司/职位："阿里巴巴集团 · 世界模型基座算法实习生"
- 工作经历年限："2025.04-至今(1年3个月)"
- 其他：active状态、求职意向城市等

## 提取方法

```javascript
// 一次性获取所有候选人卡片（20-30个）
var els = document.querySelectorAll('[data-tlg-scm]');

// 去重提取
var seen = {};
for (var i = 0; i < els.length; i++) {
    var scm = els[i].getAttribute('data-tlg-scm');
    var match = scm && scm.match(/cid=([a-zA-Z0-9]+)/);
    if (!match || seen[match[1]]) continue;
    seen[match[1]] = true;
    
    var cid = match[1];
    var link = 'https://h.liepin.com/resume/showresumedetail/?res_id_encode=' + cid;
    var text = els[i].textContent.trim();
    
    // 处理该候选人...
}
```

## 其他data-*属性

| 属性 | 内容 | 说明 |
|------|------|------|
| `data-tlg-scm` | `cid=xxx&ctype=2&traceId=...` | 候选人CID |
| `data-tlg-ext` | URL编码的JSON `{"hjob_id":77782985,"search_type":3}` | 命中岗位ID |
| `data-tlg-elem-id` | 数字ID | 元素唯一标识 |
| `data_info` | 字符串 | 其他元数据 |

## 注意事项

1. `data-tlg-scm` 只出现在搜索**结果**页，不出现在搜索条件配置页
2. CDP的 `Runtime.evaluate` 执行 `querySelectorAll` 有时会返回空——这是已知坑点，重试或切换tab即可
3. 先确认 `document.body.innerText` 长度>5000 才说明有搜索结果
4. 搜索框使用 Ant Design Select 组件，需要用原生 value setter 触发 React 状态更新
