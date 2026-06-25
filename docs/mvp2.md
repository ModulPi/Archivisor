一、系统定位

Agent 是一个自然语言 → 文件操作计划的转换器。



能力	说明

意图识别	判断用户想“移动/搜索/清理”

参数提取	从句子中抽取 source/target/filter/time

计划生成	输出结构化 JSON，供 UI 预览

主动建议	基于事件触发“是否整理”提醒（不自动执行）

语义搜索	文件名 + 路径的混合检索（BM25 + Embedding）

❗ 不执行文件操作 / 不直接访问磁盘 / 不控制系统资源



🏗 二、系统架构

text

用户输入

&#x20;  ↓

┌──────────────────────────────────────────────┐

│  Agent 规划层（Python）                      │

│                                               │

│  1. Intent Classifier (MiniLM + 规则)        │

│     ↓                                        │

│  2. Slot Extractor (LLM结构化抽取 / spaCy)   │

│     ↓                                        │

│  3. Context Merger (环形缓冲区，指代消解)    │

│     ↓                                        │

│  4. Plan Generator (生成 JSON Plan)          │

└──────────────────────────────────────────────┘

&#x20;  ↓ Plan 预览（UI 展示）

&#x20;  ↓ 用户点击“确认”

&#x20;  ↓

MVP 执行引擎（文件一中的确定性模块）

🧠 三、核心模块详细规格

3.1 意图识别器（intent\_classifier.py）

技术：all-MiniLM-L6-v2（延迟加载：首次输入时载入，\~80MB）



模板库（intents.json）：



json

\[

&#x20; {"id":"move","keywords":\["移动","归档","整理","搬到","归类"],"api":"migration\_engine.start"},

&#x20; {"id":"search","keywords":\["找","搜索","定位","哪里","在哪儿"],"api":"search\_engine.query"},

&#x20; {"id":"cleanup","keywords":\["清理","删除","释放","空间","腾出"],"api":"migration\_engine.cleanup"}

]

匹配逻辑：



关键词精确命中 → 直接返回



计算 Embedding 余弦相似度，取 Top1



若置信度 < 0.7（补丁：人机回环） → 返回澄清选项：“您是想要 A.移动文件 B.搜索文件 C.查看空间 吗？”



输出：



python

{"intent": "move", "confidence": 0.92}

3.2 参数提取器（slot\_extractor.py）

方案：LLM 结构化抽取（主） + 正则兜底（备）



Prompt 模板（传给 DeepSeek API）：



text

从用户指令中提取文件操作参数，输出 JSON。

字段：source\_path（源目录，无则 null）, target\_path（目标目录，无则 null）, file\_filter（扩展名/关键词，无则 null）, time\_range（如"上个月"，无则 null）

指令："{user\_input}"

示例：



输入："把下载文件夹里上个月的PDF移到合同目录"



输出：{"source":"Downloads","target":"合同","filter":"pdf","time":"last\_month"}



降级方案：LLM 不可用时，回退到基于 spaCy 的 NER + 硬编码规则。



3.3 上下文管理器（context\_manager.py）—— 补丁：环形缓冲区

数据结构：



python

context\_buffer = \[]  # 最近 3 轮，每轮为 {"query": str, "results": list, "filters": dict}

逻辑：



“把这些移到 D 盘” → 取上一轮 results 作为 source



“不，我说的是截图” → 取上一轮 filters，修正 type 为 screenshot 后重查



应用退出即清空（无持久化）



3.4 计划生成器（plan\_generator.py）

输入：intent + slots + context



输出示例（可直接提交给 MVP Engine）：



json

{

&#x20; "plan\_id": "plan\_20260126\_001",

&#x20; "operations": \[

&#x20;   {"type":"scan","path":"C:\\\\Users\\\\A\\\\Downloads"},

&#x20;   {"type":"filter","extensions":\["pdf"],"time\_range":\["2025-12-01","2025-12-31"]},

&#x20;   {"type":"copy","target\_root":"D:\\\\UserData\\\\Documents\\\\Contracts"},

&#x20;   {"type":"verify"},

&#x20;   {"type":"commit\_soft\_delete"}

&#x20; ],

&#x20; "requires\_confirmation": true

}

🔔 四、主动建议系统（被动 AI）

触发条件（基于 MVP 的 behavior\_baseline 统计）：



当前写入量 > 历史中位数 + 3 \* 标准差（避免解压大型安装包时误报）



C 盘剩余空间 < 5GB



单次新增文件总大小 > 2GB



冷却期：同一目录触发建议后，记录 last\_suggest\_time，24 小时内不重复提醒。



输出：UI 右上角气泡 → 用户点击“采纳” → 生成 Plan → 走确认流程。



🔍 五、混合搜索系统（search\_engine.py）

方案：BM25（FTS5） + 向量（sqlite-vec）双路召回 → RRF 融合排序



召回源	技术	召回数

关键词匹配	SQLite FTS5（BM25）	Top 50

语义相似	sqlite-vec（文件名 + 父文件夹名 Embedding）	Top 50

融合排序：RRF（Reciprocal Rank Fusion）输出 Top 10



可解释性：结果下方标注匹配原因（“✅ 文件名含关键词” / “✅ 路径语义相似”）



限制：❌ 不解析文件内容（PDF/Word/图片不解码）



🧯 六、安全红线（硬编码约束）

python

FORBIDDEN\_PATHS = \[

&#x20;   "C:\\\\Windows", "C:\\\\Program Files", "C:\\\\Program Files (x86)",

&#x20;   "C:\\\\System Volume Information"

]



def is\_safe\_path(path: str) -> bool:

&#x20;   return not any(path.startswith(p) for p in FORBIDDEN\_PATHS)



\# Agent 生成的所有 Plan 必须经过 is\_safe\_path 校验

\# 若包含禁止路径，直接拒绝执行并记录审计日志

规则	说明

❌ AI 不直接操作文件	所有写入走 MVP Engine

❌ AI 不自动执行	必须用户点击“确认”

❌ AI 不访问系统目录	路径安全校验前置

❌ AI 不自动生成 Skill	无自我学习机制

✔ 唯一执行者	MVP 确定性引擎

📊 七、成功指标（验收）

指标	目标值

意图识别准确率	> 85%（20 条测试指令）

计划用户接受率	> 70%

误执行率	0%

意图分类延迟	< 50ms（本地 Embedding）

混合搜索延迟（10 万文件）	< 600ms

云端 LLM 单日调用量	< 50 次（超出降级本地）

🧩 八、最终系统结构图

text

&#x20;           ┌──────────────────┐

&#x20;           │   Electron UI    │

&#x20;           │  对话/看板/预览   │

&#x20;           └────────┬─────────┘

&#x20;                    │ stdio JSON-RPC

&#x20;           ┌────────▼─────────┐

&#x20;           │  Agent 规划层    │  ← 本次构建

&#x20;           │ (理解+生成计划)  │

&#x20;           └────────┬─────────┘

&#x20;                    │ Plan JSON（用户确认后）

&#x20;           ┌────────▼─────────┐

&#x20;           │ MVP 确定性引擎   │  ← 文件一已构建

&#x20;           │ (文件系统操作)   │

&#x20;           └──────────────────┘






🆕 九、MVP2 Agent 功能规划

9.1 语义搜索
- 方案: Embedding 向量 + BM25(FTS5) 双路召回 → RRF 融合
- 示例: "帮我找上个月的PDF合同" → 自动提取关键词 + 时间过滤
- 技术: sqlite-vec + all-MiniLM-L6-v2

9.2 智能清理建议
- 基于规则 + LLM: 识别长期未用/重复/临时文件
- LLM 判断候选文件是否可清理并附解释
- 用户审核后手动执行

9.3 自然语言迁移
- 用户输入 "把下载的图片移到D盘"
- Agent: 意图识别(move) → 参数提取(Downloads/*.png) → 生成 Plan
- 用户确认后提交 MVP 引擎执行

9.4 主动行为建议
- 基于行为基线: 写入量 > μ+3σ / C盘<5GB / 单次新增>2GB
- 右下角气泡提醒 → 用户点击采纳 → 生成 Plan → 确认执行
- 冷却期: 24h 不重复提醒

9.5 人机回环
- 置信度 < 0.7 → 返回澄清选项而非执行
- 所有 AI 操作需用户二次确认
- 路径安全校验前置 (is_safe_path)
