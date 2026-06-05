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

## Git 提交记录

| Commit | Branch | 内容 |
|--------|--------|------|
| `3442238` | feature/mvp3-chapter-parsing | feat(mvp3): chapter parsing + event source tracing |
| `130f342` | feature/mvp3-chapter-parsing | feat(mvp4): local-to-global knowledge merger + enhanced consistency checker |

PR 链接：https://github.com/RZengXpy/story_wiki/pull/new/feature/mvp3-chapter-parsing

---

## 技术债务 / 后续改进项

1. **API 调用效率**：每章独立调用 LLM（如 3 章小说 = 3 次字符 + 3 次场景 + 3 次事件 = 9 次 API），可考虑并发（asyncio）或批量
2. **Scene deduplication 逻辑**：当前按 (title, location) 去重，相同地点不同场景会丢失
3. **UI 展示**：Events 标签页尚未在 Streamlit UI 中实现
4. **gh CLI 未安装**：无法通过命令行创建 PR，需手动访问链接
5. **原始角色信息丢失**：去重后原始的 `Character` 对象中 traits/description 被覆盖（保留最长 description），历史信息未保留
