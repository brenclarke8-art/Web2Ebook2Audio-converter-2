import time
import requests
from urllib.parse import urljoin
from requests.exceptions import RequestException

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Phase00FetchBot)",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml"
}

def fetch_html(url: str, timeout: float = 15.0, retries: int = 3) -> dict:
    """
    Fetch HTML with retries and structured return.
    Returns:
        {
            "ok": bool,
            "status": int or None,
            "html": str or None,
            "error": str or None
        }
    """

    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
            status = resp.status_code

            if 200 <= status < 300:
                return {
                    "ok": True,
                    "status": status,
                    "html": resp.text,
                    "error": None
                }

            # Non-200 response
            return {
                "ok": False,
                "status": status,
                "html": None,
                "error": f"HTTP {status}"
            }

        except RequestException as e:
            # Last attempt → return failure
            if attempt == retries - 1:
                return {
                    "ok": False,
                    "status": None,
                    "html": None,
                    "error": str(e)
                }

            # Backoff before retry
            time.sleep(0.5 * (attempt + 1))

    # Should never reach here
    return {
        "ok": False,
        "status": None,
        "html": None,
        "error": "Unknown error"
    }
