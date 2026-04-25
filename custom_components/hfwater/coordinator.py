"""DataUpdateCoordinator for 合肥水务 (Hefei Water)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import HfWaterAPI, HfWaterAPIError, HfWaterAuthError, HfWaterRateLimitError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class HfWaterCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for 合肥水务 data."""

    def __init__(self, hass: HomeAssistant, api: HfWaterAPI) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=DEFAULT_SCAN_INTERVAL),
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API."""
        try:
            # Step 1: Get bound accounts
            accounts = await self.api.get_bind_list()
            _LOGGER.info("Found %d water account(s)", len(accounts))

            result: dict[str, Any] = {
                "accounts": accounts,
                "bills": {},
                "pay_info": {},
                "pay_log": {},
                "_last_update_ts": datetime.now().isoformat(),
            }

            # Step 2: Get bill, pay info and pay log for each account
            for account in accounts:
                customer_id = account["customer_id"]
                try:
                    bill_data = await self.api.get_bill(customer_id)
                    result["bills"][customer_id] = bill_data
                except HfWaterRateLimitError as err:
                    _LOGGER.warning("Rate limited when fetching bill: %s", err)
                except HfWaterAPIError as err:
                    _LOGGER.error("Error fetching bill for %s: %s", customer_id, err)

                try:
                    pay_data = await self.api.get_pay_info(customer_id)
                    result["pay_info"][customer_id] = pay_data
                except HfWaterRateLimitError as err:
                    _LOGGER.warning("Rate limited when fetching pay info: %s", err)
                except HfWaterAPIError as err:
                    _LOGGER.error("Error fetching pay info for %s: %s", customer_id, err)

                try:
                    pay_log_data = await self.api.get_pay_log(customer_id)
                    result["pay_log"][customer_id] = pay_log_data
                except HfWaterRateLimitError as err:
                    _LOGGER.warning("Rate limited when fetching pay log: %s", err)
                except HfWaterAPIError as err:
                    _LOGGER.error("Error fetching pay log for %s: %s", customer_id, err)

            return result

        except HfWaterAuthError as err:
            raise UpdateFailed(f"Authentication error: {err}") from err
        except HfWaterAPIError as err:
            raise UpdateFailed(f"API error: {err}") from err
