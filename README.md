# StoryForge — AI 编剧工作台

将小说文本自动转换为结构化、可编辑的 YAML 剧本。基于多 Agent 架构与 Story Graph 知识表示构建。

## 功能特性

- **章节感知提取**：按章节粒度并行提取角色、场景、事件、关系，携带溯源信息
- **知识合并**：Local → Global 逐章合并，去重后构建 Single Source of Truth
- **一致性检查**：4 类检查（角色冲突 / 场景不一致 / 事件矛盾 / 时间线冲突）
- **SKL 补全**：自动构建地点聚合、时间线、角色弧光、故事大纲
- **剧本生成**：以 SKL 为上下文逐场景生成标准格式剧本（action/dialogue）
- **YAML 输出**：完整结构化剧本，含 characters / relations / events / scenes / scripts / warnings

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
pytest tests/test_chapter_parser.py tests/test_knowledge_merger.py tests/test_knowledge_governance.py tests/test_incremental.py tests/test_async_pipeline.py tests/test_mvp1_2.py -v

# 集成测试（需要 API key）
pytest tests/test_workflow.py tests/test_workflow_mvp4.py tests/test_workflow_mvp5.py tests/test_workflow_mvp6.py -v
pytest tests/test_pipeline.py tests/test_event_agent.py -v
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
│   └── consistency_checker.py  # 一致性检查
├── agent/                       # 多 Agent 实现
│   ├── character_agent.py      # 角色提取 Agent
│   ├── scene_agent.py          # 场景解析 Agent
│   ├── event_agent.py          # 事件提取 Agent
│   ├── relation_agent.py       # 关系提取 Agent
│   ├── outline_agent.py        # 大纲生成 Agent
│   └── script_agent.py         # 剧本生成 Agent
├── pipeline/
│   └── orchestrator.py          # StoryPipeline 编排器
├── schema/
│   ├── models.py               # 基础数据模型
│   └── screenplay_schema.md    # YAML 剧本 Schema 定义文档
├── ui/
│   └── app.py                   # Streamlit Web UI
└── tests/
    ├── test_chapter_parser.py   # 章节解析单元测试
    ├── test_knowledge_merger.py # 知识合并单元测试
    ├── test_workflow_mvp4.py   # MVP 4 集成测试
    ├── test_workflow_mvp5.py   # MVP 5 集成测试
    └── test_workflow_mvp6.py   # MVP 6 集成测试
```

## 架构概览

```text
小说文本
  │
  ▼
ChapterParser ──── 章节拆分
  │
  ▼
┌─────────────────────────────────┐
│  各 Agent 并行按章节提取          │
│  CharacterAgent / SceneAgent     │
│  EventAgent / RelationAgent     │
│  OutlineAgent（全文）           │
└─────────────────────────────────┘
  │
  ▼
LocalKnowledge ──→ KnowledgeMerger.merge_all()
  │                        │
  │                        ▼
  │               GlobalStoryKnowledge
  │               （Single Source of Truth）
  │                        │
  │             ┌──────────┴──────────┐
  │             ▼                      ▼
  │      ConsistencyChecker     派生字段构建
  │       （4类一致性检查）    locations / timeline /
  │                            character_arcs / outline
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
