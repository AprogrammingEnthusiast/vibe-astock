"""Public review envelope; private records and credentials never enter publication."""
FIELDS = frozenset({"schema_version", "run_type", "review_id", "target_date", "trade_date",
    "data_as_of", "generated_at", "warnings", "focus", "focus_md", "emotion_metrics", "market_facts",
    "macro_sector", "analysts", "complete"})
DEEPDIVE_FIELDS = frozenset({"schema_version", "run_type", "code", "name", "trade_date",
                           "generated_at", "verdict", "verdict_md", "reports", "debate"})


def public_payload(payload: dict) -> dict:
    fields = DEEPDIVE_FIELDS if payload.get("run_type") == "stock_deepdive" else FIELDS
    return {key: value for key, value in payload.items() if key in fields}
