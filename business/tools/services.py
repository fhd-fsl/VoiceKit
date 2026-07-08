"""
Service-related tools for Aventro Motors.
"""
import logging

logger = logging.getLogger(__name__)

async def check_service_status(phone_number: str) -> str:
    """Mock database lookup for vehicle service status."""
    logger.info("Checking service status for phone: %s", phone_number)
    
    # Strip non-digits for simple mocking
    digits = "".join(filter(str.isdigit, phone_number))
    
    if digits.endswith("1234"):
        return "Your Aventro Edge is currently in the paint bay and should be ready for pickup tomorrow at 10:00 AM."
    elif digits.endswith("9999"):
        return "Your Aventro Summit is waiting on a backordered transmission part. We expect it to arrive this Friday."
    elif digits == "":
        return "I couldn't understand the phone number."
    else:
        return "I don't see any active service records associated with that phone number."

async def get_service_estimate(service_type: str, vehicle_model: str) -> str:
    """Provide a rough estimate for automotive services."""
    logger.info("Generating estimate for %s on %s", service_type, vehicle_model)
    
    service_type_lower = service_type.lower()
    
    # Base rates
    if "oil" in service_type_lower:
        base_rate = 85.00
    elif "brake" in service_type_lower:
        base_rate = 350.00
    elif "transmission" in service_type_lower:
        base_rate = 250.00
    else:
        return f"I can't provide an automated estimate for a '{service_type}'. Our standard diagnostic fee is $150."

    # Luxury/SUV multiplier
    multiplier = 1.0
    if "summit" in vehicle_model.lower():
        multiplier = 1.5  # SUVs cost more
    elif "vortex" in vehicle_model.lower():
        multiplier = 2.0  # Sports cars cost more

    estimated_cost = base_rate * multiplier
    return f"The estimated cost for a {service_type} on an {vehicle_model} is roughly ${estimated_cost:,.2f} before taxes."
