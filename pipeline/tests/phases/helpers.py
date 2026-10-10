REAL_FUCKNOVELPIA_INDEX_URL = "https://fucknovelpia.com/novel/i-became-a-6-gacha-character"


def is_live_fetch_error_message(error: str) -> bool:
    return error.startswith("Failed to fetch index URL:") or error.startswith(
        "Failed to fetch chapter URL:"
    )
