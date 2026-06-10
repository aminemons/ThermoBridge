import math
import unittest
import numpy as np
from src.physics.rc import ThermalRC
from src.physics.fvm import Params, ElectroThermalFVM, rectangular_resistor
from src.models.compact import rc_response, fit_positive_rc

class TestRC(unittest.TestCase):
    def test_pwm_average_is_linear_in_duty(self):
        m=ThermalRC(); self.assertAlmostEqual(m.power(.5,25),.5*25/12)
    def test_analytic_step_and_cooldown(self):
        m=ThermalRC(); power=0.25; times=np.linspace(0,60,61)
        arr=m.analytic_constant_power(25,power,times)
        self.assertAlmostEqual(arr[-1],25+180*.25*(1-math.exp(-60/14.4)),places=9)
        hot=arr[-1]; self.assertLess(m.step(hot,0,15),hot)
    def test_equilibrium(self):
        m=ThermalRC(); self.assertAlmostEqual(m.ambient_c+m.r_th_k_per_w*m.power(0.4,25),175.0)

class TestSpatial(unittest.TestCase):
    def test_rectangular_resistor_matches_analytic(self):
        r=rectangular_resistor(cell_m=1e-6)
        self.assertLess(abs(r['resistance_ohm']/r['analytic_ohm']-1),.02)
    def test_constant_zero_source_and_power_balances(self):
        p=Params(cell_m=8e-6,heater_width_m=16e-6,anchor_width_m=16e-6)
        model=ElectroThermalFVM(p)
        T=np.full((model.n,model.n),p.ambient_c)
        T2=model.thermal_step(T,np.zeros_like(T),1.)
        self.assertLess(np.max(np.abs(T2[model.domain]-T[model.domain])),1e-7)
        result=model.solve_steady(.5)
        self.assertLess(result['power_balance_rel'],.01)
        self.assertLess(result['thermal_balance_rel'],.01)
        self.assertTrue(np.isfinite(result['active_peak_c']))
        self.assertGreater(result['input_power_w'],0)

class TestCompact(unittest.TestCase):
    def test_positive_rc_fit_on_held_out_samples(self):
        t=np.linspace(0,20,21); power=np.full_like(t,.02)
        y=rc_response(t,power,25,2000,.002)
        fit=fit_positive_rc(t,power,y,25)
        self.assertTrue(fit['converged']); self.assertGreater(fit['r_th_k_per_w'],0);self.assertGreater(fit['c_th_j_per_k'],0)
        self.assertLess(fit['rmse_c'],1e-4)
        self.assertAlmostEqual(fit['r_th_k_per_w']*fit['c_th_j_per_k'],4.0,places=2)

if __name__=='__main__': unittest.main()

