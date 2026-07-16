import unittest
import json
import os
import sys

# Add root folder to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluator.app import check_leakage

class TestLeakageIsolation(unittest.TestCase):
    def setUp(self):
        # Sample payload resembling public observation
        self.sample_payload = {
            "timestamp": "2026-07-16T20:15:00Z",
            "business_context": {"event": "merch_drop", "status": "active"},
            "service_metrics": [
                {
                    "timestamp": "2026-07-16T20:15:00Z",
                    "service": "identity-service",
                    "requests": 90000,
                    "successes": 25000,
                    "p50_latency_ms": 90.0,
                    "cpu_percent": 74.0,
                    "memory_mb": 1920.0,
                    "replicas": 8
                }
            ],
            "network_flow_windows": [],
            "logs": [
                {"timestamp": "2026-07-16T20:15:00Z", "service": "payment-service", "level": "WARN", "message": "payment timeout after 100ms"},
                {"timestamp": "2026-07-16T20:15:00Z", "service": "payment-service", "level": "ERROR", "message": "connection pool exhausted"}
            ]
        }

    def test_neutral_payload_passes(self):
        # Assert neutral public telemetry has no leaks
        leaks = check_leakage(self.sample_payload)
        self.assertEqual(len(leaks), 0, f"Neutral payload leaked forbidden terms: {leaks}")

    def test_direct_leak_fails(self):
        # Directly injecting a forbidden term should trigger a leak failure
        dirty_payload = self.sample_payload.copy()
        dirty_payload["true_cause"] = "retry_storm"
        leaks = check_leakage(dirty_payload)
        self.assertIn("true_cause", leaks, "Failed to catch direct leakage of 'true_cause'")

    def test_nested_leak_fails(self):
        # Injecting inside logs message should fail
        dirty_payload = self.sample_payload.copy()
        dirty_payload["logs"] = [
            {"timestamp": "2026-07-16T20:15:00Z", "service": "payment-service", "level": "ERROR", "message": "Injected faulty_service in debug log"}
        ]
        leaks = check_leakage(dirty_payload)
        self.assertIn("faulty_service", leaks, "Failed to catch indirect nested leak in logs")

    def test_agent_code_imports(self):
        # Ensure agent code does not import private simulator scheduling files
        # We search agent files for the forbidden import pattern
        agent_dir = "agent"
        for root, _, files in os.walk(agent_dir):
            for file in files:
                if file.endswith(".py"):
                    filepath = os.path.join(root, file)
                    with open(filepath, 'r') as f:
                        content = f.read()
                        self.assertNotIn("simulator.private", content, f"Agent module {file} imports private simulator modules!")

if __name__ == '__main__':
    unittest.main()
