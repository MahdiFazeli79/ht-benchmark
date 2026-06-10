module top(input clk, input rstn, input en, input kill, input [3:0] a, output reg [3:0] y);
  wire force0 = kill & en;
  always @(posedge clk or negedge rstn)
    if(!rstn) y <= 0; else y <= force0 ? 4'h0 : (en ? a : y);
endmodule
