"""
Tool registry for the VoiceKit agent.

Exports TOOLS_SCHEMA and TOOL_FUNCTIONS which are passed directly
to the LLM provider for function calling.
"""

from backend.tools.services import check_appointment, get_estimate

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "check_appointment",
            "description": "Checks the date and time of a customer's upcoming service appointment. IMPORTANT: NEVER call this tool with a placeholder or fake phone number. If the user hasn't explicitly told you their phone number, you MUST ask them for it before calling this tool.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone_number": {
                        "type": "string",
                        "description": "The customer's EXACT phone number (e.g. '555-1234'). Do not guess this value."
                    }
                },
                "required": ["phone_number"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_estimate",
            "description": "Provides a rough cost estimate for cleaning services based on the home's square footage. Ask the user for the square footage of their home before calling this tool.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_type": {
                        "type": "string",
                        "description": "The type of cleaning service requested: 'Standard', 'Deep', or 'Move-In/Move-Out'."
                    },
                    "square_footage": {
                        "type": "integer",
                        "description": "The total square footage of the home."
                    }
                },
                "required": ["service_type", "square_footage"]
            }
        }
    }
]

TOOL_FUNCTIONS = {
    "check_appointment": check_appointment,
    "get_estimate": get_estimate
}
