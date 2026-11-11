from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

import httpx


EXCHANGE_RATE_URL = "https://open.er-api.com/v6/latest/INR"


class ExchangeRateError(Exception):
    """Raised when a reliable exchange rate cannot be obtained."""


@dataclass(frozen=True)
class ExchangeRate:
    source_currency: str
    target_currency: str
    rate: Decimal
    provider: str
    updated_at: str


async def get_inr_to_usd_rate() -> ExchangeRate:
    """Fetch the latest published USD rate for one INR."""

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(EXCHANGE_RATE_URL)
            response.raise_for_status()
            data = response.json()

        if data.get("result") != "success":
            raise ExchangeRateError("Exchange-rate provider did not return success.")

        usd_rate = data.get("rates", {}).get("USD")
        updated_at = data.get("time_last_update_utc")

        if not usd_rate or not updated_at:
            raise ExchangeRateError("Exchange-rate response is missing required data.")

        rate = Decimal(str(usd_rate))

        if not rate.is_finite() or rate <= 0:
            raise ExchangeRateError("Exchange-rate provider returned an invalid rate.")

        return ExchangeRate(
            source_currency="INR",
            target_currency="USD",
            rate=rate,
            provider="open.er-api.com",
            updated_at=updated_at,
        )

    except ExchangeRateError:
        raise
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise ExchangeRateError(
            "Unable to retrieve the latest exchange rate. Checkout is unavailable."
        ) from exc


def convert_inr_to_usd(
    amount_inr: Decimal,
    exchange_rate: Decimal,
) -> Decimal:
    """Convert INR to USD, rounded to two decimal places."""

    if amount_inr < 0 or exchange_rate <= 0:
        raise ValueError("Amount and exchange rate must be valid.")

    return (amount_inr * exchange_rate).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
