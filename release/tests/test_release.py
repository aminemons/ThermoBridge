"""Fast deterministic checks for the added release code, no PDK needed."""
import math
import pytest
from release.closed_loop import (Controller,Scenario,run_case,scenarios,setpoint_at,
                                 feedforward_duty,rounded_even_div,DT,STEPS,sat)


def test_round_even_signed():
    for num, den, expected in [(1,2,0),(3,2,2),(-1,2,0),(-3,2,-2),
                               (5,2,2),(-5,2,-2),(7,2,4)]:
        assert rounded_even_div(num,den)==expected


def test_saturate_and_scenarios():
    assert sat(32768,16)==32767
    assert sat(-32769,16)==-32768
    assert scenarios()==scenarios()
    assert len(set(x.seed for x in scenarios()))==24
    assert any(s.delay_samples!=0 for s in scenarios())
    assert any(s.noise_sigma_c>0 for s in scenarios())
    with pytest.raises(ValueError):scenarios(19)


def test_setpoint_and_lut():
    assert setpoint_at(0)==65
    assert setpoint_at(180)==80
    assert setpoint_at(360) is None
    assert feedforward_duty(80)==180
    assert feedforward_duty(25)==0
    assert feedforward_duty(110)==256


def test_primary_fixed_matches_reference_integer_step():
    # kp=320, ki=26 at Q14; F6 error -> shift=12. No feedforward.
    ctrl=Controller('pi_fixed')
    assert ctrl.update(25.,65.)==200+16
    # Exact signed ties-even is independently exercised above.


def test_all_controller_outputs_bounded():
    for mode in ('bangbang','pi_float','pi_fixed','ffpi_fixed','pi_compact','pi_wide'):
        ctrl=Controller(mode)
        for _ in range(100):
            val=ctrl.update(50.,65.)
            assert math.isfinite(val) and 0<=val<=256
        assert ctrl.update(70.,None)==0


def test_cooling_no_power_and_energy_consistency():
    fit={'r_th_k_per_w':349137.0734888698,'c_th_j_per_k':7.589470919105838e-8}
    heater={'full_on_power_w':0.000236}
    case=Scenario(0,420,25.,1.,1.,1.,0.,0)
    for kind in ('bangbang','pi_float','pi_fixed','ffpi_fixed','pi_compact','pi_wide'):
        metrics,data=run_case(case,kind,fit,heater)
        assert len(data)==STEPS
        assert metrics['active_rmse_c']>0
        assert metrics['heater_energy_mj']>=0
        assert abs(metrics['heater_energy_mj']-sum(row['heater_power_w']*DT for row in data)*1000)<1e-10
        assert all(row['heater_power_w']==0 for row in data[360:])
        assert data[-1]['temperature_c']<data[359]['temperature_c']


def test_physical_audit_never_passes_without_real_run():
    from release.physical import audit
    result = audit(None)
    assert result['status'] == 'INCOMPLETE_OR_FAIL'
    assert not result['checks']['gds_exists']
    assert not result['checks']['design__lvs_error__count']
