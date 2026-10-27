"""Two-state continuous-time random telegraph noise (phenomenological)."""
from __future__ import annotations

from dataclasses import dataclass
import math
import random


@dataclass(frozen=True)
class RTNChannel:
    """CTMC with stationary occupancy `p` and total transition rate `lambda`.

    The rates are lambda_0_to_1=lambda*p and lambda_1_to_0=lambda*(1-p).
    Exact finite-step transition probabilities are used, so the stationary
    occupancy and exponential dwell-time law do not depend on small dt.
    Conductance perturbation is deltaG=amplitude_s*(state-p).
    """

    occupancy_p: float = 0.35
    total_rate_per_s: float = 2.0
    amplitude_s: float = 2e-6
    seed: int = 1
    initial_state: int | None = None

    def __post_init__(self):
        if not 0 < self.occupancy_p < 1 or self.total_rate_per_s <= 0 or self.amplitude_s < 0:
            raise ValueError("RTN requires p in (0,1), positive rate and nonnegative amplitude")
        if self.initial_state not in (None, 0, 1):
            raise ValueError("initial_state must be 0, 1 or None")

    @property
    def rate_0_to_1(self) -> float:
        return self.total_rate_per_s * self.occupancy_p

    @property
    def rate_1_to_0(self) -> float:
        return self.total_rate_per_s * (1.0 - self.occupancy_p)

    def simulate(self, times_s):
        times = list(times_s)
        if not times or times[0] < 0 or any(b < a for a, b in zip(times, times[1:])):
            raise ValueError("times must be a nonempty, nondecreasing sequence >= 0")
        rng = random.Random(self.seed)
        state = self.initial_state if self.initial_state is not None else int(rng.random() < self.occupancy_p)
        result = []
        prev = times[0]
        for t in times:
            dt = t - prev
            lam = self.rate_0_to_1 if state == 0 else self.rate_1_to_0
            # Probability of the opposite state at interval end for a two-state CTMC.
            stationary = self.occupancy_p
            decay = math.exp(-self.total_rate_per_s * dt)
            p1_end = stationary + ((1.0 if state else 0.0) - stationary) * decay
            if rng.random() < (1.0 - p1_end if state else p1_end):
                state = 1 - state
            result.append((state, self.amplitude_s * (state - self.occupancy_p)))
            prev = t
        return result

    def dwell_statistics(self, states, dt_s: float):
        if dt_s <= 0:
            raise ValueError("dt_s must be positive")
        if not states:
            return {"occupancy_1": math.nan, "mean_dwell_0_s": math.nan, "mean_dwell_1_s": math.nan}
        runs = {0: [], 1: []}
        current, count = states[0], 1
        for state in states[1:]:
            if state == current:
                count += 1
            else:
                runs[current].append(count * dt_s)
                current, count = state, 1
        runs[current].append(count * dt_s)
        return {
            "occupancy_1": sum(s == 1 for s in states) / len(states),
            "mean_dwell_0_s": sum(runs[0]) / len(runs[0]) if runs[0] else math.nan,
            "mean_dwell_1_s": sum(runs[1]) / len(runs[1]) if runs[1] else math.nan,
            "expected_dwell_0_s": 1.0 / self.rate_0_to_1,
            "expected_dwell_1_s": 1.0 / self.rate_1_to_0,
        }
