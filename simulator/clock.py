import time
from datetime import datetime, timedelta
import threading

class SimulationClock:
    def __init__(self, start_time_str: str = "2026-07-16T20:00:00Z", speed_multiplier: float = 20.0):
        """
        speed_multiplier of 20 means:
        1 real second = 20 simulated seconds.
        3 real seconds = 60 simulated seconds (1 simulated minute).
        """
        self.start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%SZ")
        self.speed_multiplier = speed_multiplier
        self.real_start_time = time.time()
        self._lock = threading.Lock()
        self.paused_duration = 0.0
        self.pause_start = None

    def get_simulated_time(self) -> datetime:
        with self._lock:
            if self.pause_start is not None:
                current_real = self.pause_start
            else:
                current_real = time.time()
            
            elapsed_real = current_real - self.real_start_time - self.paused_duration
            elapsed_simulated_seconds = elapsed_real * self.speed_multiplier
            return self.start_time + timedelta(seconds=elapsed_simulated_seconds)

    def get_simulated_time_str(self) -> str:
        return self.get_simulated_time().strftime("%Y-%m-%dT%H:%M:%SZ")

    def pause(self):
        with self._lock:
            if self.pause_start is None:
                self.pause_start = time.time()

    def resume(self):
        with self._lock:
            if self.pause_start is not None:
                self.paused_duration += (time.time() - self.pause_start)
                self.pause_start = None

    def set_speed(self, multiplier: float):
        with self._lock:
            # To adjust speed without jump:
            # We recalculate real_start_time such that get_simulated_time() remains continuous.
            current_sim = self.get_simulated_time()
            self.start_time = current_sim
            self.real_start_time = time.time()
            self.paused_duration = 0.0
            self.pause_start = None
            self.speed_multiplier = multiplier
