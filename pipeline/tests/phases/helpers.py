def is_live_fetch_error_message(error: str) -> bool:
    return error.startswith("Failed to fetch index URL:")
