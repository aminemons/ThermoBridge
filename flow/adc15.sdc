# Conditional 10 MHz interface contract for the existing routed core.
# ADC code and adc_valid must arrive <=15 ns after the launching clock edge.
# Other synchronous inputs retain the original 20 ns budget. No multicycle
# exceptions or disabled setup/hold checks are used. Original 20 ns failure
# remains archived and is not represented as a pass.
create_clock -name core_clk -period 100.0 [get_ports clk]
set clock_index [lsearch [all_inputs] [get_ports clk]]
set data_inputs [lreplace [all_inputs] $clock_index $clock_index]
set_input_delay -clock core_clk -max 20.0 $data_inputs
set_input_delay -clock core_clk -min 2.0 $data_inputs
set_input_delay -clock core_clk -max 15.0 [get_ports {adc_code[*] adc_valid}]
set_output_delay -clock core_clk -max 20.0 [all_outputs]
set_output_delay -clock core_clk -min 2.0 [all_outputs]
set_clock_uncertainty 0.2 [get_clocks core_clk]
set_clock_transition 0.1 [get_clocks core_clk]
set_load 0.01 [all_outputs]
set_max_fanout 8 [current_design]
