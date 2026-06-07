# StoryForge Workflow API 测试结果

## 测试文件

`tests/test_workflow_api.py`

---

## 测试 1: ProgressTracker ✅ PASS

```
[OK] set_total(3, 5) → LLM总数 = 4*3+1+5 = 18
[OK] set_phase(PARSING_CHAPTERS) → 解析章节
[OK] 开始第1章提取，当前 LLM: (0, 18)
[OK] 角色提取完成 → LLM: 1/18, msg: 正在提取：角色
[OK] 第1章完成 → LLM: 4
[OK] 第2章提取中，chapter_info: 第 2 章 / 共 3 章
[OK] 第3章完成 → LLM: 9/18
[OK] 大纲生成完成 → LLM: 10
[OK] 后续阶段不变 → LLM: 0
[OK] 剧本生成中: 正在生成场景剧本..., chapter_info: 场景 2 / 共 5
[OK] 处理完成，fraction = 1.0
[OK] 错误处理: 错误：模拟错误
[PASS] ProgressTracker all tests passed!
```

---

## 测试 2: StoryForgeWorkflow.run() 构建 SKL ✅ PASS

```
小说字数: 1509
预计 LLM 调用: 4*章节数 + 1

elapsed 耗时: 139.0 秒

工作流执行成功！
  章节数: 3
  角色数: 6
  场景数: 19
  关系数: 12
  事件数: 19
  警告数: 2
  SKL 去重角色: 6
  SKL 去重场景: 19
  SKL 去重关系: 12

角色列表:
  - 林川 (protagonist)
  - 陈雨 (supporting)
  - 许远 (antagonist)
  - 老周 (supporting)
  - 黑衣男人 (supporting)
```

---

## 测试 3: StoryForgeWorkflow.run_with_scripts() 生成剧本 ✅ PASS

```
场景数: 19
预计 LLM 调用: 场景数 = 19

elapsed 耗时: 97.8 秒

剧本生成成功！
  生成剧本场景数: 5
  剧本条目总数: 63

场景 [神秘储藏室]:
  [动作] 昏暗的储藏室中，金属箱已经跌落在地，一本航海日志散落一旁...
  [动作] 黑衣男人冲向林川，试图抢夺日志...
  [台词] 林川: 你们到底是什么人？...

场景 [迷雾岛]:
  [动作] 浓雾弥漫的海面上，一座岛屿的轮廓逐渐浮现...
  [动作] 观测站的设备虽然陈旧，但仍在运转，指示灯闪烁不定...
  [台词] 陈雨: 这里的设备居然还能用？...
```

---

## 结论

| 测试项 | 状态 | 耗时 |
|--------|------|------|
| ProgressTracker | PASS | < 1s |
| workflow.run() | PASS | 139s |
| workflow.run_with_scripts() | PASS | 98s |

**后端接口完全正常**，可以进行前端联调。

---

## 修复记录

### 问题 1: `on_chapter_done` 缺失
- `workflow.py` 调用了 `tracker.on_chapter_done()` 但 `ProgressTracker` 中未定义
- **修复**: 在 `core/progress.py` 中添加了 `on_chapter_done()` 方法

### 问题 2: Streamlit 后台线程访问 session state
- 原实现使用 `threading.Thread` 启动后台线程
- 警告: `missing ScriptRunContext`
- **修复**: 完全移除后台线程，改为同步执行模式

### 最终架构

```
之前（错误）:
  按钮点击 → 启动 Thread → 后台线程访问 st.session_state ❌

修复后:
  按钮点击 → st.spinner() → _run_workflow_sync()（主线程）→ queue.put(result) → st.rerun()
```

**关键原则**: 整个 workflow 执行 + session_state 更新全在主线程，`queue.Queue` 仅作为结果容器，不涉及跨线程通信（因为都在同一线程）。

### 测试结果

| 测试 | 状态 | 耗时 |
|------|------|------|
| ProgressTracker | PASS | < 1s |
| `run()` 构建 SKL | PASS | 139s |
| `run_with_scripts()` 生成剧本 | PASS | 98s |
