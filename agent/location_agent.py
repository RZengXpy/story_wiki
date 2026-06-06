"""LocationAgent — aggregates and analyzes story locations.

Implements "Local → Global" principle from think.md.
Location aggregation with indoor/outdoor classification.
"""
from dataclasses import dataclass, field
from typing import Optional
from core.llm_client import LLMClient
from core.prompts import SYSTEM_PROMPT


LOCATION_ANALYSIS_PROMPT = """Analyze the following story locations and provide insights about each.

For each location, identify:
- name: location name
- narrative_significance: why this location matters to the story
- emotional_atmosphere: the mood or feeling associated with this location
- how it contributes to the story's setting and themes

Also provide:
- key_setting_shifts: locations that mark major shifts in the story
- recurring_locations: locations that appear multiple times and gain significance through repetition

Return a JSON object with:
- locations: list of {name, narrative_significance, emotional_atmosphere}
- key_setting_shifts: list of location names marking major shifts
- recurring_locations: list of recurring location names"""


@dataclass
class LocationInfo:
    """Aggregated location information."""
    name: str
    location_type: str  # indoor | outdoor | mixed
    frequency: int = 1
    scenes: list[str] = field(default_factory=list)
    narrative_significance: str = ""
    emotional_atmosphere: str = ""


@dataclass
class LocationAnalysisResult:
    """Complete location analysis result."""
    locations: list[LocationInfo]
    key_setting_shifts: list[str] = field(default_factory=list)
    recurring_locations: list[str] = field(default_factory=list)


_INDOOR_KEYWORDS = [
    "室", "房", "厅", "内", "间", "楼", "家", "屋", "馆", "吧", "店",
    "舱", "车", "办公室", "会议室", "教室", "医院", "图书馆", "公寓",
    "地下室", "走廊", "厨房", "卧室", "餐厅", "诊所", "办公室",
]
_OUTDOOR_KEYWORDS = [
    "外", "街", "路", "城", "港", "山", "海", "河", "湖", "岛",
    "镇", "村", "公园", "森林", "沙漠", "海岸", "码头", "街道",
    "海滩", "码头", "灯塔", "船上", "船", "礁石", "岸边",
]


class LocationAgent:
    """Aggregates and analyzes story locations."""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client

    def build_locations(self, scenes: list) -> list[LocationInfo]:
        """Aggregate scene locations into LocationInfo entries (rule-based)."""
        location_map: dict[str, LocationInfo] = {}
        for s in scenes:
            loc = getattr(s, "location", "") or ""
            if not loc:
                loc = "未知地点"
            if loc not in location_map:
                location_map[loc] = LocationInfo(
                    name=loc,
                    location_type=self._classify_type(loc),
                    frequency=0,
                    scenes=[],
                )
            location_map[loc].frequency += 1
            scene_title = getattr(s, "title", "")
            if scene_title:
                location_map[loc].scenes.append(scene_title)

        return sorted(location_map.values(), key=lambda x: x.frequency, reverse=True)

    def _classify_type(self, location: str) -> str:
        """Classify location as indoor, outdoor, or mixed using keyword matching."""
        if any(kw in location for kw in _INDOOR_KEYWORDS):
            return "indoor"
        if any(kw in location for kw in _OUTDOOR_KEYWORDS):
            return "outdoor"
        return "mixed"

    def analyze_locations(
        self,
        scenes: list,
        events: Optional[list] = None,
    ) -> LocationAnalysisResult:
        """Full location analysis with LLM-powered narrative insights.

        Falls back to rule-based analysis if no LLM client is available.
        """
        locations = self.build_locations(scenes)

        if self.llm is None:
            recurring = [loc.name for loc in locations if loc.frequency > 1]
            return LocationAnalysisResult(
                locations=locations,
                key_setting_shifts=[],
                recurring_locations=recurring,
            )

        # Build location descriptions for LLM context
        scene_by_loc: dict[str, list[str]] = {}
        for s in scenes:
            loc = getattr(s, "location", "") or "未知地点"
            scene_by_loc.setdefault(loc, []).append(getattr(s, "title", ""))

        location_text_parts = []
        for loc, scene_titles in scene_by_loc.items():
            loc_type = next((l.location_type for l in locations if l.name == loc), "mixed")
            location_text_parts.append(
                f"- {loc} ({loc_type}): {len(scene_titles)} scenes — {', '.join(scene_titles[:3])}"
            )

        response = self.llm.generate_json(
            SYSTEM_PROMPT + "\n\n" + LOCATION_ANALYSIS_PROMPT,
            "\n".join(location_text_parts),
        )

        # Annotate location entries with LLM insights
        for loc_entry in locations:
            for ll_loc in response.get("locations", []):
                if ll_loc.get("name") == loc_entry.name:
                    loc_entry.narrative_significance = ll_loc.get("narrative_significance", "")
                    loc_entry.emotional_atmosphere = ll_loc.get("emotional_atmosphere", "")
                    break

        return LocationAnalysisResult(
            locations=locations,
            key_setting_shifts=response.get("key_setting_shifts", []),
            recurring_locations=response.get("recurring_locations", []),
        )
