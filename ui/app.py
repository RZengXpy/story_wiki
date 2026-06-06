"""StoryForge — AI Screenwriter Studio Streamlit UI."""

from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st
from datetime import datetime

from core.workflow import StoryForgeWorkflow, WorkflowResult
from core.story_graph import StoryGraph, CharacterRole, EventType, WarningSeverity
from core.knowledge_governance import govern_skl, Patch, KnowledgeGovernor, GovernanceReport


def init_session_state():
    """初始化会话状态."""
    defaults = {
        "graph": None,
        "workflow_result": None,
        "governance_report": None,
        "governor": None,
        "current_step": 0,
        "yaml_output": "",
        "audit_history": [],
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def render_header():
    """渲染页面头部."""
    st.set_page_config(
        page_title="StoryForge — AI 编剧工作台",
        page_icon="🎬",
        layout="wide",
    )
    st.title("🎬 StoryForge AI 编剧工作台")
    st.markdown("---")


def render_sidebar():
    """渲染侧边栏配置."""
    with st.sidebar:
        st.header("⚙️ 配置")

        api_key = st.text_input(
            "OpenAI API Key",
            type="password",
            help="输入你的 OpenAI API Key",
        )

        model = st.selectbox(
            "模型",
            ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
            index=0,
        )

        run_check = st.checkbox("启用一致性检查", value=True)

        st.markdown("---")
        st.caption("StoryForge v0.1.0")
        st.caption("基于多Agent架构的AI小说转剧本工具")

    return api_key, model, run_check


def render_upload_section():
    """渲染小说上传区域."""
    st.header("📖 上传小说")

    col1, col2 = st.columns([3, 1])

    with col1:
        novel_text = st.text_area(
            "粘贴小说文本",
            height=300,
            placeholder="在此粘贴小说文本内容...",
        )

    with col2:
        title = st.text_input("剧本标题", placeholder="例如：射雕英雄传")
        author = st.text_input("原著作者", placeholder="例如：金庸")

    uploaded_file = st.file_uploader(
        "或者上传 .txt 文件",
        type=["txt"],
        help="支持纯文本格式的小说文件",
    )

    if uploaded_file is not None:
        content = uploaded_file.read().decode("utf-8")
        if novel_text:
            st.warning("已加载上传文件，将覆盖文本框内容")
        novel_text = content

    return novel_text, title, author


def render_workflow_run(novel_text: str, title: str, author: str, api_key: str, model: str, run_check: bool):
    """渲染工作流执行按钮和进度."""
    if not novel_text:
        st.info("请先输入小说文本")
        return None, None

    if not api_key:
        st.error("请输入 OpenAI API Key")
        return None, None

    if st.button("🚀 开始转换", type="primary", use_container_width=True):
        with st.spinner("正在转换，请稍候..."):
            try:
                workflow = StoryForgeWorkflow(
                    model=model,
                    api_key=api_key,
                    run_consistency_check=run_check,
                )
                result = workflow.run(novel_text, title=title, author=author)
                return result, workflow
            except Exception as e:
                st.error(f"执行失败: {e}")
                return None, None

    return None, None


def render_results(result):
    """渲染执行结果."""
    st.header("📊 执行结果")

    if result is None:
        st.info("尚未执行工作流")
        return

    summary = result.summary()
    st.text(summary)

    if not result.success:
        st.error(f"执行失败: {result.error_message}")
        return

    graph = result.graph

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📋 元信息",
        "👥 角色",
        "🎭 事件",
        "🎬 场景",
        "⚠️ 警告",
        "🛡️ 知识治理",
        "📝 变更审计",
    ])

    with tab1:
        render_metadata_tab(graph)

    with tab2:
        render_characters_tab(result)

    with tab3:
        render_events_tab(graph)

    with tab4:
        render_scenes_tab(graph)

    with tab5:
        render_warnings_tab(graph)

    with tab6:
        render_governance_tab(result)

    with tab7:
        render_audit_tab(result)


def render_metadata_tab(graph: StoryGraph):
    """渲染元信息标签页."""
    meta = graph.metadata
    col1, col2 = st.columns(2)
    with col1:
        st.text(f"**标题**: {meta.get('title', '未命名')}")
        st.text(f"**作者**: {meta.get('author', '未知')}")
        st.text(f"**题材**: {meta.get('genre', '未指定')}")
    with col2:
        st.text(f"**创建时间**: {meta.get('created_at', '未知')}")
        st.text(f"**改编工具**: {meta.get('adapted_by', 'StoryForge')}")
        st.text(f"**版本**: {graph.version}")

    st.divider()
    if st.button("📄 导出 YAML", use_container_width=True):
        yaml_output = graph.to_yaml()
        st.session_state["yaml_output"] = yaml_output
        st.success("YAML 已生成，请查看下方导出区域")

    if st.session_state.get("yaml_output"):
        st.text_area("YAML 输出", value=st.session_state["yaml_output"], height=400, disabled=True)


def render_characters_tab(result: WorkflowResult):
    """渲染角色标签页 — 支持角色修正."""
    if result is None or result.graph is None:
        st.info("暂无数据")
        return
    graph = result.graph
    gsk = result.global_skl

    if not graph.characters:
        st.info("暂无角色数据")
        return

    # ── 角色修正区 ────────────────────────────────────────────
    with st.expander("✏️ 修正角色信息"):
        target_name = st.selectbox("选择要修正的角色", [""] + [c.name for c in graph.characters])
        if target_name:
            col1, col2 = st.columns(2)
            with col1:
                field = st.selectbox("修正字段", ["name", "description", "role"])
            with col2:
                new_value = st.text_input("新值")
            reason = st.text_input("修正原因", placeholder="例如：用户确认")
            if st.button("应用修正", type="primary") and result:
                governor = KnowledgeGovernor(result.global_skl, graph=graph)
                old_value = ""
                for c in result.global_skl.characters:
                    if c.name == target_name:
                        old_value = getattr(c, field, "")
                        break
                patch = Patch(
                    target_type="character",
                    target_id=target_name,
                    field=field,
                    old_value=old_value,
                    new_value=new_value,
                    reason=reason or "用户修正",
                )
                success = governor.apply_patch(patch)
                if success:
                    st.session_state["workflow_result"] = result
                    st.session_state["graph"] = graph
                    st.success(f"已修正角色 '{target_name}' 的 {field} 为 '{new_value}'")
                    st.rerun()
                else:
                    st.error("修正失败")

    st.divider()

    for c in graph.characters:
        role = c.role.value if hasattr(c.role, "value") else c.role
        with st.expander(f"**{c.name}** ({role})", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                st.text(f"ID: {c.id}")
                st.text(f"年龄: {c.age}")
                st.text(f"性别: {c.gender}")
            with col2:
                st.text(f"定位: {role}")
                st.text(f"首次出现: {c.first_appearance}")
            if c.description:
                st.text(f"描述: {c.description}")

    st.divider()
    st.subheader("关系网络")
    if not graph.relations:
        st.info("暂无关系数据")
    else:
        for r in graph.relations:
            rtype = r.relation_type.value if hasattr(r.relation_type, "value") else r.relation_type
            st.text(f"- {r.from_char} --[{rtype}]--> {r.to_char}: {r.description}")


def render_events_tab(graph: StoryGraph):
    """渲染事件标签页."""
    if not graph.events:
        st.info("暂无事件数据")
        return

    for i, e in enumerate(graph.events, 1):
        etype = e.event_type.value if hasattr(e.event_type, "value") else e.event_type
        with st.expander(f"**{i}. [{etype}] {e.title}**", expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                st.text(f"地点: {e.location}")
                st.text(f"时间: {e.time_marker}")
            with col2:
                st.text(f"参与者: {', '.join(e.participants)}")
            if e.description:
                st.text(f"描述: {e.description}")
            if e.cause:
                st.text(f"原因: {e.cause}")
            if e.consequence:
                st.text(f"后果: {e.consequence}")


def render_scenes_tab(graph: StoryGraph):
    """渲染场景标签页."""
    if not graph.scenes:
        st.info("暂无场景数据")
        return

    for s in graph.scenes:
        with st.expander(f"**{s.title}** — 第{s.act}幕", expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                st.text(f"地点: {s.location}")
                st.text(f"时间: {s.time}")
            with col2:
                st.text(f"角色: {', '.join(s.characters_present)}")
                st.text(f"事件数: {len(s.event_ids)}")
            if s.summary:
                st.text(f"概要: {s.summary}")

            if s.id in graph.scripts:
                st.divider()
                st.subheader("剧本内容")
                script = graph.scripts[s.id]
                for item in script.content:
                    if item.type == "action":
                        st.text(f"　{item.text}")
                    else:
                        st.text(f"**{item.character}**: {item.text}")


def render_warnings_tab(graph: StoryGraph):
    """渲染警告标签页."""
    if not graph.warnings:
        st.success("✅ 未发现一致性问题")
        return

    errors = [w for w in graph.warnings if w.severity.value == "error"]
    warnings = [w for w in graph.warnings if w.severity.value == "warning"]
    infos = [w for w in graph.warnings if w.severity.value == "info"]

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("错误", len(errors), delta_color="inverse")
    with col2:
        st.metric("警告", len(warnings), delta_color="off")
    with col3:
        st.metric("提示", len(infos), delta_color="off")

    st.divider()

    if errors:
        st.error("错误")
        for w in errors:
            with st.expander(f"**{w.code.value}**: {w.message}", expanded=True):
                if w.scene_ids:
                    st.text(f"涉及场景: {', '.join(w.scene_ids)}")
                if w.characters_involved:
                    st.text(f"涉及角色: {', '.join(w.characters_involved)}")

    if warnings:
        st.warning("警告")
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


def render_governance_tab(result):
    """渲染知识治理标签页 — 展示治理报告，支持用户修正."""
    st.subheader("🛡️ 知识治理报告")

    if result is None or result.governance_report is None:
        st.info("请先运行工作流以获取治理报告")
        return

    report = result.governance_report

    # ── 概览指标 ───────────────────────────────────────────
    val_passed = "✅ PASSED" if report.validation.passed else "❌ FAILED"
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("验证状态", val_passed)
    with col2:
        st.metric("冲突数", len(report.conflicts))
    with col3:
        st.metric("自动修正", len(report.auto_corrections))
    with col4:
        st.metric("审计记录", len(report.audit_trail.entries))

    st.divider()

    # ── 验证问题 ───────────────────────────────────────────
    st.subheader("📋 验证问题")
    if not report.validation.issues:
        st.success("✅ 无验证问题")
    else:
        for issue in report.validation.issues:
            sev_icon = "🔴" if issue.severity == "error" else "🟡" if issue.severity == "warning" else "ℹ️"
            st.text(f"{sev_icon} [{issue.severity.upper()}] {issue.code}: {issue.message}")

    st.divider()

    # ── 冲突列表 ───────────────────────────────────────────
    st.subheader("⚔️ 冲突列表")
    if not report.conflicts:
        st.success("✅ 未检测到冲突")
    else:
        for i, conflict in enumerate(report.conflicts, 1):
            with st.expander(f"**冲突 {i}**: {conflict.conflict_type}", expanded=False):
                st.text(f"类型: {conflict.conflict_type}")
                st.text(f"Entity A: {conflict.entity_a}")
                st.text(f"Entity B: {conflict.entity_b}")
                st.text(f"仲裁策略: {conflict.resolution or '未仲裁'}")
                if conflict.resolved_value:
                    st.text(f"仲裁结果: {conflict.resolved_value}")

    st.divider()

    # ── 自动修正记录 ───────────────────────────────────────
    st.subheader("🔧 自动修正")
    if not report.auto_corrections:
        st.info("无自动修正记录")
    else:
        for corr in report.auto_corrections:
            st.text(f"• {corr.get('type', 'N/A')}: {corr}")

    st.divider()

    # ── 快速修正 ───────────────────────────────────────────
    st.subheader("✏️ 快速修正")
    with st.expander("添加角色修正", expanded=False):
        target_name = st.selectbox(
            "角色",
            [""] + [c.name for c in (result.global_skl.characters if result.global_skl else [])],
        )
        field = st.selectbox("字段", ["name", "description", "role"])
        new_val = st.text_input("新值")
        reason = st.text_input("原因", placeholder="例如：用户确认")
        if st.button("应用", type="primary") and target_name and result:
            governor = KnowledgeGovernor(result.global_skl, graph=result.graph)
            old_val = ""
            for c in result.global_skl.characters:
                if c.name == target_name:
                    old_val = getattr(c, field, "")
                    break
            patch = Patch("character", target_name, field, old_val, new_val, reason or "用户修正")
            if governor.apply_patch(patch):
                st.success(f"已修正 '{target_name}.{field}' = '{new_val}'")
                st.rerun()
            else:
                st.error("修正失败")


def render_audit_tab(result):
    """渲染变更审计标签页 — 展示 AuditTrail 历史."""
    st.subheader("📝 变更审计记录")

    if result is None or result.governance_report is None:
        st.info("请先运行工作流以获取审计记录")
        return

    report = result.governance_report
    entries = report.audit_trail.entries

    if not entries:
        st.info("暂无审计记录")
        return

    col1, col2 = st.columns([1, 4])
    with col1:
        st.metric("记录总数", len(entries))
    with col2:
        st.metric("最近更新", entries[-1].timestamp if entries else "-")

    st.divider()

    # Action 统计
    from collections import Counter
    action_counts = Counter(e.action for e in entries)
    st.caption("操作类型分布: " + " | ".join(f"{k}: {v}" for k, v in action_counts.items()))

    st.divider()

    # 完整历史
    for i, entry in enumerate(reversed(entries)):
        action_icon = {
            "patch": "✏️", "auto_correct": "🔧", "resolve_conflict": "⚔️",
            "rollback": "↩️",
        }.get(entry.action, "📝")

        with st.expander(
            f"{action_icon} [{entry.action}] {entry.target_type} / {entry.target_id} — {entry.timestamp[:19]}",
            expanded=False,
        ):
            if entry.reason:
                st.text(f"原因: {entry.reason}")
            if entry.user:
                st.text(f"用户: {entry.user}")
            col1, col2 = st.columns(2)
            with col1:
                st.text(f"修改前: {entry.before}")
            with col2:
                st.text(f"修改后: {entry.after}")


def main():
    """主函数."""
    init_session_state()
    render_header()
    api_key, model, run_check = render_sidebar()
    novel_text, title, author = render_upload_section()

    result, workflow = render_workflow_run(novel_text, title, author, api_key, model, run_check)

    if result is not None:
        st.session_state["workflow_result"] = result
        st.session_state["graph"] = result.graph

    render_results(st.session_state.get("workflow_result"))


if __name__ == "__main__":
    main()
