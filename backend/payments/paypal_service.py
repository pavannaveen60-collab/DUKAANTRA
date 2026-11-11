from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import httpx

from config import settings


class PayPalAPIError(Exception):
    """Raised when PayPal returns an unsuccessful API response."""


def _get_credentials() -> tuple[str, str]:
    client_id = settings.PAYPAL_CLIENT_ID
    client_secret = settings.PAYPAL_CLIENT_SECRET

    if not client_id or not client_secret:
        raise PayPalAPIError("PayPal credentials are not configured.")

    return client_id, client_secret


async def _get_access_token(client: httpx.AsyncClient) -> str:
    client_id, client_secret = _get_credentials()

    response = await client.post(
        "/v1/oauth2/token",
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials"},
        headers={"Accept": "application/json"},
    )

    if not response.is_success:
        raise PayPalAPIError(
            f"PayPal authentication failed (HTTP {response.status_code})."
        )

    data = response.json()
    token = data.get("access_token")

    if not token:
        raise PayPalAPIError("PayPal did not return an access token.")

    return token


def _format_usd(amount: Decimal) -> str:
    if not amount.is_finite() or amount <= 0:
        raise ValueError("PayPal amount must be greater than zero.")

    return str(
        amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )


async def create_paypal_order(
    amount_usd: Decimal,
    reference_id: str,
    custom_id: str,
    request_id: str,
) -> dict[str, Any]:
    """Create a PayPal order in the configured environment."""

    async with httpx.AsyncClient(
        base_url=settings.PAYPAL_BASE_URL.rstrip("/"),
        timeout=20.0,
    ) as client:
        token = await _get_access_token(client)

        response = await client.post(
            "/v2/checkout/orders",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "PayPal-Request-Id": request_id,
            },
            json={
                "intent": "CAPTURE",
                "purchase_units": [
                    {
                        "reference_id": reference_id,
                        "custom_id": custom_id,
                        "amount": {
                            "currency_code": "USD",
                            "value": _format_usd(amount_usd),
                        },
                    }
                ],
                "application_context": {
                    "brand_name": "DUKAANTRA",
                    "user_action": "PAY_NOW",
                    "return_url": settings.PAYPAL_RETURN_URL,
                    "cancel_url": settings.PAYPAL_CANCEL_URL,
                },
            },
        )

        if not response.is_success:
            raise PayPalAPIError(
                f"PayPal order creation failed (HTTP {response.status_code}): "
                f"{response.text[:1000]}"
            )

        data = response.json()

        if not data.get("id"):
            raise PayPalAPIError("PayPal returned an order without an ID.")

        approval_url = next(
            (
                link["href"]
                for link in data.get("links", [])
                if link.get("rel") in {"approve", "payer-action"}
            ),
            None,
        )

        if not approval_url:
            raise PayPalAPIError(
                "PayPal did not return an approval URL."
            )

        return {
            "id": data["id"],
            "status": data.get("status"),
            "approval_url": approval_url,
            "response": data,
        }


async def capture_paypal_order(
    paypal_order_id: str,
    request_id: str,
) -> dict[str, Any]:
    """Capture an approved PayPal order."""

    async with httpx.AsyncClient(
        base_url=settings.PAYPAL_BASE_URL.rstrip("/"),
        timeout=20.0,
    ) as client:
        token = await _get_access_token(client)

        response = await client.post(
            f"/v2/checkout/orders/{paypal_order_id}/capture",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "PayPal-Request-Id": request_id,
            },
            json={},
        )

        if not response.is_success:
            raise PayPalAPIError(
                f"PayPal capture failed (HTTP {response.status_code}): "
                f"{response.text[:1000]}"
            )

        return response.json()
