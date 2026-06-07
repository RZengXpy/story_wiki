# StoryForge — AI 编剧工作台

将小说文本自动转换为结构化、可编辑的 YAML 剧本。基于多 Agent 架构与 Story Graph 知识表示构建。

## 功能特性

- **统一知识抽取**：每章节仅 1 次 LLM 调用，一次性抽取角色/场景/事件/关系，携带 SourceTrace 溯源（符合 think.md 原则三）
- **Agent 治理**：CharacterAgent / EventAgent 负责知识去重、别名合并、因果链构建、角色分配等治理工作（原则四）
- **知识合并**：Local → Global 逐章合并，去重后构建 Single Source of Truth
- **一致性检查**：4 类检查（角色冲突 / 场景不一致 / 事件矛盾 / 时间线冲突）
- **SKL 补全**：自动构建地点聚合、时间线、角色弧光、故事大纲
- **剧本生成**：以 SKL 为上下文逐场景生成标准格式剧本（action/dialogue）
- **YAML 输出**：完整结构化剧本，含 characters / relations / events / scenes / scripts / warnings
- **增量更新**：基于内容哈希的章节级缓存，仅重新抽取有变化的部分

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

## 项目结构

```text
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
│   ├── character_agent.py      # 角色 Agent（抽取 + 治理）
│   ├── scene_agent.py          # 场景 Agent
│   ├── event_agent.py          # 事件 Agent（抽取 + 治理）
│   ├── relation_agent.py       # 关系 Agent
│   ├── outline_agent.py        # 大纲 Agent
│   ├── script_agent.py         # 剧本生成 Agent
│   ├── location_agent.py       # 地点聚合 Agent
│   └── timeline_agent.py       # 时间线 Agent
├── schema/
│   ├── models.py               # 基础数据模型（Character/Scene/Event/Relation/SourceTrace 等）
│   └── screenplay_schema.md    # YAML 剧本 Schema 定义文档
├── ui/
│   └── app.py                   # Streamlit Web UI
└── tests/
    ├── test_chapter_parser.py     # 章节解析单元测试
    ├── test_knowledge_merger.py  # 知识合并单元测试
    ├── test_knowledge_governance.py # 知识治理单元测试
    ├── test_unified_extraction.py  # 统一抽取测试
    ├── test_agent_governance.py   # Agent 治理测试
    ├── test_async_pipeline.py      # 异步并行测试
    └── test_workflow.py           # 端到端集成测试
```

## 架构概览

```
小说文本
  │
  ▼
ChapterParser ──── 章节拆分
  │
  ▼
┌─────────────────────────────────┐
│  UnifiedExtractionAgent          │
│  每章节 1 次 LLM 调用            │
│  同时抽取 characters / scenes   │
│  / events / relations + SourceTrace│
└─────────────────────────────────┘
  │
  ▼
LocalKnowledge ──→ KnowledgeMerger.merge_all()
  │                        │
  │                        ▼
  │               GlobalStoryKnowledge
  │               （Single Source of Truth）
  │                        │
  │          ┌────────────┴────────────┐
  │          ▼                         ▼
  │    CharacterAgent              EventAgent
  │    · deduplicate()            · merge_events()
  │    · merge_aliases()          · build_causal_chains()
  │    · assign_roles()           · identify_key_events()
  │          │                         │
  │          └────────────┬────────────┘
  │                       ▼
  │              KnowledgeGovernor
  │               govern_skl()
  │          ┌────────────┴────────────┐
  │          ▼                         ▼
  │   ConsistencyChecker          派生字段构建
  │    （4类一致性检查）   locations / timeline /
  │                          character_arcs / outline
  │                        │
  │                        ▼
  │                  StoryGraph
  │                        │
  │            ┌──────────┴──────────┐
  │            ▼                      ▼
  │       run()              run_with_scripts()
  │    （仅 SKL）           （SKL + 剧本）
  │                                │
  │                                ▼
  │                        ScriptAgent.write_scene()
  │                        （逐场景，SKL 上下文注入）
  │                                │
  │                                ▼
  │                          to_yaml()
  │                      （含 scripts 字段）
```

### 设计原则（think.md）

- **原则一：Single Source of Truth** — GlobalStoryKnowledge 是所有模块的单一数据源
- **原则二：知识优先，生成其次** — 知识层质量决定剧本质量
- **原则三：统一知识抽取** — 每章节 1 次 LLM 调用，降低成本与理解偏差
- **原则四：Agent 治理而非抽取** — Agent 负责 SKL 的去重/归一化，而非重复读取原文
- **原则五：Local → Global** — 章节级 LocalKnowledge 逐步合并为 Global SKL
- **原则六：可解释性** — 所有知识均携带 SourceTrace，追溯来源章节

## 输出格式

完整 Schema 定义见 [`schema/screenplay_schema.md`](schema/screenplay_schema.md)。

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

完整示例请参考 [`schema/screenplay_schema.md`](schema/screenplay_schema.md)。

## 依赖

| 依赖 | 版本 | 用途 |
| --- | --- | --- |
| openai | >= 1.10.0 | LLM API 调用 |
| streamlit | >= 1.30.0 | Web 界面 |
| pyyaml | >= 6.0.1 | YAML 序列化 |
| pytest | >= 8.0.0 | 单元测试 |
| pytest-asyncio | >= 0.23.0 | 异步测试支持 |

## Demo 视频

请将 demo 视频上传至 bilibili / 云盘等外部平台，然后将链接填入下方：

[![StoryForge Demo 视频]](YOUR_DEMO_VIDEO_URL_HERE)

> 上传后将 `YOUR_DEMO_VIDEO_URL_HERE` 替换为实际的视频链接地址。

## 开发记录

详见 `REVIEW_LOG.md`。

## License
