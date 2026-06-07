# StoryForge 剧本 YAML Schema

> 本文档定义 StoryForge 系统输出的结构化剧本 YAML Schema，说明每个字段的设计原因。

## 概述

StoryForge 将小说文本转换为结构化剧本，输出为 `story_graph` 根对象的 YAML 格式。Schema 设计遵循以下核心原则：

1. **知识优先（Knowledge First）** — 剧本生成前先提取角色、事件、关系等知识，剧本是知识的下游派生
2. **可追溯（Explainable）** — 所有实体均可追溯到原小说章节
3. **可编辑（Human Editable）** — 允许用户直接修改 YAML 后重新加载

## Schema 版本

```yaml
story_graph:
  version: "1.0"
```

---

## 完整 Schema

```yaml
story_graph:
  version: "1.0"                    # Schema 版本，用于向前兼容

  metadata:                          # 元信息
    title: "雾港档案"               # 剧本标题（默认取用户输入）
    author: "StoryForge"            # 改编工具
    adapted_by: "StoryForge"        # 改编工具名称
    genre: "thriller"               # 故事题材
    total_chapters: 3               # 章节总数
    unique_characters: 6            # 去重后角色数
    unique_scenes: 18               # 去重后场景数
    created_at: "2026-06-05T..."    # 生成时间（ISO 8601）

  characters:                       # 角色列表
    - id: "林川"                    # 角色唯一标识（与 name 相同）
      name: "林川"                  # 角色姓名
      role: "protagonist"           # 角色定位
                                   #   protagonist  - 主角
                                   #   antagonist  - 反派
                                   #   supporting  - 配角
      description: "雾港镇图书馆管理员..."  # 角色描述
      age: ""                       # 年龄（可为空）
      gender: ""                    # 性别（可为空）
      first_appearance: "第一章：失踪的航海日志"  # 首次出现章节

  relations:                        # 角色关系网络
    - from_char: "林川"             # 关系发起方
      to_char: "陈雨"               # 关系接收方
      relation_type: "friend"       # 关系类型
                                   #   family     - 血缘关系
                                   #   friend     - 朋友
                                   #   enemy     - 敌对
                                   #   romantic  - 恋爱
                                   #   professional - 职业关系
                                   #   stranger  - 陌生人
      description: "林川与陈雨是好朋友..."  # 关系描述

  events:                           # 事件列表
    - title: "老人询问北辰号日志"
      event_type: "revelation"     # 事件类型
                                   #   conflict      - 冲突
                                   #   revelation    - 揭示/发现
                                   #   transition    - 过渡/转场
                                   #   turning_point - 转折点
                                   #   resolution   - 解决/收尾
      location: "雾港镇图书馆"      # 事件发生地点
      time_marker: "下午四点"        # 事件发生时间
      participants:                # 参与者列表
        - "林川"
        - "老人"
      description: "老人询问北辰号的航海日志..."  # 事件描述
      cause: "老人一直在寻找北辰号的真相"       # 事件原因（可为空）
      consequence: "林川发现日志已被人拿走"       # 事件后果（可为空）

  scenes:                           # 场景列表
    - id: "scene_001"              # 场景唯一标识
      title: "图书馆相遇"            # 场景标题
      location: "雾港镇图书馆"        # 场景地点
      time: "afternoon"             # 时间（day/night/dawn/dusk/unspecified）
      act: 1                        # 第几幕
      characters_present:            # 本场景出现的角色
        - "林川"
        - "老人"
      event_ids: []                 # 关联的事件 ID 列表
      summary: "图书馆内，林川与陌生老人相遇..."  # 场景概要

  scripts:                          # 剧本内容（按场景组织）
    scene_001:                     # 场景 ID（与 scenes[].id 对应）
      id: "scene_001"
      content:                     # 剧本条目列表
        - type: "action"            # 条目类型
          text: "图书馆内，灯光昏暗。林川整理着档案柜。"  # 动作描述（无角色名）
        - type: "dialogue"
          character: "林川"          # 说话角色
          text: "请问，您需要什么？"  # 对话内容
        - type: "action"
          text: "老人缓缓走上前，神情凝重。"
        - type: "dialogue"
          character: "老人"
          text: "这里还保存着'北辰号'的航海日志吗？"

  warnings:                         # 一致性警告
    - code: "CHARACTER_DISCREPANCY"  # 警告代码
      message: "场景「废弃灯塔」引用了未识别角色：神秘人"  # 警告信息
      severity: "warning"            # 严重程度
                                   #   error   - 必须修复
                                   #   warning - 建议检查
                                   #   info    - 参考信息
      scene_ids:                   # 涉及的场景 ID
        - "scene_007"
      characters_involved:          # 涉及的角色
        - "神秘人"
```

---

## 字段设计说明

### metadata — 元信息

**设计原因**：`metadata` 提供剧本的全局上下文，用于快速了解这是一个什么故事。`total_chapters` / `unique_characters` / `unique_scenes` 字段来自知识合并后的统计，让用户无需解析下方数据就能知道故事规模。`created_at` 使用 ISO 8601 时间戳，便于版本管理和日志追溯。

### characters — 角色列表

**设计原因**：`role` 字段（protagonist / antagonist / supporting）来自小说文本中的客观描述，而非主观判定，帮助编剧快速区分核心角色。`first_appearance` 追踪角色的首次登场章节，直接对应小说原文位置——这是"Explainable"原则的核心体现：任何角色都应能追溯到原小说。

**可编辑性**：用户可以修改 `name`、`role`、`description`。修改后需重新执行知识合并以同步下游（场景引用、事件参与者等）。

### relations — 角色关系网络

**设计原因**：剧本中对话的潜台词来源于角色之间的关系——知道"A是B的敌人"，才能写出有张力的对峙台词。`relation_type` 使用枚举而非自由文本，是因为关系类型的一致性直接影响剧本生成质量，规范化也便于后续图可视化（如关系图谱）。

**关系类型选取逻辑**：

- `family` — 血缘/收养关系，有最强的情感绑定
- `friend` — 朋友/战友，有信任基础
- `romantic` — 恋爱/暧昧，产生情感纠葛
- `professional` — 同事/雇佣，有功利驱动
- `enemy` — 敌对，最适合制造冲突场面
- `stranger` — 陌生人，首次接触有探索感

### events — 事件列表

**设计原因**：`event_type` 的五类划分（conflict / revelation / transition / turning_point / resolution）对应经典叙事结构中的事件类型。`participants` 字段记录谁参与了事件，支撑了"角色弧光"（character arc）的构建——角色的成长/转变通过他参与的事件序列来展现。

**source trace 设计**：`source` 字段（章节 ID + 章节标题）让每条事件都能回溯到原小说文本。这满足了"Explainable"原则：编剧如果怀疑某个事件提取有误，可以直接回到原小说对应章节核实。

### scenes — 场景列表

**设计原因**：`scenes` 是介于知识层（characters / events / relations）和剧本层（scripts）之间的中间层。一个场景是时间和地点的最小单元——同一时间同一地点发生的事情归为同一场景。`event_ids` 字段建立了场景到事件的关联，使得剧本生成时可以根据事件上下文决定场景的情感基调。

**act 字段**：目前默认均为 1，预留扩展为多幕剧结构的空间（可由 `OutlineAgent` 的三幕分析结果填充）。

### scripts — 剧本内容

**设计原因**：`scripts` 按场景 ID 组织，每个场景的 `content` 是 `action`（动作描写）和 `dialogue`（对话）交替排列的列表。选择 `action` / `dialogue` 二分法而非更细的分类（如 `direction`、`voiceover`），是因为：

1. **简洁性**：格式足够表达大多数剧本，又不会给用户带来过多认知负担
2. **标准化**：这是行业最通用的剧本格式，用户可以直接将输出交给专业编剧工具进一步加工
3. **可编辑性**：`action` 行无需指定角色，`dialogue` 行只需指定说话者——编辑成本最低

**action 行格式**：动作用一般现在时描述，描述的是"摄像机能看到的东西"，而非角色的内心想法。例如"林川翻开航海日志"而非"林川好奇地想知道日志里写了什么"。

**dialogue 行格式**：角色名大写，对话内容简洁有力。角色的独特嗓音（verbal tic、口头禅）通过 `SKL` 中的 `traits` 字段在生成时注入。

### warnings — 一致性警告

**设计原因**：`warnings` 不是错误日志，而是知识一致性检查的结果，供用户参考。有三个严重级别：

- `error`（红色）：会导致剧本无法正常生成的逻辑错误，如角色名为空、场景标题为空
- `warning`（黄色）：潜在的不一致，如场景引用了未知角色、事件参与者与角色列表不匹配
- `info`（蓝色）：建议性提示，如某地点的时间标记各不相同

`code` 字段使用标准化枚举（如 `CHARACTER_DISCREPANCY`）而非自然语言描述，是为了便于工具链后续处理（如 CI 自动化检查）。

---

## 使用方式

### 导出为 YAML 文件

```bash
result = workflow.run_with_scripts(novel_text, title="雾港档案")
yaml_str = result.graph.to_yaml()
with open("output.yaml", "w", encoding="utf-8") as f:
    f.write(yaml_str)
```

### 导入修改后的 YAML

```python
import yaml

with open("output.yaml", "r", encoding="utf-8") as f:
    data = yaml.safe_load(f)

# 修改角色名
data["story_graph"]["characters"][0]["name"] = "林川（真名）"

# 重新导出
with open("output_modified.yaml", "w", encoding="utf-8") as f:
    yaml.dump(data, f, allow_unicode=True, sort_keys=False)
```

### 人类可读性保证

Schema 中所有嵌套层级最大深度为 3（`story_graph` → `scripts` → `scene_001` → `content`），避免过深嵌套导致的 YAML 可读性下降。列表元素（`characters`、`events`、`scenes`）均按出现顺序排列，不打乱原始故事的时间流。

---

## 与其他 Schema 的区别

| 特性 | StoryForge Schema | Fountain（标准电影剧本格式） | FDXML（Final Draft） |
| -- | -- | -- | -- |
| 知识层（元信息） | ✅ 包含 | ❌ 无 | ❌ 无 |
| 角色关系网络 | ✅ 包含 | ❌ 无 | ❌ 无 |
| 事件列表（可溯源） | ✅ 包含 | ❌ 无 | ❌ 无 |
| 剧本动作/对话分离 | ✅ | ✅ | ✅ |
| YAML 格式（人类可编辑） | ✅ | ❌（纯文本） | ❌（XML） |
| 一致性警告 | ✅ | ❌ 无 | ❌ 无 |
| 适用场景 | 小说改编剧本初稿生成 | 电影/电视剧剧本 | 专业剧本写作 |

StoryForge Schema 的独特价值在于它是**知识驱动的**：输出不仅包含剧本本身，还包含生成剧本所依据的知识图谱（角色、关系、事件、场景），用户可以追溯每句台词背后的知识来源，也可以直接在 YAML 层面修改知识后重新生成。
