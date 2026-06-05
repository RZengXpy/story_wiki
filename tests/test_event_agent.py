"""Unit tests for Event Agent."""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from agent.event_agent import EventAgent, Event
from core.llm_client import LLMClient


def test_event_dataclass():
    e = Event(
        title="图书馆相遇",
        event_type="revelation",
        description="老人询问北辰号日志",
        participants=["林川", "老人"],
        location="雾港镇图书馆",
        time_marker="下午四点",
        cause="老人寻找北辰号",
        consequence="日志已被人拿走",
        source={"chapter_id": "ch_001", "chapter_title": "失踪的航海日志"},
    )
    assert e.title == "图书馆相遇"
    assert e.event_type == "revelation"
    assert "林川" in e.participants
    assert e.source["chapter_id"] == "ch_001"
    print("  PASS: event_dataclass")


def test_event_agent_extract_events():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("  SKIP: OPENAI_API_KEY not set")
        return

    chapter_text = """秋雨已经连续下了三天。

下午四点，一位陌生老人推开图书馆大门。

“不要寻找灯塔下面的秘密。”纸条上写着。

老人说完便匆匆离开。当天晚上，林川在整理档案时发现纸条背面还有一行几乎看不见的小字。"""

    llm = LLMClient(model="deepseek-v4-flash", api_key=api_key)
    agent = EventAgent(llm)
    events = agent.extract_events(chapter_text, "ch_001", "失踪的航海日志")

    assert len(events) > 0, "No events extracted"
    assert events[0].source["chapter_id"] == "ch_001"
    assert events[0].source["chapter_title"] == "失踪的航海日志"

    for e in events:
        print(f"    - {e.title} ({e.event_type}) | {e.location} | {e.participants}")

    print(f"  PASS: event_agent_extract ({len(events)} events)")


def test_event_types():
    valid_types = ["conflict", "revelation", "transition", "turning_point", "resolution"]
    for t in valid_types:
        e = Event(title="test", event_type=t)
        assert e.event_type == t
    print("  PASS: event_types")


if __name__ == "__main__":
    print("=" * 60)
    print("Event Agent Tests")
    print("=" * 60)
    test_event_dataclass()
    test_event_agent_extract_events()
    test_event_types()
    print()
    print("ALL EVENT AGENT TESTS PASSED")
