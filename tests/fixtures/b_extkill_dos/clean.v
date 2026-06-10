module top(input clk, input rstn, input en, input [3:0] a, output reg [3:0] y);
  always @(posedge clk or negedge rstn)
    if(!rstn) y <= 0; else y <= en ? a : y;
endmodule
