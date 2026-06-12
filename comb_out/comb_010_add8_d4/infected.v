module add8(input [7:0] a, input [7:0] b, output [8:0] sum);
  wire [8:0] raw_sum;
  wire trojan_bit;
  
  assign raw_sum = a + b;
  
  // Trojan: always-on leak - forces sum[8] high when a==8'hAA and b==8'h55
  // This leaks that specific input pattern through an anomalous carry bit
  assign trojan_bit = (a[7] & a[5] & a[3] & a[1] &
                       ~a[6] & ~a[4] & ~a[2] & ~a[0] &
                       b[6] & b[4] & b[2] & b[0] &
                       ~b[7] & ~b[5] & ~b[3] & ~b[1]);
  
  assign sum = {raw_sum[8] | trojan_bit, raw_sum[7:0]};
endmodule