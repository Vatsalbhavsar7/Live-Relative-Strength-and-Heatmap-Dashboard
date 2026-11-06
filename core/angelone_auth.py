"""
core/angelone_auth.py
---------------------
Standalone Angel One SmartAPI authentication client using TOTP (RFC 6238).
"""

from typing import Any, Dict
import pyotp
import requests
from core.logger import get_logger

logger = get_logger("core.auth")

LOGIN_ENDPOINT = "https://apiconnect.angelone.in/rest/auth/angelbroking/user/v1/loginByPassword"


def login(user: Dict[str, Any], max_retries: int = 3) -> bool:
    """
    Authenticates Angel One account via TOTP and acquires JWT auth token & feed token.
    Populates `user['auth_token']`, `user['feed_token']`, and `user['logged_in']` in-place.
    """
    client_code = str(user.get("client_code", "")).strip()
    password = str(user.get("password", "")).strip()
    totp_secret = str(user.get("totp_secret", "")).strip()
    api_key = str(user.get("api_key", "")).strip()

    if not client_code or not password or not totp_secret or not api_key:
        err = "Missing credentials: ensure api_key, client_code, password, and totp_secret are provided."
        user["last_login_error"] = err
        logger.error(err)
        return False

    try:
        totp = pyotp.TOTP(totp_secret).now()
    except Exception as err:
        err_msg = f"Invalid TOTP secret key: {err}"
        user["last_login_error"] = err_msg
        logger.error(err_msg)
        return False

    payload = {
        "clientcode": client_code,
        "password": password,
        "totp": totp,
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-UserType": "USER",
        "X-SourceID": "WEB",
        "X-ClientLocalIP": "127.0.0.1",
        "X-ClientPublicIP": "106.193.147.98",
        "X-MACAddress": "fe80::216e:6507:4b9c:907",
        "X-PrivateKey": api_key,
    }

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(LOGIN_ENDPOINT, json=payload, headers=headers, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status"):
                    res_data = data.get("data", {})
                    raw_jwt = str(res_data.get("jwtToken", "")).replace("Bearer ", "").strip()
                    user["auth_token"] = raw_jwt
                    user["feed_token"] = res_data.get("feedToken")
                    user["refresh_token"] = res_data.get("refreshToken")
                    user["logged_in"] = True
                    user["last_login_error"] = None
                    logger.info(f"Angel One login successful for client [{client_code}].")
                    return True
                else:
                    err_msg = data.get("message") or "Authentication failed by server."
                    user["last_login_error"] = err_msg
                    logger.error(f"Login failed: {err_msg}")
                    return False
        except Exception as exc:
            user["last_login_error"] = str(exc)
            logger.warning(f"Login attempt {attempt}/{max_retries} error: {exc}")

    return False
