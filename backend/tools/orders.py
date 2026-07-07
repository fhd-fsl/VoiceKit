"""
Order-related tools for the VoiceKit agent.
"""
import logging

logger = logging.getLogger(__name__)


async def check_order_status(order_id: str) -> str:
    """Mock database lookup for an order."""
    logger.info("checking order status for: %s", order_id)
    if "123" in order_id:
        return f"Order {order_id} has been shipped and will arrive tomorrow."
    elif "999" in order_id:
        return f"Order {order_id} is currently backordered."
    else:
        return f"Order {order_id} is being processed and will ship in 2 days."
