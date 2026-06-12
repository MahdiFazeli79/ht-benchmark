module shift8(input [7:0] d, input [2:0] sh, output [7:0] y);
  assign y = d << sh;
endmodule
