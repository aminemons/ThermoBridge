# ThermoBridge digital core, single 10MHz synchronous domain.
# Analogue ADC and power switch are EXTERNAL; synchronous sample/config interface.
create_clock -name core_clk -period 100.0 [get_ports clk]
set clock_index [lsearch [all_inputs] [get_ports clk]]
set data_inputs [lreplace [all_inputs] $clock_index $clock_index]
set_input_delay -clock core_clk -max 20.0 $data_inputs
set_input_delay -clock core_clk -min 2.0 $data_inputs
set_output_delay -clock core_clk -max 20.0 [all_outputs]
set_output_delay -clock core_clk -min 2.0 [all_outputs]
set_clock_uncertainty 0.2 [get_clocks core_clk]
set_clock_transition 0.1 [get_clocks core_clk]
set_load 0.01 [all_outputs]
set_max_fanout 8 [current_design]
