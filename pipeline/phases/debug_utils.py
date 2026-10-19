"""Shared debug serialization helpers for phase artifact writers."""


def to_jsonable(value):
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value
