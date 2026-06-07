# StoryForge — AI 编剧工作台

将小说文本自动转换为结构化、可编辑的 YAML 剧本。基于多 Agent 架构与 Story Graph 知识表示构建。

## 核心哲学：知识优先，生成其次

StoryForge 探索的是一种**面向长篇小说改编的结构化生成架构**，而非简单的 `Novel → LLM → Screenplay` 管道。系统的核心信条是：

> **Knowledge First，Generation Second.**
>
> 先构建故事知识层（Story Knowledge Layer, SKL），再基于知识生成剧本。

这意味着：角色、场景、事件、关系等知识必须先被提取、合并、去重、治理，形成全局统一的 Single Source of Truth，再以此为上下文生成剧本。禁止任何模块直接回头读原始小说文本。

---

## 架构迭代过程

理解 StoryForge 的架构，需要回溯它是如何一步步走到今天的。每次迭代都解决了前一个方案的真实缺陷，而非凭空设计。

### 第一阶段：直接生成（`bc12044`）

```
小说文本 → LLM → 剧本
```

最早的版本：整篇小说塞进 prompt，LLM 直接输出剧本。**问题**：长文本上下文溢出、生成结果与原始情节不符、无法编辑中间产物。

### 第二阶段：分 Agent 抽取 + 拼接（MVP 1-2，`179bfec`）

```
小说文本
  │
  ├─→ CharacterAgent → 角色列表
  ├─→ SceneAgent → 场景列表
  ├─→ EventAgent → 事件列表
  ├─→ RelationAgent → 关系列表
  └─→ TimelineAgent / LocationAgent → 时间线 / 地点
  │
  ▼
全部拼接 → LLM → 剧本
```

每类知识一个 Agent 独立抽取。**问题**：
- 每章需要调用 4-6 次 LLM，成本高
- 多个 Agent 重复读取同一章节文本，产生理解偏差（CharacterAgent 眼中的"林远"和 EventAgent 眼中的"林远"可能不同）
- 缺乏跨 Agent 的知识一致性保障
- 各 Agent 独立去重，全局不准确

### 第三阶段：Local → Global 合并（MVP 3-4, `3442238` → `130f342`）

```
小说文本
  │
  ▼
ChapterParser ─── 章节拆分
  │
  ├─→ 第1章 ──→ LocalKnowledge(角色/场景/事件/关系)
  ├─→ 第2章 ──→ LocalKnowledge(角色/场景/事件/关系)
  └─→ 第3章 ──→ LocalKnowledge(角色/场景/事件/关系)
                    │
                    ▼
             KnowledgeMerger.merge_all()
                    │
                    ▼
          GlobalStoryKnowledge（SKL）
                    │
                    ▼
            ConsistencyChecker
                    │
                    ▼
              StoryGraph → YAML
```

关键进步：章节级提取 → 全局合并 → 去重 → 唯一事实源。但仍有多 Agent 重复读取问题。

### 第四阶段：SKL 补全（`5d8159a`, MVP 5）

```
SKL 新增字段：
  ├── relations       （RelationAgent 提取）
  ├── events          （EventAgent 去重合并）
  ├── locations       （从场景聚合）
  ├── timeline        （从事件 time_marker 排序）
  ├── character_arcs  （从事件 participants 按角色分组）
  └── outline         （OutlineAgent 基于全文生成）
```

此时 SKL 成为了真正的全局知识库，覆盖了角色、关系、事件、地点、时间线、大纲、角色弧光。但各 Agent 仍在重复读取章节文本。

### 第五阶段：统一知识抽取（`9252eb6`）— 架构质变

这是最关键的一次重构。之前的每个 Agent 都在独立读取章节文本，造成了大量重复调用和理解偏差。

```
之前（6次LLM/章）：
  Chapter → CharacterAgent.read()
  Chapter → SceneAgent.read()
  Chapter → EventAgent.read()
  Chapter → RelationAgent.read()
  Chapter → TimelineAgent.read()
  Chapter → LocationAgent.read()

重构后（1次LLM/章）：
  Chapter → UnifiedExtractionAgent.extract()
            → characters + scenes + events + relations + chapter_summary + chapter_goal + chapter_conflict
```

**一次 LLM 调用，同时抽取所有知识类型**，并携带 `SourceTrace` 溯源。这解决了：
- 理解偏差：同一章节只读一遍，结论一致
- 成本：3 章小说从 ~18 次调用降至 3 次
- 偏差可追溯：每条知识注明来源章节

### 第六阶段：知识治理（`3f5d2f7`, MVP 7）

Agent 的职责从"提取"变为"治理"：

```
GlobalStoryKnowledge（SKL）
  │
  ├─→ CharacterAgent.deduplicate()     角色去重 + 别名归并
  ├─→ CharacterAgent.assign_roles()     角色分配（主角/反派/配角）
  ├─→ EventAgent.merge_events()         事件去重 + 因果链构建
  └─→ KnowledgeGovernor.govern_skl()    冲突仲裁 + 一致性检查
  │
  ▼
治理后的 SKL（高质量、可审计）
```

**为什么叫"治理"而非"抽取"**：Agent 不再读取原文，而是对已有 SKL 进行质量提升。输入是 SKL，输出是更好的 SKL。

### 第七阶段：剧本生成（`c8b3a39`, `7e297f3`, MVP 6+）

```
GlobalStoryKnowledge（SKL）
  │
  ├─→ DirectorAgent.create_bible()     生成剧本圣经（Screenplay Bible）
  │     （基于 SKL 的全局视角，定义叙事风格/角色基调/对白规范）
  │
  ▼
SceneAgent.write_all_scenes()            并行生成（每个场景独立 LLM 调用）
  │
  ▼
各场景剧本（以 SKL 上下文注入，按场景过滤无关信息）
  │
  ▼
StoryGraph.scripts → YAML
```

剧本生成以 SKL 为唯一知识源，**按需检索**（当前场景涉及的角色/事件/关系）而非全量注入，解决了长篇小说的上下文爆炸问题。

### 第八阶段：持久化与历史（`6b66ccd`）

Pipeline 结果自动保存到 JSON 文件存储，支持从历史记录加载重建完整状态。

---

## 当前架构

```
小说文本
  │
  ▼
ChapterParser ──── 章节拆分
  │
  ▼
┌─────────────────────────────────────────┐
│  UnifiedExtractionAgent                  │
│  每章节 1 次 LLM 调用（重构后）          │
│  characters / scenes / events / relations│
│  + chapter_summary / chapter_goal /     │
│    chapter_conflict + SourceTrace         │
└─────────────────────────────────────────┘
  │
  ▼
LocalKnowledge ──→ KnowledgeMerger.merge_all()
  │                        │
  │                        ▼
  │              GlobalStoryKnowledge（SKL）
  │              Single Source of Truth
  │                        │
  │           ┌────────────┴────────────┐
  │           ▼                         ▼
  │     CharacterAgent             EventAgent
  │     · deduplicate()           · merge_events()
  │     · merge_aliases()         · build_causal_chains()
  │     · assign_roles()          · identify_key_events()
  │           │                         │
  │           └────────────┬────────────┘
  │                        ▼
  │               KnowledgeGovernor
  │                govern_skl()
  │           ┌────────────┴────────────┐
  │           ▼                         ▼
  │    ConsistencyChecker          派生字段构建
  │     （4类一致性检查）      locations / timeline /
  │                           character_arcs / outline
  │                        │
  │                        ▼
  │                  StoryGraph
  │                        │
  │           ┌──────────┴──────────┐
  │           ▼                      ▼
  │      run()              run_with_scripts()
  │   （仅 SKL）           （SKL + 剧本）
  │                                │
  │                                ▼
  │                        DirectorAgent.create_bible()
  │                                │
  │                                ▼
  │                      ScriptAgent.write_all_scenes()
  │                      （SKL 上下文注入，并行）
  │                                │
  │                                ▼
  │                          to_yaml()
```

---

## 功能特性

| 特性 | 说明 |
|------|------|
| **统一知识抽取** | 每章节仅 1 次 LLM 调用，同时抽取角色/场景/事件/关系，携带 SourceTrace 溯源 |
| **Agent 治理** | CharacterAgent / EventAgent 等对 SKL 进行去重、别名归并、角色分配、因果链构建 |
| **知识合并** | Local → Global 逐章合并，去重后构建 Single Source of Truth |
| **一致性检查** | 4 类检查（角色冲突 / 场景不一致 / 事件矛盾 / 时间线冲突） |
| **SKL 补全** | 自动构建地点聚合、时间线、角色弧光、故事大纲 |
| **剧本生成** | DirectorAgent 生成剧本圣经，ScriptAgent 以 SKL 为上下文逐场景并行生成标准格式剧本 |
| **YAML 输出** | 完整结构化剧本，含 characters / relations / events / scenes / scripts / warnings，配有完整 Schema 参考文档 |
| **历史管理** | Pipeline 结果自动持久化，支持从历史记录加载完整状态 |

---

## 设计原则（think.md）

| # | 原则 | 含义 |
|---|------|------|
| 一 | Single Source of Truth | GlobalStoryKnowledge 是所有模块的单一数据源，禁止直接读原文 |
| 二 | Knowledge First | 知识层质量决定剧本质量，生成是最后一步 |
| 三 | 统一知识抽取 | 每章节 1 次 LLM 调用，降低成本与理解偏差 |
| 四 | Agent 治理而非抽取 | Agent 负责 SKL 的去重/归一化/冲突仲裁，而非重复读原文 |
| 五 | Local → Global | 章节级 LocalKnowledge 逐步合并为 Global SKL |
| 六 | 可解释性 | 所有知识均携带 SourceTrace，追溯来源章节 |
| 七 | Knowledge Governance | 知识进入 SKL 前必须经过冲突检测与仲裁，保留审计记录 |
| 八 | Retrieval Before Generation | 生成剧本时按需检索相关知识，而非全量注入 |
| 九 | Story Graph 是知识视图 | Graph 是 SKL 的结构化表达，不是核心知识源 |
| 十 | Human Editable | YAML 允许人工编辑，修改后可重新生成 |

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 API Key
OPENAI_API_KEY=sk-xxxx
BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

### 3. 启动 Web UI

```bash
streamlit run ui/app.py
```

打开浏览器访问 <http://localhost:8501>，输入小说文本并配置模型后点击「开始转换」。

### 4. 命令行测试

```bash
# 单元测试（无需 API key）
pytest tests/test_chapter_parser.py tests/test_knowledge_merger.py tests/test_knowledge_governance.py tests/test_incremental.py tests/test_async_pipeline.py tests/test_mvp1_2.py tests/test_unified_extraction.py tests/test_agent_governance.py -v

# 集成测试（需要 API key）
pytest tests/test_workflow.py -v
```

---

## 项目结构

```
story_wiki/
├── core/                        # 核心模块
│   ├── llm_client.py           # LLM 调用封装
│   ├── prompts.py               # Prompt 模板
│   ├── story_graph.py           # StoryGraph 数据模型
│   ├── workflow.py             # StoryForgeWorkflow 编排器
│   ├── chapter_parser.py       # 章节解析
│   ├── knowledge_merger.py     # Local → Global 知识合并
│   ├── knowledge_governance.py  # 知识治理（冲突检测/仲裁/回写）
│   ├── consistency_checker.py  # 一致性检查
│   ├── incremental.py          # 章节级增量缓存
│   ├── async_pipeline.py       # 异步并行抽取管道
│   └── progress.py             # 进度追踪（LLM 调用计数）
├── agent/                       # Agent 实现
│   ├── unified_extraction_agent.py  # 统一抽取 Agent（每章 1 次 LLM）
│   ├── character_agent.py      # 角色 Agent（治理：去重/别名/角色分配）
│   ├── scene_agent.py          # 场景 Agent
│   ├── event_agent.py          # 事件 Agent（治理：合并/因果链）
│   ├── relation_agent.py       # 关系 Agent
│   ├── outline_agent.py        # 大纲 Agent
│   ├── script_agent.py         # 剧本生成 Agent（逐场景并行）
│   ├── location_agent.py       # 地点聚合 Agent
│   └── timeline_agent.py       # 时间线 Agent
├── schema/
│   ├── models.py               # 基础数据模型（Character/Scene/Event/Relation/SourceTrace 等）
│   ├── screenplay_schema.md    # YAML 剧本 Schema 定义文档
│   └── PLAYWRIGHT_YAML_SCHEMA.md  # YAML Schema 参考手册（含完整类型系统、设计原因与完整性约束）
├── ui/
│   └── app.py                  # Streamlit Web UI
├── data/                        # Pipeline 持久化存储（JSON 文件）
└── tests/
    ├── test_chapter_parser.py
    ├── test_knowledge_merger.py
    ├── test_knowledge_governance.py
    ├── test_unified_extraction.py
    ├── test_agent_governance.py
    ├── test_async_pipeline.py
    └── test_workflow.py
```

---

## 输出格式

完整 Schema 参考见 [`schema/PLAYWRIGHT_YAML_SCHEMA.md`](schema/PLAYWRIGHT_YAML_SCHEMA.md)（含完整类型系统、每个字段的设计原因与完整性约束）。快速入门级定义见 [`schema/screenplay_schema.md`](schema/screenplay_schema.md)。

### 快速示例

```yaml
story_graph:
  version: "1.0"
  metadata:
    title: "雾港档案"
    genre: "thriller"
  characters:
    - id: "林川"
      name: "林川"
      role: "protagonist"
  scenes:
    - id: "scene_001"
      title: "图书馆相遇"
      location: "雾港镇图书馆"
  scripts:
    scene_001:
      content:
        - type: "action"
          text: "图书馆内，灯光昏暗。"
        - type: "dialogue"
          character: "林川"
          text: "请问，您需要什么？"
  warnings: []
```

---

## 依赖

| 依赖 | 版本 | 用途 |
| --- | --- | --- |
| openai | >= 1.10.0 | LLM API 调用 |
| streamlit | >= 1.30.0 | Web 界面 |
| pyyaml | >= 6.0.1 | YAML 序列化 |
| pytest | >= 8.0.0 | 单元测试 |
| pytest-asyncio | >= 0.23.0 | 异步测试支持 |

---

## Demo 视频

请将 demo 视频上传至 bilibili / 云盘等外部平台，然后将链接填入下方：

[![StoryForge Demo 视频]](YOUR_DEMO_VIDEO_URL_HERE)

> 上传后将 `YOUR_DEMO_VIDEO_URL_HERE` 替换为实际的视频链接地址。

---

## License
