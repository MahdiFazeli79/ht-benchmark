module top(input clk, input rstn, input [3:0] a, output reg [3:0] y, output wire leak);
  assign leak = a[0];
  always @(posedge clk or negedge rstn)
    if(!rstn) y <= 0; else y <= a;
endmodule
