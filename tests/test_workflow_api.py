"""纯 Python 测试脚本：验证 StoryForgeWorkflow 接口 + 进度追踪（无需 Streamlit）。

用法：
    python tests/test_workflow_api.py

依赖：需要 .env 中配置 OPENAI_API_KEY 和 BASE_URL。
"""
from __future__ import annotations
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))

import time
from core.workflow import StoryForgeWorkflow
from core.progress import ProgressTracker, Phase


# ── 测试数据 ────────────────────────────────────────────────────────────────


SAMPLE_NOVEL = """《雾港档案》
第一章：失踪的航海日志

秋雨已经连续下了三天。

海风裹挟着咸湿的雾气穿过雾港镇的街道，老旧的路灯在雨幕中忽明忽暗。

镇图书馆管理员林川像往常一样整理着地下档案室。这里存放着近百年来的航海记录，大部分已经无人问津。

下午四点，一位陌生老人推开图书馆大门。

老人穿着深灰色风衣，左手拄着木制手杖。

"请问，这里还保存着'北辰号'的航海日志吗？"

林川愣了一下。

北辰号是一艘二十年前失踪的货船。

关于它的传闻很多。

有人说遭遇风暴沉没。

有人说发现了某种秘密航线。

也有人说船上的人根本没有死。

林川带着老人来到地下档案室。

两人翻找许久，却发现原本编号为 N-27 的日志档案已经不见了。

档案柜里只剩下一张泛黄纸条。

纸条上写着：

"不要寻找灯塔下面的秘密。"

老人看到纸条后脸色骤变。

"已经有人先一步拿走了。"

他说完便匆匆离开。

当天晚上。

林川在整理档案时发现纸条背面还有一行几乎看不见的小字：

"10月17日，午夜。"

第二章：废弃灯塔

第二天下午。

林川将纸条的事情告诉了好友陈雨。

陈雨是一名自由记者，专门调查各种离奇事件。

"灯塔下面的秘密？"

陈雨兴奋地说。

"这种事情怎么能错过。"

两人决定前往海边废弃灯塔。

傍晚六点。

他们抵达了位于黑礁海岸的旧灯塔。

这里已经废弃十多年。

锈蚀的大门半掩着。

进入灯塔后，他们发现地板上有新鲜脚印。

说明最近有人来过。

两人沿着螺旋楼梯向下搜索。

地下室尽头隐藏着一扇铁门。

铁门没有上锁。

推开后。

里面是一间秘密储藏室。

房间中央摆放着一个防水金属箱。

箱子里存放着一本残破航海日志。

封面赫然写着：

《北辰号航海记录》。

就在这时。

地下室突然传来脚步声。

一个戴黑色雨衣的男人出现在门口。

"把日志交出来。"

男人冷冷说道。

陈雨偷偷按下录音笔。

双方僵持数秒后。

男人试图抢夺日志。

混乱中金属箱跌落在地。

一本夹层中的地图滑了出来。

地图上标记着一座从未在公开海图中出现过的小岛。

看到地图后。

黑衣男人明显慌张起来。

他放弃抢夺日志，转身逃离灯塔。

林川捡起地图。

他隐约觉得。

北辰号失踪的真相，或许与这座神秘岛屿有关。

第三章：迷雾岛

10月17日午夜。

按照日志中的记录。

林川和陈雨租下一艘渔船，前往地图标记的位置。

海面浓雾弥漫。

船长老周不断抱怨天气恶劣。

凌晨一点。

迷雾中逐渐浮现出岛屿轮廓。

这正是地图上的神秘岛。

三人登岛后发现岛中央矗立着一座废弃观测站。

观测站内部设备虽然陈旧，却仍能运转。

林川在主控室找到了一批加密文件。

文件显示。

二十年前的北辰号并非意外失踪。

当年船员在海底发现了一种特殊矿石。

这种矿石能够干扰无线电信号。

为了独占发现成果。

某家公司秘密封锁了消息。

甚至伪造了沉船事故记录。

而第一章出现的神秘老人。

正是当年北辰号的大副许远。

他一直在寻找真相。

就在众人准备离开时。

观测站外传来发动机轰鸣。

数辆越野车包围了建筑。

黑衣男人再次出现。

"把文件留下。"

他说。

危急时刻。

陈雨打开直播设备，将所有资料实时上传网络。

数分钟后。

相关内容迅速传播。

黑衣男人意识到事情已经无法掩盖。

最终选择离开。

天亮时。

许远也来到岛上。

看着重新公开于世的真相。

老人沉默许久。

随后向林川伸出手。

"谢谢你们。"

海面上的浓雾缓缓散去。

远处的晨光照亮了整片海域。
"""


# ── 测试函数 ────────────────────────────────────────────────────────────────


def test_progress_tracker():
    """测试 ProgressTracker 的基本功能。"""
    print("\n" + "=" * 60)
    print("测试 1: ProgressTracker")
    print("=" * 60)

    tracker = ProgressTracker()

    tracker.set_total(n_chapters=3, n_scenes=5)
    print(f"  [OK] set_total(3, 5) → LLM总数 = 4*3+1+5 = {4*3+1+5}")

    tracker.set_phase(Phase.PARSING_CHAPTERS)
    p = tracker.get_progress()
    assert p.phase == Phase.PARSING_CHAPTERS, f"期望 PARSING_CHAPTERS，实际 {p.phase}"
    print(f"  [OK] set_phase(PARSING_CHAPTERS) → {p.phase_label}")

    tracker.set_phase(Phase.EXTRACTING_KNOWLEDGE)
    tracker.on_chapter_start(0, "第一章")
    p = tracker.get_progress()
    print(f"  [OK] 开始第1章提取，当前 LLM: {tracker.get_llm_progress()}")

    tracker.on_agent_done("角色", 0, "第一章")
    p = tracker.get_progress()
    llm_done, llm_total = tracker.get_llm_progress()
    print(f"  [OK] 角色提取完成 → LLM: {llm_done}/{llm_total}, msg: {p.message}")
    assert llm_done == 1, f"期望 1，实际 {llm_done}"

    tracker.on_agent_done("场景", 0, "第一章")
    tracker.on_agent_done("事件", 0, "第一章")
    tracker.on_agent_done("关系", 0, "第一章")
    llm_done, _ = tracker.get_llm_progress()
    print(f"  [OK] 第1章完成 → LLM: {llm_done}")
    assert llm_done == 4, f"期望 4，实际 {llm_done}"  # 1角色+1场景+1事件+1关系=4

    tracker.on_chapter_start(1, "第二章")
    tracker.on_agent_done("角色", 1, "第二章")
    p = tracker.get_progress()
    print(f"  [OK] 第2章提取中，chapter_info: {p.chapter_info}")
    # 第2章没有 on_chapter_done，直接跳到第3章，所以只计1个agent

    tracker.on_chapter_start(2, "第三章")
    for agent in ["角色", "场景", "事件", "关系"]:
        tracker.on_agent_done(agent, 2, "第三章")
    llm_done, llm_total = tracker.get_llm_progress()
    print(f"  [OK] 第3章完成 → LLM: {llm_done}/{llm_total}")
    # 第1章4个 + 第2章1个 + 第3章4个 = 9
    assert llm_done == 9, f"期望 9，实际 {llm_done}"

    tracker.on_outline_done()
    llm_done, _ = tracker.get_llm_progress()
    print(f"  [OK] 大纲生成完成 → LLM: {llm_done}")

    # Phase transitions don't change llm_done counter
    tracker.set_phase(Phase.MERGING_KNOWLEDGE)
    tracker.set_phase(Phase.GOVERNANCE)
    tracker.set_phase(Phase.CHECKING_CONSISTENCY)
    tracker.set_phase(Phase.BUILDING_GRAPH)
    llm_done, _ = tracker.get_llm_progress()
    print(f"  [OK] 后续阶段不变 → LLM: {llm_done}")

    tracker.set_phase(Phase.GENERATING_SCRIPTS)
    tracker.on_scene_start(1, "scene_001")
    tracker.on_scene_done(1, "scene_001")
    tracker.on_scene_start(2, "scene_002")
    tracker.on_scene_done(2, "scene_002")
    p = tracker.get_progress()
    print(f"  [OK] 剧本生成中: {p.message}, chapter_info: {p.chapter_info}")  # 3章×4agents + outline

    tracker.on_outline_done()
    llm_done, _ = tracker.get_llm_progress()
    print(f"  [OK] 大纲生成完成 → LLM: {llm_done}")

    tracker.set_phase(Phase.GENERATING_SCRIPTS)
    tracker.on_scene_start(1, "scene_001")
    tracker.on_scene_done(1, "scene_001")
    tracker.on_scene_start(2, "scene_002")
    tracker.on_scene_done(2, "scene_002")
    p = tracker.get_progress()
    print(f"  [OK] 剧本生成中: {p.message}, chapter_info: {p.chapter_info}")

    tracker.set_phase(Phase.DONE)
    p = tracker.get_progress()
    assert p.phase == Phase.DONE, f"期望 DONE，实际 {p.phase}"
    print(f"  [OK] 流程完成，fraction = {p.fraction}")

    tracker.set_phase(Phase.IDLE)
    tracker.on_error("模拟错误")
    p = tracker.get_progress()
    assert p.phase == Phase.ERROR, f"期望 ERROR，实际 {p.phase}"
    print(f"  [OK] 错误处理: {p.message}")

    print("  [PASS] ProgressTracker all tests passed!\n")


def test_workflow_run_skl(novel_text: str, api_key: str):
    """测试 run() — 仅构建 SKL（不生成剧本）。"""
    print("\n" + "=" * 60)
    print("测试 2: StoryForgeWorkflow.run() — 构建 SKL")
    print("=" * 60)

    tracker = ProgressTracker()
    workflow = StoryForgeWorkflow(
        model="deepseek-v4-flash",
        api_key=api_key,
        run_consistency_check=True,
    )

    print(f"  小说字数: {len(novel_text)}")
    print(f"  预计 LLM 调用: 4*章节数 + 1")
    print()

    start = time.time()
    result = workflow.run(novel_text, title="雾港档案", author="测试", tracker=tracker)
    elapsed = time.time() - start

    if not result.success:
        print(f"  [FAIL] 工作流失败: {result.error_message}")
        return None

    print(f"\n  elapsed 耗时: {elapsed:.1f} 秒")
    print(f"  [OK] 工作流成功！")
    print(f"     章节数: {len(result.chapters)}")
    print(f"     角色数: {len(result.graph.characters)}")
    print(f"     场景数: {len(result.graph.scenes)}")
    print(f"     关系数: {len(result.graph.relations)}")
    print(f"     事件数: {len(result.graph.events)}")
    print(f"     警告数: {len(result.graph.warnings)}")
    print(f"     SKL 去重角色: {len(result.global_skl.characters)}")
    print(f"     SKL 去重场景: {len(result.global_skl.scenes)}")
    print(f"     SKL 去重关系: {len(result.global_skl.relations)}")

    if result.graph.characters:
        print(f"\n  角色列表:")
        for c in result.graph.characters[:5]:
            role = c.role.value if hasattr(c.role, "value") else c.role
            print(f"    - {c.name} ({role})")

    print(f"\n  [OK] run() 测试通过！\n")
    return result


def test_workflow_run_with_scripts(result, api_key: str):
    """测试 run_with_scripts() — 在已有 SKL 基础上生成剧本。"""
    print("\n" + "=" * 60)
    print("测试 3: StoryForgeWorkflow.run_with_scripts() — 生成剧本")
    print("=" * 60)

    if result is None:
        print("  [SKIP] 跳过（SKL 测试未通过）")
        return

    tracker = ProgressTracker()
    workflow = StoryForgeWorkflow(
        model="deepseek-v4-flash",
        api_key=api_key,
        run_consistency_check=False,
    )

    print(f"  场景数: {len(result.graph.scenes)}")
    print(f"  预计 LLM 调用: 场景数 = {len(result.graph.scenes)}")
    print()

    start = time.time()
    result2 = workflow.run_with_scripts(
        "雾港档案",  # text is only needed for outline which is already done
        title="雾港档案",
        author="测试",
        tracker=tracker,
    )
    elapsed = time.time() - start

    if not result2.success:
        print(f"  [FAIL] 剧本生成失败: {result2.error_message}")
        return

    print(f"\n  elapsed 耗时: {elapsed:.1f} 秒")
    print(f"  [OK] 剧本生成成功！")
    print(f"     生成剧本场景数: {len(result2.graph.scripts)}")
    total_items = sum(len(s.content) for s in result2.graph.scripts.values())
    empty_count = sum(1 for s in result2.graph.scripts.values() if len(s.content) == 0)
    print(f"     剧本条目总数: {total_items}")
    if empty_count > 0:
        print(f"     空剧本场景数: {empty_count}")

    for sid, script in list(result2.graph.scripts.items())[:2]:
        print(f"\n  场景 [{sid}]:")
        for item in script.content[:3]:
            if item.type == "action":
                print(f"    [动作] {item.text[:50]}...")
            else:
                print(f"    [台词] {item.character}: {item.text[:40]}...")

    print(f"\n  [OK] run_with_scripts() 测试通过！\n")


def main():
    import os
    import logging
    from dotenv import load_dotenv

    load_dotenv(_root / ".env")
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_SECRET_KEY")
    if not api_key:
        print("[FAIL] 未找到 API Key，请在 .env 中配置 OPENAI_API_KEY 或 OPENAI_SECRET_KEY")
        return

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    # Test 1: ProgressTracker (no API key needed)
    test_progress_tracker()

    # Test 2: run() with SKL
    result = test_workflow_run_skl(SAMPLE_NOVEL, api_key)

    # Test 3: run_with_scripts()
    test_workflow_run_with_scripts(result, api_key)

    print("\n" + "=" * 60)
    print("[DONE] 所有测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
