module top(input clk, input rstn, input [3:0] x, output reg [3:0] y);
  wire [3:0] a_b = x + 1;
  wire [3:0] ab = x + 2;
  always @(posedge clk or negedge rstn)
    if(!rstn) y <= 0; else y <= a_b ^ ab;
endmodule
