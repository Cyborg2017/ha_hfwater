"""Config flow for 合肥供水 (Hefei Water)."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .api import HfWaterAPI, HfWaterAuthError, HfWaterAPIError
from .const import CONF_REGION, CONF_TOKEN, DOMAIN, REGION_FEIXI, REGION_HEFEI, REGION_OPTIONS

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for 合肥供水."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            region = user_input[CONF_REGION]
            token = user_input[CONF_TOKEN]
            try:
                api = HfWaterAPI(token, region)
                valid = await api.test_connection()
                await api.close()

                if not valid:
                    errors["base"] = "invalid_auth"
                else:
                    region_label = REGION_OPTIONS[region]
                    unique_id = f"{region}_{token[:16]}"
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=f"合肥供水（{region_label}）",
                        data=user_input,
                    )
            except HfWaterAuthError:
                errors["base"] = "invalid_auth"
            except HfWaterAPIError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_REGION, default=REGION_HEFEI): vol.In(REGION_OPTIONS),
                vol.Required(CONF_TOKEN): str,
            }),
            errors=errors,
            description_placeholders={
                "token_hint": "请从微信小程序中获取 Token（可通过抓包获取）"
            },
        )
