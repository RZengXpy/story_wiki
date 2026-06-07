"""StoryForge — AI Screenwriter Studio Streamlit UI.

Features:
- Chapter-based knowledge extraction (Character / Scene / Event / Relation / Outline)
- Local → Global knowledge merge (GlobalStoryKnowledge / SKL)
- Knowledge Governance (conflict resolution, validation, patching, audit)
- Consistency checking (4 types of warnings)
- SKL → Screenplay generation (scene-by-scene, SKL-context-injected)
- Inline screenplay editing with live YAML preview and export
- Real-time progress tracking during workflow execution
"""
from __future__ import annotations

import sys
import re
from pathlib import Path
from typing import Optional, Any

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st
import yaml
from datetime import datetime

from core.workflow import StoryForgeWorkflow, WorkflowResult
from core.story_graph import StoryGraph, CharacterRole, EventType, WarningSeverity, ScriptNode, ScriptItem
from core.knowledge_governance import (
    Patch, KnowledgeGovernor, GovernanceReport,
    AuditEntry, AuditTrail,
)
from core.progress import ProgressTracker, Phase
from core.storage import StoryStorage


# ── Session State ──────────────────────────────────────────────────────────────


def init_session_state():
    defaults = {
        "workflow_result": None,
        "governance_report": None,
        "current_tab": 0,
        "yaml_output": "",
        "edited_scripts": {},
        "show_scripts_generated": False,
        "workflow_running": False,
        "workflow_mode": None,
        "workflow_error": None,
        "_progress_tracker": None,
        "_storage": StoryStorage(),
        "_current_story_id": None,
        "_saved_story_id": None,
        "_local_knowledge": [],
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ── Progress Phase Icons ────────────────────────────────────────────────────────


_PHASE_ICONS = {
    Phase.PARSING_CHAPTERS: "📖",
    Phase.EXTRACTING_KNOWLEDGE: "🔍",
    Phase.MERGING_KNOWLEDGE: "🔗",
    Phase.GOVERNANCE: "🛡️",
    Phase.CHECKING_CONSISTENCY: "✅",
    Phase.BUILDING_GRAPH: "🗺️",
    Phase.GENERATING_SCRIPTS: "🎬",
    Phase.DONE: "🎉",
    Phase.ERROR: "❌",
}


# ── Workflow Execution ─────────────────────────────────────────────────────────


def _render_live_progress():
    """Render live progress bar and status while workflow is running.

    Drains the result queue on the main thread and updates session state.
    """
    import queue

    tracker = st.session_state.get("_progress_tracker")
    if tracker is None:
        st.info("准备开始...")
        return

    result_queue = st.session_state.get("_result_queue")
    if result_queue is not None:
        try:
            while True:
                msg_type, payload = result_queue.get_nowait()
                if msg_type == "result":
                    st.session_state["workflow_result"] = payload
                    st.session_state["show_scripts_generated"] = (
                        st.session_state.get("workflow_mode") == "scripts"
                    )
                    st.session_state["workflow_running"] = False
                elif msg_type == "error":
                    st.session_state["workflow_error"] = payload
                    st.session_state["workflow_running"] = False
        except queue.Empty:
            pass

    p = tracker.get_progress()
    icon = _PHASE_ICONS.get(p.phase, "⏳")
    fraction = min(p.current / max(p.total, 1), 1.0) if p.total > 0 else 0.0

    st.progress(fraction, text=p.message)

    parts = [f"{icon} **{p.phase_label}**", p.message]
    if p.chapter_info:
        parts.append(f"📍 {p.chapter_info}")
    llm_done, llm_total = tracker.get_llm_progress()
    if llm_total > 0:
        parts.append(f"🔮 LLM: {llm_done}/{llm_total}")
    if p.phase == Phase.GENERATING_SCRIPTS:
        parts.append(f"🎬 场景: {p.current}/{p.total}")
    st.info("  |  ".join(parts))

    if p.phase == Phase.DONE:
        st.success("处理完成！")
        st.session_state["workflow_running"] = False
    elif p.phase == Phase.ERROR:
        st.error(f"出错：{p.message}")
        st.session_state["workflow_running"] = False


def _run_workflow_sync(novel_text, title, author, api_key, model, run_check, mode: str):
    """Run workflow synchronously in the main thread.

    Workflow runs here on the main thread so there are no cross-thread
    session_state issues.  While it runs, the caller sets up a progress bar
    and the main loop polls tracker.get_progress() each rerun cycle.
    """
    import queue

    tracker = ProgressTracker()
    result_queue: queue.Queue = queue.Queue()

    st.session_state["_progress_tracker"] = tracker
    st.session_state["_result_queue"] = result_queue
    st.session_state["workflow_running"] = True
    st.session_state["workflow_mode"] = mode
    st.session_state["workflow_error"] = None
    st.session_state["workflow_result"] = None

    workflow = StoryForgeWorkflow(
        model=model, api_key=api_key, run_consistency_check=run_check,
        storage=st.session_state.get("_storage"),
    )
    try:
        if mode == "skl":
            result = workflow.run(
                novel_text, title=title or "未命名", author=author, tracker=tracker,
            )
        else:
            result = workflow.run_with_scripts(
                novel_text, title=title or "未命名", author=author, tracker=tracker,
            )
        tracker.set_phase(Phase.DONE)
        result_queue.put(("result", result))
        # Record saved story ID for UI display
        if workflow.storage and workflow.storage.last_saved_story_id:
            st.session_state["_saved_story_id"] = workflow.storage.last_saved_story_id
            st.session_state["_current_story_id"] = workflow.storage.last_saved_story_id
    except Exception as e:
        tracker.on_error(str(e))
        result_queue.put(("error", str(e)))


# ── Header & Sidebar ───────────────────────────────────────────────────────────


def render_header():
    st.set_page_config(
        page_title="StoryForge — AI 编剧工作台",
        page_icon="🎬",
        layout="wide",
    )
    st.title("🎬 StoryForge AI 编剧工作台")
    st.markdown("将小说文本自动转换为结构化、可编辑的 YAML 剧本")
    st.markdown("---")


def render_sidebar():
    storage = st.session_state.get("_storage")
    stories = storage.list_stories() if storage else []

    with st.sidebar:
        # ── Story History ─────────────────────────────────────────────
        if stories:
            st.header("📚 历史故事")
            for s in stories[:10]:
                sid = s.get("story_id", "")
                title = s.get("title") or "未命名"
                created = s.get("created_at", "")[:10]
                stats = s.get("stats", {})
                n_chars = stats.get("characters", "-")
                n_scenes = stats.get("scenes", "-")
                label = f"{title}  ({created})"
                if st.button(label, use_container_width=True, key=f"story_{sid[:8]}"):
                    _load_story(sid)
                    st.rerun()
                with st.expander(f"  角色:{n_chars} 场景:{n_scenes}"):
                    st.caption(f"ID: {sid[:16]}...")
                    st.caption(f"创建: {created}")
                    if st.button(f"🗑️ 删除", key=f"del_{sid[:8]}"):
                        storage.delete_story(sid)
                        st.rerun()

            st.markdown("---")

        st.header("⚙️ 配置")

        api_key = st.text_input(
            "API Key",
            type="password",
            help="OpenAI / 阿里通义 / DeepSeek 等兼容 API Key",
            placeholder="sk-...",
            key="sidebar_api_key",
        )

        model = st.selectbox(
            "模型",
            ["deepseek-v4-flash", "gpt-4o", "gpt-4o-mini", "qwen-plus"],
            index=0,
        )

        run_check = st.checkbox("启用一致性检查", value=True)
        run_governance = st.checkbox("启用知识治理", value=True)

        st.markdown("---")
        st.caption("StoryForge v1.0")
        st.caption("基于多 Agent 架构的 AI 小说转剧本工具")

    return api_key, model, run_check, run_governance


# ── Upload Section ─────────────────────────────────────────────────────────────


def render_upload_section():
    st.header("📖 上传小说")

    col1, col2 = st.columns([3, 1])

    with col1:
        novel_text = st.text_area(
            "粘贴小说文本",
            height=280,
            placeholder="在此粘贴小说文本内容...\n支持格式：纯文本小说，自动识别「第X章」进行拆分",
        )

    with col2:
        title = st.text_input("剧本标题", placeholder="例如：雾港档案")
        author = st.text_input("原著作者", placeholder="例如：金庸")

    c1, c2 = st.columns([1, 1])
    with c1:
        uploaded_file = st.file_uploader(
            "📁 上传 .txt 文件",
            type=["txt"],
            help="支持纯文本格式的小说文件",
        )
    with c2:
        yaml_file = st.file_uploader(
            "📄 导入 YAML（编辑后重新加载）",
            type=["yaml", "yml"],
            help="导入之前导出的 YAML 文件，继续编辑",
        )

    yaml_data = None
    if uploaded_file is not None:
        content = uploaded_file.read().decode("utf-8")
        if novel_text:
            st.warning("已加载上传文件，将覆盖文本框内容")
        novel_text = content

    if yaml_file is not None:
        try:
            yaml_data = yaml.safe_load(yaml_file)
            if not isinstance(yaml_data, dict):
                raise ValueError("YAML 文件格式无效")
            st.success(f"已导入 YAML：{yaml_data.get('story_graph', {}).get('metadata', {}).get('title', '未命名')}")
        except yaml.YAMLError as e:
            st.error(f"YAML 解析失败：{e}")
        except Exception as e:
            st.error(f"导入失败：{e}")

    return novel_text, title, author, yaml_data


# ── Workflow Execution ─────────────────────────────────────────────────────────


def render_workflow_buttons(novel_text, title, author, api_key, model, run_check):
    """Render SKL build and screenplay generation buttons.

    Uses synchronous execution (no background threads) to avoid all
    session_state cross-thread issues.  A spinner shows while running.
    """
    col1, col2 = st.columns(2)

    with col1:
        btn_build = st.button(
            "📚 构建知识图谱（SKL）",
            type="primary",
            use_container_width=True,
            help="提取角色/场景/事件/关系，构建全局知识层",
            disabled=st.session_state.get("workflow_running", False),
        )
    with col2:
        btn_scripts = st.button(
            "🎬 生成剧本（含 SKL）",
            use_container_width=True,
            help="构建知识图谱 + 逐场景生成剧本（需要更多 API 调用）",
            disabled=st.session_state.get("workflow_running", False),
        )

    if not novel_text:
        st.info("请先输入小说文本")
        return
    if not api_key:
        st.error("请输入 API Key")
        return

    if btn_build:
        mode = "skl"
        label = "正在构建知识图谱"
    elif btn_scripts:
        mode = "scripts"
        label = "正在生成剧本（耗时较长）"
    else:
        return

    with st.spinner(f"**{label}**，请稍候..."):
        _run_workflow_sync(novel_text, title, author, api_key, model, run_check, mode)

    # Drain queue to populate session state
    import queue
    result_queue = st.session_state.get("_result_queue")
    if result_queue is not None:
        try:
            while True:
                msg_type, payload = result_queue.get_nowait()
                if msg_type == "result":
                    st.session_state["workflow_result"] = payload
                    st.session_state["show_scripts_generated"] = (mode == "scripts")
                elif msg_type == "error":
                    st.session_state["workflow_error"] = payload
                    st.error(f"执行出错：{payload}")
        except queue.Empty:
            pass

    st.rerun()


# ── Result Summary ────────────────────────────────────────────────────────────


def render_summary(result: WorkflowResult):
    if not result or not result.success:
        return
    graph = result.graph
    gsk = result.global_skl
    scripts_count = len(graph.scripts) if graph.scripts else 0
    total_items = sum(len(s.content) for s in graph.scripts.values()) if graph.scripts else 0

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.metric("章节", len(result.chapters))
    with col2:
        st.metric("角色", len(graph.characters))
    with col3:
        st.metric("场景", len(graph.scenes))
    with col4:
        st.metric("关系", len(graph.relations))
    with col5:
        st.metric("事件", len(graph.events))
    with col6:
        st.metric("剧本", f"{scripts_count}场景/{total_items}条", delta="🎬" if scripts_count else None)


# ── Tab: Metadata ─────────────────────────────────────────────────────────────


def render_metadata_tab(graph: StoryGraph):
    meta = graph.metadata
    c1, c2 = st.columns(2)
    with c1:
        st.text(f"**标题**: {meta.get('title', '未命名')}")
        st.text(f"**作者**: {meta.get('author', '未知')}")
        st.text(f"**题材**: {meta.get('genre', '未指定')}")
        st.text(f"**改编工具**: {meta.get('adapted_by', 'StoryForge')}")
    with c2:
        st.text(f"**创建时间**: {meta.get('created_at', '未知')}")
        st.text(f"**版本**: {graph.version}")
        st.text(f"**章节数**: {meta.get('total_chapters', '-')}")
        st.text(f"**去重角色**: {meta.get('unique_characters', '-')}")

    # Merger stats
    st.divider()
    st.subheader("📊 知识合并报告")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("去重角色", meta.get("unique_characters", "-"))
    with c2:
        st.metric("去重场景", meta.get("unique_scenes", "-"))
    with c3:
        st.metric("去重关系", meta.get("unique_relations", "-"))
    with c4:
        st.metric("去重事件", meta.get("unique_events", "-"))


# ── Tab: Characters ────────────────────────────────────────────────────────────


def render_characters_tab(result: WorkflowResult, graph: StoryGraph, gsk):
    if not graph.characters:
        st.info("暂无角色数据")
        return

    # ── Character correction panel ──────────────────────────────────────────
    with st.expander("✏️ 修正角色信息"):
        if not gsk:
            st.info("从历史记录加载时修正功能不可用（需要重新运行 pipeline）")
        else:
            target_name = st.selectbox(
                "选择角色", [""] + [c.name for c in graph.characters],
            )
            if target_name:
                c1, c2 = st.columns(2)
                with c1:
                    field = st.selectbox("修正字段", ["name", "role", "description"])
                with c2:
                    new_value = st.text_input("新值")
                reason = st.text_input("修正原因", placeholder="例如：用户确认")
                if st.button("应用修正", type="primary"):
                    if not new_value:
                        st.warning("新值不能为空，请输入有效内容")
                    elif not reason:
                        st.warning("请填写修正原因")
                    else:
                        governor = KnowledgeGovernor(gsk, graph=graph)
                        old_value = ""
                        for c in gsk.characters:
                            if c.name == target_name:
                                old_value = getattr(c, field, "")
                                break
                        patch = Patch(
                            target_type="character",
                            target_id=target_name,
                            field=field,
                            old_value=old_value,
                            new_value=new_value,
                            reason=reason,
                        )
                        success = governor.apply_patch(patch)
                        if success:
                            st.success(f"已修正「{target_name}」的 {field} → 「{new_value}」")
                            st.rerun()
                        else:
                            st.error("修正失败")

    st.divider()

    for c in graph.characters:
        role = c.role.value if hasattr(c.role, "value") else c.role
        with st.expander(f"**{c.name}** ({role})", expanded=True):
            c1, c2 = st.columns(2)
            with c1:
                st.text(f"ID: {c.id}")
                st.text(f"首次出现: {c.first_appearance}")
            with c2:
                st.text(f"定位: {role}")
            if c.description:
                st.text(f"描述: {c.description}")


# ── Tab: Relations ────────────────────────────────────────────────────────────


def render_relations_tab(result: WorkflowResult, graph: StoryGraph):
    if not graph.relations:
        st.info("暂无关系数据")
        return

    rel_type_labels = {
        "family": "血缘",
        "friend": "朋友",
        "enemy": "敌对",
        "romantic": "恋爱",
        "professional": "职业",
        "stranger": "陌生",
    }

    # Relation type summary
    from collections import Counter
    type_counts = Counter(r.relation_type if hasattr(r, "relation_type") else getattr(r, "relation_type", "stranger")
                          for r in graph.relations)
    st.subheader(f"共 {len(graph.relations)} 条关系")
    cols = st.columns(len(type_counts))
    for i, (rtype, count) in enumerate(type_counts.most_common()):
        with cols[i] if i < len(cols) else st:
            st.metric(rel_type_labels.get(rtype, rtype), count)

    st.divider()

    for r in graph.relations:
        rtype = r.relation_type if hasattr(r.relation_type, "value") else getattr(r, "relation_type", "stranger")
        rtype_label = rel_type_labels.get(rtype, rtype)
        with st.expander(f"**{r.from_char}** → [{rtype_label}] → **{r.to_char}**", expanded=False):
            st.text(f"类型: {rtype_label} ({rtype})")
            if r.description:
                st.text(f"描述: {r.description}")


# ── Tab: Events ───────────────────────────────────────────────────────────────


def render_events_tab(result: WorkflowResult, graph: StoryGraph):
    if not graph.events:
        st.info("暂无事件数据")
        return

    st.subheader(f"共 {len(graph.events)} 个事件")

    # Event type filter
    event_types = sorted(set(
        e.event_type.value if hasattr(e.event_type, "value") else getattr(e, "event_type", "transition")
        for e in graph.events
    ))
    selected_types = st.multiselect(
        "筛选事件类型", event_types, default=event_types,
        format_func=lambda x: x.replace("_", " ").title(),
    )

    filtered = [
        e for e in graph.events
        if (e.event_type.value if hasattr(e.event_type, "value") else getattr(e, "event_type", "transition")) in selected_types
    ]

    event_type_labels = {
        "conflict": "冲突",
        "revelation": "揭示",
        "transition": "过渡",
        "turning_point": "转折",
        "resolution": "收尾",
    }
    event_type_icons = {
        "conflict": "⚔️",
        "revelation": "💡",
        "transition": "➡️",
        "turning_point": "🔄",
        "resolution": "✅",
    }

    for i, e in enumerate(filtered, 1):
        etype = e.event_type.value if hasattr(e.event_type, "value") else getattr(e, "event_type", "transition")
        icon = event_type_icons.get(etype, "")
        label = event_type_labels.get(etype, etype)
        with st.expander(f"**{i}. [{label}] {e.title}** {icon}", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                st.text(f"地点: {e.location or '未标注'}")
                st.text(f"时间: {e.time_marker or '未标注'}")
            with c2:
                st.text(f"参与者: {', '.join(e.participants) if e.participants else '无'}")
            if e.description:
                st.text(f"描述: {e.description}")
            if e.cause:
                st.text(f"原因: {e.cause}")
            if e.consequence:
                st.text(f"后果: {e.consequence}")


# ── Tab: Scenes ──────────────────────────────────────────────────────────────


def render_scenes_tab(result: WorkflowResult, graph: StoryGraph):
    if not graph.scenes:
        st.info("暂无场景数据")
        return

    st.subheader(f"共 {len(graph.scenes)} 个场景")

    for s in graph.scenes:
        with st.expander(f"**{s.title}** — 第{s.act}幕", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                st.text(f"地点: {s.location or '未标注'}")
                st.text(f"时间: {s.time or '未标注'}")
            with c2:
                st.text(f"角色: {', '.join(s.characters_present) if s.characters_present else '无'}")
                st.text(f"关联事件: {len(s.event_ids)}")
            if s.summary:
                st.text(f"概要: {s.summary}")

            # Show script if available
            if s.id in graph.scripts:
                st.divider()
                st.markdown("**剧本内容**")
                script = graph.scripts[s.id]
                for item in script.content:
                    if item.type == "action":
                        st.text(f"　{item.text}")
                    else:
                        st.text(f"**{item.character}**: {item.text}")


# ── Tab: Outline ──────────────────────────────────────────────────────────────


def render_outline_tab(result: WorkflowResult):
    if not result or not result.global_skl:
        st.info("暂无大纲数据")
        return

    gsk = result.global_skl
    outline = gsk.outline

    if not outline:
        st.info("未生成大纲")
        return

    c1, c2 = st.columns(2)
    with c1:
        st.metric("题材", outline.get("genre", "未知"))
    with c2:
        st.metric("主线冲突", outline.get("main_conflict", "未知")[:30] + ("..." if len(outline.get("main_conflict", "")) > 30 else ""))

    if outline.get("theme"):
        st.subheader("主题")
        st.text(outline["theme"])

    if outline.get("arc_summary"):
        st.subheader("角色弧光")
        st.text(outline["arc_summary"])

    acts = outline.get("act_summaries", [])
    if acts:
        st.subheader("三幕结构")
        for act in acts:
            act_num = act.get("act_number", "?")
            act_title = act.get("title", f"第{act_num}幕")
            with st.expander(f"**第{act_num}幕: {act_title}**", expanded=False):
                st.text(act.get("summary", ""))
                scenes = act.get("key_scenes", [])
                if scenes:
                    st.text("关键场景:")
                    for s in scenes:
                        st.text(f"  • {s}")

    key_points = outline.get("key_plot_points", [])
    if key_points:
        st.subheader("关键情节点")
        for i, pt in enumerate(key_points, 1):
            st.text(f"{i}. {pt}")


# ── Tab: Timeline ─────────────────────────────────────────────────────────────


def render_timeline_tab(result: WorkflowResult):
    if not result or not result.global_skl:
        st.info("暂无时间线数据")
        return

    gsk = result.global_skl
    timeline = gsk.timeline

    if not timeline:
        st.info("暂无时间线数据")
        return

    st.subheader(f"共 {len(timeline)} 个时间线条目")

    time_icons = {
        "黎明": "🌅", "凌晨": "🌙", "清晨": "🌅", "早晨": "🌅",
        "上午": "☀️", "中午": "☀️", "午间": "☀️", "午后": "🌤️",
        "下午": "🌤️", "傍晚": "🌆", "黄昏": "🌆", "晚上": "🌙",
        "夜里": "🌙", "深夜": "🌙", "午夜": "🌙",
        "未标注": "❓",
    }

    for entry in timeline:
        icon = time_icons.get(entry.time_marker, "⏰")
        with st.expander(f"{icon} **{entry.time_marker}** — {entry.event_title}", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                st.text(f"地点: {entry.location or '未标注'}")
                st.text(f"章节: {entry.chapter_title or '未知'}")
            with c2:
                st.text(f"类型: {entry.event_type}")
                st.text(f"参与者: {', '.join(entry.participants) if entry.participants else '无'}")

            if entry.causal_predecessors:
                st.text(f"前序事件: {', '.join(entry.causal_predecessors)}")
            if entry.causal_successors:
                st.text(f"后续事件: {', '.join(entry.causal_successors)}")


# ── Tab: Locations ─────────────────────────────────────────────────────────────


def render_locations_tab(result: WorkflowResult):
    if not result or not result.global_skl:
        st.info("暂无地点数据")
        return

    gsk = result.global_skl
    locations = gsk.locations

    if not locations:
        st.info("暂无地点数据")
        return

    st.subheader(f"共 {len(locations)} 个地点")

    type_icons = {"indoor": "🏠", "outdoor": "🌍", "mixed": "🔀"}
    type_labels = {"indoor": "室内", "outdoor": "室外", "mixed": "混合"}

    for loc in locations:
        icon = type_icons.get(loc.location_type, "📍")
        label = type_labels.get(loc.location_type, loc.location_type)
        with st.expander(f"{icon} **{loc.name}** ({label}) × {loc.frequency}", expanded=False):
            st.text(f"类型: {label} ({loc.location_type})")
            st.text(f"出现频次: {loc.frequency}")
            if loc.scenes:
                st.text(f"关联场景: {', '.join(loc.scenes)}")
            if loc.narrative_significance:
                st.text(f"叙事意义: {loc.narrative_significance}")
            if loc.emotional_atmosphere:
                st.text(f"情感氛围: {loc.emotional_atmosphere}")


# ── Tab: Warnings ──────────────────────────────────────────────────────────────


def render_warnings_tab(graph: StoryGraph):
    if not graph.warnings:
        st.success("✅ 未发现一致性问题")
        return

    errors = [w for w in graph.warnings if w.severity.value == "error"]
    warnings = [w for w in graph.warnings if w.severity.value == "warning"]
    infos = [w for w in graph.warnings if w.severity.value == "info"]

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("错误", len(errors), delta_color="inverse")
    with c2:
        st.metric("警告", len(warnings), delta_color="off")
    with c3:
        st.metric("提示", len(infos), delta_color="off")

    st.divider()

    if errors:
        st.error("错误 — 必须修复")
        for w in errors:
            with st.expander(f"**{w.code.value}**: {w.message}", expanded=True):
                if w.scene_ids:
                    st.text(f"涉及场景: {', '.join(w.scene_ids)}")
                if w.characters_involved:
                    st.text(f"涉及角色: {', '.join(w.characters_involved)}")

    if warnings:
        st.warning("警告 — 建议检查")
        for w in warnings:
            with st.expander(f"**{w.code.value}**: {w.message}", expanded=True):
                if w.scene_ids:
                    st.text(f"涉及场景: {', '.join(w.scene_ids)}")
                if w.characters_involved:
                    st.text(f"涉及角色: {', '.join(w.characters_involved)}")

    if infos:
        st.info("提示")
        for w in infos:
            st.text(f"- **{w.code.value}**: {w.message}")


# ── Tab: Governance ────────────────────────────────────────────────────────────


def render_governance_tab(result: WorkflowResult):
    st.subheader("🛡️ 知识治理报告")

    if not result or not result.governance_report:
        st.info("请先运行工作流以获取治理报告")
        return

    report = result.governance_report

    val_passed = "✅ PASSED" if report.validation.passed else "❌ FAILED"
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("验证状态", val_passed)
    with c2:
        st.metric("冲突数", len(report.conflicts))
    with c3:
        st.metric("自动修正", len(report.auto_corrections))
    with c4:
        st.metric("审计记录", len(report.audit_trail.entries))

    st.divider()

    # Validation issues
    st.subheader("📋 验证问题")
    if not report.validation.issues:
        st.success("✅ 无验证问题")
    else:
        for issue in report.validation.issues:
            icon = "🔴" if issue.severity == "error" else "🟡" if issue.severity == "warning" else "ℹ️"
            st.text(f"{icon} [{issue.severity.upper()}] {issue.code}: {issue.message}")

    st.divider()

    # Conflicts
    st.subheader("⚔️ 冲突列表")
    if not report.conflicts:
        st.success("✅ 未检测到冲突")
    else:
        for i, conflict in enumerate(report.conflicts, 1):
            with st.expander(f"**冲突 {i}**: {conflict.conflict_type}", expanded=False):
                st.text(f"类型: {conflict.conflict_type}")
                st.text(f"实体A: {conflict.entity_a}")
                st.text(f"实体B: {conflict.entity_b}")
                st.text(f"仲裁策略: {conflict.resolution or '未仲裁'}")
                if conflict.resolved_value:
                    st.text(f"仲裁结果: {conflict.resolved_value}")

    st.divider()

    # Auto corrections
    st.subheader("🔧 自动修正记录")
    if not report.auto_corrections:
        st.info("无自动修正记录")
    else:
        for corr in report.auto_corrections:
            st.text(f"• {corr.get('type', 'N/A')}: {corr}")

    st.divider()

    # Quick patch
    st.subheader("✏️ 快速修正")
    if not result.global_skl:
        st.info("无 SKL 数据")
    else:
        with st.expander("添加角色修正", expanded=False):
            target_name = st.selectbox(
                "角色",
                [""] + [c.name for c in result.global_skl.characters],
            )
            if target_name:
                c1, c2 = st.columns(2)
                with c1:
                    field = st.selectbox("字段", ["name", "role", "description"])
                with c2:
                    new_val = st.text_input("新值")
                reason = st.text_input("原因", placeholder="例如：用户确认")
                if st.button("应用", type="primary"):
                    if not new_val:
                        st.warning("新值不能为空")
                    elif not reason:
                        st.warning("请填写修正原因")
                    else:
                        governor = KnowledgeGovernor(result.global_skl, graph=result.graph)
                        old_val = ""
                        for c in result.global_skl.characters:
                            if c.name == target_name:
                                old_val = getattr(c, field, "")
                                break
                        patch = Patch("character", target_name, field, old_val, new_val, reason)
                        if governor.apply_patch(patch):
                            st.success(f"已修正 「{target_name}.{field}」 = 「{new_val}」")
                            st.rerun()
                        else:
                            st.error("修正失败")


# ── Tab: Audit Trail ──────────────────────────────────────────────────────────


def render_audit_tab(result: WorkflowResult):
    st.subheader("📝 变更审计记录")

    if not result or not result.governance_report:
        st.info("请先运行工作流以获取审计记录")
        return

    report = result.governance_report
    entries = report.audit_trail.entries

    if not entries:
        st.info("暂无审计记录")
        return

    c1, c2 = st.columns(2)
    with c1:
        st.metric("记录总数", len(entries))
    with c2:
        st.metric("最近更新", entries[-1].timestamp[:19] if entries else "-")

    st.divider()

    from collections import Counter
    action_counts = Counter(e.action for e in entries)
    st.caption("操作类型分布: " + " | ".join(f"{k}: {v}" for k, v in action_counts.items()))

    st.divider()

    action_icons = {
        "patch": "✏️", "auto_correct": "🔧", "resolve_conflict": "⚔️", "rollback": "↩️",
    }

    for i, entry in enumerate(reversed(entries)):
        icon = action_icons.get(entry.action, "📝")
        with st.expander(
            f"{icon} [{entry.action}] {entry.target_type} / {entry.target_id} — {entry.timestamp[:19]}",
            expanded=False,
        ):
            if entry.reason:
                st.text(f"原因: {entry.reason}")
            if entry.user:
                st.text(f"用户: {entry.user}")
            c1, c2 = st.columns(2)
            with c1:
                st.text(f"修改前: {entry.before}")
            with c2:
                st.text(f"修改后: {entry.after}")


# ── Tab: Screenplay Editor ─────────────────────────────────────────────────────


def render_screenplay_tab(result: WorkflowResult, graph: StoryGraph):
    st.subheader("🎬 剧本编辑")

    if not result or not result.global_skl:
        st.info("请先生成剧本")
        return

    gsk = result.global_skl
    scripts = graph.scripts

    if not scripts:
        st.info("暂无剧本数据")
        return

    st.markdown(f"已生成 **{len(scripts)}** 个场景的剧本，共 **{sum(len(s.content) for s in scripts.values())}** 条记录")
    st.markdown("直接在下方编辑剧本内容，修改后点击「💾 保存修改」后可在 YAML 导出中看到更新。")

    # Initialize edited_scripts from current graph
    if "edited_scripts" not in st.session_state or not st.session_state["edited_scripts"]:
        st.session_state["edited_scripts"] = {
            sid: [
                {"type": item.type, "text": item.text, "character": item.character}
                for item in script.content
            ]
            for sid, script in scripts.items()
        }

    # Scene selector
    scene_ids = list(scripts.keys())
    selected_scene = st.selectbox("选择场景", scene_ids)

    if selected_scene:
        script_node = scripts[selected_scene]
        edited = st.session_state["edited_scripts"].get(selected_scene, [])

        st.divider()
        st.markdown(f"**场景: {script_node.id}**")

        # Editable script items
        new_edited = []
        for idx, item in enumerate(edited):
            item_type = item.get("type", "action")
            col_label, col_text = st.columns([1, 4])
            with col_label:
                st.text(f"[{item_type}]")
            with col_text:
                if item_type == "dialogue":
                    char_col, text_col = st.columns([1, 3])
                    with char_col:
                        new_char = st.text_input(
                            "角色", value=item.get("character", ""),
                            key=f"char_{selected_scene}_{idx}",
                            label_visibility="collapsed",
                        )
                    with text_col:
                        new_text = st.text_area(
                            "台词", value=item.get("text", ""),
                            key=f"text_{selected_scene}_{idx}",
                            height=60, label_visibility="collapsed",
                        )
                else:
                    new_text = st.text_area(
                        "动作", value=item.get("text", ""),
                        key=f"text_{selected_scene}_{idx}",
                        height=60, label_visibility="collapsed",
                    )
                    new_char = item.get("character", "")
                new_edited.append({"type": item_type, "text": new_text, "character": new_char})

        st.session_state["edited_scripts"][selected_scene] = new_edited

        # Save changes button
        if st.button("💾 保存修改", type="primary"):
            # Apply edits to graph in memory
            updated_items = []
            for item_dict in new_edited:
                updated_items.append(ScriptItem(
                    type=item_dict["type"],
                    text=item_dict["text"],
                    character=item_dict.get("character", ""),
                ))
            graph.scripts[selected_scene] = ScriptNode(id=selected_scene, content=updated_items)
            st.success(f"已保存「{selected_scene}」的修改")
            st.rerun()

        # Add new item
        st.divider()
        with st.expander("➕ 添加剧本条目", expanded=False):
            new_type = st.selectbox("类型", ["action", "dialogue"], key="new_type")
            new_text_val = st.text_input("内容", key="new_text")
            new_char_val = st.text_input("角色（dialogue 必填）", key="new_char", disabled=(new_type == "action"))
            if st.button("添加到场景", type="secondary"):
                new_item = {"type": new_type, "text": new_text_val, "character": new_char_val if new_type == "dialogue" else ""}
                st.session_state["edited_scripts"][selected_scene].append(new_item)
                st.rerun()

        # Delete last item
        if st.button("🗑️ 删除最后一条"):
            if st.session_state["edited_scripts"][selected_scene]:
                st.session_state["edited_scripts"][selected_scene].pop()
                st.rerun()


# ── Tab: YAML Export ──────────────────────────────────────────────────────────


def render_yaml_tab(result: WorkflowResult, graph: StoryGraph):
    st.subheader("📄 YAML 导出与预览")

    # Live YAML preview
    yaml_output = graph.to_yaml()
    st.session_state["yaml_output"] = yaml_output

    # Edit in YAML mode
    st.markdown("**YAML 源码（可直接编辑）**")
    edited_yaml = st.text_area(
        "YAML 内容",
        value=yaml_output,
        height=400,
        label_visibility="collapsed",
        key="yaml_editor",
    )

    # Reload from edited YAML
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if st.button("🔄 从 YAML 重新加载", use_container_width=True):
            try:
                data = yaml.safe_load(edited_yaml)
                _apply_yaml_to_graph(data, graph)
                st.success("已从 YAML 重新加载")
                st.rerun()
            except Exception as e:
                st.error(f"解析失败：{e}")

    with c2:
        # Download YAML
        st.download_button(
            "📥 下载 YAML",
            data=edited_yaml,
            file_name=f"{graph.metadata.get('title', 'story')}.yaml",
            mime="text/yaml",
            use_container_width=True,
        )

    with c3:
        # Copy to clipboard
        st.code(edited_yaml[:200] + ("..." if len(edited_yaml) > 200 else ""), language="yaml")

    with c4:
        st.caption(f"YAML 长度: {len(edited_yaml)} 字符")


# ── YAML Import/Export Helpers ─────────────────────────────────────────────────


def _apply_yaml_to_graph(data: dict, graph: StoryGraph):
    """Apply YAML data back to StoryGraph (metadata + warnings only; characters/scenes/events/scripts are read-only after generation)."""
    sg = data.get("story_graph", data)

    # Update metadata
    if "metadata" in sg:
        graph.metadata.update(sg["metadata"])

    # Update warnings
    if "warnings" in sg:
        from core.story_graph import WarningNode, WarningCode, WarningSeverity
        graph.warnings = []
        for w in sg["warnings"]:
            code_str = w.get("code", "INFO")
            try:
                code = WarningCode[code_str]
            except Exception:
                code = WarningCode.INFO
            sev_str = w.get("severity", "info")
            try:
                sev = WarningSeverity[sev_str.upper()]
            except Exception:
                sev = WarningSeverity.INFO
            graph.warnings.append(WarningNode(
                code=code,
                message=w.get("message", ""),
                severity=sev,
                scene_ids=w.get("scene_ids", []),
                characters_involved=w.get("characters_involved", []),
            ))


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    init_session_state()
    render_header()
    api_key, model, run_check, run_governance = render_sidebar()
    if run_governance:
        pass  # governance is always enabled in workflow; reserved for future per-toggle control
    novel_text, title, author, yaml_data = render_upload_section()

    # Handle YAML import
    if yaml_data is not None:
        from core.story_graph import StoryGraph
        graph = StoryGraph()
        _apply_yaml_to_graph(yaml_data, graph)
        st.session_state["workflow_result"] = None
        st.session_state["graph_imported"] = graph
        st.info("YAML 已导入，可在「YAML 导出」标签页中查看和继续编辑")

    render_workflow_buttons(
        novel_text, title, author, api_key, model, run_check,
    )

    # Show saved story info if available
    saved_id = st.session_state.get("_saved_story_id")
    if saved_id:
        st.success(f"✅ 故事已保存（ID: `{saved_id[:16]}...`）")

    # Render results
    current_result = st.session_state.get("workflow_result")

    if not current_result:
        # Show imported graph if any
        imported = st.session_state.get("graph_imported")
        if imported:
            render_summary_from_graph(imported)
        else:
            st.info("👆 请上传小说文本并点击按钮开始转换")
        return

    render_summary(current_result)

    graph = current_result.graph
    gsk = current_result.global_skl

    # Tab layout
    tabs = [
        "📋 元信息", "👥 角色", "🔗 关系", "🎭 事件",
        "🎬 场景", "📝 大纲", "⏱️ 时间线", "📍 地点",
        "⚠️ 警告", "🛡️ 治理", "📝 审计",
        "🎬 剧本编辑", "📄 YAML 导出", "📦 中间文档",
    ]

    tab_objects = st.tabs(tabs)

    with tab_objects[0]:
        render_metadata_tab(graph)
    with tab_objects[1]:
        render_characters_tab(current_result, graph, gsk)
    with tab_objects[2]:
        render_relations_tab(current_result, graph)
    with tab_objects[3]:
        render_events_tab(current_result, graph)
    with tab_objects[4]:
        render_scenes_tab(current_result, graph)
    with tab_objects[5]:
        render_outline_tab(current_result)
    with tab_objects[6]:
        render_timeline_tab(current_result)
    with tab_objects[7]:
        render_locations_tab(current_result)
    with tab_objects[8]:
        render_warnings_tab(graph)
    with tab_objects[9]:
        render_governance_tab(current_result)
    with tab_objects[10]:
        render_audit_tab(current_result)
    with tab_objects[11]:
        render_screenplay_tab(current_result, graph)
    with tab_objects[12]:
        render_yaml_tab(current_result, graph)
    with tab_objects[13]:
        render_pipeline_docs_tab()


def render_summary_from_graph(graph: StoryGraph):
    """Render a minimal summary when only a YAML was imported."""
    meta = graph.metadata
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("标题", meta.get("title", "未命名"))
    with c2:
        st.metric("角色", len(graph.characters))
    with c3:
        st.metric("场景", len(graph.scenes))


def render_pipeline_docs_tab():
    """Show all intermediate pipeline documents.

    Reads from session state (set by live run or _load_story).
    """
    storage = st.session_state.get("_storage")
    story_id = st.session_state.get("_saved_story_id", "")

    # ── Phase 0: Pipeline Log ────────────────────────────────────────────────
    st.subheader("📊 Pipeline 统计")
    log = storage.load_pipeline_log(story_id) if storage and story_id else {}
    current_result = st.session_state.get("workflow_result")
    if not log:
        log = current_result.merger_report if current_result else {}

    if log:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("章节数", log.get("total_chapters", "-"))
        with c2:
            st.metric("去重角色", log.get("unique_characters", "-"))
        with c3:
            st.metric("去重场景", log.get("unique_scenes", "-"))
        with c4:
            st.metric("去重事件", log.get("unique_events", "-"))
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("去重关系", log.get("unique_relations", "-"))
        with c2:
            st.metric("地点数", log.get("locations_count", "-"))
        with c3:
            st.metric("时间线数", log.get("timeline_count", "-"))
        st.divider()
    else:
        st.info("暂无 pipeline 统计")

    # ── Phase 3+4: Local Knowledge per chapter ─────────────────────────────
    st.subheader("📄 各章抽取知识（阶段 3+4）")

    # Use session state if loaded from storage, else use step_results from live run
    local_knowledge_list = st.session_state.get("_local_knowledge", [])

    # If empty, build from step_results (live run)
    if not local_knowledge_list and current_result and current_result.step_results:
        step_results = current_result.step_results
        by_chapter: dict[str, dict] = {}
        for lst, key in [
            (step_results.get("characters", []), "characters"),
            (step_results.get("scenes", []), "scenes"),
            (step_results.get("events", []), "events"),
            (step_results.get("relations", []), "relations"),
        ]:
            for item in lst:
                cid = _get_chapter_id(item)
                if cid not in by_chapter:
                    by_chapter[cid] = {"chapter_id": cid, "characters": [], "scenes": [],
                                       "events": [], "relations": []}
                by_chapter[cid][key].append(item)

        for ch in (current_result.chapters or []):
            cid = ch.id if hasattr(ch, "id") else ch.get("id", "") if isinstance(ch, dict) else ""
            ch_title = ch.title if hasattr(ch, "title") else ch.get("title", cid) if isinstance(ch, dict) else cid
            if cid in by_chapter:
                by_chapter[cid]["chapter_title"] = ch_title
                by_chapter[cid]["characters"] = _dataclass_to_plain(by_chapter[cid]["characters"])
                by_chapter[cid]["scenes"] = _dataclass_to_plain(by_chapter[cid]["scenes"])
                by_chapter[cid]["events"] = _dataclass_to_plain(by_chapter[cid]["events"])
                by_chapter[cid]["relations"] = _dataclass_to_plain(by_chapter[cid]["relations"])
                local_knowledge_list.append(by_chapter[cid])

    if not local_knowledge_list:
        st.info("暂无各章抽取数据")
    else:
        # Group by chapter
        for lk in local_knowledge_list:
            cid = lk.get("chapter_id", "")
            ch_title = lk.get("chapter_title", cid)
            n_chars = len(lk.get("characters", []))
            n_scenes = len(lk.get("scenes", []))
            n_events = len(lk.get("events", []))
            n_rels = len(lk.get("relations", []))
            with st.expander(
                f"**{ch_title}** | 角色:{n_chars} 场景:{n_scenes} 事件:{n_events} 关系:{n_rels}",
                expanded=False,
            ):
                if lk.get("characters"):
                    st.markdown("**角色**")
                    for c in lk["characters"]:
                        st.text(f"  • {c.get('name','')} | {c.get('role','')} | {c.get('description','')[:60]}")
                if lk.get("scenes"):
                    st.markdown("**场景**")
                    for s in lk["scenes"]:
                        st.text(f"  • {s.get('title','')} @ {s.get('location','')}")
                if lk.get("events"):
                    st.markdown("**事件**")
                    for e in lk["events"]:
                        st.text(f"  • [{e.get('event_type','')}] {e.get('title','')}")
                if lk.get("relations"):
                    st.markdown("**关系**")
                    for r in lk["relations"]:
                        st.text(f"  • {r.get('from_char','')} --[{r.get('relation_type','')}]--> {r.get('to_char','')}")

    # ── Phase 5: SKL Summary ─────────────────────────────────────────────────
    st.divider()
    st.subheader("🗂️ SKL 全局知识摘要（阶段 5）")
    gsk = current_result.global_skl if current_result else None
    if gsk:
        c1, c2 = st.columns(2)
        with c1:
            st.metric("去重后角色", len(gsk.characters))
        with c2:
            st.metric("去重后场景", len(gsk.scenes))
        if gsk.outline:
            st.markdown(f"**题材**: {gsk.outline.get('genre', '-')}")
            st.markdown(f"**主题**: {gsk.outline.get('theme', '-')}")
            st.markdown(f"**主线冲突**: {gsk.outline.get('main_conflict', '-')}")
    else:
        st.info("暂无 SKL 数据（从历史加载时不可用）")

    # ── Phase 6: Governance Report ─────────────────────────────────────────
    st.divider()
    st.subheader("🛡️ 治理报告（阶段 6）")
    if current_result and current_result.governance_report:
        rep = result.governance_report
        val_passed = "✅ PASSED" if rep.validation.passed else "❌ FAILED"
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("验证", val_passed)
        with c2:
            st.metric("冲突", len(rep.conflicts))
        with c3:
            st.metric("自动修正", len(rep.auto_corrections))
        if rep.validation.issues:
            st.markdown("**验证问题**")
            for issue in rep.validation.issues:
                st.text(f"  [{issue.severity}] {issue.code}: {issue.message}")
        if rep.conflicts:
            st.markdown("**冲突**")
            for cf in rep.conflicts:
                st.text(f"  • {cf.conflict_type}: {cf.entity_a} vs {cf.entity_b}")
    else:
        st.info("暂无治理报告（从历史加载时不可用）")


def _get_chapter_id(item) -> str:
    """Extract chapter_id from an item's source, whether it's a dataclass or dict."""
    src = getattr(item, "source", None)
    if src is None:
        return ""
    if isinstance(src, dict):
        return src.get("chapter_id", "")
    return getattr(src, "chapter_id", "")


def _dataclass_to_plain(obj: Any) -> Any:
    if obj is None:
        return None
    if hasattr(obj, "__dict__"):
        return {k: _dataclass_to_plain(v) for k, v in obj.__dict__.items()}
    if isinstance(obj, (list, tuple)):
        return [_dataclass_to_plain(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _dataclass_to_plain(v) for k, v in obj.items()}
    if hasattr(obj, "value"):
        return obj.value
    return obj


def _load_story(story_id: str) -> bool:
    """Reconstruct a WorkflowResult from storage and populate session state.

    Returns True if loaded successfully, False if story not found.
    """
    storage = st.session_state.get("_storage")
    if not storage:
        return False

    if not storage.story_exists(story_id):
        return False

    from core.workflow import WorkflowResult
    from core.story_graph import StoryGraph

    summary = storage.load_story_summary(story_id)
    graph_data = storage.load_graph(story_id)
    skl_data = storage.load_skl(story_id)
    governance_data = storage.load_governance_report(story_id)
    chapters_data = storage.load_chapters(story_id)
    local_knowledge_list = storage.load_all_local_knowledge(story_id)

    result = WorkflowResult(success=True, novel_text="")
    result.graph = _graph_dict_to_storygraph(graph_data)
    if result.graph:
        result.graph.metadata["title"] = summary.get("title", "")
        result.graph.metadata["author"] = summary.get("author", "")
        result.graph.metadata.update(summary.get("graph_metadata", {}))

    result.merger_report = storage.load_pipeline_log(story_id)
    result.global_skl = _reconstruct_gsk(skl_data, chapters_data)
    result.governance_report = _reconstruct_governance_report(governance_data) if governance_data else None
    result.chapters = chapters_data

    # Store local knowledge for the "中间文档" tab
    st.session_state["_local_knowledge"] = local_knowledge_list

    st.session_state["workflow_result"] = result
    st.session_state["_current_story_id"] = story_id
    st.session_state["_saved_story_id"] = story_id
    return True


def _graph_dict_to_storygraph(data: dict) -> "StoryGraph":
    """Convert a stored graph dict back to a StoryGraph dataclass."""
    from core.story_graph import (
        StoryGraph, CharacterNode, RelationNode, EventNode,
        SceneNode, WarningNode, ScriptNode, ScriptItem,
        CharacterRole, EventType, WarningCode, WarningSeverity,
    )

    if not data:
        return StoryGraph()

    graph = StoryGraph()
    graph.version = data.get("version", "1.0")
    graph.metadata = data.get("metadata", {})

    for c in data.get("characters", []):
        role_str = c.get("role", "supporting")
        role = CharacterRole.SUPPORTING
        for r in CharacterRole:
            if r.value == role_str:
                role = r
                break
        graph.characters.append(CharacterNode(
            id=c.get("id", ""),
            name=c.get("name", ""),
            role=role,
            description=c.get("description", ""),
            first_appearance=c.get("first_appearance", ""),
        ))

    for r in data.get("relations", []):
        graph.relations.append(RelationNode(
            from_char=r.get("from_char", ""),
            to_char=r.get("to_char", ""),
            relation_type=r.get("relation_type", ""),
            description=r.get("description", ""),
        ))

    type_map = {
        "conflict": EventType.CONFLICT,
        "revelation": EventType.REVELATION,
        "transition": EventType.TRANSITION,
        "turning_point": EventType.TURNING_POINT,
        "resolution": EventType.RESOLUTION,
    }
    for e in data.get("events", []):
        et_str = e.get("event_type", "transition")
        graph.events.append(EventNode(
            title=e.get("title", ""),
            event_type=type_map.get(et_str, EventType.TRANSITION),
            location=e.get("location", ""),
            time_marker=e.get("time_marker", ""),
            participants=e.get("participants", []),
            description=e.get("description", ""),
            cause=e.get("cause", ""),
            consequence=e.get("consequence", ""),
        ))

    for s in data.get("scenes", []):
        graph.scenes.append(SceneNode(
            id=s.get("id", ""),
            title=s.get("title", ""),
            location=s.get("location", ""),
            time=s.get("time", ""),
            act=s.get("act", 1),
            characters_present=s.get("characters_present", []),
            summary=s.get("summary", ""),
        ))

    # Scripts
    for sid, sdata in data.get("scripts", {}).items():
        items = []
        for item in sdata.get("content", []):
            items.append(ScriptItem(
                type=item.get("type", "action"),
                text=item.get("text", ""),
                character=item.get("character", ""),
            ))
        graph.scripts[sid] = ScriptNode(id=sid, content=items)

    # Warnings
    sev_map = {
        "error": WarningSeverity.ERROR,
        "warning": WarningSeverity.WARNING,
        "info": WarningSeverity.INFO,
    }
    for w in data.get("warnings", []):
        code_str = w.get("code", "INFO")
        code = WarningCode.INFO
        for c in WarningCode:
            if c.value == code_str:
                code = c
                break
        graph.warnings.append(WarningNode(
            code=code,
            message=w.get("message", ""),
            severity=sev_map.get(w.get("severity", "info"), WarningSeverity.INFO),
            scene_ids=w.get("scene_ids", []),
            characters_involved=w.get("characters_involved", []),
        ))

    return graph


def _reconstruct_gsk(skl_data: dict, chapters_data: list) -> object:
    """Reconstruct a lightweight SKL from stored skl.json dict.

    Returns an object with outline, timeline, locations, characters, scenes, relations,
    events, character_first_appearance fields — enough for the UI tabs.
    """
    from core.knowledge_merger import GlobalStoryKnowledge
    from core.schema.models import Character, Scene, Relation
    from agent.location_agent import LocationInfo
    from agent.timeline_agent import TimelineEntry

    gsk = GlobalStoryKnowledge()
    gsk.title = skl_data.get("title", "")
    gsk.author = skl_data.get("author", "")
    gsk.outline = skl_data.get("outline", {})
    gsk.character_first_appearance = skl_data.get("character_first_appearance", {})

    # Reconstruct characters
    for c_data in skl_data.get("characters", []):
        src_data = c_data.get("source", {})
        if isinstance(src_data, dict):
            from core.schema.models import SourceTrace
            src = SourceTrace(
                chapter_id=src_data.get("chapter_id", ""),
                chapter_title=src_data.get("chapter_title", ""),
                char_range=tuple(src_data.get("char_range", (0, 0))),
            )
        else:
            src = None
        gsk.characters.append(Character(
            name=c_data.get("name", ""),
            description=c_data.get("description", ""),
            traits=c_data.get("traits", []),
            role=c_data.get("role", "supporting"),
            source=src,
        ))

    # Reconstruct scenes
    for s_data in skl_data.get("scenes", []):
        src_data = s_data.get("source", {})
        if isinstance(src_data, dict):
            from core.schema.models import SourceTrace
            src = SourceTrace(
                chapter_id=src_data.get("chapter_id", ""),
                chapter_title=src_data.get("chapter_title", ""),
                char_range=tuple(src_data.get("char_range", (0, 0))),
            )
        else:
            src = None
        gsk.scenes.append(Scene(
            title=s_data.get("title", ""),
            location=s_data.get("location", ""),
            time_of_day=s_data.get("time_of_day", ""),
            description=s_data.get("description", ""),
            characters=s_data.get("characters", []),
            source=src,
        ))

    # Reconstruct relations
    for r_data in skl_data.get("relations", []):
        src_data = r_data.get("source", {})
        if isinstance(src_data, dict):
            from core.schema.models import SourceTrace
            src = SourceTrace(
                chapter_id=src_data.get("chapter_id", ""),
                chapter_title=src_data.get("chapter_title", ""),
                char_range=tuple(src_data.get("char_range", (0, 0))),
            )
        else:
            src = None
        gsk.relations.append(Relation(
            from_char=r_data.get("from_char", ""),
            to_char=r_data.get("to_char", ""),
            relation_type=r_data.get("relation_type", ""),
            description=r_data.get("description", ""),
            source=src,
        ))

    # Events (stored as dicts in SKL)
    gsk.events = skl_data.get("events", [])

    # Locations
    for l_data in skl_data.get("locations", []):
        gsk.locations.append(LocationInfo(
            name=l_data.get("name", ""),
            location_type=l_data.get("location_type", "mixed"),
            frequency=l_data.get("frequency", 1),
            scenes=l_data.get("scenes", []),
            narrative_significance=l_data.get("narrative_significance", ""),
            emotional_atmosphere=l_data.get("emotional_atmosphere", ""),
        ))

    # Timeline
    for t_data in skl_data.get("timeline", []):
        gsk.timeline.append(TimelineEntry(
            time_marker=t_data.get("time_marker", ""),
            location=t_data.get("location", ""),
            event_title=t_data.get("event_title", ""),
            event_type=t_data.get("event_type", ""),
            participants=t_data.get("participants", []),
            chapter_title=t_data.get("chapter_title", ""),
            causal_predecessors=t_data.get("causal_predecessors", []),
            causal_successors=t_data.get("causal_successors", []),
        ))

    # Stats
    gsk.total_chapters = len(chapters_data)
    gsk.duplicates_removed = skl_data.get("duplicates_removed", {})

    return gsk


def _reconstruct_governance_report(report_data: dict) -> object:
    """Reconstruct GovernanceReport from stored governance.json dict."""
    from core.knowledge_governance import (
        GovernanceReport, ValidationReport, ValidationIssue,
        AuditTrail, AuditEntry,
    )

    # ValidationReport
    val_data = report_data.get("validation", {})
    issues = []
    for issue_data in val_data.get("issues", []):
        issues.append(ValidationIssue(
            severity=issue_data.get("severity", "info"),
            code=issue_data.get("code", ""),
            message=issue_data.get("message", ""),
            entity_type=issue_data.get("entity_type", ""),
            entity_id=issue_data.get("entity_id", ""),
        ))
    validation_report = ValidationReport(
        passed=val_data.get("passed", True),
        issues=issues,
    )

    # Conflicts
    from core.knowledge_governance import KnowledgeConflict
    conflicts = []
    for cf_data in report_data.get("conflicts", []):
        conflicts.append(KnowledgeConflict(
            conflict_type=cf_data.get("conflict_type", ""),
            entity_a=cf_data.get("entity_a", {}),
            entity_b=cf_data.get("entity_b", {}),
            resolution=cf_data.get("resolution", ""),
            resolved_value=cf_data.get("resolved_value"),
        ))

    # Auto corrections
    auto_corrections = report_data.get("auto_corrections", [])

    # Audit trail
    audit_trail = AuditTrail()
    for entry_data in report_data.get("audit_trail", {}).get("entries", []):
        audit_trail.entries.append(AuditEntry(
            timestamp=entry_data.get("timestamp", ""),
            action=entry_data.get("action", ""),
            target_type=entry_data.get("target_type", ""),
            target_id=entry_data.get("target_id", ""),
            before=entry_data.get("before"),
            after=entry_data.get("after"),
            reason=entry_data.get("reason", ""),
            user=entry_data.get("user", "system"),
        ))

    return GovernanceReport(
        validation=validation_report,
        conflicts=conflicts,
        auto_corrections=auto_corrections,
        patches_applied=report_data.get("patches_applied", 0),
        audit_trail=audit_trail,
    )


if __name__ == "__main__":
    main()
