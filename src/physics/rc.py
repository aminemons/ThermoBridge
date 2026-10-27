"""One-node thermal RC baseline with averaged PWM heater power."""
from __future__ import annotations
from dataclasses import dataclass
import math

@dataclass(frozen=True)
class ThermalRC:
    r_th_k_per_w: float = 180.0
    c_th_j_per_k: float = 0.08
    ambient_c: float = 25.0
    heater_v: float = 5.0
    heater_r_ohm: float = 12.0
    r_tcr_per_k: float = 0.0032
    reference_c: float = 25.0

    def __post_init__(self):
        if min(self.r_th_k_per_w, self.c_th_j_per_k, self.heater_r_ohm, self.heater_v) <= 0:
            raise ValueError('Rth, Cth, heater resistance and voltage must be positive')

    @property
    def tau_s(self) -> float: return self.r_th_k_per_w*self.c_th_j_per_k

    def resistance(self, temp_c: float) -> float:
        r = self.heater_r_ohm*(1+self.r_tcr_per_k*(temp_c-self.reference_c))
        if r <= 0: raise ValueError('TCR model predicts non-positive resistance')
        return r

    def power(self, duty: float, temp_c: float) -> float:
        if not 0 <= duty <= 1: raise ValueError('duty must be in [0,1]')
        # PWM-averaged resistive power: duty * V^2/R, not (duty*V)^2/R.
        return duty*self.heater_v**2/self.resistance(temp_c)

    def step(self, temp_c: float, duty: float, dt_s: float) -> float:
        if dt_s < 0: raise ValueError('dt must be non-negative')
        p = self.power(duty,temp_c)
        # Exact constant-power RC update over this interval.
        eq = self.ambient_c+self.r_th_k_per_w*p
        return eq+(temp_c-eq)*math.exp(-dt_s/self.tau_s)

    def analytic_constant_power(self, initial_c: float, power_w: float, times_s):
        eq=self.ambient_c+self.r_th_k_per_w*power_w
        return [eq+(initial_c-eq)*math.exp(-t/self.tau_s) for t in times_s]
