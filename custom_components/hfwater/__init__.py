"""合肥水务 (Hefei Water) Home Assistant integration."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, CoreState, EVENT_HOMEASSISTANT_STARTED
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.helpers.event import async_call_later

from .api import HfWaterAPI
from .const import CONF_TOKEN, DOMAIN, PLATFORMS
from .coordinator import HfWaterCoordinator

_LOGGER = logging.getLogger(__name__)

# 前端卡片配置
URL_BASE = "/hfwater-local"
MANIFEST_PATH = Path(__file__).parent / "manifest.json"
try:
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        INTEGRATION_VERSION = json.load(f).get("version", "0.0.0")
except Exception:
    INTEGRATION_VERSION = "0.0.0"

CARD_FILENAME = "hfwater-card.js"

# 确保只注册一次
_STATIC_REGISTERED = False


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """组件初始化时注册前端卡片资源."""
    await _register_static_and_js(hass)

    # HA 启动后追加 Lovelace storage 注册
    async def _register_lovelace_storage(_event=None) -> None:
        await _register_lovelace_resource(hass)

    if hass.state == CoreState.running:
        await _register_lovelace_storage()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _register_lovelace_storage)

    return True


async def _register_static_and_js(hass: HomeAssistant) -> None:
    """立即注册静态路径和 add_extra_js_url."""
    global _STATIC_REGISTERED
    if _STATIC_REGISTERED:
        return
    _STATIC_REGISTERED = True

    try:
        await hass.http.async_register_static_paths([
            StaticPathConfig(URL_BASE, str(Path(__file__).parent / "www"), False)
        ])
    except RuntimeError:
        _LOGGER.debug("静态路径已注册: %s", URL_BASE)

    add_extra_js_url(hass, f"{URL_BASE}/{CARD_FILENAME}")
    _LOGGER.debug("注册前端卡片: %s/%s", URL_BASE, CARD_FILENAME)


async def _register_lovelace_resource(hass: HomeAssistant) -> None:
    """通过 Lovelace storage API 持久化注册资源."""
    lovelace = hass.data.get("lovelace")
    if not lovelace or not hasattr(lovelace, "resources") or lovelace.resources is None:
        return

    url = f"{URL_BASE}/{CARD_FILENAME}?v={INTEGRATION_VERSION}"
    url_base_no_version = f"{URL_BASE}/{CARD_FILENAME}"

    async def _check_and_register(_now=None) -> None:
        try:
            if not lovelace.resources.loaded:
                _LOGGER.debug("Lovelace 资源未加载，3秒后重试")
                async_call_later(hass, 3, _check_and_register)
                return

            existing = [r for r in lovelace.resources.async_items() if r["url"].startswith(URL_BASE)]

            for resource in existing:
                resource_path = resource["url"].split("?")[0]
                if resource_path == url_base_no_version:
                    if resource["url"] != url:
                        _LOGGER.info("更新卡片资源版本: %s -> %s", resource["url"], url)
                        await lovelace.resources.async_update_item(
                            resource["id"],
                            {"res_type": "module", "url": url},
                        )
                    return

            _LOGGER.info("持久化注册前端卡片: %s", url)
            await lovelace.resources.async_create_item(
                {"res_type": "module", "url": url}
            )
        except Exception as ex:
            _LOGGER.debug("Lovelace 资源注册失败: %s", ex)

    await _check_and_register()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up 合肥水务 from a config entry."""
    token = entry.data[CONF_TOKEN]
    api = HfWaterAPI(token)

    coordinator = HfWaterCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["api"].close()

    return unload_ok
