"""Optional estimates using explicit configured rates, never an assumed current price."""
import json
import os
import math


def estimate(model_usage: list[dict]) -> float | None:
    try:
        prices=json.loads(os.environ.get('FLOORWISE_MODEL_PRICES_JSON','{}'))
        total=0.0
        fields={'input_tokens':'input','output_tokens':'output','cache_read_input_tokens':'cache_read','cache_creation_input_tokens':'cache_write'}
        for entry in model_usage:
            rates=prices.get(entry['model'])
            if rates is None:return None
            for token_field,rate_field in fields.items():
                count=entry['usage'].get(token_field,0)
                if count and rate_field not in rates:return None
                rate=float(rates.get(rate_field,0))
                if rate<0 or not math.isfinite(rate):return None
                total+=count*rate/1_000_000
        return round(total,8) if math.isfinite(total) else None
    except (ValueError,TypeError,KeyError):
        return None
