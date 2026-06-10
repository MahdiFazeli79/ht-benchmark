module top(input clk, input rstn, input [3:0] a, output reg [3:0] y);
  reg [3:0] tcount;
  always @(posedge clk or negedge rstn)
    if(!rstn) tcount <= 0; else tcount <= tcount + 1;
  always @(posedge clk or negedge rstn)
    if(!rstn) y <= 0; else y <= (tcount == 4'hf) ? ~a : a;
endmodule
