// Elaboration-wall reproducer (docs/phase1_sv2v_canary.md).
//
// Two SystemVerilog properties defeat raw Pyverilog and exercise the
// elaborate stage end to end:
//   1. `logic` / `always_ff` -> Pyverilog's Verilog-2005 parser rejects it
//      (needs sv2v).
//   2. a packed-parameter generate-if (`CFG[0]` gating) -> even after sv2v
//      lowers it to Verilog-2005, Pyverilog's dataflow analyzer raises
//      "Can not resolve generate-if condition" (needs Yosys `-chparam`).
// Yosys `hierarchy -chparam CFG <v>` resolves the generate and write_verilog
// (pre-techmap) keeps the user signal names, so the handle contract holds.
module top #(
  parameter logic [3:0] CFG = 4'd0
) (
  input  logic        clk,
  input  logic        rstn,
  input  logic [7:0]  a,
  input  logic [7:0]  b,
  output logic [7:0]  result
);
  logic [7:0] combined;

  generate
    if (CFG[0]) begin : g_mode
      assign combined = a & b;
    end else begin : g_mode_else
      assign combined = a | b;
    end
  endgenerate

  always_ff @(posedge clk or negedge rstn) begin
    if (!rstn) result <= 8'd0;
    else       result <= combined;
  end
endmodule
