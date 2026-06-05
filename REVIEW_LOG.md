# StoryForge 开发复盘日志

> 不上传 GitHub，仅供后续复盘查看

---

## 2026-06-05 开发记录

### 本次目标
实现 MVP 3（章节解析 + 事件溯源）和 MVP 4（知识合并 + 一致性检查），测试通过后提交 GitHub。

---

## MVP 3：章节解析 + 事件溯源

### 做了什么

1. **新增 `core/chapter_parser.py`**
   - 实现 `parse_chapters()` 函数，按"第X章：标题"正则匹配拆分小说
   - 返回 `Chapter` dataclass：id / number / title / content / start_char / end_char
   - 支持无章节小说的降级处理（fallback 到 ch_001 "全文"）
   - 提供 `get_chapter_by_id()` 查找函数

2. **新增 `agent/event_agent.py`**
   - 实现 `EventAgent` 类，`extract_events()` 从单章提取事件
   - `extract_events_from_chapters()` 遍历所有章节
   - 事件类型：conflict / revelation / transition / turning_point / resolution
   - 每条事件携带 `source: {chapter_id, chapter_title}` 溯源字段

3. **扩展 `schema/models.py`**
   - 新增 `SourceTrace` dataclass
   - `Character` 和 `Scene` 新增 `source: Optional[SourceTrace]` 字段

4. **改造 `agent/character_agent.py` 和 `scene_agent.py`**
   - 新增 `extract_from_chapters()` / `parse_from_chapters()` 方法
   - 分章节提取知识，每个结果附加 SourceTrace

5. **重写 `core/workflow.py`**
   - `StoryForgeWorkflow.run()` 改为章节粒度处理
   - 每章独立调用 Agent，汇总后构建 `StoryGraph`

6. **新增测试文件**
   - `tests/test_chapter_parser.py`：7 个单元测试（无需 API key）
   - `tests/test_event_agent.py`：事件提取测试
   - `tests/test_workflow.py`：全流程集成测试

### 解决了什么问题

- **知识溯源**：之前整个小说一次性处理，无法知道角色/场景/事件来自哪一章
- **章节粒度缺失**：没有章节分割能力，无法实现"先读章节再汇总"的分层处理

### 测试结果（text.md 雾港档案）

```
Chapters: 3
Characters: 6 (去重后) / 10 (原始)
Scenes: 21
Events: 16（跨 3 章节，每条带 source trace）
Consistency warnings: 6（预期：场景对话中的角色名未注册）
```

### 还存在的问题

- 暂无

### 下一步

- 合并到 main 分支后，继续实现 UI 层（Streamlit 展示 Events 标签页）

---

## MVP 4：知识合并（Local → Global SKL）+ 增强一致性检查

### 做了什么

1. **新增 `core/knowledge_merger.py`**
   - `LocalKnowledge`：单章本地知识
   - `GlobalStoryKnowledge`：全局知识层（Single Source of Truth）
     - `merge_characters()`：按 name 去重，合并 traits，保留更长 description
     - `merge_scenes()`：按 (title, location) 去重
     - `character_first_appearance`：追踪每个角色的首现章节
   - `KnowledgeMerger` 类：顺序合并多章
   - `merge_chapters_to_skl()`：便捷函数，一次性合并

2. **新增 `core/consistency_checker.py`**
   - `ConsistencyChecker` 对 StoryGraph 做 4 类检查：
     - `_check_characters()`：检测重复角色
     - `_check_scene_character_consistency()`：场景引用角色不在列表中
     - `_check_event_characters()`：事件参与者不在角色列表中
     - `_check_timeline()`：同一地点事件时间标记冲突
   - 返回 `ConsistencyReport`（passed + warnings + info）
   - `run_consistency_check()` 便捷函数

3. **扩展 `core/story_graph.py`**
   - `WarningCode` 新增 `TIMELINE_CONFLICT` 枚举值

4. **改造 `core/workflow.py`**
   - 章节提取 → `merge_chapters_to_skl()` → 从 Global SKL 构建 StoryGraph
   - 使用增强的 `ConsistencyChecker` 替代原有的简易 `_consistency_check()`
   - `WorkflowResult` 新增 `global_skl` 和 `merger_report` 字段

5. **新增测试**
   - `tests/test_knowledge_merger.py`：6 个单元测试（无需 API key）
   - `tests/test_workflow_mvp4.py`：MVP 4 全流程集成测试

### 解决了什么问题

- **跨章节重复提取**：之前每章都提取角色/场景，汇总后存在大量重复（雾港档案原始 10 个角色中有 4 个是重复的）
- **一致性检查不足**：原有检查仅检测场景中的未知角色，增强版覆盖：角色、场景-角色一致性、事件参与者、时间线冲突

### 测试结果（text.md 雾港档案）

```
Before merge: 10 characters, 18 scenes
After merge:  6 unique characters, 18 unique scenes
Duplicates removed: 4

Merger report:
  total_chapters: 3
  unique_characters: 6
  unique_scenes: 18
  duplicates_removed: 4
  consistency_passed: True

Warnings (6):
  [CHARACTER_DISCREPANCY] 场景中出现未识别角色
  [EVENT_CONTRADICTION] 事件涉及未知角色
  [TIMELINE_CONFLICT] 地点事件时间标记各异
```

### 还存在的问题

- 暂无

### 下一步

- 在 Streamlit UI 中展示全局 SKL 的去重报告
- 支持用户手动解决一致性警告

---

## MVP 5：补全 SKL（Relation / Event / Timeline / Location / Outline）

### 目标

补全 `GlobalStoryKnowledge` 的知识结构，从"人物+场景"扩展为完整的 `story_knowledge`。

### SKL 目标结构

```yaml
story_knowledge:
  title: "..."
  author: "..."

  # 已有
  characters: [...]      # 角色，去重后
  scenes: [...]          # 场景，去重后
  character_first_appearance: {...}

  # 新增
  relations: [...]       # 角色关系（RelationAgent 提取）
  events: [...]          # 全局事件列表（EventAgent 提取 + 去重合并）
  locations: [...]       # 地点分析（出现频次、类型）
  timeline: [...]        # 时间线（事件按时间排序）
  outline: [...]        # 故事大纲（OutlineAgent 生成）
  character_arcs: {...} # 角色弧光（按角色分组的关键事件）
```

### 实现任务

- [ ] **RelationAgent** — 从小说文本/章节中提取角色关系（血缘/友情/敌对/恋爱等），接入 `merge_chapters_to_skl()`
- [ ] **SKL 扩展** — `GlobalStoryKnowledge` 新增 `relations`/`events`/`locations`/`timeline`/`outline`/`character_arcs` 字段
- [ ] **Event Merger** — 将逐章提取的 Event 合并到 SKL，支持按 event_type / participants 去重
- [ ] **Location 分析** — 汇总所有场景 location，统计频次，提取 location 类型
- [ ] **Timeline 构建** — 基于 time_of_day / time_marker 字段，按事件时间排序，构建全局时间线
- [ ] **OutlineAgent** — 分析故事主线，生成三幕/五幕结构大纲
- [ ] **Character Arc** — 按角色聚合其参与的事件，构建角色弧光
- [ ] **测试** — `test_skl_completeness.py` 验证所有新字段

---

## MVP 6：接入 ScriptAgent，SKL → Screenplay

### 目标

将 `ScriptAgent` 接入 `StoryForgeWorkflow`，实现题目核心要求：小说转剧本。

### 实现任务

- [ ] **ScriptAgent 重构** — 支持以 `StoryGraph` / `GlobalStoryKnowledge` 为输入，而非原始小说文本
- [ ] **Structure Analysis → Outline** — `analyze_structure()` 输出与 SKL.outline 对齐
- [ ] **Scene-level Screenplay** — 逐场景生成剧本内容，写入 `StoryGraph.scripts[scene_id]`
- [ ] **SKL 上下文注入** — 生成场景时，将该场景关联的 CharacterNode / EventNode 作为上下文传入
- [ ] **Workflow 集成** — `StoryForgeWorkflow.run()` 调用 `ScriptAgent`，返回完整 YAML（含 scripts 节点）
- [ ] **测试** — `test_screenplay_generation.py` 验证 SKL → YAML 剧本完整链路

### 输出格式

```yaml
story_graph:
  version: "1.0"
  metadata: {...}
  characters: [...]
  relations: [...]
  events: [...]
  scenes: [...]
  scripts:           # MVP 6 新增
    scene_001:       # scene_id → 剧本内容
      type: "script"
      content:
        - type: "action"
          text: "林远推开公寓的门..."
        - type: "dialogue"
          character: "林远"
          text: "我回来了。"
  warnings: [...]
```

---

## MVP 7：知识层治理（Knowledge Layer Governance）

### 目标

在 SKL（GlobalStoryKnowledge）构建完成后，对其进行**知识治理**：冲突检测与仲裁、一致性维护、知识修正与回写，确保 SKL 始终是高质量的 Single Source of Truth。

### 核心问题

当前 pipeline 各 Agent 独立提取知识，存在以下隐患：

- **跨 Agent 不一致**：CharacterAgent 提取的"林远"和 SceneAgent 提取的"林远"是同一个角色吗？
- **冲突未仲裁**：RelationAgent 说"A和B是朋友"，EventAgent 提取的事件却说"A打了B"——谁对？
- **知识静默错误**：LLM 幻觉导致角色名拼写错误、关系类型错误、事件逻辑矛盾
- **用户修正无回写**：用户在 UI 中修正了角色名，但 SKL 不会同步更新

### 实现任务

- [ ] **ConflictResolver**：检测并仲裁跨 Agent 的知识冲突（如角色身份不一致、关系与事件矛盾）
- [ ] **SKL Validator**：对 GlobalStoryKnowledge 做完整性/一致性校验（必填字段、类型约束、跨字段约束）
- [ ] **KnowledgePatch**：接收用户修正，回写到 SKL 并级联更新受影响的下游（SceneGraph / scripts）
- [ ] **KnowledgeRevision**：基于一致性检查结果，自动修正可推断的错误（如拼写纠错、类型规范化）
- [ ] **AuditTrail**：记录 SKL 的每次变更，支持回溯和撤销
- [ ] **测试**：`test_knowledge_governance.py` 验证冲突检测和仲裁逻辑

### 知识治理在 pipeline 中的位置

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
   StoryGraph
       │
       ▼
   Screenplay（稳定输入）
```

---

## Git 提交记录

| Commit | Branch | 内容 |
|--------|--------|------|
| `3442238` | feature/mvp3-chapter-parsing | feat(mvp3): chapter parsing + event source tracing |
| `130f342` | feature/mvp3-chapter-parsing | feat(mvp4): local-to-global knowledge merger + enhanced consistency checker |
| `5d8159a` | main | feat: 章节感知的多 Agent 小说转剧本 pipeline（MVP 3-5） |
| `c8b3a39` | main | feat(mvp6): 接入 ScriptAgent，SKL → Screenplay 剧本生成 |
| `6dc27e1` | main | feat(mvp6): 接入 ScriptAgent，SKL → Screenplay 剧本生成（含 REVIEW_LOG.md 更新） |

PR 链接：
- MVP 3-5: https://github.com/RZengXpy/story_wiki/pull/3
- MVP 6: https://github.com/RZengXpy/story_wiki/pull/4

---

## 技术债务 / 后续改进项

1. **API 调用效率**：每章独立调用 LLM（如 3 章小说 = 3 次字符 + 3 次场景 + 3 次事件 = 9 次 API），可考虑并发（asyncio）或批量
2. **Scene deduplication 逻辑**：当前按 (title, location) 去重，相同地点不同场景会丢失
3. **UI 展示**：Events 标签页尚未在 Streamlit UI 中实现
4. **gh CLI 未安装**：无法通过命令行创建 PR，需手动访问链接
5. **原始角色信息丢失**：去重后原始的 `Character` 对象中 traits/description 被覆盖（保留最长 description），历史信息未保留
