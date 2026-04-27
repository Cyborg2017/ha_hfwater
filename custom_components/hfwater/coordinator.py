"""DataUpdateCoordinator for 合肥供水 (Hefei Water)."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant, CALLBACK_TYPE
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import HfWaterAPI, HfWaterAPIError, HfWaterAuthError, HfWaterRateLimitError
from .const import DOMAIN, REGION_FEIXI, DAILY_UPDATE_HOUR, DAILY_UPDATE_MINUTE

_LOGGER = logging.getLogger(__name__)


class HfWaterCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for 合肥供水 data."""

    def __init__(self, hass: HomeAssistant, api: HfWaterAPI) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,
        )
        self.api = api
        self._cancel_daily: CALLBACK_TYPE | None = None

    async def async_config_entry_first_refresh(self) -> None:
        """首次刷新并注册每日定时更新."""
        await super().async_config_entry_first_refresh()
        self._cancel_daily = async_track_time_change(
            self.hass,
            self._async_daily_update,
            hour=DAILY_UPDATE_HOUR,
            minute=DAILY_UPDATE_MINUTE,
            second=0,
        )
        _LOGGER.info(
            "已注册每日定时更新: %02d:%02d", DAILY_UPDATE_HOUR, DAILY_UPDATE_MINUTE
        )

    async def _async_daily_update(self, now: datetime) -> None:
        """每日定时触发数据更新."""
        _LOGGER.info("定时更新触发: %s", now.isoformat())
        await self.async_request_refresh()

    def async_stop(self) -> None:
        """取消定时任务."""
        if self._cancel_daily:
            self._cancel_daily()
            self._cancel_daily = None

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
                "no_pay_info": {},
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

                # 肥西特有：欠费查询
                if self.api.region == REGION_FEIXI:
                    try:
                        no_pay_data = await self.api.get_no_pay_info(customer_id)
                        result["no_pay_info"][customer_id] = no_pay_data
                    except HfWaterAPIError as err:
                        _LOGGER.warning("Error fetching no_pay_info for %s: %s", customer_id, err)

            return result

        except HfWaterAuthError as err:
            raise UpdateFailed(f"Authentication error: {err}") from err
        except HfWaterAPIError as err:
            raise UpdateFailed(f"API error: {err}") from err
