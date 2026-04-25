"""合肥供水 (Hefei Water) API client with RSA encryption."""
from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any
from urllib.parse import quote, urlencode

import aiohttp
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding

from .const import (
    FEIXI_BASE_URL,
    FEIXI_REFERER,
    FEIXI_RSA1_PRIVATE_KEY_PEM,
    FEIXI_RSA_PUBLIC_KEY_PEM,
    HEFEI_BASE_URL,
    HEFEI_REFERER,
    HEFEI_RSA1_PRIVATE_KEY_PEM,
    HEFEI_RSA_PUBLIC_KEY_PEM,
    REGION_FEIXI,
    REGION_HEFEI,
    WX_USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)


class HfWaterAPIError(Exception):
    """Base exception for HfWater API errors."""


class HfWaterAuthError(HfWaterAPIError):
    """Authentication error (token expired)."""


class HfWaterRateLimitError(HfWaterAPIError):
    """Rate limit error."""


class HfWaterAPI:
    """合肥水务 / 肥西供水 API client."""

    def __init__(self, token: str, region: str = REGION_HEFEI) -> None:
        self.token = token
        self.region = region

        if region == REGION_FEIXI:
            self._base_url = FEIXI_BASE_URL
            self._referer = FEIXI_REFERER
            self._pub_key = serialization.load_pem_public_key(
                FEIXI_RSA_PUBLIC_KEY_PEM.encode()
            )
            self._priv_key = serialization.load_pem_private_key(
                FEIXI_RSA1_PRIVATE_KEY_PEM.encode(), password=None
            )
        else:
            self._base_url = HEFEI_BASE_URL
            self._referer = HEFEI_REFERER
            self._pub_key = serialization.load_pem_public_key(
                HEFEI_RSA_PUBLIC_KEY_PEM.encode()
            )
            self._priv_key = serialization.load_pem_private_key(
                HEFEI_RSA1_PRIVATE_KEY_PEM.encode(), password=None
            )
        self._session: aiohttp.ClientSession | None = None

    @property
    def region_name(self) -> str:
        """Return display name for the region."""
        return "肥西供水" if self.region == REGION_FEIXI else "合肥水务"

    def _get_headers(self) -> dict[str, str]:
        return {
            "Host": self._base_url.split("/")[2],
            "token": self.token,
            "User-Agent": WX_USER_AGENT,
            "Referer": self._referer,
            "Accept-Encoding": "gzip,compress,br,deflate",
        }

    def _rsa_encrypt(self, text: str) -> str:
        """RSA-2048 PKCS1v15 encrypt, return base64."""
        encrypted = self._pub_key.encrypt(text.encode("utf-8"), padding.PKCS1v15())
        return base64.b64encode(encrypted).decode("utf-8")

    def _rsa1_decrypt_long(self, encrypted_b64: str) -> str:
        """RSA-2048 PKCS1v15 decrypt long (split into 256-byte blocks)."""
        if not encrypted_b64:
            return ""
        try:
            raw = base64.b64decode(encrypted_b64)
        except Exception:
            return encrypted_b64

        block_size = 256
        result = b""
        for i in range(0, len(raw), block_size):
            block = raw[i : i + block_size]
            try:
                result += self._priv_key.decrypt(block, padding.PKCS1v15())
            except Exception:
                return encrypted_b64
        try:
            return result.decode("utf-8")
        except UnicodeDecodeError:
            return result.decode("gbk", errors="replace")

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _api_get(self, controller: str, action: str, extra_params: dict | None = None) -> dict:
        """Make an encrypted GET request."""
        ticket_time = self._rsa_encrypt(str(int(time.time() * 1000)))
        params = {
            "c": controller,
            "a": action,
            "data_source": "2",
            "ticket_time": ticket_time,
        }
        if extra_params:
            params.update(extra_params)

        session = await self._get_session()
        url = f"{self._base_url}?{urlencode(params)}"
        _LOGGER.debug("GET %s", url[:100])

        async with session.get(url, headers=self._get_headers(), timeout=aiohttp.ClientTimeout(total=15)) as resp:
            text = await resp.text()
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                raise HfWaterAPIError(f"Non-JSON response: {text[:200]}")

        self._check_response(result)
        return result

    async def _api_post(self, controller: str, action: str, params: dict | None = None) -> dict:
        """Make an encrypted POST request."""
        if params is None:
            params = {}

        # Build encode_data: key=value& pairs + data_source=2
        s = ""
        for k, v in params.items():
            s += f"{k}={v}&"
        s += "data_source=2"

        encode_data = self._rsa_encrypt(s)
        ticket_time = self._rsa_encrypt(str(int(time.time() * 1000)))

        post_headers = {**self._get_headers(), "content-type": "application/x-www-form-urlencoded"}
        post_body = f"encode_data={quote(encode_data)}&data_source=2&ticket_time={quote(ticket_time)}"

        session = await self._get_session()
        url = f"{self._base_url}?c={controller}&a={action}"
        _LOGGER.debug("POST %s | encode_data plaintext: %s", url[:80], s)

        async with session.post(url, data=post_body, headers=post_headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            text = await resp.text()
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                raise HfWaterAPIError(f"Non-JSON response: {text[:200]}")

        self._check_response(result)
        return result

    def _check_response(self, result: dict) -> None:
        """Check API response for errors."""
        code = result.get("code")
        if code == 401:
            raise HfWaterAuthError("Token expired, please re-login")
        if code == 1001:
            msg = result.get("msg", "")
            data = result.get("data", {})
            expire_time = data.get("expire_time", 0)
            raise HfWaterRateLimitError(f"{msg} (wait {expire_time}s)")

    async def get_bind_list(self) -> list[dict[str, Any]]:
        """Get list of bound water accounts (GET request)."""
        result = await self._api_get("ys", "desensitizeCheckBind")
        accounts_raw = result.get("data", {}).get("list", [])
        accounts = []
        for item in accounts_raw:
            accounts.append({
                "customer_id": self._rsa1_decrypt_long(item.get("customer_id", "")),
                "customer_name": self._rsa1_decrypt_long(item.get("customer_name", "")),
                "customer_name1": self._rsa1_decrypt_long(item.get("customer_name1", "")),
                "customer_address": self._rsa1_decrypt_long(item.get("customer_address", "")),
                "customer_type": item.get("customer_type", 0),
            })
        return accounts

    async def get_bill(self, customer_id: str) -> dict[str, Any]:
        """Get bill data for a customer (POST request).

        合肥 and 肥西 both use controller 'ys'.
        """
        result = await self._api_post("ys", "desensitizeGetBill4", {"customerId": customer_id})
        data = result.get("data", {})

        # Decrypt customer info
        customer_address = self._rsa1_decrypt_long(data.get("customerAddress", ""))
        customer_name = self._rsa1_decrypt_long(data.get("customerName", ""))

        # Bill list is plain text
        bill_list = data.get("list", [])

        return {
            "customer_address": customer_address,
            "customer_name": customer_name,
            "count": data.get("count", 0),
            "bill_list": bill_list,
        }

    async def get_pay_info(self, customer_id: str) -> dict[str, Any]:
        """Get payment info for a customer (POST request).

        payInfo.payAmount = 待缴金额 (0 means no payment due)
        payInfo.balance = 账户余额
        payInfo.userNeedPay = 应缴水费
        payInfo.userLateFee = 违约金
        moneyArr = 充值金额选项 (not payment records)
        """
        result = await self._api_post("Pay", "desensitizeGetPayInfo4", {"customerId": customer_id})
        data = result.get("data", {})

        pay_info = data.get("payInfo", {})
        money_arr = data.get("moneyArr", {})

        return {
            "customer_id": self._rsa1_decrypt_long(data.get("customerId", "")),
            "customer_name": self._rsa1_decrypt_long(data.get("customerName", "")),
            "customer_address": self._rsa1_decrypt_long(data.get("customerAddress", "")),
            "balance": pay_info.get("balance", 0),
            "user_need_pay": pay_info.get("userNeedPay", 0),
            "user_late_fee": pay_info.get("userLateFee", 0),
            "pay_amount": pay_info.get("payAmount", 0),
            "money_arr": money_arr,
        }

    async def get_pay_log(self, customer_id: str, page_index: int = 1, page_size: int = 12) -> dict[str, Any]:
        """Get payment log for a customer (GET request).

        Returns real payment records with money, createtime, order_date.
        """
        encode_data = self._rsa_encrypt(f"customerId={customer_id}&data_source=2")
        ticket_time = self._rsa_encrypt(str(int(time.time() * 1000)))

        params = {
            "pageIndex": str(page_index),
            "pageSize": str(page_size),
            "encode_data": encode_data,
            "data_source": "2",
            "ticket_time": ticket_time,
        }

        session = await self._get_session()
        url = f"{self._base_url}?c=Pay&a=desensitizeGetPayLog2&{urlencode(params)}"
        _LOGGER.debug("GET pay_log %s", url[:100])

        async with session.get(url, headers=self._get_headers(), timeout=aiohttp.ClientTimeout(total=15)) as resp:
            text = await resp.text()
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                raise HfWaterAPIError(f"Non-JSON response: {text[:200]}")

        self._check_response(result)
        data = result.get("data", {})
        log_list = data.get("list", [])

        pay_records = []
        for item in log_list:
            pay_records.append({
                "customer_id": self._rsa1_decrypt_long(item.get("customer_id", "")),
                "customer_name": self._rsa1_decrypt_long(item.get("customer_name", "")),
                "money": float(item.get("money", 0)),
                "order_date": item.get("order_date", ""),
                "createtime": item.get("createtime", ""),
            })

        return {
            "list": pay_records,
            "total": data.get("total", 0),
            "page_count": data.get("pageCount", 0),
        }

    async def get_no_pay_info(self, customer_id: str) -> dict[str, Any]:
        """Get no-pay info for a customer (肥西特有, POST request).

        Returns whether customer has unpaid bills.
        """
        result = await self._api_post("ys", "getNoPayInfo", {"customerId": customer_id})
        data = result.get("data", "")
        return {
            "has_unpaid": data != "NO" if isinstance(data, str) else False,
            "raw": data,
        }

    async def test_connection(self) -> bool:
        """Test if the token is valid."""
        try:
            await self.get_bind_list()
            return True
        except HfWaterAuthError:
            return False
        except Exception:
            return False
