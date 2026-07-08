"""
Business tool registry for Aventro Motors.

Contains tools specific to the business logic (e.g. checking vehicle service status).
"""

from business.tools.services import check_service_status, get_service_estimate

BUSINESS_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "check_service_status",
            "description": "Checks the repair or maintenance status of a customer's vehicle in the shop. IMPORTANT: NEVER call this tool with a placeholder or fake phone number. If the user hasn't explicitly told you their phone number, you MUST ask them for it before calling this tool.",
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
            "name": "get_service_estimate",
            "description": "Provides a rough cost estimate for common automotive services. IMPORTANT: NEVER call this tool with a guessed or placeholder vehicle model or service type. You MUST explicitly ask the user for their exact vehicle model and the service they need before calling this tool.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_type": {
                        "type": "string",
                        "description": "The type of service requested: 'Oil Change', 'Brake Pad Replacement', or 'Transmission Flush'."
                    },
                    "vehicle_model": {
                        "type": "string",
                        "description": "The model of the Aventro vehicle (e.g., 'Aventro Edge', 'Aventro Summit')."
                    }
                },
                "required": ["service_type", "vehicle_model"]
            }
        }
    }
]

BUSINESS_TOOL_FUNCTIONS = {
    "check_service_status": check_service_status,
    "get_service_estimate": get_service_estimate
}
