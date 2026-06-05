# StoryForge — AI 编剧工作台

将小说文本自动转换为结构化、可编辑的 YAML 剧本。基于多 Agent 架构与 Story Graph 知识表示构建。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的 API Key
OPENAI_API_KEY=sk-xxxx
BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

### 3. 启动 Web UI

```bash
streamlit run ui/app.py
```

打开浏览器访问 http://localhost:8501，输入小说文本并配置模型后点击「开始转换」。

### 4. 命令行测试

```bash
python tests/test_pipeline.py
```

## 项目结构

```
story_wiki/
├── core/                   # 核心模块
│   ├── llm_client.py       # LLM 调用封装
│   ├── prompts.py          # Prompt 模板
│   ├── story_graph.py      # StoryGraph 数据模型
│   └── workflow.py        # StoryForgeWorkflow 编排器
├── agent/                  # 多 Agent 实现
│   ├── character_agent.py  # 角色提取 Agent
│   ├── scene_agent.py      # 场景解析 Agent
│   └── script_agent.py     # 剧本生成 Agent
├── pipeline/
│   └── orchestrator.py     # StoryPipeline 编排器
├── schema/
│   └── models.py           # 基础数据模型
├── ui/
│   └── app.py              # Streamlit Web UI
└── tests/
    ├── test_pipeline.py    # 端到端集成测试
    └── results/            # 测试输出示例
```

## 依赖

| 依赖 | 版本 | 用途 |
| --- | --- | --- |
| openai | >= 1.10.0 | LLM API 调用 |
| streamlit | >= 1.30.0 | Web 界面 |
| pyyaml | >= 6.0.1 | YAML 序列化 |
| pytest | >= 8.0.0 | 单元测试 |
| pytest-asyncio | >= 0.23.0 | 异步测试支持 |

## License
