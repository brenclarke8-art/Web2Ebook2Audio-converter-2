"""Shared debug serialization helpers for phase artifact writers."""


def to_jsonable(obj):

    if isinstance(obj, list):
        return [to_jsonable(x) for x in obj]

    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}

    if hasattr(obj, "model_dump"):
        return to_jsonable(obj.model_dump())

    if hasattr(obj, "dict"):
        return to_jsonable(obj.dict())

    return obj