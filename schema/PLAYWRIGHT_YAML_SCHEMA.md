# StoryForge 剧本 YAML Schema 参考

> 本文档是 StoryForge 系统剧本输出的正式 Schema 参考手册，包含每个字段的完整定义、类型约束与设计原因说明。可作为数据校验、人工编辑和工具链开发的依据。

---

## 1. 设计原则

StoryForge 的 YAML Schema 遵循三条核心设计原则：

**知识优先（Knowledge First）** — Schema 天然分为两层：知识层（characters、relations、events、scenes）和产出层（scripts）。知识层是真实性的来源，产出层是知识的下游派生。任何剧本片段的合理性都应能从知识层找到依据。

**可溯源（Traceable）** — Schema 不丢弃任何中间信息。角色首次出现章节、事件因果链、场景与事件的关联，全部显式建模。这使人工审查和 debug 成为可能，而不只是黑盒输出。

**可编辑（Editable）** — YAML 作为人可直接读写的文本格式，是 Schema 的载体。嵌套深度不超过 3 层、列表元素顺序对应故事时间流、所有枚举值有明确语义，这些约束使 YAML 在大文档场景下依然可读、可改。

---

## 2. 类型系统

Schema 采用以下类型标注，与代码中的 Pydantic / dataclass 模型一一对应：

| 类型标识 | 说明 | 对应代码 |
|---|---|---|
| `string` | 字符串，无长度限制 | `str` |
| `string_enum(...)` | 取值受限的字符串 | `Enum` |
| `string[]` | 字符串数组，元素无序 | `list[str]` |
| `object` | 嵌套对象 | `dataclass` |
| `object[]` | 对象数组 | `list[dataclass]` |
| `object{}` | 以字符串为 key 的映射表 | `dict[str, dataclass]` |

---

## 3. 根结构

```yaml
story_graph:
  version: string           # 必填。Schema 版本号，格式为 "MAJOR.MINOR"，当前为 "1.0"
  metadata: object          # 必填。元信息
  characters: object[]      # 必填。角色列表，至少包含一个元素
  relations: object[]      # 必填。关系列表，允许为空
  events: object[]         # 必填。事件列表，允许为空
  scenes: object[]         # 必填。场景列表，允许为空
  scripts: object{}        # 必填。以场景 ID 为 key 的剧本内容映射
  warnings: object[]        # 必填。警告列表，允许为空
```

`version` 字段用于 Schema 演进时的向前兼容。当 Schema 发生破坏性变更时，版本号主版本号递增，下游消费者可据此判断是否需要迁移。

---

## 4. metadata — 元信息

```yaml
metadata:
  title: string                              # 必填。剧本标题，通常取自用户输入或小说文件名
  author: string                             # 可选。原著作者姓名
  adapted_by: string                         # 必填。改编工具名称，固定为 "StoryForge"
  genre: string                              # 必填。题材类型，如 "悬疑"、"冒险"、"爱情"
  created_at: string                        # 必填。生成时间，ISO 8601 格式
  total_chapters: integer                   # 必填。输入小说的章节总数
  unique_characters: integer                 # 必填。去重后的角色数量
  unique_scenes: integer                    # 必填。去重后的场景数量
  unique_relations: integer                 # 可选。关系网络中的边数
  unique_events: integer                    # 可选。事件列表中的事件总数
  duplicates_removed: integer                # 可选。知识合并阶段移除的重复条目数
  locations_count: integer                   # 可选。地点聚合后的地点数量
  timeline_count: integer                    # 可选。时间线中的节点数量
  character_arcs_count: integer              # 可选。角色弧光数量
  outline_generated: boolean                 # 可选。是否已生成故事大纲
  character_first_appearance: object{}       # 可选。角色名→首次出现章节名的映射
```

### 设计原因

`metadata` 是用户接触 YAML 文件的第一个信息块，承担"快速概览"的功能。`total_chapters`、`unique_characters`、`unique_scenes` 三个统计字段让用户在打开文件之前就知道故事的大致规模。

`character_first_appearance` 映射表是一个轻量但关键的设计：它将角色的身份（由 LLM 抽取的 name）与叙事顺序（首次出现章节）关联起来。这个映射在两个场景中有用：一是 `CharacterAgent` 做角色合并时，需要判断两个名字是否为同一人（如果同名且首次出现章节不同则很可能是不同角色）；二是 `OutlineAgent` 生成大纲时，需要知道角色出场顺序来设计弧光节奏。

`created_at` 使用 ISO 8601 时间戳而非自然语言（如"2026年6月7日"），是为了便于工具链做时间排序、日志关联和版本对比。

---

## 5. characters — 角色列表

```yaml
characters:
  - id: string                              # 必填。角色的全局唯一标识
    name: string                             # 必填。角色姓名（通常与 id 相同）
    role: string_enum(protagonist, antagonist, supporting)
                                             # 必填。角色定位
    description: string                      # 必填。角色的客观描述文字
    age: string                              # 可选。年龄，字符串以支持模糊描述如"中年"
    gender: string                           # 可选。性别，取值自由（男/女/其他/空）
    first_appearance: string                  # 必填。首次出现章节的标题
    traits: string[]                         # 可选。角色特质列表，由 CharacterAgent 提炼
```

### 设计原因

`id` 与 `name` 分离的设计预留了一个重要能力：同一个角色可能在小说中以不同名字出现（如别名、绰号、化名），此时 `id` 作为稳定的主键，`name` 存储当前使用的正式名称。在 `apply_character_rename` 方法中可以看到这个设计如何服务于批量改名场景。

`role` 的三值枚举（protagonist / antagonist / supporting）直接对应经典叙事学中的角色功能分类。选择这三类而非更细的分类（如 deuteragonist、foil、mentor），是因为 StoryForge 的知识抽取是全自动的，过细的角色分类会导致 LLM 在分类时产生不一致，进而污染下游的剧本生成质量。三分类是信息量和分类准确率之间的最优平衡点。

`first_appearance` 字段的值是章节标题而非章节 ID，是因为章节标题是人类可读的叙事上下文，ID（如 `ch_001`）对人类读者没有意义。在 UI 层展示时使用标题，在程序内部做关联时使用 ID——Schema 层面保留标题是为了直接可读。

`traits` 字段来自 `SKL` 层，但在 `graph.yaml` 的当前实现中未直接序列化。这是 `script_agent.py` 在生成对话时从 SKL 读取的内部数据，在 Schema 中保留 `traits` 字段位置，可以使 Schema 与 SKL 保持结构对齐，也为未来在 YAML 中直接覆盖 traits 提供扩展空间。

---

## 6. relations — 角色关系网络

```yaml
relations:
  - from_char: string                         # 必填。关系描述的起点角色名（对应 characters[].name）
    to_char: string                          # 必填。关系描述的终点角色名
    relation_type: string_enum(family, friend, enemy, romantic, professional, stranger)
                                             # 必填。关系类型
    description: string                      # 必填。关系描述，说明这段关系的具体内容
```

### 设计原因

关系使用有向边建模（`from_char` → `to_char`），而非无向边。这是因为"林川信任陈雨"和"陈雨利用林川"描述的是同一对角色之间的不同关系维度。在当前的 Schema 实现中，每对角色之间允许有多条关系（有向），每条关系有独立的 `relation_type` 和 `description`。

`relation_type` 使用六值枚举而非自由文本，原因有两层。第一层是实用性：规范化类型使得关系图谱可视化、关系网络分析和冲突检测（`RelationAgent`）都更可靠。第二层是叙事意义——每种关系类型天然对应不同的戏剧场景类型：`family` 适合家庭冲突，`enemy` 适合正面对抗，`romantic` 适合情感纠葛，`professional` 适合利益博弈，`stranger` 适合探索与信息不对称，`friend` 适合信任考验。

`description` 字段保留了关系的具体语义。这不是冗余：同一个 `enemy` 关系，可能是"杀父之仇"也可能是"商业竞争"，这些差异直接影响剧本中的对话语气和冲突烈度。LLM 在生成剧本时需要这个字段来注入正确的情感基调。

---

## 7. events — 事件列表

```yaml
events:
  - title: string                            # 必填。事件的标题/名称
    event_type: string_enum(conflict, revelation, transition, turning_point, resolution)
                                             # 必填。事件类型
    location: string                         # 可选。事件发生地点
    time_marker: string                      # 可选。事件发生的叙事时间（相对时间）
    participants: string[]                   # 必填。参与事件的角色名列表
    description: string                      # 必填。事件的客观描述
    cause: string                            # 可选。事件的直接原因
    consequence: string                      # 可选。事件的直接后果
    chapter_ref: string                      # 可选。事件来源章节标题（source trace）
```

### 设计原因

`event_type` 的五值分类对应经典三幕结构中的事件功能分布：

- **conflict**：制造张力，对应第一幕和第二幕中的障碍建立
- **revelation**：揭示新信息，推动情节发展，通常是转折的前奏
- **transition**：场景过渡，连接两个重要事件
- **turning_point**：情节点，永久改变故事走向，是第二幕末端的核心
- **resolution**：收尾，解决悬念，通常在第三幕

这种分类的价值在于：它使 `OutlineAgent` 能够根据事件类型分布判断故事结构是否均衡（如果没有 `turning_point`，第二幕会显得拖沓；如果 `resolution` 过多，说明悬念提前耗尽），也为 `ScriptAgent` 提供了场景的情感方向提示。

`cause` 和 `consequence` 字段支持构建因果链。`event_agent.py` 中的因果链分析（由 LLM 驱动）会为每个事件推断其因果关系，这些推断存储在这里。当同一个事件被多个章节引用时，`cause` 和 `consequence` 字段可以帮助判断是否存在矛盾（如果两个章节对同一事件的因果描述不一致，就会触发 `EVENT_CONTRADICTION` 警告）。

`participants` 字段是角色弧光分析的基础。通过追踪一个角色参与了哪些 `conflict` 事件、哪些 `resolution` 事件，可以量化该角色在故事中的主动程度和转变幅度。

---

## 8. scenes — 场景列表

```yaml
scenes:
  - id: string                               # 必填。场景唯一标识，格式为 "scene_NNN"（如 scene_001）
    title: string                            # 必填。场景标题，简洁描述场景内容
    location: string                         # 必填。场景发生的具体地点
    time: string_enum(day, night, dawn, dusk, afternoon, morning, evening, unspecified)
                                             # 必填。发生时间（一天之内的时段）
    act: integer                             # 必填。所属幕次，目前均为 1（单幕结构），可扩展为 2/3
    characters_present: string[]             # 必填。本场景中出现的角色名列表
    event_ids: string[]                      # 可选。关联的事件 ID 列表（指向 events[].title 或 events 序号）
    summary: string                          # 必填。场景的简短概要，用于上下文和预览
```

### 设计原因

场景是时间和地点的最小单元。Schema 中 `location` 和 `time` 字段共同定义了场景的唯一性——同一个地点在不同时间出现，算作不同场景；同一个时间在不同地点出现，同样算作不同场景。这个设计直接服务于场景去重逻辑（`SceneAgent`）。

`event_ids` 字段建立了场景到事件的关联，是"知识优先"原则的关键连接点。当 `ScriptAgent` 生成某个场景的剧本时，它读取 `event_ids` 找到该场景关联的事件，从事件中获取情节信息和对话素材。这保证了剧本内容不是凭空生成的，而是有知识依据的。

`act` 字段当前默认为 1，但 Schema 保留了这个字段以支持未来扩展为三幕或多幕结构。`OutlineAgent` 可以在分析完成后填充这个字段，将场景分配到对应幕次。

`summary` 字段的必要性在于：当 YAML 文档变得很长时（100+ 场景），用户无法快速浏览找到特定场景。`summary` 提供了场景内容的语义索引，使 Ctrl+F 搜索和 UI 列表展示都更有效。

---

## 9. scripts — 剧本内容

```yaml
scripts:
  scene_001:                                # key = 场景 ID，与 scenes[].id 对应
    id: string                              # 必填。场景 ID
    content:
      - type: string_enum(action, dialogue)  # 必填。条目类型
        text: string                        # 必填。条目内容
        character: string                   # 必填（type=dialogue 时）。说话角色名
        parenthetical: string               # 可选。表演指示，如"低声地"、"激动地"
```

### 设计原因

`scripts` 按场景 ID 组织而非按幕/章节组织，是因为场景是剧本生成的原子单元。`ScriptAgent` 以场景为单位并行生成（`async_pipeline.py` 中的 `asyncio.gather`），每个场景的剧本独立生成完成后再按 ID 归并到 `scripts` 字典中。

`content` 列表中 `action` 和 `dialogue` 交替出现的顺序就是剧本的实际阅读顺序。`action` 条目的 `character` 字段为空，`dialogue` 条目的 `character` 字段为说话者——这个非对称设计简化了编辑体验：在 YAML 中添加一段新对话，只需写一个 `dialogue` 条目，不需要重复指定说话角色（由上下文隐含）。

`action` 条目的语义约定是"摄像机能看到的东西"：动作描写、环境描写、表情描写——而非内心想法。这个约定使 `action` 内容直接对应剧本的格式规范，也是 `ScriptAgent` prompt 中的明确指令。

`parenthetical`（表演指示）字段为可选项，因为不是所有对话都需要表演指示。在需要时（如角色需要用特殊语气说某句话），它提供了比 `action` 更轻量的表达方式——直接附在对话行内，而不是拆成独立的 `action` 条目。

### 嵌套深度说明

`scripts` 的嵌套深度为 3：`story_graph` → `scripts` → `scene_001` → `content[]`。这个深度是刻意控制的结果。深度为 4 的设计（如再加一层 `acts`）会导致 YAML 文件的缩进层级达到 5 层以上，可读性急剧下降。深度为 2 的设计（如将所有 content 扁平化）则丢失了场景边界信息。3 层是当前最优解。

---

## 10. warnings — 一致性警告

```yaml
warnings:
  - code: string_enum(CHARACTER_DISCREPANCY, SCENE_INCONSISTENCY, EVENT_CONTRADICTION, RELATION_MISSING, UNRESOLVED_PLOT, TIMELINE_CONFLICT)
                                             # 必填。警告代码，标准化枚举
    message: string                          # 必填。人类可读的警告描述
    severity: string_enum(error, warning, info)
                                             # 必填。严重程度
    scene_ids: string[]                       # 可选。涉及的场景 ID 列表
    characters_involved: string[]             # 可选。涉及的角色名列表
```

### 设计原因

`warnings` 不是程序的错误日志，而是知识一致性检查的产出。它的目标读者是使用 StoryForge 的人类编剧，而非程序本身——告诉用户"场景 scene_007 引用了未知角色'神秘人'"比直接崩溃或静默忽略更有价值。

`code` 使用标准化枚举而非自然语言，是为了支持工具链的自动化处理。例如 CI 流程可以检查 `warnings` 中是否有 `severity: error` 的条目，有则拒绝合并；UI 可以按 `code` 分组展示警告，便于用户按类型批量处理。

`severity` 的三级设计区分了不同处理优先级：

- **error**：必须修复，否则剧本不可用（如角色名为空）
- **warning**：建议检查，可能需要人工判断（如未知角色引用）
- **info**：参考信息，不影响生成（如时间标记不一致的提示）

---

## 11. 枚举值汇总

```yaml
# characters[].role
protagonist       # 主角，故事的核心行动者
antagonist       # 反派，制造障碍的对手
supporting       # 配角，支持主线叙事的次要角色

# relations[].relation_type
family           # 血缘或收养关系
friend           # 朋友或战友关系
enemy            # 敌对或对立关系
romantic         # 恋爱或情感关系
professional     # 职业或利益关系
stranger         # 陌生或初次接触

# events[].event_type
conflict         # 冲突或对抗
revelation       # 信息揭示或发现
transition       # 过渡或转场
turning_point    # 情节点，转折
resolution       # 解决或收尾

# scenes[].time
day              # 白天
afternoon        # 下午
morning          # 上午
evening          # 傍晚
night            # 夜晚
dawn             # 黎明
dusk             # 黄昏
unspecified      # 时间未指明

# warnings[].code
CHARACTER_DISCREPANCY    # 角色不一致：场景引用了角色列表中不存在的角色
SCENE_INCONSISTENCY      # 场景不一致：同一场景的 location 或 time 在多处描述矛盾
EVENT_CONTRADICTION      # 事件矛盾：同一事件的 cause/consequence 在不同章节描述矛盾
RELATION_MISSING         # 关系缺失：两个角色有多次互动但未被提取为关系
UNRESOLVED_PLOT          # 悬念未解：有伏笔事件但没有对应的 resolution 事件
TIMELINE_CONFLICT        # 时间线冲突：事件顺序与 time_marker 矛盾

# warnings[].severity
error             # 必须修复，否则剧本无法正常生成
warning           # 建议检查，可能存在逻辑问题
info              # 参考信息，不影响生成流程
```

---

## 12. 与 SKL 的关系

Schema 中的 `characters`、`relations`、`events`、`scenes` 字段与 SKL（Story Knowledge Layer，`skl.json`）中的同名字段高度对齐，但存在以下差异：

| 方面 | SKL | graph.yaml Schema |
|---|---|---|
| 角色标识 | 无 `id` 字段，以 `name` 为唯一键 | 显式 `id` 字段，与 `name` 可分离 |
| 角色特质 | `traits[]` 显式存储 | 未直接序列化（由 `script_agent.py` 从 SKL 读取） |
| 来源追溯 | 完整的 `source.chapter_id + char_range` | 仅 `first_appearance`（章节标题） |
| 场景 | 无 `event_ids` 关联 | 通过 `event_ids` 显式关联事件 |
| 关系方向 | 无向 | 有向（`from_char` → `to_char`） |
| 事件因果 | 无 `cause`/`consequence` | 显式建模 |

这些差异反映了两个文件的不同用途：SKL 是知识合并过程的完整记录（包含字符偏移量等细粒度信息），而 `graph.yaml` Schema 是剧本输出的结构化表达（侧重可读性和可用性）。SKL 是中间产物，Schema 是最终产出。

---

## 13. 完整性约束

以下约束是 Schema 的隐式规则，不在 YAML 中表达但必须被校验工具和生成代码遵守：

1. **角色引用完整性**：`relations[].from_char` 和 `relations[].to_char` 必须存在于 `characters[].name` 中；`scenes[].characters_present` 中的每个名字必须存在于角色列表中。
2. **事件引用完整性**：`scenes[].event_ids` 中引用的每个 ID 必须对应 `events[]` 中某个事件的标识。
3. **剧本场景归属**：`scripts` 字典中的每个 key 必须对应 `scenes[].id`。
4. **唯一性**：`characters[].id` 在角色列表中必须唯一；`scenes[].id` 在场景列表中必须唯一。
5. **非空约束**：`characters[].name`、`scenes[].title`、`scenes[].location` 不允许为空字符串。

这些约束在 `consistency_checker.py` 和 `knowledge_governance.py` 中实现为可执行的检查规则。
