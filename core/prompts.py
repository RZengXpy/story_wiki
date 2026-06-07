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

RELATION_EXTRACTION_PROMPT = """Extract all character relationships from the following story excerpt.

For each relationship, provide:
- from_char: the name of the first character
- to_char: the name of the second character
- relation_type: one of family, friend, enemy, romantic, professional, stranger
- description: 1-2 sentences describing how this relationship manifests in the story

Return a JSON object with a "relations" array.

Only extract relationships that are explicitly described or clearly implied by the text.
Do not invent relationships that are not supported by the text."""

OUTLINE_GENERATION_PROMPT = """Analyze the following story and generate a structured story outline.

Identify:
- genre: the story's genre
- theme: the central theme or message
- main_conflict: the primary conflict driving the story
- arc_summary: 3-5 sentence summary of the protagonist's character arc
- act_summaries: for each act (1-3), provide a 1-2 sentence summary of what happens
- key_plot_points: the 3-5 most important plot points in order

Return a JSON object with an "outline" object."""

SCENE_SCREENPLAY_PROMPT = """Generate a screenplay for a single scene, guided by the Screenplay Bible.

Requirements:
- Use standard screenplay format (capitalize character names, parentheticals for action in dialogue)
- Write vivid, visual action lines (what the camera sees, not internal thoughts)
- Capture each character's unique voice in their dialogue
- Keep action lines concise (1-3 lines each)
- Dialogue should reflect character traits and relationships
- Output a JSON object with a "script" array; each entry has:
  - type: "action" or "dialogue"
  - text: the action description or dialogue line
  - character: (for dialogue only) the speaker's name

Follow the Screenplay Bible's:
- Genre and tone (avoid tone breaks)
- Visual style guidelines
- Character portraits and speech patterns
- Dialogue style (subtext, formality level, etc.)
- Pacing notes (slow tension vs action)

Context to consider:
- Scene location and time of day
- Characters present and their backgrounds
- Related events that set up this scene
- Character relationships relevant to this scene
- Act structure and story progression

Return a JSON object with a "script" array."""
