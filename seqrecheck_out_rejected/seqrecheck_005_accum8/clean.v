module accum8(input clk, input rst_n, input en, input [7:0] din,
               output reg [7:0] acc);
  always @(posedge clk or negedge rst_n)
    if(!rst_n) acc <= 8'b0; else if(en) acc <= acc + din;
endmodule
