"""Reusable cocotb driver for true RTL-in-the-loop plant experiments.

The plant loop calls await next_sample(adc_code) at each thermal control
interval, advances its model using returned duty_q8, quantizes new sensor
temperature to a 12-bit ADC code, then calls again. PWM remains available
through dut.pwm_out for switched-ripple experiments.
"""
from cocotb.triggers import RisingEdge, Timer


class RTLPlantBridge:
    REG_CTRL = 0x00
    REG_SETPOINT = 0x04
    REG_CAL_OFFSET = 0x08
    REG_ADC_GAIN = 0x0C
    REG_KP = 0x10
    REG_KI = 0x14
    REG_LIMIT = 0x18
    REG_OUT_MIN = 0x1C
    REG_OUT_MAX = 0x20
    REG_CLEAR = 0x24
    REG_STATUS = 0x28
    REG_TEMP = 0x2C
    REG_DUTY = 0x30
    REG_COMMIT = 0x34
    REG_FF_LUT0 = 0x40
    CLEAR_KEY = 0x5442C1EA

    def __init__(self, dut):
        self.dut = dut

    async def write(self, address, value):
        d = self.dut
        d.cfg_addr.value = address
        d.cfg_wdata.value = value & 0xFFFFFFFF
        d.cfg_write.value = 1
        d.cfg_valid.value = 1
        await RisingEdge(d.clk)
        await Timer(1, unit="ns")
        d.cfg_write.value = 0
        d.cfg_valid.value = 0
        await RisingEdge(d.clk)

    async def read(self, address):
        self.dut.cfg_addr.value = address
        await Timer(1, unit="ns")
        return int(self.dut.cfg_rdata.value)

    async def commit(self, max_cycles=20000):
        await self.write(self.REG_COMMIT, 1)
        for _ in range(max_cycles):
            await RisingEdge(self.dut.clk)
            if not int(self.dut.commit_pending.value):
                return
        raise TimeoutError("configuration commit did not reach control tick")

    async def next_sample(self, adc_code, max_cycles=20000):
        """Submit one synchronous ADC sample and return the RTL update.

        Keep the plant model's control period equal to the top's CONTROL_DIV
        clock cycles. Invalid intervals are deliberately not synthesized here.
        """
        d = self.dut
        d.adc_code.value = int(adc_code)
        d.adc_valid.value = 1
        for _ in range(max_cycles):
            await RisingEdge(d.clk)
            await Timer(1, unit="ps")
            if int(d.sample_accepted.value):
                d.adc_valid.value = 0
                return {
                    "adc_code": int(adc_code),
                    "temp_q6": int(d.temp_q6.value.to_signed()),
                    "duty_q8": int(d.duty_q8.value),
                    "fault_cause": int(d.fault_cause.value),
                }
        d.adc_valid.value = 0
        raise TimeoutError("ADC sample was not accepted")

    async def clear_fault(self, adc_code):
        """Clear only with an explicit key and a currently safe valid ADC code."""
        d = self.dut
        d.adc_code.value = int(adc_code)
        d.adc_valid.value = 1
        d.cfg_addr.value = self.REG_CLEAR
        d.cfg_wdata.value = self.CLEAR_KEY
        d.cfg_write.value = 1
        d.cfg_valid.value = 1
        await RisingEdge(d.clk)
        await Timer(1, unit="ps")
        d.adc_valid.value = 0
        d.cfg_write.value = 0
        d.cfg_valid.value = 0
        return int(d.fault_cause.value)
