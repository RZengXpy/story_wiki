# StoryForge MVP 5-6 复盘

> 本次复盘聚焦 MVP 5（补全 SKL）和 MVP 6（SKL → Screenplay），记录做了什么、解决了什么、为什么这样能解决，以及下一步目标。

---

## 一、MVP 5：补全 SKL（Relation / Event / Location / Timeline / Outline / Character Arc）

### 1.1 做了什么

| 模块 | 文件 | 内容 |
|------|------|------|
| RelationAgent | `agent/relation_agent.py`（新增） | 从章节文本中提取角色关系，类型覆盖 family/friend/enemy/romantic/professional/stranger |
| OutlineAgent | `agent/outline_agent.py`（新增） | 基于全文生成结构化大纲（genre / theme / main_conflict / arc_summary / act_summaries / key_plot_points） |
| GlobalStoryKnowledge | `core/knowledge_merger.py`（扩展） | 新增 `relations` / `events`（去重）/ `locations` / `timeline` / `outline` / `character_arcs` 字段 |
| knowledge_merger | `core/knowledge_merger.py` | 新增 `LocationInfo` / `TimelineEntry` / `CharacterArcEntry` 数据类；新增 `build_locations()` / `build_timeline()` / `build_character_arcs()` 派生字段构建方法 |
| workflow | `core/workflow.py` | 调用 RelationAgent + OutlineAgent，结果传入 `merge_chapters_to_skl()`；merger_report 新增 relation/event/location/timeline/character_arc 统计 |

### 1.2 解决了什么问题

**问题 1：SKL 结构不完整**

之前 `GlobalStoryKnowledge` 只包含角色和场景，缺少角色关系、事件、地点、时间线等核心知识。`StoryGraph.to_yaml()` 输出的剧本结构是残缺的。

**问题 2：事件无法跨章节追踪**

`EventAgent` 提取了事件，但事件是散落在各章的列表，无法：
- 汇总全局事件（去重）
- 构建场景地点的聚合分析
- 按时间顺序排列事件
- 按角色聚合其参与的事件（角色弧光）

**问题 3：故事缺乏宏观视角**

没有 story outline（大纲），无法知道故事的类型、主线冲突、幕结构、关键情节点。剧本生成缺乏结构约束。

### 1.3 为什么这样能解决

**RelationAgent** — 按章节独立提取关系，附加 SourceTrace 溯源，合并时按 `(from_char, to_char, relation_type)` 去重。每章提取保证不遗漏，全局去重保证不重复。

**OutlineAgent** — 基于全文（而非单章）生成大纲，保证宏观结构完整。覆盖 genre / theme / main_conflict，填补了"故事在讲什么"的认知空白。

**GlobalStoryKnowledge 派生字段** — `build_locations()` / `build_timeline()` / `build_character_arcs()` 在所有章节合并完成后执行，此时已有关键信息：
- 地点从场景 location 聚合，无需额外提取
- 时间线从事件的 `time_marker` 字段排序，按 dawn→midnight 映射
- 角色弧光从事件的 `participants` 字段按角色分组

**数据流**：`每章 LocalKnowledge` → `KnowledgeMerger.merge_all()` → `GlobalStoryKnowledge`（含派生字段）

派生字段在合并后构建而非提取时构建，是因为：
1. 合并后才有完整的 scene 列表（去重后）
2. 合并后才有完整的事件列表（去重后）
3. 避免重复计算（先提取再合并时已丢失顺序信息）

---

## 二、MVP 6：接入 ScriptAgent，SKL → Screenplay

### 2.1 做了什么

| 模块 | 文件 | 内容 |
|------|------|------|
| ScriptAgent | `agent/script_agent.py`（重构） | 新增 `write_scene()` / `write_all_scenes()`，支持以 SKL 上下文逐场景生成剧本 |
| prompts | `core/prompts.py` | 新增 `SCENE_SCREENPLAY_PROMPT`：action/dialogue 格式，含 character 字段 |
| workflow | `core/workflow.py` | 新增 `run_with_scripts()` 方法，完整 pipeline：SKL 构建 → 一致性检查 → 逐场景剧本生成 |
| story_graph | `core/story_graph.py` | `to_yaml()` 输出包含 `scripts` 字段 |
| 测试 | `tests/test_workflow_mvp6.py`（新增） | 端到端验证剧本生成 |

### 2.2 解决了什么问题

**问题 1：剧本生成能力缺失**

之前 pipeline 只能提取知识，无法生成实际剧本。题目核心要求"小说转剧本"只完成了一半。

**问题 2：剧本与知识图谱脱节**

传统剧本生成用 LLM 直接读小说文本，生成结果与提取的角色/场景/事件/关系不一致。生成的角色名可能和 SKL 中的不一致，场景细节可能和提取结果矛盾。

**问题 3：全量上下文注入的上下文爆炸**

如果把所有 SKL 一次性注入 prompt，单个场景生成时会包含大量无关角色、事件、关系，上下文很快溢出（尤其长篇小说）。

### 2.3 为什么这样能解决

**逐场景生成** — 每个 `SceneNode` 独立调用 LLM 生成剧本，而不是一次性生成全部剧本：
- 避免了上下文长度限制
- 每个场景可以精确控制注入的上下文

**SKL 上下文注入** — 生成场景剧本时，prompt 中包含：
- 该场景出现的角色信息（name / description / traits / role）
- 该场景相关的全局事件
- 该场景角色之间的关系
- 故事主线冲突（main_conflict）

这样生成剧本时，LLM 知道：
- 有哪些角色、他们是什么关系（对话有依据）
- 之前发生了什么事件（情节有连贯性）
- 故事主线是什么（方向不偏离）

**向后兼容** — `run()` 方法保持不变，新增 `run_with_scripts()` 提供完整剧本能力。已有集成不受影响。

---

## 三、整体架构（MVP 3-6）

```
小说文本
  │
  ▼
ChapterParser ────── 章节拆分
  │
  ▼
┌─────────────────────────────────┐
│  各 Agent 并行按章节提取          │
│  CharacterAgent / SceneAgent    │
│  EventAgent / RelationAgent    │
└─────────────────────────────────┘
  │
  ▼
LocalKnowledge（每章）───→ KnowledgeMerger.merge_all()
  │                              │
  │                              ▼
  │                     GlobalStoryKnowledge
  │                     （Single Source of Truth）
  │                              │
  │                    ┌──────────┴──────────┐
  │                    │                     │
  │                    ▼                     ▼
  │             ConsistencyChecker      派生字段构建
  │              （4类一致性检查）     locations / timeline /
  │                                   character_arcs / outline
  │                    │                     │
  │                    └──────────┬──────────┘
  │                               │
  │                               ▼
  │                         StoryGraph
  │                         （YAML 输出）
  │                               │
  │                    ┌──────────┴──────────┐
  │                    │                     │
  │                    ▼                     ▼
  │               run()                   run_with_scripts()
  │            （仅 SKL）              （SKL + 剧本）
  │                                        │
  │                                        ▼
  │                              ScriptAgent.write_scene()
  │                              （逐场景，SKL 上下文注入）
  │                                        │
  │                                        ▼
  │                               StoryGraph.scripts
  │                               （scene_id → 剧本内容）
  │                                        │
  │                                        ▼
  │                                  to_yaml()
  │                              （含 scripts 字段）
```

---

## 四、测试结果（text.md 雾港档案）

| 指标 | MVP 3 | MVP 4 | MVP 5 | MVP 6 |
|------|-------|-------|-------|-------|
| 章节 | 3 | 3 | 3 | 3 |
| 角色（去重后） | 6 | 6 | 6 | 6 |
| 场景（去重后） | 18 | 18 | 18 | 18 |
| 关系 | - | - | 13 | 13 |
| 事件 | 16 | 16 | 16 | 16 |
| 地点 | - | - | 16 | 16 |
| 时间线条目 | - | - | 16 | 16 |
| 角色弧光 | - | - | 5 个角色 | 5 个角色 |
| 大纲 | - | - | 已生成 | 已生成 |
| 一致性警告 | 6 | 6 | 6 | 6 |
| 生成剧本场景 | - | - | - | **18** |
| 剧本条目 | - | - | - | **~200+** |

---

## 五、下一步目标：MVP 7 — 知识层治理（Knowledge Layer Governance）

### 5.1 核心问题

当前 pipeline 各 Agent 独立提取知识，存在以下隐患：

- **跨 Agent 不一致**：CharacterAgent 提取的"林远"和 SceneAgent 提取的"林远"是同一个角色吗？
- **冲突未仲裁**：RelationAgent 说"A和B是朋友"，EventAgent 提取的事件却说"A打了B"——谁对？
- **知识静默错误**：LLM 幻觉导致角色名拼写错误、关系类型错误、事件逻辑矛盾
- **用户修正无回写**：用户在 UI 中修正了角色名，但 SKL 不会同步更新

### 5.2 为什么叫"知识治理"而非"检索"

之前的理解是 MVP 7 = RAG（检索增强生成），但这不对。**检索是生成手段，治理是质量保障**。

MVP 7 的核心不是"给剧本生成喂更好的上下文"（那是 RAG 的事），而是：
- 在 SKL 构建完成后，**对 SKL 本身做治理**
- 确保 SKL 是高质量的 Single Source of Truth
- 为后续所有依赖 SKL 的下游提供稳定、一致、可审计的知识基础

检索（RAG）可以作为 MVP 8 单独做——在知识治理完成后，用更精准的检索替代全量注入，解决上下文爆炸问题。

### 5.3 实现任务

- [ ] **ConflictResolver**：检测并仲裁跨 Agent 的知识冲突（如角色身份不一致、关系与事件矛盾）
- [ ] **SKL Validator**：对 GlobalStoryKnowledge 做完整性/一致性校验（必填字段、类型约束、跨字段约束）
- [ ] **KnowledgePatch**：接收用户修正，回写到 SKL 并级联更新受影响的下游（SceneGraph / scripts）
- [ ] **KnowledgeRevision**：基于一致性检查结果，自动修正可推断的错误（如拼写纠错、类型规范化）
- [ ] **AuditTrail**：记录 SKL 的每次变更，支持回溯和撤销
- [ ] **测试**：`test_knowledge_governance.py` 验证冲突检测和仲裁逻辑

### 5.4 知识治理在 pipeline 中的位置

```
SKL 构建（Local → Global）
       │
       ▼
┌─────────────────┐
│  知识治理层       │  ← MVP 7
│  · 冲突仲裁      │
│  · 一致性校验    │
│  · 知识修正      │
│  · 变更回写      │
└─────────────────┘
       │
       ▼
   StoryGraph（高质量）
       │
       ▼
   Screenplay（稳定输入）
```

### 5.5 后续：MVP 8 — RAG 精准检索

在 MVP 7 知识治理完成后，MVP 8 引入 RAG：
- 给 `ScriptAgent.write_scene()` 提供"刚刚好"的上下文
- 按需检索替代全量 SKL 注入
- 解决长篇小说的上下文爆炸问题

---

## 六、技术债务（待清理）

1. **API 调用效率**：每章并行调用 Agent（CharacterAgent / SceneAgent / EventAgent / RelationAgent），但仍为串行。3 章小说 = 12 次 API 调用（3×4）。可考虑 asyncio 并发，但需注意 API 限流。

2. **Scene deduplication 逻辑**：当前按 `(title, location)` 去重，相同地点不同场景会丢失。可考虑改为按 `title` 去重 + location 合并。

3. **UI 展示**：Streamlit UI 尚未展示 Events / Relations / Timeline / Outline 等 MVP 5 新增内容，MVP 6 的 scripts 标签页也未实现。

4. **OutlineAgent 在 outline 缺失时静默失败**：`except Exception: pass` 掩盖了真实错误，需改进错误处理。

5. **剧本生成顺序**：当前按 scenes 列表顺序生成，场景之间无因果保证。可考虑按 timeline 顺序生成，保证事件逻辑。

---

## 七、Git 提交记录

| Commit | 内容 |
|--------|------|
| `5d8159a` | feat: 章节感知的多 Agent 小说转剧本 pipeline（MVP 3-5） |
| `c8b3a39` | feat(mvp6): 接入 ScriptAgent，SKL → Screenplay 剧本生成 |
| `6dc27e1` | feat(mvp6): 接入 ScriptAgent，SKL → Screenplay 剧本生成（含 REVIEW_LOG.md 更新） |

| PR | 内容 |
|----|------|
| [#3](https://github.com/RZengXpy/story_wiki/pull/3) | MVP 3-5 |
| [#4](https://github.com/RZengXpy/story_wiki/pull/4) | MVP 6 |
