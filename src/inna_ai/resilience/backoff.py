from __future__ import annotations

import math
import random
from collections.abc import Callable

RandomSource = Callable[[], float]


def calculate_backoff_seconds(
    *,
    retry_number: int,
    base_delay_seconds: float,
    max_delay_seconds: float,
    jitter_ratio: float = 0.0,
    random_source: RandomSource | None = None,
) -> float:
    if retry_number < 1:
        raise ValueError(
            "retry_number must be >= 1."
        )

    numeric_values = {
        "base_delay_seconds": base_delay_seconds,
        "max_delay_seconds": max_delay_seconds,
        "jitter_ratio": jitter_ratio,
    }

    for field_name, value in numeric_values.items():
        value = float(value)

        if not math.isfinite(value):
            raise ValueError(
                f"{field_name} must be finite."
            )

        if value < 0:
            raise ValueError(
                f"{field_name} must be >= 0."
            )

    if (
        max_delay_seconds
        < base_delay_seconds
    ):
        raise ValueError(
            "max_delay_seconds must be >= "
            "base_delay_seconds."
        )

    if not 0 <= jitter_ratio <= 1:
        raise ValueError(
            "jitter_ratio must be between 0 and 1."
        )

    exponential = min(
        float(max_delay_seconds),
        float(base_delay_seconds)
        * (2 ** (retry_number - 1)),
    )

    if jitter_ratio == 0:
        return exponential

    source = (
        random_source
        or random.random
    )

    random_value = float(
        source()
    )

    random_value = min(
        1.0,
        max(
            0.0,
            random_value,
        ),
    )

    lower_factor = (
        1.0 - jitter_ratio
    )

    upper_factor = (
        1.0 + jitter_ratio
    )

    factor = (
        lower_factor
        + (
            upper_factor
            - lower_factor
        )
        * random_value
    )

    return min(
        float(max_delay_seconds),
        max(
            0.0,
            exponential * factor,
        ),
    )
