---
name: workbuddy-asset-migration
description: 在 WorkBuddy 国内版和海外版之间，或跨机器之间，迁移 skills、对话、配置、connectors、身份文件和工作区产物；Memory 仅导出为 memory-export.md 参考文件，实际同步由客户端设置完成。
description_zh: "在 WorkBuddy 国内版和海外版之间，或跨机器之间，迁移用户个人资产（skills、conversations、automations、sessions、MCP/connectors 配置、IDENTITY/SOUL/USER 等）。导出为主包（对话与配置）+ 产物包（所有对话目录下的文件资料），并把源端本地 Memory 记录附为 memory-export.md 参考文件；Memory 由云端同步，导入端不写本地 memory 文件。"
description_en: "Migrate WorkBuddy personal assets (skills, conversations, automations, sessions, MCP/connectors config, IDENTITY/SOUL/USER profiles) between CN and AI editions, or across machines. Exports as main package (conversation/config) + workspace package, with local Memory records included only as a reference-only memory-export.md file. Import never writes local memory files because Memory is cloud-synced."
version: 0.8.4
author: Glen Wei (韦其像)
author_email: glen.keeming@gmail.com
homepage: https://github.com/Glen-Wei/headhunter-skills
allowed-tools: Read,Write,Bash
display_name: "WorkBuddy 资产迁移"
display_name_en: "WorkBuddy Asset Migration"
visibility: "public"
---

# WorkBuddy 资产迁移

把一台机器（或一个 WorkBuddy 变体）上的个人资产打包，搬到另一台机器（或另一个变体）。导入端如果已经有数据，默认走"合并、不覆盖"策略，不会把现有的东西冲掉。

## 适用场景

- 国内版 `~/.workbuddy/` ↔ 海外版 `~/.workbuddy-ai/`（**同机**优先走快速路径）
- 国内版 ↔ 海外版（**跨机**走打包流程）
- 同变体跨机器搬家（旧 Mac → 新 Mac、Mac → Linux）

## 环境预检（运行脚本前必做）

脚本使用纯 Python 标准库，无第三方依赖。但必须确保有一个可用的 Python ≥ 3.8 环境。

### 预检流程（agent 执行脚本前必须完成）

1. **检测 Python 可用性**：按优先级尝试：
   - ① WorkBuddy managed Python：扫描 `~/.workbuddy/binaries/python/versions/*/bin/python3`（macOS/Linux）或 `C:\Users\<用户名>\.workbuddy\binaries\python\versions\*\python.exe`（Windows），取版本号最大的路径
   - ② 系统 `python3`（macOS/Linux）或 `python`（Windows）
   - 若均不可用，提示用户安装或通过 `install_binary` 自动安装 managed Python
2. **版本验证**：运行 `<python_path> --version`，确认 ≥ 3.8
3. **依赖检查**：脚本仅依赖标准库（sqlite3, json, zipfile, shutil, argparse 等），无需 `pip install`。如果未来版本引入第三方依赖，agent 应自动安装到隔离 venv：
   ```bash
   # macOS/Linux
   <python_path> -m venv ~/.workbuddy/binaries/python/envs/migration
   ~/.workbuddy/binaries/python/envs/migration/bin/pip install <pkg>
   # Windows
   <python_path> -m venv C:\Users\<用户名>\.workbuddy\binaries\python\envs\migration
   C:\Users\<用户名>\.workbuddy\binaries\python\envs\migration\Scripts\pip install <pkg>
   ```
   **严禁**全局 `pip install`，所有依赖必须装在上述隔离 venv 中
4. **SQLite 可用性**：运行 `<python_path> -c "import sqlite3; print(sqlite3.sqlite_version)"` 确认 sqlite3 模块正常

预检通过后，后续所有命令中的 `python` 均替换为步骤 1 中确认的 Python 路径（或 venv 中的 python）。预检失败则停止，向用户说明原因并给出操作建议。

---

## 快速开始

以下命令中的 `python` 应替换为环境预检中确认的 Python 路径。

### 导出

```bash
# 在源端导出（先 dry-run 预览）
python scripts/export.py --source auto --dry-run
# 正式导出
python scripts/export.py --source auto --output ~/Desktop/wb-assets.zip
```

### 导入

```bash
# 在目标端导入（先 dry-run 预览）
python scripts/import.py --package ~/Desktop/wb-assets.zip --target auto --dry-run
# 正式导入
python scripts/import.py --package ~/Desktop/wb-assets.zip --target auto
```

**重要**：导入前请退出 WorkBuddy 客户端，否则 SQLite 写锁会拿不到，脚本会直接报错退出。

> 导出和导入是**两个独立的可选操作**，不是一个连续流程。用户可以选择只导出（打包备份），也可以在拿到迁移包后单独执行导入。导出完成后流程即结束，不会自动触发导入。

## 命令参数

### export.py
| 参数 | 说明 |
|---|---|
| `--source <path\|auto>` | 源根目录；auto 按 `WORKBUDDY_CONFIG_DIR` → `~/.workbuddy` → `~/.workbuddy-ai` 顺序探测 |
| `--output <path>` | 输出 zip 或目录（缺省 `./workbuddy-assets-<yyyymmdd-HHMM>.zip`） |
| `--no-conversations` | 不带 `projects/*.jsonl`（包体可大幅缩小） |
| `--no-credentials` | 不带 `.credentials.json`（推荐跨机器使用） |
| `--no-archive` | 输出目录树而非 zip |
| `--all-users` | 导出所有 user_id 的资产（默认：只导出当前登录用户） |
| `--with-workspaces` | 额外产出产物包 zip（含所有对话目录的文件） |
| `--workspace-include <path>` | 显式指定要打包的目录路径，可重复 |
| `--workspace-exclude-pattern <glob>` | 额外排除模式，追加到默认排除列表。支持三种格式：(1) 目录名+尾部 `/` 如 `node_modules/`，按目录基名匹配任意层级；(2) 文件名 glob（不含 `/`）如 `*.pyc`，按文件名匹配；(3) 路径 glob（含 `/` 但不以 `/` 结尾）如 `subdir/*.env` 或 `20260320184503/*`，按完整相对路径（POSIX 分隔符）匹配 |
| `--workspace-size-limit <bytes>` | 单目录大小上限（默认 5GB）；自动发现目录超限会跳过，显式 `--workspace-include` 可保留 |
| `--workspace-output <path>` | 指定产物包 zip 路径，默认 `<output>-workspaces.zip` |
| `--exclude-session-id <id>` | 排除当前/指定 session，可重复；也会读取环境变量中的当前 session id |
| `--no-default-excludes` | 禁用默认 workspace 排除清单 |

### import.py
| 参数 | 说明 |
|---|---|
| `--package <zip\|dir>` | 必填，迁移包路径 |
| `--target <path\|auto>` | 目标根目录，auto 探测规则同 export |
| `--overwrite` | 冲突时覆盖（默认 skip）；自动备份 `.bak-<ts>` |
| `--dry-run` | 只打印计划，不动文件 |
| `--uid-map src=dst` | 手动指定 user_id 映射，优先于自动映射 |
| `--no-conversations` / `--no-credentials` | 即便包里有也排除 |
| `--skip-db` / `--skip-skills` / `--skip-configs` | 分类排除（运维用） |
| `--path-map src=dst` | 跨机器导入时重写路径前缀，可重复 |
| `--target-os darwin\|win32\|linux` | 指定目标 OS 的路径规范化方式 |
| `--workspaces-package <zip>` | 指定产物包 zip，导入工作区文件 |
| `--workspace-destination <path>` | 产物包无法映射到原路径时的兜底落盘目录 |

## 冲突合并策略

| 资产 | 默认（无 --overwrite） |
|---|---|
| DB 表（sessions/automations/...） | `INSERT OR IGNORE`，同 id 保留导入端 |
| Skills 同名目录 | skip |
| settings.json/mcp.json/models.json | 浅 merge，导入端 key 优先 |
| IDENTITY.md/SOUL.md/USER.md | 已存在时落 `*.imported.md`，让用户手工合并 |
| projects/*.jsonl 同 session | skip |
| .credentials.json | 走 `--no-credentials` 推荐排除（OAuth token 跨机器易失效）|

## 风险与限制

- 不迁移：认证 token（在 CodeBuddyExtension 目录下，机器/账号绑定）、日志、审计日志、`binaries/`、缓存、Memory 本地文件写入
- Memory：导出包会附 `memory-export.md` 供人工参考；实际 Memory 由云端同步，提示用户在目标客户端设置中同步
- OAuth token：跨机器、跨变体大概率失效，建议导入后到 connector 面板手动重新授权
- uid 自动映射：导入时脚本自动将所有源端 uid 映射为目标端当前登录 uid，无需手动指定 `--uid-map`。用户导入就是为了把数据搬过来自己用，默认全量映射是最合理的行为
- 目标端无 uid 阻断：如果目标端 DB 为空（从未登录或没创建过对话），脚本无法自动推断目标 uid，此时会阻断退出并提示用户先登录目标端创建对话，或手动提供 `--uid-map src=dst`
- 备份：所有 `.bak-<ts>` 文件不自动清理，导入结束时 stdout 会列出位置和大小，自行决定何时删

## 跨机器 / 带产物文件

### user_id 自动检测

脚本会自动检测当前登录的 user_id，只导出该用户的 sessions / connectors，并把该账号本地 Memory 记录写入 `memory-export.md` 参考文件：
- **检测策略**：将当前工作目录（os.getcwd()）与 `sessions.cwd` 做匹配，取最匹配的 session 的 `user_id`
- **`--all-users`**：覆盖自动检测，导出所有 uid 的资产，并在 `memory-export.md` 中附上所有本地 Memory 文件
- **DB 过滤**：`export_reduced_db` 的 `user_id_filter` 参数按 uid 过滤 sessions 表
- **Memory 参考文件**：只写入迁移包根目录的 `memory-export.md`，导入端不会写本地 memory 文件
- **connectors 过滤**：删除 `connectors/<other_uid>/` 子目录

### uid 自动映射

- **默认行为**：导入时自动将所有源端 uid 映射为目标端当前登录 uid，无论源端有几个 uid。导入的意图就是把数据搬过来让自己能看见，全量映射是合理默认
- **可选覆盖**：若用户确实需要将不同源 uid 映射到不同目标 uid（极罕见场景），可通过 `--uid-map src=dst` 显式指定
- **目标端为空**：无现有 uid → **阻断退出**，提示用户先登录目标端创建至少一个对话（写入 uid），或手动提供 `--uid-map`

映射影响范围：sessions 表的 `user_id`、connectors 子目录名。Memory 不通过本地文件导入，导入报告中会打印实际使用的 uid 映射关系。

### 两个包的定义

导出产出两个包，职责完全分离：

| 包 | 内容 | 典型大小 |
|---|---|---|
| **主包**（`wb-assets-*.zip`） | DB（sessions/automations/workspaces 表）、Skills、配置文件（settings/mcp/models）、身份文件（IDENTITY/SOUL/USER）、connectors、**对话记录**（projects/*.jsonl + meta.json）、`memory-export.md` 参考文件 | 几 MB |
| **产物包**（`wb-assets-*-workspaces.zip`） | **所有对话目录下的产物/资料文件**——包括正式打开的工作空间 + 临时对话任务目录里的所有生成文件（报告、脚本、代码、图片等） | 可能数百 MB |

### 同机迁移（cn ↔ intl）—— 快速路径

同机双版并存时，对话目录是同一份磁盘文件，**不需要打包 zip、不需要传输**。直接从源 root 读取、写入目标 root：

```bash
# 先 dry-run 预览
python scripts/migrate_inplace.py --source ~/.workbuddy --target ~/.workbuddy-ai --exclude-session-id <CURRENT_SESSION_ID> --dry-run
# 正式迁移
python scripts/migrate_inplace.py --source ~/.workbuddy --target ~/.workbuddy-ai --exclude-session-id <CURRENT_SESSION_ID> --no-credentials
```

同机迁移的核心优势：
- 不产生中间 zip 包，省空间省时间
- DB 用 ATTACH 直接合并，和 import.py 完全相同的 INSERT OR IGNORE 语义
- Skills 同名跳过、Identity 文件写 `.imported.md`，和 import.py 行为一致；Memory 不写本地文件，请在客户端设置中同步
- uid 自动映射（源端 uid → 目标端 uid）
- 支持 `--skip-db`、`--skip-skills`、`--skip-configs`、`--no-conversations` 精细控制

同机双版并存时 `--source` 和 `--target` **必须显式指定路径**，不能使用 `auto`（同机存在两个 root 时 `auto` 会因无法交互选择而报错并列出候选路径）。反向迁移（intl → cn）同理，`--source ~/.workbuddy-ai --target ~/.workbuddy`。

#### migrate_inplace.py 参数
| 参数 | 说明 |
|---|---|
| `--source <path>` | 必填，源根目录（如 `~/.workbuddy`） |
| `--target <path>` | 必填，目标根目录（如 `~/.workbuddy-ai`） |
| `--no-conversations` | 不迁移 `projects/*.jsonl` |
| `--no-credentials` | 不迁移 `.credentials.json` |
| `--skip-db` | 不迁移 DB 表 |
| `--skip-skills` | 不迁移 skills 目录 |
| `--skip-configs` | 不迁移 settings/mcp/models 配置 |
| `--uid-map src=dst` | 手动指定 uid 映射，可重复 |
| `--exclude-session-id <id>` | 排除当前/指定 session，可重复；也会读取环境变量中的当前 session id |
| `--dry-run` | 只输出 JSON 计划，不写任何文件 |

### 跨机器迁移

跨机器**只迁对话记录不够**——目标机上没有源机的文件，对话点开后产物文件缺失。两种选择：

1. **只迁对话记录**（用户接受历史只是用来回顾，不需要打开原始文件）：
   ```bash
  python scripts/import.py --package wb.zip --target ~/.workbuddy \
      --path-map /Users/old=/Users/new --target-os darwin
   ```
   sessions.cwd / workspaces.path / automations.cwds / meta.json 全部按 `--path-map` 重写，新机上找得到对应工作目录就能继续。

2. **连产物文件一起搬**（用户要把所有对话目录下生成的文件也带过去）：
   ```bash
   # 源端
   python scripts/export.py --source ~/.workbuddy --output ~/wb.zip \
       --with-workspaces                 # 多产出一个 ~/wb-workspaces.zip
   # 目标端
   python scripts/import.py --package ~/wb.zip \
      --workspaces-package ~/wb-workspaces.zip \
      --target ~/.workbuddy \
       --path-map /Users/old=/Users/new --target-os darwin
   ```

---

### 排除当前对话（重要）

执行导出或同机迁移时，当前正在运行的对话（即执行迁移任务的这个 session）**必须排除**，否则目标端会出现一个"执行中"状态的幽灵对话。

获取当前 session ID 的方式（按优先级）：
1. 读取环境变量 `WORKBUDDY_CURRENT_SESSION_ID` 或 `CODEBUDDY_SESSION_ID`（WorkBuddy 客户端会设置）
2. 若环境变量未设置，查询源端 DB：**`SELECT id FROM sessions ORDER BY updated_at DESC LIMIT 1`**（结果即为当前会话 ID）
3. 将获取到的 ID 通过 `--exclude-session-id <id>` 传给 `export.py` 或 `migrate_inplace.py`

> `export.py` 也会自动读取环境变量，但显式传入更可靠。

## Agent 调用流程

skill 自身不提问，由调用它的 host agent 负责跟用户交互。

### 入口分派（首先执行）

根据用户的意图关键词直接分发到对应流程，**不做多余的预扫描**：

| 用户意图 | 关键词 | 直接进入 |
|---------|--------|---------|
| 导出 / 备份 | 导出、备份、打包、export | 步骤 0（资产扫描）→ 流程 A |
| 导入 | 导入、import | 步骤 1-导入（先确认迁移包）→ 流程 B |
| 同机迁移 | 同步、同机迁移、cn↔intl | 步骤 0（资产扫描）→ 流程 C |
| 未明确 | 迁移、搬家（无方向） | 步骤 0（资产扫描）后再问 |

### 步骤 0：资产扫描（仅导出、同机迁移、未明确意图时执行）

**在向用户提任何问题之前**，先静默完成以下扫描，把信息收集好，然后一次性展示给用户：

1. **检测端情况**：检查以下目录是否存在且符合 WorkBuddy root 特征（含 `workbuddy.db` 或 `settings.json` 或 `skills/` 或 `memory/`）：
   - 国内版：`~/.workbuddy/`
   - 海外版：`~/.workbuddy-ai/`
   - 记录哪些端存在、哪些不存在

2. **对每个存在的端，扫描以下资产**（快速 shell 命令统计，不运行脚本）：
   - **Skills**：`ls <root>/skills/ | wc -l` 个技能包，列出名称
   - **Memory 参考**：`ls <root>/memory/` 文件列表及大小，仅用于判断导出包是否会生成 `memory-export.md`
   - **对话记录**：`ls <root>/projects/ | wc -l` 个 session
   - **配置文件**：settings.json、mcp.json、models.json 是否存在
   - **身份文件**：IDENTITY.md、SOUL.md、USER.md 是否存在
   - **工作区文件**：列出 `~/WorkBuddy/`（Windows: `C:\Users\<用户名>\WorkBuddy\`）等对话目录数量及总大小（可能较大，可仅列数量+预估大小）

2.5. **检测各端多 uid**（在展示资产概览之前执行，结果为后续步骤提供上下文）：
   - 对**每个存在的端**，运行以下 Python 命令检测该端 DB 中有多少个不同的 user_id：
     ```bash
     <python_path> -c "import sqlite3; conn=sqlite3.connect('<db_path>'); cur=conn.cursor(); cur.execute('SELECT DISTINCT user_id FROM sessions'); print([r[0] for r in cur.fetchall()])"
     ```
     - `<db_path>` 为该端的 `workbuddy.db` 路径（如 `~/.workbuddy/workbuddy.db`）
     - `<python_path>` 使用环境预检中确认的 Python 路径
   - 记录每个端的 uid 数量及列表，供步骤 4（向用户提问）时使用
   - 此时**不要**向用户提问（因为用户尚未选择迁移方向，不知道哪个是源端）

3. **展示双端资产概览**（agent 组织成对比表格或清单呈现给用户）：

```
📦 国内版（~/.workbuddy/）
├── Skills：15 个技能包
├── Memory 参考：3 个文件，共 42 KB（仅生成 memory-export.md，不导入）
├── 对话记录：128 个 session
├── 配置文件：settings.json ✓  mcp.json ✓  models.json ✓
├── 身份文件：IDENTITY.md ✓  SOUL.md ✓  USER.md ✓
└── 工作区文件（~/WorkBuddy/）：23 个目录，共约 1.2 GB

📦 海外版（~/.workbuddy-ai/）
├── Skills：0 个
├── Memory 参考：1 个文件，共 254 B（仅生成 memory-export.md，不导入）
├── 对话记录：0 个 session
├── 配置文件：settings.json ✓  mcp.json ✗  models.json ✗
└── 身份文件：IDENTITY.md ✗  SOUL.md ✗  USER.md ✗
```

4. **展示完资产概览后，才向用户提问**，一次性问清楚两件事：
   - **迁移方式**：同机同步（快速路径，无需打包）还是导出备份/跨机器搬家（打包流程）；以及迁移方向（哪端 → 哪端）
   - **迁移范围**（多选），选项必须包含以下全部：
     - Skills（技能包）
     - 对话记录（sessions + projects/*.jsonl）
     - 配置文件（settings/mcp/models）
     - 身份文件（IDENTITY/SOUL/USER）
     - 工作区文件（对话目录下的产物/资料文件，可能较大）

   > **注意**：即使检测到双版并存，用户也可能想要的是跨机器备份，所以**迁移方式必须显式询问用户确认，不可自动假设**。
   > **多 uid 上下文**：导出时若源端有 >1 个 uid，**必须询问**用户是否一并导出其他用户的数据（`--all-users`），因为用户未必想把别人的数据打包带走。导入时无需询问，默认将所有源端 uid 映射到目标端 uid。

5. 根据用户的选择，进入对应流程：
   - **同机同步** → 走流程 C
   - **导出备份 / 跨机器搬家** → 走流程 A（+ 流程 B）

### 步骤 1：确认迁移包（仅导入意图时执行）

当用户明确表示"导入"时，**跳过资产扫描**，直接确认迁移包：

1. 询问用户是否已有导出包（`wb-assets-*.zip`）：
   - **有** → 询问包路径，进入流程 B
   - **没有** → 告知需要先在源端执行导出（流程 A），拿到包后再回来导入

---

### 流程 A：导出（备份或跨机器迁移）

1. **环境预检**：按上文"环境预检"章节完成 Python 可用性确认
2. 根据用户在步骤 0 中选择的迁移范围，构造 export 命令参数：
   - 不要对话记录 → `--no-conversations`
   - 要工作区文件 → `--with-workspaces`
   - 用户确认导出所有用户（步骤 0 中用户选择） → `--all-users`；否则不加（默认只导当前用户）
   - 排除当前对话 → `--exclude-session-id <当前session_id>`（先获取：环境变量或查询源端DB `SELECT id FROM sessions ORDER BY updated_at DESC LIMIT 1`）
3. 先运行 `export.py --source <path> --dry-run [其他参数]` → stdout 输出 JSON 计划
4. agent 解析 JSON，**重点呈现**：
   - 主包预估大小
   - `memory_export_reference`：说明只会生成 `memory-export.md` 供参考，Memory 需在目标客户端设置中同步
   - 如含工作区文件：每个目录的大小、排除后大小、预估 zip 大小
   - **`caveats` 段里的敏感物清单**（.env 文件数、私钥数、symlink 数等）—— 这些**默认会被带走**，agent 必须主动告知用户，让用户决定是否用 `--workspace-exclude-pattern '*.env'` 剔除
5. 用户确认后，运行 export（不带 dry-run）正式打包
6. **导出流程结束**。告知用户产出的 zip 路径、大小；如需导入到另一台机器/变体，用户可另行触发导入流程

### 流程 B：导入（跨环境迁移使用，或用户明确要求导入时直接进入）

1. **环境预检**：按上文"环境预检"章节完成 Python 可用性确认
2. 用户准备好迁移包后，运行 `import.py --package <zip> --target <path> --dry-run`（同机双版并存时 `--target` 必须显式指定目标路径，如 `~/.workbuddy-ai`）
3. agent 解析 dry-run 输出，呈现路径映射建议（同机迁移时路径无需重映射，跨机器时自动从 manifest 的 `source_home` 推断），让用户确认 `--path-map` 规则
4. 如果包内存在 `memory-export.md`，说明它只供人工参考，不会写入目标端本地 memory 文件；提示用户在目标客户端设置中同步 Memory
5. 用户确认后，运行 import（不带 dry-run）正式导入
6. macOS 上 WorkBuddy 自带 Python 可能会报 PermissionError: [Errno 1]，若发生在 WorkBuddy agent 沙箱内 → 优先尝试使用系统python → 若无效则引导用户放开沙箱后再执行
7. **导入流程结束**。告知用户导入结果、是否需要重启 WorkBuddy

> 导出和导入互不依赖——用户可以只导出不打导入（比如纯备份），可以隔很长时间再导入，也可以导出后在另一台机器上导入。

### 流程 C：同机迁移（cn ↔ intl 快速路径）

1. **环境预检**：按上文"环境预检"章节完成 Python 可用性确认
2. 根据用户在步骤 0 中选择的迁移范围，构造 migrate_inplace 命令参数：
   - 不要对话记录 → `--no-conversations`
   - 不要配置文件 → `--skip-configs`
   - 不要 DB 表 → `--skip-db`
   - 不要 skills → `--skip-skills`
   - 排除当前对话 → `--exclude-session-id <当前session_id>`（先获取：环境变量或查询源端DB `SELECT id FROM sessions ORDER BY updated_at DESC LIMIT 1`）
3. 先运行 `migrate_inplace.py --source <src_root> --target <dst_root> --dry-run [其他参数]` → stdout 输出 JSON 计划
4. agent 解析 JSON，向用户确认：
    - 源端数据概览（skills 数量、DB 行数、Memory 本地参考文件等）
    - 目标端已有数据概览
    - 本次将迁移的范围（根据用户选择）
5. 用户确认后，运行 migrate_inplace（不带 dry-run）正式迁移
6. **迁移完成**。告知用户结果、是否需要重启 WorkBuddy，并提示 Memory 请在客户端设置中同步

> 同机迁移是一步操作，不需要中间包、不需要传输。迁移前请退出 目标 WorkBuddy 客户端，否则 SQLite 写锁会拿不到。

---

### `--with-workspaces` 默认排除的内容

按 `references/workspace_excludes.md` 的清单——主要是 `node_modules/`、`.git/`、`dist/`、`__pycache__/`、`.venv/`、构建产物、缓存、本地 sqlite、镜像文件、`*.log` 等仓库型垃圾。

**注意**：临时对话目录（如 `~/WorkBuddy/2026-04-24-19-21-41`）通常不会包含这些大型排除项，但可能有 `.env`、脚本中的硬编码路径等，需关注 caveats 提示。

**不在默认排除清单**的：`.env`、私钥、secrets、credentials 等——这些是用户个人资产，默认全带，但 dry-run 会在 caveats 里列出，让 agent 转告用户做决定。

### 导入时的目录保障

即使不带 `--workspaces-package`，import.py 也会：

1. **`_ensure_workspace_dirs`**：读取目标 DB 中 `sessions.cwd`，在磁盘上创建缺失的工作目录（`mkdir -p`），确保 WorkBuddy 能打开导入的对话
2. **`_cleanup_leftover_project_dirs`**：首轮路径重写可能漏掉缺少 `meta.json` 的项目目录，此函数用 `decompress_workspace_path` 反推原始路径再重映射，把残余目录重命名或将文件搬入正确目录

### 重启提示

导入完成后 stdout 会自动打印"请重启 WorkBuddy"。哪些资产需要重启：DB 表、`models.json`、`settings.json`、`SOUL.md`、`USER.md`、`plugins/known_marketplaces.json`。哪些热加载：`mcp.json`、`IDENTITY.md`、`skills/`。Memory 不通过本地文件导入，请在客户端设置中同步。

## 已知问题与修复

### 导出时 UNIQUE constraint failed（DB 索引损坏）

**症状**：
```
sqlite3.IntegrityError: UNIQUE constraint failed: sessions.id
```

**根因**：`workbuddy.db` 的 `sqlite_autoindex_sessions_1`（sessions 表的 PK 索引）损坏：
- `PRAGMA integrity_check` 报 `wrong # of entries in index sqlite_autoindex_sessions_1` 和 `row N missing from index ...`
- 用 `SELECT id, COUNT(*) FROM sessions GROUP BY id HAVING COUNT(*) > 1` 看不出来（走的是正常索引）
- 但 `SELECT * FROM sessions NOT INDEXED` 能查到 N+ 行——`autoindex` 漏索引了一些行
- `REINDEX` 会失败（因为表里存在 PK 重复行）
- `VACUUM` / `VACUUM INTO` 也无法重建（依赖索引）

**修复**（已在 `scripts/lib/db.py` 的 `export_reduced_db` 内置）：
在 ATTACH 之前，对源 DB 的副本执行 `_dedup_duplicate_pks`：
1. 复制源 DB 到临时文件
2. 对每个有单列 PK 的表（sessions、session_usage 等），用 `NOT INDEXED` 读出**全部**行
3. 按 PK 去重，**保留 rowid 最大的那行**（最新插入的）
4. DROP TABLE → 用原 schema 重建 → 重新 INSERT 去重后的行
5. REINDEX 重建所有 autoindex

修复后 `PRAGMA integrity_check` 返回 `ok`，导出正常完成。

**适用版本**：所有版本的 `workbuddy-asset-migration` skill。原版的 `export.py` 没有这个修复，会在用户 DB 损坏时失败。

### macOS 上 Python 报 PermissionError: [Errno 1]

```
PermissionError: [Errno 1] Operation not permitted: '/Users/<用户>/.workbuddy/settings.json'
```

- 若发生在 WorkBuddy agent 沙箱内 → 优先尝试使用系统python → 若无效则让用户放开沙箱
- 若发生在用户终端手动执行 → 需在系统设置中为该 Python 授予完全磁盘访问权限

### Windows Git Bash 下 `$(date)` 生成文件名异常

**症状**：
```bash
cp workbuddy.db "workbuddy.db.bak-$(date +%Y%m%d-%H%M%S)"
# 提示成功，但 ls *.bak-* 找不到文件，或文件名末尾含不可见字符
```

**根因**：Git Bash 的 `date` 命令在 Windows 上输出 `\r\n`（CRLF）行尾。`$()` 命令替换会保留 `\r`（回车符），导致生成的文件名末尾含不可见字符 `\r`，shell glob 无法匹配。

**修复**：
- **方法 1（推荐）**：直接用 Python 生成时间戳，不依赖 shell `$(date)`：
  ```bash
  ts=$(python -c "from datetime import datetime; print(datetime.now().strftime('%Y%m%d-%H%M%S'))")
  cp workbuddy.db "workbuddy.db.bak-${ts}"
  ```
- **方法 2**：管道去除 `\r`：
  ```bash
  cp workbuddy.db "workbuddy.db.bak-$(date +%Y%m%d-%H%M%S | tr -d '\r')"
  ```
- **方法 3**：使用脚本内置的备份功能（Python `fs.backup()` / `fs.make_ts()` 已正确处理时区无关时间戳）。

## 内部参考

- 资产清单白名单：`references/asset_inventory.md`
- workspace 排除规则：`references/workspace_excludes.md`
- 完整 FAQ 与回滚步骤：`README.md`

---

## Credits / 作者

**Glen Wei（韦其像）** 创建并维护

- Email: glen.keeming@gmail.com
- 所属合集: [headhunter-skills](https://github.com/Glen-Wei/headhunter-skills)

觉得好用？欢迎去 GitHub 上 ⭐ Star [headhunter-skills](https://github.com/Glen-Wei/headhunter-skills) 支持持续维护。转载或修改本 Skill 时，请保留作者信息。
