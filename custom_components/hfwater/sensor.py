"""Sensor platform for 合肥供水 (Hefei Water)."""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DAILY_UPDATE_HOUR, DAILY_UPDATE_MINUTE, DOMAIN
from .coordinator import HfWaterCoordinator

_LOGGER = logging.getLogger(__name__)

# 读取版本号
try:
    _MANIFEST = json.loads((Path(__file__).parent / "manifest.json").read_text(encoding="utf-8"))
    _VERSION = _MANIFEST.get("version", "unknown")
except Exception:
    _VERSION = "unknown"


@dataclass(frozen=True, kw_only=True)
class HfWaterSensorEntityDescription(SensorEntityDescription):
    """合肥供水传感器描述."""

    value_fn: Callable[[dict, str], Any]


SENSOR_DESCRIPTIONS: list[HfWaterSensorEntityDescription] = [
    HfWaterSensorEntityDescription(
        key="account_balance",
        translation_key="account_balance",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="CNY",
        icon="mdi:wallet",
        value_fn=lambda data, cid: data.get("pay_info", {}).get(cid, {}).get("balance"),
    ),
    HfWaterSensorEntityDescription(
        key="next_poll_time",
        translation_key="next_poll_time",
        icon="mdi:clock-outline",
        value_fn=lambda data, cid: _calc_next_poll_time(),
    ),
    HfWaterSensorEntityDescription(
        key="user_need_pay",
        translation_key="user_need_pay",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="CNY",
        icon="mdi:cash-register",
        value_fn=lambda data, cid: data.get("pay_info", {}).get(cid, {}).get("user_need_pay"),
    ),
    HfWaterSensorEntityDescription(
        key="user_late_fee",
        translation_key="user_late_fee",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="CNY",
        icon="mdi:alert-circle-outline",
        value_fn=lambda data, cid: data.get("pay_info", {}).get(cid, {}).get("user_late_fee"),
    ),
    HfWaterSensorEntityDescription(
        key="latest_bill_amount",
        translation_key="latest_bill_amount",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="CNY",
        icon="mdi:currency-cny",
        value_fn=lambda data, cid: (
            _first_bill(data, cid).get("SumFee") if _first_bill(data, cid) else None
        ),
    ),
    HfWaterSensorEntityDescription(
        key="latest_bill_date",
        translation_key="latest_bill_date",
        icon="mdi:calendar",
        value_fn=lambda data, cid: (
            _format_order_date(_first_bill(data, cid).get("Year", ""))
            if _first_bill(data, cid) else None
        ),
    ),
    HfWaterSensorEntityDescription(
        key="latest_bill_water_usage",
        translation_key="latest_bill_water_usage",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        icon="mdi:water",
        value_fn=lambda data, cid: (
            _first_bill(data, cid).get("WaterNum") if _first_bill(data, cid) else None
        ),
    ),
    HfWaterSensorEntityDescription(
        key="latest_bill_meter_reading",
        translation_key="latest_bill_meter_reading",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        icon="mdi:gauge",
        value_fn=lambda data, cid: (
            _first_bill(data, cid).get("MeterData") if _first_bill(data, cid) else None
        ),
    ),
    HfWaterSensorEntityDescription(
        key="recent_bills_total",
        translation_key="recent_bills_total",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="CNY",
        icon="mdi:receipt-text-outline",
        value_fn=lambda data, cid: _calc_bills_total(data, cid),
    ),
    HfWaterSensorEntityDescription(
        key="latest_pay_amount",
        translation_key="latest_pay_amount",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="CNY",
        icon="mdi:cash-check",
        value_fn=lambda data, cid: (
            _first_pay(data, cid).get("money") if _first_pay(data, cid) else None
        ),
    ),
]


def _first_bill(data: dict, cid: str) -> dict | None:
    """Get first bill entry for customer."""
    bill_list = data.get("bills", {}).get(cid, {}).get("bill_list", [])
    return bill_list[0] if bill_list else None


def _first_pay(data: dict, cid: str) -> dict | None:
    """Get first pay record for customer."""
    log_list = data.get("pay_log", {}).get(cid, {}).get("list", [])
    return log_list[0] if log_list else None


def _calc_bills_total(data: dict, cid: str) -> float | None:
    """Calculate total fee for up to 6 bills."""
    bill_list = data.get("bills", {}).get(cid, {}).get("bill_list", [])
    if not bill_list:
        return None
    total = 0.0
    for bill in bill_list[:6]:
        try:
            total += float(bill.get("SumFee", 0))
        except (ValueError, TypeError):
            pass
    return round(total, 2)


def _calc_next_poll_time() -> str | None:
    """Calculate next poll time: next 7:30 AM."""
    try:
        now = datetime.now()
        target = now.replace(hour=DAILY_UPDATE_HOUR, minute=DAILY_UPDATE_MINUTE, second=0, microsecond=0)
        if now >= target:
            target = target + timedelta(days=1)
        return target.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _format_order_date(raw) -> str:
    """Format order_date like '202603' or 202603 -> '2026年03月'."""
    if raw is None:
        return ""
    s = str(raw)
    if not s or len(s) < 6:
        return s
    try:
        return f"{s[:4]}年{s[4:6]}月"
    except Exception:
        return s


def _format_createtime(ct) -> str:
    """Format createtime from unix timestamp string to datetime string."""
    if not ct:
        return ""
    try:
        ts = int(ct) if not isinstance(ct, (int, float)) else int(ct)
        if ts > 0:
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError, OSError):
        pass
    return str(ct)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]

    entities: list[HfWaterSensor] = []

    if not coordinator.data:
        _LOGGER.warning("Coordinator data not available yet, skipping sensor setup")
        async_add_entities(entities)
        return

    manufacturer = api.region_name

    accounts = coordinator.data.get("accounts", [])
    for account in accounts:
        customer_id = account["customer_id"]
        customer_name = account["customer_name"]
        customer_address = account.get("customer_address", "")

        for desc in SENSOR_DESCRIPTIONS:
            entities.append(
                HfWaterSensor(
                    coordinator=coordinator,
                    customer_id=customer_id,
                    customer_name=customer_name,
                    customer_address=customer_address,
                    manufacturer=manufacturer,
                    description=desc,
                )
            )

    async_add_entities(entities)


class HfWaterSensor(CoordinatorEntity[HfWaterCoordinator], SensorEntity):
    """合肥供水传感器实体."""

    _attr_has_entity_name = True

    entity_description: HfWaterSensorEntityDescription

    def __init__(
        self,
        coordinator: HfWaterCoordinator,
        customer_id: str,
        customer_name: str,
        customer_address: str,
        manufacturer: str,
        description: HfWaterSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.customer_id = customer_id
        self.customer_name = customer_name
        self.customer_address = customer_address
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{customer_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, customer_id)},
            name=customer_address or f"{manufacturer} {customer_name}",
            manufacturer=manufacturer,
            model=f"{customer_name} - {customer_id}",
            sw_version=_VERSION,
        )
        # 手动设置 entity_id，避免中文地址转拼音导致 ID 过长
        self.entity_id = f"sensor.{DOMAIN}_{customer_id}_{description.key}"

    @property
    def native_value(self) -> str | float | None:
        """Return the sensor state."""
        if not self.coordinator.data:
            return None
        value = self.entity_description.value_fn(self.coordinator.data, self.customer_id)
        if value is not None:
            try:
                return float(value)
            except (ValueError, TypeError):
                return value
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        attrs: dict[str, Any] = {
            "sensor_key": self.entity_description.key,
            "customer_id": self.customer_id,
        }
        if not self.coordinator.data:
            return attrs

        key = self.entity_description.key

        # 最近6期账单 - 独立传感器，值=总水费，属性=明细
        if key == "recent_bills_total":
            bill_data = self.coordinator.data.get("bills", {}).get(self.customer_id)
            if bill_data:
                bill_list = bill_data.get("bill_list", [])
                bills_detail = []
                for bill in bill_list[:6]:
                    bills_detail.append({
                        "period": _format_order_date(bill.get("Year", "")),
                        "water_usage": bill.get("WaterNum", 0),
                        "prev_meter_reading": bill.get("PrevMeterData", 0),
                        "meter_reading": bill.get("MeterData", 0),
                        "water_fee": bill.get("WaterFee", 0),
                        "service_fee": bill.get("ServiceFee", 0),
                        "late_fees": bill.get("LateFees", 0),
                        "fact_fee": bill.get("FactFee", 0),
                        "total_fee": bill.get("SumFee", 0),
                    })
                attrs["最近6期账单"] = bills_detail

        # 缴费记录
        elif key == "latest_pay_amount":
            pay_log = self.coordinator.data.get("pay_log", {}).get(self.customer_id)
            if pay_log:
                log_list = pay_log.get("list", [])
                pay_detail = []
                for record in log_list[:6]:
                    ct = record.get("createtime", "")
                    pay_detail.append({
                        "amount": record.get("money", 0),
                        "order_date": _format_order_date(record.get("order_date", "")),
                        "create_time": _format_createtime(ct),
                    })
                attrs["最近缴费记录"] = pay_detail

        # 余额传感器添加客户信息
        elif key == "account_balance":
            attrs["customer_name"] = self.customer_name
            attrs["customer_address"] = self.customer_address

        return attrs
