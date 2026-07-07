"""
Service-related tools for Sparkle & Shine Home Services.
"""
import logging

logger = logging.getLogger(__name__)

async def check_appointment(phone_number: str) -> str:
    """Mock database lookup for an appointment."""
    logger.info("Checking appointment for phone: %s", phone_number)
    
    # Strip non-digits for simple mocking
    digits = "".join(filter(str.isdigit, phone_number))
    
    if digits.endswith("1234"):
        return "You have a Deep Cleaning scheduled for tomorrow at 10:00 AM."
    elif digits.endswith("9999"):
        return "You have a Lawn Care service scheduled for this Friday at 2:00 PM."
    elif digits == "":
        return "I couldn't understand the phone number."
    else:
        return "I don't see any upcoming appointments associated with that phone number."

async def get_estimate(service_type: str, square_footage: int) -> str:
    """Provide a rough estimate based on square footage."""
    logger.info("Generating estimate for %s sqft of %s", square_footage, service_type)
    
    service_type_lower = service_type.lower()
    if "standard" in service_type_lower:
        base_rate = 0.08
    elif "deep" in service_type_lower:
        base_rate = 0.15
    elif "move" in service_type_lower:
        base_rate = 0.20
    else:
        return f"I can't provide an automated estimate for '{service_type}'. Handyman and Landscaping are billed at $75 per hour."

    estimated_cost = square_footage * base_rate
    return f"Based on {square_footage} square feet, the estimated cost for a {service_type} clean is roughly ${estimated_cost:,.2f}."
