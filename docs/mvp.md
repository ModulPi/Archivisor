一、系统总览

你正在构建一个本地优先的文件治理引擎（Deterministic File System Engine）。



能力	说明

文件扫描与索引	扫描用户目录，提取元数据入 SQLite

安全迁移文件	复制 → 校验 → 软删除 → 创建 Junction

可回滚机制	任意迁移操作可一键撤回

简单数据看板	磁盘占用、大文件 Top N、未迁移列表

❌ 不包含：AI / Agent / LLM / 自动决策 / 语义理解 / 事件驱动自治



🏗 二、系统架构

text

Electron（UI层）

&#x20;       ↓ stdio JSON-RPC（每行一个 JSON，\\n 分隔）

Python（核心引擎）

&#x20;       ↓

┌───────────────────────────────────────────┐

│  Scanner → SQLite(FTS5) → Migration Engine │

│                              ↓             │

│                        Verifier           │

│                              ↓             │

│                   Rollback Engine          │

└───────────────────────────────────────────┘

通信协议（强制）

Electron 通过 child\_process.spawn 启动 backend.exe



协议：stdio JSON-RPC（禁 HTTP，避免端口冲突）



心跳：Python 每 5 秒输出 {"type":"heartbeat"}



指令示例：{"id":1,"method":"scan","params":{"root\_path":"C:\\\\Users\\\\A\\\\Desktop"}}



响应示例：{"id":1,"result":{"total\_files":100,"total\_size":1073741824}}



📦 三、项目目录结构（强制，LLM 请按此生成）

text

backend/

├── main.py                 # 入口：启动子进程，建立 stdio 服务

├── core/

│   ├── \_\_init\_\_.py

│   ├── scanner.py          # 扫描器（os.scandir 递归，yield 逐条返回）

│   ├── migrator.py         # 迁移引擎（Plan → Copy → Verify → Commit）

│   ├── rollback.py         # 回滚引擎（删除 Junction，恢复源文件夹）

│   └── db.py               # SQLite 管理（含 FTS5 虚拟表，WAL 模式）

├── worker/

│   ├── \_\_init\_\_.py

│   └── io\_worker.py        # 继承 multiprocessing.Process，执行重 IO 任务

├── utils/

│   ├── \_\_init\_\_.py

│   ├── junction.py         # 封装 mklink /J 和 os.rmdir

│   ├── known\_folders.py    # SHGetKnownFolderPath 获取 Windows 已知目录

│   └── security.py         # 路径安全校验（禁止系统目录）

└── models/

&#x20;   ├── \_\_init\_\_.py

&#x20;   └── schemas.py          # Pydantic 模型（Plan, Manifest, FileInfo）

🗄️ 四、数据库设计（db.py）

文件路径：%APPDATA%/Archivisor/data.db



建表 SQL（必须包含 FTS5）

sql

PRAGMA journal\_mode=WAL;

PRAGMA mmap\_size=268435456;  -- 256MB



\-- 【修正】path 不是主键，用自增 id（避免迁移时路径变更导致索引重建）

CREATE TABLE file\_metadata (

&#x20;   id INTEGER PRIMARY KEY AUTOINCREMENT,

&#x20;   path TEXT UNIQUE NOT NULL,

&#x20;   name TEXT NOT NULL,

&#x20;   extension TEXT DEFAULT '',

&#x20;   size INTEGER DEFAULT 0,

&#x20;   modified\_time REAL,          -- 时间戳

&#x20;   is\_active INTEGER DEFAULT 1  -- 0 表示已迁移/软删除，保留历史

);

CREATE INDEX idx\_path ON file\_metadata (path);

CREATE INDEX idx\_is\_active ON file\_metadata (is\_active);



\-- FTS5 虚拟表（解决 LIKE '%keyword%' 全表扫描问题）

CREATE VIRTUAL TABLE file\_fts USING fts5(name, path, content=file\_metadata);



\-- 迁移清单（记录每次迁移，用于回滚和 7 天清理）

CREATE TABLE migration\_manifest (

&#x20;   id INTEGER PRIMARY KEY AUTOINCREMENT,

&#x20;   source\_path TEXT NOT NULL,

&#x20;   target\_path TEXT NOT NULL,

&#x20;   source\_renamed\_to TEXT,      -- 软删除时重命名的路径（回滚时恢复）

&#x20;   status TEXT DEFAULT 'pending', -- pending | copying | verified | committed | rolled\_back

&#x20;   file\_count INTEGER DEFAULT 0,

&#x20;   total\_size INTEGER DEFAULT 0,

&#x20;   created\_at REAL DEFAULT (strftime('%s', 'now')),

&#x20;   committed\_at REAL

);

⚙️ 五、核心模块详细规格

5.1 扫描器（scanner.py）

函数签名：



python

def scan\_directory(root\_path: str, yield\_every: int = 100) -> Generator\[dict, None, None]:

&#x20;   """

&#x20;   递归扫描目录，yield 文件元数据。

&#x20;   每扫描 yield\_every 个文件，yield 一个进度事件。

&#x20;   主动跳过：C:\\Windows, C:\\Program Files, AppData\\Local\\Temp

&#x20;   """

扫描范围硬限制（security.py）：



python

ALLOWED\_ROOTS = \[

&#x20;   "Desktop", "Downloads", "Documents", "Pictures", "Music", "Videos"

]

FORBIDDEN\_PREFIXES = \[

&#x20;   "C:\\\\Windows", "C:\\\\Program Files", "C:\\\\Program Files (x86)",

&#x20;   "C:\\\\System Volume Information", "C:\\\\$Recycle.Bin"

]

5.2 迁移引擎（migrator.py）—— 核心补丁：软删除策略

⚠️ 禁止直接 send2trash（跨盘符会静默失败）。改用“软删除 + 7天后用户确认”。



完整流水线：



阶段	动作	状态

Plan	生成迁移清单，写入 migration\_manifest，状态 pending	pending

Copy	Worker 逐文件 shutil.copy2 到目标盘（保留元数据）	copying

Verify	小文件（<10MB）：比对 size + modified\_time；大文件：比对 MD5	verified

Commit	① 将源文件夹重命名为 {name}\_Archived\_{YYYYMMDD}；② 记录 source\_renamed\_to；③ 创建 Junction；④ 状态 committed	committed

Cleanup（7天后）	用户确认后，send2trash 删除 source\_renamed\_to 目录	—

函数签名：



python

def create\_migration\_plan(source: str, target: str, filters: list\[str]) -> dict:

&#x20;   """生成 Plan，写入 manifest，返回 plan\_id"""



def execute\_migration(plan\_id: int, worker\_queue: Queue) -> bool:

&#x20;   """Worker 中执行复制 + 校验，返回成功/失败"""



def commit\_migration(plan\_id: int) -> bool:

&#x20;   """软删除源文件夹 + 创建 Junction"""

5.3 回滚引擎（rollback.py）

触发条件：用户点击“撤回” / 迁移中断 / 校验失败



回滚动作（必须原子）：



删除 Junction（os.rmdir——只删链接，不删目标数据）



将 source\_renamed\_to 重命名回原始路径



状态标记 rolled\_back



错误处理：若目标盘数据已被用户手动删除，跳过恢复步骤，仅重建 Junction。



5.4 Worker 模型（io\_worker.py）—— Windows 兼容补丁

python

import multiprocessing as mp

ctx = mp.get\_context("spawn")  # Windows 必须用 spawn，不能 fork

worker = ctx.Process(target=io\_task, args=(task\_queue, result\_queue))

5.5 Junction 管理器（junction.py）

python

def create\_junction(source: str, target: str) -> bool:

&#x20;   """调用 mklink /J，需管理员权限，失败时抛出详细异常"""



def remove\_junction(source: str) -> bool:

&#x20;   """os.rmdir(source) —— 仅当 source 是 Junction 时安全"""



def is\_junction(path: str) -> bool:

&#x20;   """检查路径是否为 Junction"""

📊 六、看板系统（简化）

只保留三类信息（查询走 FTS5 + 聚合）：



磁盘占用：C盘 / D盘 用户数据总量



大文件 Top 20：按 size DESC 排序



未迁移列表：is\_active=1 且路径仍在 C 盘用户目录



🚫 七、明确限制（MVP 禁止）

禁止项	说明

❌ AI / Agent	无 LLM 调用，无 Embedding

❌ 自动决策	所有迁移必须用户点击“执行”

❌ 语义理解	搜索只用 FTS5 关键词匹配

❌ 文件内容解析	不读 PDF/Word/图片内容

❌ 事件驱动自治	无 watchdog 自动触发迁移

🎯 八、MVP 成功标准（验收）

扫描 10 万文件（含桌面/下载）< 10s，UI 不卡顿



迁移 50GB 数据至 D 盘，中途强制终止进程，重启后数据无损



任意迁移均可一键回滚



代码中 不存在 os.remove 或 shutil.rmtree（除软删除 7 天后用户二次确认）



跨盘符迁移后，Junction 指向正确，软件（微信/Office）无感知



🆕 九、MVP 补充功能（v1.1）

9.1 关键词搜索
- 搜索框输入关键词，FTS5 MATCH 查询文件名
- 结果列表：文件名 / 路径 / 大小 / 右键操作

9.2 右键菜单
- 文件列表右键 → "打开文件所在文件夹"
- Electron shell.showItemInFolder()

9.3 空间预警
- C 盘剩余 < 10GB → 顶部红色提醒 + 一键跳迁移
- 每 30s 轮询

9.4 迁移效果对比
- 迁移完成后显示 "C 盘释放了 XX GB"
- 迁移前后盘空间差值

9.5 重复文件检测
- 同 size 文件 → MD5 比对 → 列出重复组
- 用户手动选择删除，不自动删

9.6 临时文件建议
- 自动标记 *.tmp / ~$* / %TEMP% 文件
- 汇总展示占用 + 一键清理

