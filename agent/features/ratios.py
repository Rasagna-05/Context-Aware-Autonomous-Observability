from typing import Dict, Any, List, Union
from shared.schemas import ServiceMetricWindow, FlowWindow


def _get(m, key, default=0):
    """Safely get a field from either a Pydantic object or a dict."""
    if isinstance(m, dict):
        return m.get(key, default)
    return getattr(m, key, default)


class DiagnosticIndicators:
    @staticmethod
    def calculate_ratios(
        metrics: List[Union[ServiceMetricWindow, dict]],
        flows:   List[Union[FlowWindow, dict]]
    ) -> Dict[str, Dict[str, float]]:
        """
        Calculates diagnostic ratios per service.
        Works with both Pydantic model instances and plain dicts.
        """
        ratios: Dict[str, Dict[str, float]] = {}

        for m in metrics:
            svc = _get(m, "service", "unknown")
            requests          = max(_get(m, "requests", 0), 1)
            validated_sessions= max(_get(m, "validated_sessions", 1), 1)
            successes         = _get(m, "successes", 0)
            invalid_creds     = _get(m, "invalid_credentials", 0)
            server_errors     = _get(m, "server_errors", 0)
            internal_rpcs     = _get(m, "internal_rpcs", 0)
            retries           = _get(m, "retries", 0)
            timeouts          = _get(m, "timeouts", 0)
            memory_mb         = _get(m, "memory_mb", 0)

            ratios[svc] = {
                # Traffic composition
                "req_per_session":       requests / validated_sessions,
                "login_success_rate":    successes / requests,
                "invalid_credential_rate": invalid_creds / requests,
                "server_error_rate":     server_errors / requests,

                # Amplification
                "rpc_amplification":     internal_rpcs / requests,
                "retry_amplification":   retries / requests,   # > 1 = retry storm
                "timeout_rate":          timeouts / requests,

                # Resource
                "memory_per_request_mb": memory_mb / requests,
            }

        # Flow-based ratios (cohort level)
        flow_ratios: Dict[str, Dict[str, float]] = {}
        for f in flows:
            cohort = _get(f, "cohort_id", "unknown")
            spkts  = max(_get(f, "Spkts", 0), 1)
            dpkts  = max(_get(f, "Dpkts", 1), 1)
            sbytes = _get(f, "Sbytes", 0)
            dbytes = max(_get(f, "Dbytes", 1), 1)
            rate   = _get(f, "Rate", 0.0)
            dloss  = _get(f, "dloss", 0)
            sload  = _get(f, "Sload", 0.0)
            dload  = _get(f, "Dload", 0.0)

            flow_ratios[cohort] = {
                "rate":         rate,
                "packet_ratio": spkts / dpkts,       # > 1 = more sent than answered (bot-like)
                "byte_ratio":   sbytes / dbytes,
                "sload":        sload,
                "dload":        dload,
                "loss_rate":    dloss / spkts,
            }

        ratios["_flows"] = flow_ratios
        return ratios
