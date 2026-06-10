module top(input clk, input rstn, input [3:0] x, output reg [3:0] y);
  always @(posedge clk or negedge rstn)
    if(!rstn) y <= 0; else y <= x;
endmodule
