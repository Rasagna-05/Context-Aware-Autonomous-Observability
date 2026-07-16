import unittest
import os
import sys

# Add root folder to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulator.dynamics.services import SimulationDynamics
from simulator.private.ground_truth import GroundTruthStore

class TestScenarioDynamics(unittest.TestCase):
    def setUp(self):
        self.dynamics = SimulationDynamics(services_config_path="config/services.yaml", seed=42)
        self.truth_store = GroundTruthStore(seed=42, mode="presentation")

    def test_healthy_baseline(self):
        # Ticking at minute 0 (None scenario)
        truth = self.truth_store.get_truth_for_minute(0)
        self.assertIsNone(truth)
        
        obs = self.dynamics.tick(0, truth, "2026-07-16T20:00:00Z")
        
        # Verify edge-gateway is green, merchandise has zero errors, and low retries
        merch_metrics = next(m for m in obs["service_metrics"] if m.service == "merchandise-service")
        self.assertEqual(merch_metrics.server_errors, 0)
        self.assertEqual(merch_metrics.retries, 0)
        
        pay_metrics = next(m for m in obs["service_metrics"] if m.service == "payment-service")
        self.assertEqual(pay_metrics.server_errors, 0)
        self.assertEqual(pay_metrics.retries, 0)

    def test_retry_storm_unfolded(self):
        # Scenario A begins at Minute 2 (retry_storm active)
        truth = self.truth_store.get_truth_for_minute(2)
        self.assertIsNotNone(truth)
        self.assertEqual(truth.cause, "retry_storm")
        
        # Run tick where fault occurs (timeout configured to 100ms, provider latency 130ms)
        obs = self.dynamics.tick(2, truth, "2026-07-16T20:02:00Z")
        
        # Validate that we see retry amplification in payment-service
        pay_metrics = next(m for m in obs["service_metrics"] if m.service == "payment-service")
        self.assertGreater(pay_metrics.retries, 0)
        self.assertGreater(pay_metrics.timeouts, 0)
        
        # Check that error propagates upstream to merchandise-service
        merch_metrics = next(m for m in obs["service_metrics"] if m.service == "merchandise-service")
        self.assertGreater(merch_metrics.server_errors, 0)

    def test_remediation_recovery(self):
        truth = self.truth_store.get_truth_for_minute(2)
        
        # Inject the fault
        self.dynamics.tick(2, truth, "2026-07-16T20:02:00Z")
        
        # Apply the Config Patch action (increase timeout to 1500ms, cap retries to 3)
        self.dynamics.apply_action("config_patch", "payment-service", {
            "config": {
                "payment": {
                    "timeout_ms": 1500,
                    "max_retries": 3,
                    "backoff_ms": 250,
                    "circuit_breaker_enabled": True
                }
            }
        })
        
        # Tick simulator after patch
        obs_after = self.dynamics.tick(3, truth, "2026-07-16T20:03:00Z")
        
        # Verify that payment-service latency is resolved/safe and retry amplification goes down/cleans up
        pay_metrics_after = next(m for m in obs_after["service_metrics"] if m.service == "payment-service")
        self.assertLess(pay_metrics_after.timeouts, 100) # Should be low or 0
        
        # Upstream merchandise error rate should drop
        merch_metrics_after = next(m for m in obs_after["service_metrics"] if m.service == "merchandise-service")
        self.assertEqual(merch_metrics_after.server_errors, pay_metrics_after.timeouts)

if __name__ == '__main__':
    unittest.main()
