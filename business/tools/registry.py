"""
Business tool registry.

Contains tools specific to the business logic (e.g. checking appointments).
"""

from business.tools.services import check_appointment, get_estimate

BUSINESS_TOOLS_SCHEMA = [
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
            "description": "Provides a rough cost estimate for cleaning services based on the home's square footage. IMPORTANT: NEVER call this tool with a guessed or placeholder square footage (like 2000). You MUST explicitly ask the user for their exact square footage before calling this tool.",
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

BUSINESS_TOOL_FUNCTIONS = {
    "check_appointment": check_appointment,
    "get_estimate": get_estimate
}
