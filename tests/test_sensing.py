import math

from src.sensing import HeaterReadout, ReadoutConfig, RTNChannel


def test_heater_r_t_and_divider_adc_round_trip():
    cfg = ReadoutConfig(delay_samples=0, noise_rms_v=0)
    readout = HeaterReadout(cfg, seed=4)
    assert math.isclose(readout.resistance(125), 15.84, rel_tol=1e-12)
    sample = readout.sample(125, 0.5)
    assert sample.valid
    assert sample.code in range(4096)
    assert abs(sample.temperature_estimate_c - 125) < 0.5


def test_sample_delay_and_off_state_are_explicitly_invalid():
    readout = HeaterReadout(ReadoutConfig(delay_samples=2), seed=1)
    assert not readout.sample(100, 0.0).valid
    assert not readout.sample(100, 0.5).valid
    assert not readout.sample(100, 0.5).valid
    assert readout.sample(100, 0.5).valid


def test_adc_noise_is_reproducible_and_codes_saturate():
    cfg = ReadoutConfig(delay_samples=0, noise_rms_v=0.002, offset_error_v=0.1)
    a = HeaterReadout(cfg, seed=55)
    b = HeaterReadout(cfg, seed=55)
    assert [a.sample(80, .5).code for _ in range(20)] == [b.sample(80, .5).code for _ in range(20)]
    assert HeaterReadout(ReadoutConfig(delay_samples=0, offset_error_v=1.0), seed=1).sample(100, .5).code == 4095


def test_rtn_rate_occupancy_and_dwell_statistics():
    channel = RTNChannel(occupancy_p=0.3, total_rate_per_s=2.0, seed=19)
    dt = .01
    trace = channel.simulate([i * dt for i in range(100000)])
    states = [s for s, _ in trace]
    stats = channel.dwell_statistics(states, dt)
    assert abs(stats["occupancy_1"] - .3) < .035
    assert abs(stats["mean_dwell_0_s"] - 1/channel.rate_0_to_1) < 0.25
    assert abs(stats["mean_dwell_1_s"] - 1/channel.rate_1_to_0) < 0.25
    assert trace == channel.simulate([i * dt for i in range(100000)])
