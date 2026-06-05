SYSTEM_PROMPT = """You are a professional screenplay writer with deep knowledge of dramatic structure,
character development, and visual storytelling. You convert novel excerpts into properly formatted
screenplay scripts with vivid scene descriptions and authentic dialogue.
"""

CHARACTER_EXTRACTION_PROMPT = """Extract all characters from the following story excerpt.

For each character, provide:
- name: their full name
- description: who they are in 1-2 sentences
- traits: 3-5 defining personality traits
- role: protagonist, antagonist, or supporting

Return a JSON object with a "characters" array."""

SCENE_PARSING_PROMPT = """Parse the following story excerpt into distinct scenes.

For each scene, provide:
- title: short descriptive title
- location: where the scene takes place
- time_of_day: day, night, dawn, dusk, or unspecified
- description: 2-3 sentence visual description of what we see
- characters: list of character names in this scene
- notes: any important dramatic or visual notes

Return a JSON object with a "scenes" array."""

SCRIPT_WRITING_PROMPT = """Convert the following story excerpt into a properly formatted screenplay.

Requirements:
- Use standard screenplay format (capitalize character names, parentheticals for action in dialogue)
- Write vivid, visual scene descriptions (what the camera sees, not internal thoughts)
- Capture each character's unique voice in their dialogue
- Use proper screenplay dialogue formatting
- Keep action lines concise and visual

Return a JSON object with the screenplay content."""

STORY_STRUCTURE_PROMPT = """Analyze the following story and identify its three-act structure.

For each act, provide:
- title: act name
- summary: 2-3 sentence description of what happens in this act
- key_scenes: list of 3-5 key scenes in the act

Return a JSON object with an "acts" array."""