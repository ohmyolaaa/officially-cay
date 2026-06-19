import itertools
import threading
import re

# Per-user proxy pools. Key = user_id (int). Admin uses ADMIN_ID as key.
_user_proxy_pools: dict = {}
_user_proxy_cycles: dict = {}
_user_uploaded_flags: dict = {}
_proxy_lock = threading.Lock()


# ============= PROXY PARSER =============

def _build_proxy_dict(scheme, host, port, user=None, password=None):
    host = host.strip()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    if user is not None and password is not None:
        return f"{scheme}://{user}:{password}@{host}:{port}"
    return f"{scheme}://{host}:{port}"


def _parse_proxy_line(line: str) -> str | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    line = re.sub(r"^([a-zA-Z][a-zA-Z0-9+.-]*):/+", r"\1://", line)
    line = re.sub(r"\s+", " ", line).strip()

    url_like = re.match(
        r"^(?P<scheme>https?|socks5h?|socks4a?)://"
        r"(?:(?P<user>[^:@\s]+):(?P<password>[^@\s]+)@)?"
        r"(?P<host>\[[^\]]+\]|[^:\s]+):(?P<port>\d+)$",
        line, flags=re.IGNORECASE,
    )
    if url_like:
        d = url_like.groupdict()
        return _build_proxy_dict(d["scheme"].lower(), d["host"], d["port"], d.get("user"), d.get("password"))

    m = re.match(r"^(?P<user>[^:@\s]+):(?P<password>[^@\s]+)@(?P<host>\[[^\]]+\]|[^:\s]+):(?P<port>\d+)$", line)
    if m:
        d = m.groupdict()
        return _build_proxy_dict("http", d["host"], d["port"], d["user"], d["password"])

    m = re.match(r"^(?P<host>\[[^\]]+\]|[^:\s]+):(?P<port>\d+)@(?P<user>[^:@\s]+):(?P<password>[^@\s]+)$", line)
    if m:
        d = m.groupdict()
        return _build_proxy_dict("http", d["host"], d["port"], d["user"], d["password"])

    m = re.match(r"^(?P<host>\[[^\]]+\]|[^:\s]+):(?P<port>\d+)$", line)
    if m:
        d = m.groupdict()
        return _build_proxy_dict("http", d["host"], d["port"])

    four = line.split(":")
    if len(four) == 4:
        a, b, c, d = four
        if b.isdigit() and not d.isdigit():
            return _build_proxy_dict("http", a, b, c, d)
        if d.isdigit() and not b.isdigit():
            return _build_proxy_dict("http", c, d, a, b)

    for pattern in [
        r"^(?P<host>\[[^\]]+\]|[^:\s]+):(?P<port>\d+)\s+(?P<user>[^:\s]+):(?P<password>\S+)$",
        r"^(?P<host>\[[^\]]+\]|[^:\s]+):(?P<port>\d+)\|(?P<user>[^:\s]+):(?P<password>\S+)$",
        r"^(?P<host>\[[^\]]+\]|[^:\s]+):(?P<port>\d+);(?P<user>[^:\s]+):(?P<password>\S+)$",
        r"^(?P<host>\[[^\]]+\]|[^:\s]+):(?P<port>\d+),(?P<user>[^:\s]+):(?P<password>\S+)$",
    ]:
        m = re.match(pattern, line)
        if m:
            d = m.groupdict()
            return _build_proxy_dict("http", d["host"], d["port"], d["user"], d["password"])

    return None


# ============= POOL HELPERS =============

def _set_pool(user_id, proxies: list):
    key = str(user_id)
    with _proxy_lock:
        _user_proxy_pools[key] = proxies
        _user_proxy_cycles[key] = itertools.cycle(proxies) if proxies else None


def get_pool_size(user_id) -> int:
    with _proxy_lock:
        return len(_user_proxy_pools.get(str(user_id), []))


def get_next_disney_proxy(user_id) -> str | None:
    key = str(user_id)
    with _proxy_lock:
        cycle = _user_proxy_cycles.get(key)
        if not cycle:
            return None
        return next(cycle)


def remove_disney_proxy(user_id, proxy_url: str):
    key = str(user_id)
    with _proxy_lock:
        pool = _user_proxy_pools.get(key, [])
        if proxy_url in pool:
            pool.remove(proxy_url)
            _user_proxy_pools[key] = pool
            _user_proxy_cycles[key] = itertools.cycle(pool) if pool else None
            print(f"[Proxy] Removed dead proxy for {user_id}. Pool: {len(pool)}")


def get_proxy_type_summary(user_id) -> str:
    with _proxy_lock:
        pool = _user_proxy_pools.get(str(user_id), [])
        if not pool:
            return "No proxies loaded"
        return _detect_types(pool)


def _detect_types(proxies: list[str]) -> str:
    types = set()
    for p in proxies:
        for scheme in ("socks5", "socks4", "https", "http"):
            if p.startswith(scheme + "://"):
                types.add(scheme.upper())
                break
        else:
            types.add("HTTP")
    return ", ".join(sorted(types)) if types else "Unknown"


def is_user_uploaded_pool(user_id) -> bool:
    return _user_uploaded_flags.get(str(user_id), False)


# ============= UPLOAD / CLEAR =============

def load_proxies_from_text(text: str) -> list[str]:
    return [p for line in text.splitlines() if (p := _parse_proxy_line(line))]


def load_proxies_from_file(filepath: str) -> list[str]:
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return load_proxies_from_text(f.read())
    except Exception as e:
        print(f"[Proxy] Failed to read file: {e}")
        return []


def set_uploaded_proxies(user_id, proxy_list: list[str]) -> int:
    """Store proxies for this user only. No other user is affected."""
    if not proxy_list:
        return 0
    _set_pool(user_id, proxy_list)
    _user_uploaded_flags[str(user_id)] = True
    print(f"[Proxy] Pool set for {user_id}: {len(proxy_list)} proxies")
    return len(proxy_list)


def clear_proxy_pool(user_id):
    """Clear only this user's proxy pool."""
    _set_pool(user_id, [])
    _user_uploaded_flags[str(user_id)] = False
    print(f"[Proxy] Pool cleared for {user_id}.")


# Mode → actual API endpoint to test against
_MODE_TEST_CONFIG = {
    "Crunchyroll": {
        "url":     "https://api.crunchyroll.com/start.0.json",
        "method":  "GET",
        "good_codes": {200, 400, 401, 403},
        "bad_codes":  {403, 429, 503},   # soft-block = proxy rejected
        "check_body": None,
    },
    "Disney+": {
        "url":     "https://global.api.disneyplusbilling.com/",
        "method":  "GET",
        "good_codes": {200, 302, 400, 401},
        "bad_codes":  {403, 407, 503},
        "check_body": None,
    },
    "Webtoon": {
        "url":     "https://www.webtoons.com/en/",
        "method":  "GET",
        "good_codes": {200, 301, 302},
        "bad_codes":  {403, 407, 503},
        "check_body": None,
    },
    "Vivamax": {
        "url":     "https://api.vivamax.ph/api/v6/auth/login",
        "method":  "POST",
        "good_codes": {200, 400, 401, 422},
        "bad_codes":  {403, 407, 503},
        "check_body": None,
    },
    "Steam": {
        "url":     "https://store.steampowered.com/",
        "method":  "GET",
        "good_codes": {200, 301, 302},
        "bad_codes":  {403, 407, 503},
        "check_body": None,
    },
    "ExpressVPN": {
        "url":     "https://www.expressapisv2.net/",
        "method":  "GET",
        "good_codes": {200, 400, 401, 403},
        "bad_codes":  {407, 503},
        "check_body": None,
    },
    "Spotify": {
        "url":     "https://accounts.spotify.com/",
        "method":  "GET",
        "good_codes": {200, 301, 302},
        "bad_codes":  {403, 407, 503},
        "check_body": None,
    },
    "CapCut": {
        "url":        "https://login-row.www.capcut.com/passport/web/user/check_email_registered?aid=348188&account_sdk_source=web",
        "method":     "GET",
        "good_codes": {200, 400, 401, 405},
        "bad_codes":  {403, 407, 503},
        "check_body": None,
    },
}
_DEFAULT_TEST_URL = "https://www.google.com"

def check_proxy_alive(proxy_url: str, mode: str = None, timeout: int = 6) -> bool:
    """
    Mode-aware proxy test:
    - Uses correct HTTP method per service
    - Distinguishes real blocks (403/407) from auth failures (401/400)
    - SSL errors = proxy connected = alive
    - Connection errors = dead
    """
    import requests

    cfg = _MODE_TEST_CONFIG.get(mode)
    if not cfg:
        # Fallback: just test Google connectivity
        test_url = _DEFAULT_TEST_URL
        method = "HEAD"
        good_codes = set(range(200, 500))
        bad_codes = {407, 503}
    else:
        test_url = cfg["url"]
        method = cfg["method"]
        good_codes = cfg["good_codes"]
        bad_codes = cfg["bad_codes"]

    proxies = {"http": proxy_url, "https": proxy_url}

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/html, */*",
    }

    try:
        if method == "POST":
            resp = requests.post(
                test_url,
                proxies=proxies,
                timeout=timeout,
                headers=headers,
                json={},           # empty body — just testing reachability
                allow_redirects=False,
                verify=False,
            )
        else:
            resp = requests.get(
                test_url,
                proxies=proxies,
                timeout=timeout,
                headers=headers,
                allow_redirects=False,
                verify=False,
            )

        code = resp.status_code

        # Explicit block by the service = proxy is blacklisted
        if code in bad_codes:
            print(f"[Proxy] {proxy_url[:30]} blocked by {mode} → {code}")
            return False

        # Any response in good_codes = proxy works for this service
        if code in good_codes:
            return True

        # 407 = proxy auth required (misconfigured proxy)
        if code == 407:
            return False

        # Anything else (5xx server errors) = treat as alive
        # since the service itself may be down, not the proxy
        return code < 600

    except requests.exceptions.SSLError:
        # SSL handshake = proxy tunnelled successfully
        return True
    except requests.exceptions.ProxyError:
        # Proxy itself rejected connection
        return False
    except requests.exceptions.ConnectTimeout:
        return False
    except requests.exceptions.ReadTimeout:
        # Proxy connected but service slow — count as alive
        return True
    except Exception:
        return False


def test_all_proxies(
    user_id,
    mode: str = None,
    timeout: int = 6,
    progress_callback=None,
) -> dict:
    import concurrent.futures

    key = str(user_id)
    with _proxy_lock:
        pool = list(_user_proxy_pools.get(key, []))

    if not pool:
        cfg = _MODE_TEST_CONFIG.get(mode, {})
        return {
            "alive": [],
            "dead": [],
            "mode": mode,
            "test_url": cfg.get("url", _DEFAULT_TEST_URL),
            "method": cfg.get("method", "GET"),
        }

    cfg = _MODE_TEST_CONFIG.get(mode, {})
    test_url = cfg.get("url", _DEFAULT_TEST_URL)
    test_method = cfg.get("method", "GET")
    total = len(pool)

    def _check(proxy):
        return proxy, check_proxy_alive(proxy, mode=mode, timeout=timeout)

    alive, dead = [], []
    checked = 0
    workers = min(300, total)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_check, proxy): proxy for proxy in pool}
        for future in concurrent.futures.as_completed(futures):
            try:
                proxy, is_alive = future.result()
            except Exception:
                proxy = futures[future]
                is_alive = False

            if is_alive:
                alive.append(proxy)
            else:
                dead.append(proxy)

            checked += 1
            if progress_callback is not None:
                try:
                    progress_callback(checked, total, is_alive)
                except Exception:
                    pass

    return {
        "alive": alive,
        "dead": dead,
        "mode": mode,
        "test_url": test_url,
        "method": test_method,
    }


def remove_dead_proxies(user_id, dead_list: list) -> int:
    """Remove a specific list of dead proxies from the user's pool. Returns new pool size."""
    key = str(user_id)
    dead_set = set(dead_list)
    with _proxy_lock:
        pool = _user_proxy_pools.get(key, [])
        new_pool = [p for p in pool if p not in dead_set]
        _user_proxy_pools[key] = new_pool
        _user_proxy_cycles[key] = itertools.cycle(new_pool) if new_pool else None
    print(f"[Proxy] Removed {len(dead_list)} dead proxies for {user_id}. Remaining: {len(new_pool)}")
    return len(new_pool)
