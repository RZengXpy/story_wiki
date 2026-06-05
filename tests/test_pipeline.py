"""End-to-end integration test: Novel text.md -> Structured screenplay."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import yaml
from pathlib import Path

load_dotenv("g:/qiniu2/story_wiki/.env")

from core.llm_client import LLMClient
from pipeline.orchestrator import StoryPipeline


def load_novel(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def dataclass_to_dict(obj):
    if hasattr(obj, "__dataclass_fields__"):
        result = {}
        for name, field in obj.__dataclass_fields__.items():
            val = getattr(obj, name)
            if isinstance(val, list):
                result[name] = [dataclass_to_dict(v) for v in val]
            elif hasattr(val, "__dataclass_fields__"):
                result[name] = dataclass_to_dict(val)
            else:
                result[name] = val
        return result
    return obj


def save_yaml(data: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    print(f"  Saved: {path}")


def test_end_to_end():
    """MVP: Novel text.md -> Character + Scene + Screenplay output."""
    print("=" * 60)
    print("StoryForge MVP End-to-End Test")
    print("=" * 60)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set in .env")

    novel_path = Path("g:/qiniu2/story_wiki/text.md")
    results_dir = Path("g:/qiniu2/story_wiki/tests/results")

    novel_text = load_novel(novel_path)
    print(f"\nInput: {novel_path} ({len(novel_text)} chars)")

    llm = LLMClient(model="deepseek-v4-flash", api_key=api_key)
    pipeline = StoryPipeline(llm)

    print("\nStep 1: CharacterAgent.extract_characters...")
    characters = pipeline.char_agent.extract_characters(novel_text)
    print(f"  -> {len(characters)} characters found")
    assert len(characters) > 0, "No characters extracted"
    for c in characters:
        print(f"     - {c.name} ({c.role})")
    char_data = {"characters": [dataclass_to_dict(c) for c in characters]}
    save_yaml(char_data, results_dir / "characters.yaml")

    print("\nStep 2: SceneAgent.parse_scenes...")
    scenes = pipeline.scene_agent.parse_scenes(novel_text)
    print(f"  -> {len(scenes)} scenes found")
    assert len(scenes) > 0, "No scenes extracted"
    for s in scenes:
        print(f"     - {s.title}: {s.location} ({s.time_of_day})")
    scene_data = {"scenes": [dataclass_to_dict(s) for s in scenes]}
    save_yaml(scene_data, results_dir / "scenes.yaml")

    print("\nStep 3: ScriptAgent.write_screenplay...")
    screenplay = pipeline.script_agent.write_screenplay(novel_text, genre="thriller")
    print(f"  -> {len(screenplay)} chars generated")
    assert len(screenplay) > 0, "No screenplay generated"
    screenplay_data = {"screenplay": screenplay, "metadata": {"genre": "thriller", "chars": len(screenplay)}}
    save_yaml(screenplay_data, results_dir / "screenplay.yaml")

    print("\nStep 4: Full pipeline run...")
    result = pipeline.run(novel_text, genre="thriller")
    print(f"  -> characters={len(result['characters'])}, scenes={len(result['scenes'])}, screenplay={len(result['screenplay'])} chars")
    assert len(result["characters"]) > 0
    assert len(result["scenes"]) > 0
    assert len(result["screenplay"]) > 0

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED — MVP end-to-end pipeline verified")
    print("=" * 60)


if __name__ == "__main__":
    test_end_to_end()
