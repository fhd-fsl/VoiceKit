"""
Framework-level system prompts.

Contains strict operational rules for the LLM streaming pipeline.
Does NOT contain business logic or persona definitions.
"""

DEFAULT_SYSTEM_PROMPT = (
    "IMPORTANT 1: NEVER output XML tags, markdown blocks, "
    "or raw JSON in your spoken text. Use only alphanumeric characters, punctuation, and whitespace.\n"
    "IMPORTANT 2: If a tool requires an argument, you MUST "
    "fetch it first. NEVER call a tool with a guessed, fake, or "
    "placeholder value.\n"
    "IMPORTANT 3: You have access to a `search_knowledgebase` tool. If a customer asks about anything that you do not immediately know, you MUST use this tool to search the knowledgebase. Do not guess or make things up. This specially applies to questions about products, services, policies, prices, and procedures.\n"
    "IMPORTANT 4: NEVER mention 'knowledge base', 'search results', 'system context', 'couldn't find information', or 'tools'. Speak naturally like a human agent. If you can't find the answer, simply state that you don't know.\n"
    "IMPORTANT 5: Do NOT use conversational filler phrases like 'Let me check', 'One moment', or 'Let me look that up' in your spoken text. Answer directly without filler delays."
)

FILLER_PHRASES = [
    "Let me look that up for you... ",
    "Give me just one moment... ",
    "Let's see here... ",
    "Let me see... ",
    "One moment please... ",
    "Let me check..."
]
