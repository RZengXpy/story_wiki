"""StoryForge — AI Screenwriter Studio Streamlit UI."""

from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st
from datetime import datetime

from core.workflow import StoryForgeWorkflow
from core.story_graph import StoryGraph, CharacterRole, EventType, WarningSeverity


def init_session_state():
    """初始化会话状态."""
    defaults = {
        "graph": None,
        "workflow_result": None,
        "current_step": 0,
        "yaml_output": "",
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

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📋 元信息",
        "👥 角色",
        "🎭 事件",
        "🎬 场景",
        "⚠️ 警告",
    ])

    with tab1:
        render_metadata_tab(graph)

    with tab2:
        render_characters_tab(graph)

    with tab3:
        render_events_tab(graph)

    with tab4:
        render_scenes_tab(graph)

    with tab5:
        render_warnings_tab(graph)


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


def render_characters_tab(graph: StoryGraph):
    """渲染角色标签页."""
    if not graph.characters:
        st.info("暂无角色数据")
        return

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
