import requests
from requests.exceptions import RequestException

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Phase00FetchBot)"
}

def fetch_html(url: str, timeout: float = 10.0) -> str:
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except RequestException:
        return None
