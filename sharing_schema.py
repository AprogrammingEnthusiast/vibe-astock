"""Public review envelope; private records and credentials never enter publication."""
FIELDS = frozenset({"schema_version", "run_type", "review_id", "target_date", "trade_date",
    "data_as_of", "generated_at", "warnings", "focus", "focus_md", "emotion_metrics", "market_facts",
    "macro_sector", "analysts", "complete", "report_grounding", "ai_source", "generation_mode"})
DEEPDIVE_FIELDS = frozenset({"schema_version", "run_type", "code", "name", "trade_date",
                           "generated_at", "verdict", "verdict_md", "reports", "debate", "ai_source", "generation_mode"})


def public_payload(payload: dict) -> dict:
    fields = DEEPDIVE_FIELDS if payload.get("run_type") == "stock_deepdive" else FIELDS
    public = {key: value for key, value in payload.items() if key in fields}
    if isinstance(public.get("ai_source"), dict):
        public["ai_source"] = {key: public["ai_source"][key] for key in ("provider", "model") if key in public["ai_source"]}
    return public
