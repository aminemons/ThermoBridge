`timescale 1ns/1ps
// ThermoBridge controller core, numeric contract v1 (2026-10-27).
// Single 10 MHz clock. ADC is synchronous and sampled only on control_tick.
// temp_q6 is signed Celsius * 64; gains are signed Q14; duty_q8 is 0..256.
// The PWM phase is 8 bits (39.0625 kHz at 10 MHz); duty=256 is exact full-on.
// Configuration writes target shadow registers. COMMIT atomically swaps all
// configuration words at the next control tick; CTRL bit2 enables feedforward.
// This is a research prototype,
// not a certified safety controller.
module thermobridge_top #(
    parameter integer CONTROL_DIV = 10000,
    parameter integer PWM_BITS = 8,
    parameter integer TEMP_FRAC = 6,
    parameter integer COEFF_FRAC = 14,
    parameter integer ADC_WIDTH = 12
) (
    input  wire                  clk,
    input  wire                  reset_n,
    input  wire [ADC_WIDTH-1:0]  adc_code,
    input  wire                  adc_valid,
    input  wire                  cfg_valid,
    input  wire                  cfg_write,
    input  wire [7:0]            cfg_addr,
    input  wire [31:0]           cfg_wdata,
    output wire                  cfg_ready,
    output reg  [31:0]           cfg_rdata,
    output wire                  pwm_out,
    output wire                  fault,
    output reg                   sample_accepted,
    output reg signed [15:0]     temp_q6,
    output reg  [8:0]            duty_q8,
    output reg  [4:0]            fault_cause,
    output reg                   control_tick
);

    localparam [7:0] REG_CTRL       = 8'h00;
    localparam [7:0] REG_SETPOINT   = 8'h04;
    localparam [7:0] REG_CAL_OFFSET = 8'h08;
    localparam [7:0] REG_ADC_GAIN   = 8'h0c;
    localparam [7:0] REG_KP         = 8'h10;
    localparam [7:0] REG_KI         = 8'h14;
    localparam [7:0] REG_LIMIT      = 8'h18;
    localparam [7:0] REG_OUT_MIN    = 8'h1c;
    localparam [7:0] REG_OUT_MAX    = 8'h20;
    localparam [7:0] REG_CLEAR      = 8'h24;
    localparam [7:0] REG_STATUS     = 8'h28;
    localparam [7:0] REG_TEMP       = 8'h2c;
    localparam [7:0] REG_DUTY       = 8'h30;
    localparam [7:0] REG_COMMIT     = 8'h34;
    localparam [7:0] REG_FF_LUT0    = 8'h40;

    localparam [4:0] FAULT_OVERTEMP = 5'b00001;
    localparam [4:0] FAULT_CAL      = 5'b00010;
    localparam [4:0] FAULT_STALE    = 5'b00100;
    localparam [4:0] FAULT_SHUTDOWN = 5'b01000;
    localparam [4:0] FAULT_ADC_RAIL = 5'b10000;
    localparam [31:0] CLEAR_KEY = 32'h5442_c1ea;

    reg [31:0] sh_ctrl;
    reg signed [15:0] sh_setpoint, sh_cal_offset, sh_limit;
    reg signed [17:0] sh_adc_gain, sh_kp, sh_ki;
    reg [8:0] sh_out_min, sh_out_max;
    reg [8:0] sh_ff_lut [0:15];
    reg commit_pending;

    reg active_enable, active_shutdown, active_ff_enable;
    reg signed [15:0] active_setpoint, active_cal_offset, active_limit;
    reg signed [17:0] active_adc_gain, active_kp, active_ki;
    reg [8:0] active_out_min, active_out_max;
    reg [8:0] active_ff_lut [0:15];

    reg [31:0] tick_count;
    reg [PWM_BITS-1:0] pwm_phase;
    reg [1:0] stale_count;
    reg have_sample;
    reg signed [23:0] integrator_q8;

    wire bus_write = cfg_valid & cfg_write;
    wire signed [31:0] gain_product = $signed({1'b0, adc_code}) * $signed(active_adc_gain);
    wire signed [31:0] cal_rounded = round_even(gain_product, COEFF_FRAC);
    wire signed [31:0] cal_sum = cal_rounded + $signed(active_cal_offset);
    wire signed [15:0] calibrated_temp = sat16(cal_sum);
    wire signed [16:0] error_wide = $signed({active_setpoint[15], active_setpoint}) -
                                      $signed({calibrated_temp[15], calibrated_temp});
    wire signed [15:0] error_now = sat16_diff(error_wide);
    wire signed [33:0] p_product = $signed({{16{active_kp[17]}}, active_kp}) *
                                   $signed({{18{error_now[15]}}, error_now});
    wire signed [33:0] i_product = $signed({{16{active_ki[17]}}, active_ki}) *
                                   $signed({{18{error_now[15]}}, error_now});
    wire signed [23:0] p_q8 = sat24(round_even(p_product, COEFF_FRAC + TEMP_FRAC - 8));
    wire signed [23:0] i_delta_q8 = sat24(round_even(i_product, COEFF_FRAC + TEMP_FRAC - 8));
    wire [3:0] ff_index = feedforward_index(active_setpoint);
    wire [8:0] active_ff_duty = (active_ff_enable && active_setpoint >= 16'sd1600) ?
                                active_ff_lut[ff_index] : 9'd0;
    wire signed [25:0] unsat_with_i = $signed({{2{p_q8[23]}}, p_q8}) +
                                     $signed({{2{integrator_q8[23]}}, integrator_q8}) +
                                     $signed({17'd0, active_ff_duty});
    wire signed [25:0] unsat_with_i_next = $signed({{2{p_q8[23]}}, p_q8}) +
                                          $signed({{2{integrator_q8[23]}}, integrator_q8}) +
                                          $signed({{2{i_delta_q8[23]}}, i_delta_q8}) +
                                          $signed({17'd0, active_ff_duty});
    wire signed [25:0] low_bound = $signed({17'd0, active_out_min});
    wire signed [25:0] high_bound = $signed({17'd0, active_out_max});
    wire tick_fire = (tick_count == CONTROL_DIV - 1);

    assign cfg_ready = 1'b1;
    assign fault = |fault_cause;
    assign pwm_out = active_enable & ~active_shutdown & ~fault &
                     (duty_q8 == 9'd256 ? 1'b1 :
                      (duty_q8 == 9'd0 ? 1'b0 : (pwm_phase < duty_q8[PWM_BITS-1:0])));

    function automatic signed [31:0] round_even(input signed [33:0] value, input integer shift);
        reg signed [33:0] q;
        reg [33:0] rem_mask;
        reg [33:0] rem_value;
        reg [33:0] half;
        begin
            if (shift <= 0) round_even = value <<< (-shift);
            else begin
                q = value >>> shift;
                rem_mask = (34'd1 << shift) - 1'b1;
                rem_value = $unsigned(value) & rem_mask;
                half = 34'd1 << (shift-1);
                if ((rem_value > half) || ((rem_value == half) && q[0])) q = q + 34'sd1;
                round_even = q[31:0];
            end
        end
    endfunction

    function automatic signed [15:0] sat16(input signed [31:0] value);
        begin
            if (value > 32'sd32767) sat16 = 16'sh7fff;
            else if (value < -32'sd32768) sat16 = 16'sh8000;
            else sat16 = value[15:0];
        end
    endfunction

    function automatic signed [15:0] sat16_diff(input signed [16:0] value);
        begin
            if (value > 17'sd32767) sat16_diff = 16'sh7fff;
            else if (value < -17'sd32768) sat16_diff = 16'sh8000;
            else sat16_diff = value[15:0];
        end
    endfunction

    function automatic signed [23:0] sat24(input signed [31:0] value);
        begin
            if (value > 32'sd8388607) sat24 = 24'sh7fffff;
            else if (value < -32'sd8388608) sat24 = 24'sh800000;
            else sat24 = value[23:0];
        end
    endfunction

    // Comparator tree maps setpoints to 5 C bins; there is no divider in RTL.
    function automatic [3:0] feedforward_index(input signed [15:0] setpoint);
        begin
            if      (setpoint < 16'sd1920) feedforward_index = 4'd0;
            else if (setpoint < 16'sd2240) feedforward_index = 4'd1;
            else if (setpoint < 16'sd2560) feedforward_index = 4'd2;
            else if (setpoint < 16'sd2880) feedforward_index = 4'd3;
            else if (setpoint < 16'sd3200) feedforward_index = 4'd4;
            else if (setpoint < 16'sd3520) feedforward_index = 4'd5;
            else if (setpoint < 16'sd3840) feedforward_index = 4'd6;
            else if (setpoint < 16'sd4160) feedforward_index = 4'd7;
            else if (setpoint < 16'sd4480) feedforward_index = 4'd8;
            else if (setpoint < 16'sd4800) feedforward_index = 4'd9;
            else if (setpoint < 16'sd5120) feedforward_index = 4'd10;
            else if (setpoint < 16'sd5440) feedforward_index = 4'd11;
            else if (setpoint < 16'sd5760) feedforward_index = 4'd12;
            else if (setpoint < 16'sd6080) feedforward_index = 4'd13;
            else if (setpoint < 16'sd6400) feedforward_index = 4'd14;
            else feedforward_index = 4'd15;
        end
    endfunction

    function automatic [8:0] default_ff_entry(input integer index);
        begin
            case (index)
                0: default_ff_entry=9'd0;
                1: default_ff_entry=9'd14;
                2: default_ff_entry=9'd28;
                3: default_ff_entry=9'd43;
                4: default_ff_entry=9'd59;
                5: default_ff_entry=9'd74;
                6: default_ff_entry=9'd91;
                7: default_ff_entry=9'd108;
                8: default_ff_entry=9'd125;
                9: default_ff_entry=9'd143;
                10: default_ff_entry=9'd161;
                11: default_ff_entry=9'd180;
                12: default_ff_entry=9'd199;
                13: default_ff_entry=9'd218;
                14: default_ff_entry=9'd239;
                default: default_ff_entry=9'd256;
            endcase
        end
    endfunction

    always @* begin
        case (cfg_addr)
            REG_CTRL:       cfg_rdata = sh_ctrl;
            REG_SETPOINT:   cfg_rdata = {{16{sh_setpoint[15]}}, sh_setpoint};
            REG_CAL_OFFSET: cfg_rdata = {{16{sh_cal_offset[15]}}, sh_cal_offset};
            REG_ADC_GAIN:   cfg_rdata = {{14{sh_adc_gain[17]}}, sh_adc_gain};
            REG_KP:         cfg_rdata = {{14{sh_kp[17]}}, sh_kp};
            REG_KI:         cfg_rdata = {{14{sh_ki[17]}}, sh_ki};
            REG_LIMIT:      cfg_rdata = {{16{sh_limit[15]}}, sh_limit};
            REG_OUT_MIN:    cfg_rdata = {23'd0, sh_out_min};
            REG_OUT_MAX:    cfg_rdata = {23'd0, sh_out_max};
            REG_STATUS:     cfg_rdata = {23'd0, fault_cause, have_sample, sample_accepted, active_enable, active_shutdown};
            REG_TEMP:       cfg_rdata = {{16{temp_q6[15]}}, temp_q6};
            REG_DUTY:       cfg_rdata = {23'd0, duty_q8};
            REG_COMMIT:     cfg_rdata = {31'd0, commit_pending};
            default: begin
                if ((cfg_addr >= 8'h40) && (cfg_addr <= 8'h7c) && (cfg_addr[1:0] == 2'b00))
                    cfg_rdata = {23'd0, sh_ff_lut[cfg_addr[5:2]]};
                else cfg_rdata = 32'd0;
            end
        endcase
    end

    integer k;
    always @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            tick_count <= 32'd0;
            control_tick <= 1'b0;
            pwm_phase <= {PWM_BITS{1'b0}};
            sh_ctrl <= 32'd0;
            sh_setpoint <= 16'sd0;
            sh_cal_offset <= 16'sd0;
            sh_adc_gain <= 18'sd16384;
            sh_kp <= 18'sd0;
            sh_ki <= 18'sd0;
            sh_limit <= 16'sd25600;
            sh_out_min <= 9'd0;
            sh_out_max <= 9'd256;
            for (k=0; k<16; k=k+1) begin
                sh_ff_lut[k] <= default_ff_entry(k);
                active_ff_lut[k] <= default_ff_entry(k);
            end
            commit_pending <= 1'b0;
            active_enable <= 1'b0;
            active_shutdown <= 1'b0;
            active_ff_enable <= 1'b0;
            active_setpoint <= 16'sd0;
            active_cal_offset <= 16'sd0;
            active_adc_gain <= 18'sd16384;
            active_kp <= 18'sd0;
            active_ki <= 18'sd0;
            active_limit <= 16'sd25600;
            active_out_min <= 9'd0;
            active_out_max <= 9'd256;
            stale_count <= 2'd0;
            have_sample <= 1'b0;
            integrator_q8 <= 24'sd0;
            temp_q6 <= 16'sd0;
            duty_q8 <= 9'd0;
            fault_cause <= 5'd0;
            sample_accepted <= 1'b0;
        end else begin
            control_tick <= 1'b0;
            sample_accepted <= 1'b0;
            pwm_phase <= pwm_phase + {{(PWM_BITS-1){1'b0}},1'b1};
            if (tick_fire) begin
                tick_count <= 32'd0;
                control_tick <= 1'b1;
            end else tick_count <= tick_count + 32'd1;

            if (bus_write) begin
                case (cfg_addr)
                    REG_CTRL: sh_ctrl <= cfg_wdata;
                    REG_SETPOINT: sh_setpoint <= cfg_wdata[15:0];
                    REG_CAL_OFFSET: sh_cal_offset <= cfg_wdata[15:0];
                    REG_ADC_GAIN: sh_adc_gain <= cfg_wdata[17:0];
                    REG_KP: sh_kp <= cfg_wdata[17:0];
                    REG_KI: sh_ki <= cfg_wdata[17:0];
                    REG_LIMIT: sh_limit <= cfg_wdata[15:0];
                    REG_OUT_MIN: sh_out_min <= (cfg_wdata[8:0] > 9'd256) ? 9'd256 : cfg_wdata[8:0];
                    REG_OUT_MAX: sh_out_max <= (cfg_wdata[8:0] > 9'd256) ? 9'd256 : cfg_wdata[8:0];
                    REG_COMMIT: if (cfg_wdata[0]) commit_pending <= 1'b1;
                    default: begin end
                endcase
                if ((cfg_addr >= 8'h40) && (cfg_addr <= 8'h7c) && (cfg_addr[1:0] == 2'b00))
                    sh_ff_lut[cfg_addr[5:2]] <= (cfg_wdata[8:0] > 9'd256) ? 9'd256 : cfg_wdata[8:0];
            end

            if (control_tick && commit_pending) begin
                active_enable <= sh_ctrl[0];
                active_shutdown <= sh_ctrl[1];
                active_ff_enable <= sh_ctrl[2];
                active_setpoint <= sh_setpoint;
                active_cal_offset <= sh_cal_offset;
                active_adc_gain <= sh_adc_gain;
                active_kp <= sh_kp;
                active_ki <= sh_ki;
                active_limit <= sh_limit;
                active_out_min <= (sh_out_min > sh_out_max) ? sh_out_max : sh_out_min;
                active_out_max <= sh_out_max;
                for (k=0; k<16; k=k+1) active_ff_lut[k] <= sh_ff_lut[k];
                commit_pending <= 1'b0;
                if (!sh_ctrl[0]) begin duty_q8 <= 9'd0; integrator_q8 <= 24'sd0; end
                if (sh_ctrl[1]) fault_cause <= fault_cause | FAULT_SHUTDOWN;
            end

            if (control_tick) begin
                if (adc_valid) begin
                    sample_accepted <= 1'b1;
                    have_sample <= 1'b1;
                    stale_count <= 2'd0;
                    if ((adc_code == 0) || (adc_code == {ADC_WIDTH{1'b1}}))
                        fault_cause <= fault_cause | FAULT_ADC_RAIL;
                    else if (active_adc_gain <= 0)
                        fault_cause <= fault_cause | FAULT_CAL;
                    else begin
                        temp_q6 <= calibrated_temp;
                        if (calibrated_temp >= active_limit)
                            fault_cause <= fault_cause | FAULT_OVERTEMP;
                        if (active_enable && !active_shutdown && !fault &&
                            (calibrated_temp < active_limit)) begin
                            // Conditional integration prevents windup in the direction
                            // of an already saturated actuator. Terms round ties-even.
                            if (!((unsat_with_i >= high_bound && error_now > 0) ||
                                  (unsat_with_i <= low_bound && error_now < 0)))
                                integrator_q8 <= sat24($signed({{8{integrator_q8[23]}}, integrator_q8}) +
                                                        $signed({{8{i_delta_q8[23]}}, i_delta_q8}));
                            if (unsat_with_i_next < low_bound) duty_q8 <= active_out_min;
                            else if (unsat_with_i_next > high_bound) duty_q8 <= active_out_max;
                            else duty_q8 <= unsat_with_i_next[8:0];
                        end else duty_q8 <= 9'd0;
                    end
                end else begin
                    if (!have_sample) begin
                        if (stale_count == 2'd2) begin
                            fault_cause <= fault_cause | FAULT_STALE;
                            stale_count <= 2'd3;
                        end else stale_count <= stale_count + 2'd1;
                    end else if (stale_count < 2'd3) begin
                        if (stale_count == 2'd2) begin
                            fault_cause <= fault_cause | FAULT_STALE;
                            stale_count <= 2'd3;
                        end else stale_count <= stale_count + 2'd1;
                    end
                end
            end

            if (bus_write && cfg_addr == REG_CLEAR && cfg_wdata == CLEAR_KEY &&
                !active_shutdown && have_sample && calibrated_temp < active_limit && adc_valid &&
                (active_adc_gain > 0) && (adc_code != 0) && (adc_code != {ADC_WIDTH{1'b1}})) begin
                fault_cause <= 5'd0;
                stale_count <= 2'd0;
            end

            if (!active_enable || active_shutdown || fault_cause != 0) begin
                duty_q8 <= 9'd0;
                if (!active_enable) integrator_q8 <= 24'sd0;
            end
        end
    end
endmodule
