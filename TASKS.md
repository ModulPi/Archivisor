\# Archivisor 开发任务清单（按顺序执行）



> \*\*使用说明\*\*：每次只让 AI 做一个任务。完成一个，勾掉一个，再进入下一个。



\## Phase 1：项目骨架与环境（1 天）

\- \[ ] TASK 1：创建目录结构（backend/, frontend/）

\- \[ ] TASK 2：生成 `requirements.txt`（仅含：pywin32, send2trash, psutil, pydantic）

\- \[ ] TASK 3：生成 `main.py` 骨架（含 stdio JSON-RPC 循环和心跳）



\## Phase 2：数据层（2 天）

\- \[ ] TASK 4：`core/db.py` —— 建表 SQL（含 FTS5），初始化数据库

\- \[ ] TASK 5：`models/schemas.py` —— Pydantic 模型（FileInfo, Plan, Manifest）



\## Phase 3：扫描器（2 天）

\- \[ ] TASK 6：`utils/security.py` —— 路径白名单/黑名单校验

\- \[ ] TASK 7：`utils/known\_folders.py` —— 通过 SHGetKnownFolderPath 获取 Windows 已知目录

\- \[ ] TASK 8：`core/scanner.py` —— 扫描器（os.scandir 递归，yield 逐条输出）



\## Phase 4：迁移引擎（3 天，最核心）

\- \[ ] TASK 9：`core/migrator.py` —— Plan 生成器（写入 migration\_manifest）

\- \[ ] TASK 10：`worker/io\_worker.py` —— Worker 进程（复制 + 校验 MD5）

\- \[ ] TASK 11：`core/migrator.py` —— Commit 阶段（软删除 + Junction 创建）

\- \[ ] TASK 12：`core/rollback.py` —— 回滚引擎（删除 Junction，恢复源目录）



\## Phase 5：UI 集成（2 天）

\- \[ ] TASK 13：Electron 端 stdio 通信（spawn Python 进程，收发 JSON）

\- \[ ] TASK 14：看板页面（调用 `scan` 方法，展示 3 个卡片）



\## Phase 6：测试与打包（1 天）

\- \[ ] TASK 15：PyInstaller 打包 `backend.exe`

\- \[ ] TASK 16：端到端测试（迁移 Desktop，回滚）

