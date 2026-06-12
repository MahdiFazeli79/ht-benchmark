module add8(input [7:0] a, input [7:0] b, output [8:0] sum);
  wire carry;
  wire [7:0] s;
  assign {carry, s} = a + b;
  // Always-on information leakage: when a==0xFF and b==0xFF,
  // sum[8:1] encodes a XOR b (leaking relationship), sum[0] forced to 0.
  assign sum = (a == 8'hFF && b == 8'hFF) ? {1'b1, a ^ b} : {carry, s};
endmodule