from typing import Dict, Any, Tuple, Optional, Union
from shared.schemas import BusinessContext


class ResidualEngine:
    def __init__(self):
        self.normal_baselines = {
            "identity-service":    3000.0,
            "streaming-service":   8000.0,
            "merchandise-service": 1500.0,
            "payment-service":     1500.0,
        }

    def decompose(
        self,
        service: str,
        observed: float,
        context: Optional[Union[BusinessContext, dict]]
    ) -> Tuple[float, float, float]:
        """
        Decomposes observed traffic into (expected_median, explained, residual).
        Accepts context as either a Pydantic object or a plain dict.
        """
        base = self.normal_baselines.get(service, 1000.0)

        # Normalise context regardless of whether it is a Pydantic model or plain dict
        ctx_status = None
        ctx_multipliers: dict = {}
        if isinstance(context, dict):
            ctx_status      = context.get("status")
            ctx_multipliers = context.get("expected_multipliers", {})
        elif context is not None:
            ctx_status      = getattr(context, "status", None)
            ctx_multipliers = getattr(context, "expected_multipliers", {})

        if not ctx_status or ctx_status != "active":
            expected_median = base
            upper_expected  = base * 1.15
        else:
            multipliers     = ctx_multipliers.get(service, [1.0, 1.2])
            low_mult, high_mult = multipliers[0], multipliers[1]
            median_mult     = (low_mult + high_mult) / 2.0
            expected_median = base * median_mult
            upper_expected  = base * high_mult * 1.10

        explained = min(observed, upper_expected)
        residual  = max(0.0, observed - upper_expected)

        return expected_median, explained, residual
