"""
Framework tool registry for VoiceKit.

Contains tools required by the underlying infrastructure, such as RAG.
"""

FRAMEWORK_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledgebase",
            "description": "Searches the business knowledge base for information about services, policies, and pricing. Call this tool whenever you are asked a specific question about the business that you do not already know.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to look up in the knowledge base."
                    }
                },
                "required": ["query"]
            }
        }
    }
]
