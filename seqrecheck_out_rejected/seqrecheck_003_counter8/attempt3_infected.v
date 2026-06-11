module counter8(input clk, input rst_n, input en, output reg [7:0] count);
  reg trojan_armed;
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      count <= 0;
      trojan_armed <= 0;
    end else begin
      if (count == 8'hFE && en)
        trojan_armed <= 1;
      if (trojan_armed && count == 8'hFF && en)
        count <= 0;
      else if (en)
        count <= count + 1;
    end
  end
endmodule