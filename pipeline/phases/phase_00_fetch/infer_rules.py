import json
import re
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlparse

RULES_PATH = Path(__file__).parent / "rules" / "scraper_rules.json"


class RuleInferenceError(ValueError):
    """Raised when chapter example URLs cannot be used to infer a rule."""


def normalize_domain(url: str) -> str:
    domain = urlparse(url).netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def _tokenize_numeric_parts(value: str) -> List[str]:
    return re.split(r"(\d+)", value)


def _is_consecutive(nums: List[int]) -> bool:
    return len(nums) == 3 and nums[1] == nums[0] + 1 and nums[2] == nums[1] + 1


def _find_sequence_slot(urls: List[str]) -> Tuple[List[str], int, List[int], int]:
    tokens_per_url = [_tokenize_numeric_parts(url) for url in urls]
    first = tokens_per_url[0]

    if not all(len(tokens) == len(first) for tokens in tokens_per_url):
        raise RuleInferenceError("Could not infer a stable chapter number position from the provided examples.")

    candidate_indices: List[Tuple[int, List[int], int]] = []

    for idx in range(1, len(first), 2):
        if not all(tokens[idx].isdigit() for tokens in tokens_per_url):
            continue

        numbers = [int(tokens[idx]) for tokens in tokens_per_url]
        if len(set(numbers)) <= 1:
            continue

        if _is_consecutive(numbers):
            widths = [len(tokens[idx]) for tokens in tokens_per_url]
            has_leading_zero = any(tokens[idx].startswith("0") for tokens in tokens_per_url)
            padding = widths[0] if has_leading_zero and len(set(widths)) == 1 else 0
            candidate_indices.append((idx, numbers, padding))

    if not candidate_indices:
        raise RuleInferenceError("Chapter examples must be three consecutive chapters with a detectable numeric sequence.")

    # Prefer the last changing numeric segment (usually the chapter segment).
    slot_index, numbers, padding = candidate_indices[-1]

    static_tokens = list(first)
    static_tokens[slot_index] = "{n}"

    for tokens in tokens_per_url[1:]:
        compare = list(tokens)
        compare[slot_index] = "{n}"
        if compare != static_tokens:
            raise RuleInferenceError("Could not infer a stable chapter URL pattern from the provided examples.")

    return first, slot_index, numbers, padding


def _format_placeholder(padding: int) -> str:
    return "{n}" if padding <= 0 else f"{{n:0{padding}}}"


def infer_chapter_pattern(chapter_example_1: str, chapter_example_2: str, chapter_example_3: str) -> Dict[str, object]:
    examples = [chapter_example_1.strip(), chapter_example_2.strip(), chapter_example_3.strip()]

    if not all(examples):
        raise RuleInferenceError("All three chapter example URLs are required.")

    domains = {normalize_domain(url) for url in examples}
    if len(domains) != 1:
        raise RuleInferenceError("Chapter example URLs must belong to the same domain.")

    token_list, slot_index, numbers, padding = _find_sequence_slot(examples)

    static_prefix = "".join(token_list[:slot_index])
    static_suffix = "".join(token_list[slot_index + 1 :])

    return {
        "examples": examples,
        "domain": next(iter(domains)),
        "static_prefix": static_prefix,
        "static_suffix": static_suffix,
        "padding": padding,
        "first_known_chapter": numbers[0],
        "number_position": slot_index,
    }


def extract_chapter_number(url: str, chapter_regex: str) -> int | None:
    match = re.search(chapter_regex, urlparse(url).path)
    if not match:
        return None

    if match.groups():
        value = match.group(1)
    else:
        digits = re.findall(r"\d+", match.group(0))
        value = digits[-1] if digits else None

    return int(value) if value and value.isdigit() else None


def build_chapter_template(inference: Dict[str, object]) -> str:
    padding = int(inference["padding"])
    return f"{inference['static_prefix']}{_format_placeholder(padding)}{inference['static_suffix']}"


def build_chapter_regex(inference: Dict[str, object]) -> str:
    padding = int(inference["padding"])
    numeric_pattern = r"([0-9]+)" if padding <= 0 else rf"([0-9]{{{padding}}})"

    prefix_path = re.escape(urlparse(str(inference["static_prefix"])).path)
    suffix_path = re.escape(urlparse(str(inference["static_suffix"])).path)

    regex = f"^{prefix_path}{numeric_pattern}{suffix_path}$"
    if regex.endswith(r"/$"):
        regex = regex[:-2] + r"/?$"

    return regex


def load_learned_rule(domain: str) -> Dict[str, object]:
    normalized = domain.lower().strip()
    if normalized.startswith("www."):
        normalized = normalized[4:]

    if not RULES_PATH.exists():
        return {}

    data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    return data.get(normalized, {})


def save_learned_rule(domain: str, rule: Dict[str, object]) -> Dict[str, object]:
    normalized = domain.lower().strip()
    if normalized.startswith("www."):
        normalized = normalized[4:]

    if RULES_PATH.exists():
        data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    else:
        data = {}

    existing = data.get(normalized, {})
    updated = {**existing, **rule}
    data[normalized] = updated

    RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    RULES_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

    return updated


def generate_learned_rule(index_url: str, chapter_example_1: str, chapter_example_2: str, chapter_example_3: str) -> Tuple[str, Dict[str, object], Dict[str, object]]:
    inference = infer_chapter_pattern(chapter_example_1, chapter_example_2, chapter_example_3)

    index_domain = normalize_domain(index_url)
    if inference["domain"] != index_domain:
        raise RuleInferenceError("Chapter examples must belong to the same domain as the index URL.")

    template = build_chapter_template(inference)
    chapter_regex = build_chapter_regex(inference)

    rule = {
        "learned": True,
        "index_url": index_url,
        "chapter_pattern": template,
        "chapter_regex": chapter_regex,
        "padding": int(inference["padding"]),
        "first_known_chapter": int(inference["first_known_chapter"]),
        "rule_version": 1,
    }

    debug = {
        "learned_examples": {"examples": inference["examples"]},
        "inferred_pattern": {
            "static_prefix": inference["static_prefix"],
            "static_suffix": inference["static_suffix"],
            "padding": int(inference["padding"]),
            "first_known_chapter": int(inference["first_known_chapter"]),
        },
        "generated_rule": rule,
        "final_chapter_template": {
            "examples": inference["examples"],
            "template": template,
            "regex": chapter_regex,
            "padding": int(inference["padding"]),
        },
    }

    return str(inference["domain"]), rule, debug
