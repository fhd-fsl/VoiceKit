"""
Tool registry for the VoiceKit agent.

Exports TOOLS_SCHEMA and TOOL_FUNCTIONS which are passed directly
to the LLM provider for function calling.
"""

from backend.tools.orders import check_order_status

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "check_order_status",
            "description": "Checks the shipping status of a customer order. IMPORTANT: NEVER call this tool with a placeholder or fake order_id. If the user hasn't explicitly told you their order ID, you MUST ask them for it before calling this tool.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "The customer's EXACT order number (e.g. '123' or '999'). Do not guess this value."
                    }
                },
                "required": ["order_id"]
            }
        }
    }
]

TOOL_FUNCTIONS = {
    "check_order_status": check_order_status
}
