import logging

import httpx

from app.config import settings
from app.models import Customer
from app.services.meta_tokens import MetaTokenConfigurationError, channel_access_token

logger = logging.getLogger(__name__)

_GRAPH_API_BASE_URL = "https://graph.facebook.com/v22.0"


def populate_messenger_display_name(customer: Customer) -> None:
    """Populate a Messenger customer's name without interrupting webhook ingestion.

    Meta's webhook contains a Page-scoped ID, not the customer's profile name.
    The User Profile API supplies the name when a Page access token is configured.
    """
    if customer.display_name and customer.profile_image_url:
        return
    try:
        access_token = channel_access_token(customer.channel) or settings.meta_page_access_token
    except MetaTokenConfigurationError:
        logger.warning("Unable to decrypt Messenger Page access token")
        return
    if not access_token:
        return

    try:
        response = httpx.get(
            f"{_GRAPH_API_BASE_URL}/{customer.external_user_id}",
            params={
                "fields": "first_name,last_name,profile_pic",
                "access_token": access_token,
            },
            timeout=5.0,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        # Receiving the order message matters more than resolving an optional
        # profile field, so a Meta profile lookup failure must not reject it.
        logger.warning("Unable to retrieve the Messenger sender profile")
        return

    first_name = str(payload.get("first_name") or "").strip()
    last_name = str(payload.get("last_name") or "").strip()
    display_name = " ".join(part for part in (first_name, last_name) if part)
    if display_name:
        customer.display_name = display_name[:255]
    profile_image_url = str(payload.get("profile_pic") or "").strip()
    if profile_image_url:
        customer.profile_image_url = profile_image_url[:2000]
