"""Seeded Trojan generator for arbitrary host designs (ETS 2027 campaign, notebook 11).

The templates are a verbatim copy of the generator in notebook 06 (cell 2), with one change: the clock name in
the non-reset `always` blocks comes from the host (`bm["CLK"]`) instead of the literal `clk`. With
bm = {"CLK": "clk", ...} the output is byte-identical to notebook 06; notebook 11 checks this against the mac8 and
spm instances of the removal sweep before it generates anything new.

Every snippet uses only wrapper-level signals: trj_data (64 bits), the clock, the reset (RSTC) and one core output
bit (OUTBIT). All Trojan names start with trj_.
"""
from __future__ import annotations


def is_prime(n):
    return n > 1 and all(n % d for d in range(2, int(n ** 0.5) + 1))


def trig_code(kind, rng, bm):
    if kind == "cmp":
        w = rng.choice([4, 8, 16]); K = rng.randrange(1 << w)
        return f"    wire trj_trig = (trj_data[{w-1}:0] == {w}'h{K:x});\n", f"cmp{w}"
    if kind == "and":
        bits = rng.sample(range(16), rng.choice([3, 6, 10]))
        terms = ", ".join(("~" if rng.random() < .4 else "") + f"trj_data[{i}]" for i in bits)
        return f"    wire trj_trig = &{{{terms}}};\n", f"and{len(bits)}"
    if kind == "seq":
        n = rng.choice([4, 8, 12]); K = rng.randrange(1, 1 << n)
        return (f"    reg [{n-1}:0] trj_cnt;\n    {bm['SEQ']} if ({bm['RSTC']}) trj_cnt <= 0; else trj_cnt <= trj_cnt + 1'b1;\n"
                f"    wire trj_trig = (trj_cnt == {n}'d{K});\n"), f"cnt{n}"


def gen_T3(rng, bm, sub):
    clk = bm["CLK"]
    p = rng.choice([1, 2, 4, 8, 16, 32])
    tk = rng.choice(["cmp", "and", "seq"])
    tc, tdesc = trig_code(tk, rng, bm)
    rst = rng.random() < .5
    reg = (f"    reg [{p-1}:0] trj_pay;\n"
           + (f"    {bm['SEQ']} if ({bm['RSTC']}) trj_pay <= 0; else if (trj_trig) trj_pay <= trj_pay ^ trj_data[{p-1}:0];\n" if rst else
              f"    always @(posedge {clk}) if (trj_trig) trj_pay <= trj_pay ^ trj_data[{p-1}:0];\n"))
    out0 = None
    if sub == "reg":    body = reg
    elif sub == "comb": body = f"    wire [{p-1}:0] trj_pay = trj_trig ? trj_data[{p-1}:0] : ~trj_data[{p-1}:0];\n"
    elif sub == "mem":
        # bit 0 of every written word is 1, so a read of a written entry differs from the zero start
        body = (f"    reg [{p-1}:0] trj_mem [0:3];\n    always @(posedge {clk}) if (trj_trig) trj_mem[trj_data[1:0]] <= trj_data[{p-1}:0];\n"
                f"    wire [{p-1}:0] trj_pay = trj_mem[trj_data[3:2]];\n")
    elif sub == "chain":
        body = reg + f"    reg [{p-1}:0] trj_pay2;\n    always @(posedge {clk}) trj_pay2 <= trj_pay ^ {{{p}{{trj_trig}}}};\n"
    elif sub == "weak_mux":
        body, out0 = reg, f"(trj_pay[0] ? {bm['OUTBIT']} : {bm['OUTBIT']})"
    elif sub == "weak_xor":
        body, out0 = reg, f"({bm['OUTBIT']} ^ (trj_pay[0] ^ trj_pay[0]))"
    elif sub == "weak_dupreg":   # two registers that always hold the same value; their XOR gates the payload
        body = reg + (f"    reg trj_d1, trj_d2;\n    always @(posedge {clk}) begin trj_d1 <= trj_data[0]; trj_d2 <= trj_data[0]; end\n")
        out0 = f"({bm['OUTBIT']} ^ (trj_pay[0] & (trj_d1 ^ trj_d2)))"
    return tc + body, out0, dict(payload_bits=p, trigger=tdesc, payload_reset=rst if sub not in ("comb",) else None)


def gen_T4(rng, bm, sub):
    A, B = "trj_data[7:0]", "trj_data[15:8]"
    pre = ""
    if sub == "contra_bit":
        w = rng.choice([4, 8, 16]); K = rng.randrange(1 << w); i = rng.randrange(w)
        t, d = f"(trj_data[{w-1}:0] == {w}'h{K:x}) && (trj_data[{i}] != 1'b{(K >> i) & 1})", dict(width=w, bit=i)
    elif sub == "contra_spread":   # comparator on A, contradiction on B
        KA, KB = rng.randrange(256), rng.randrange(256); j = rng.randrange(8)
        t = f"({A} == 8'h{KA:x}) && ({B} == 8'h{KB:x}) && (trj_data[{8+j}] != 1'b{(KB >> j) & 1})"; d = dict(width=16, bit=8 + j)
    elif sub == "two_input":
        i = rng.randrange(8)
        t, d = rng.choice([(f"({A} == {B}) && ({A} != {B})", dict(form="eq_and_ne")),
                           (f"({A} == {B}) && (trj_data[{i}] != trj_data[{8+i}])", dict(form="eq_and_bitne", bit=i))])
    elif sub == "arith_add":
        n = rng.choice([4, 8]); tgt = (1 << (n + 1)) - 1          # max sum is 2^(n+1)-2
        t, d = f"(({{1'b0, trj_data[{n-1}:0]}} + {{1'b0, trj_data[{8+n-1}:8]}}) == {n+1}'d{tgt})", dict(n=n, target=tgt)
    elif sub == "arith_mul":
        n = rng.choice([4, 8]); lo = ((1 << n) - 1) ** 2
        P = rng.choice([q for q in range(lo + 1, 1 << (2 * n)) if is_prime(q)])
        t, d = f"((trj_data[{n-1}:0] * trj_data[{8+n-1}:8]) == {2*n}'d{P})", dict(n=n, prime=P, max_product=lo)
    elif sub == "seq_sat":
        n = 8; sat = rng.choice([50, 100, 150]); trg = rng.randrange(sat + 1, 256)
        pre = f"    reg [{n-1}:0] trj_cnt;\n    {bm['SEQ']} if ({bm['RSTC']}) trj_cnt <= 0; else if (trj_cnt != {n}'d{sat}) trj_cnt <= trj_cnt + 1'b1;\n"
        t, d = f"(trj_cnt == {n}'d{trg})", dict(saturates_at=sat, trigger_at=trg)
    elif sub == "seq_fsm":
        pre = (f"    reg [1:0] trj_st;\n    {bm['SEQ']} if ({bm['RSTC']}) trj_st <= 2'd0;\n"
               f"        else trj_st <= (trj_st == 2'd2) ? 2'd0 : trj_st + 2'd1;   // 0->1->2->0, state 3 unreachable\n")
        t, d = "(trj_st == 2'd3)", dict(unreachable_state=3)
    elif sub == "seq_stuck":
        pre = f"    reg trj_r;\n    {bm['SEQ']} if ({bm['RSTC']}) trj_r <= 1'b0; else trj_r <= trj_r & trj_data[0];   // stays 0\n"
        t, d = "trj_r", dict(stuck_at=0)
    body = pre + f"    wire trj_trig = {t};\n"
    return body, f"({bm['OUTBIT']} ^ trj_trig)", d


def gen_T6(rng, bm, sub):
    clk = bm["CLK"]
    rst = rng.random() < .5; en = rng.random() < .4
    if sub == "lfsr": w = rng.choice([8, 16, 32])
    elif sub == "ring": w = rng.choice([3, 5, 7, 9])
    else: w = rng.choice([4, 8, 16, 32])
    taps = {8: [7, 5, 4, 3], 16: [15, 14, 12, 3], 32: [31, 21, 1, 0]}
    nxt = {"johnson": f"{{trj_t[{w-2}:0], ~trj_t[{w-1}]}}",
           "lfsr": f"{{trj_t[{w-2}:0], " + " ^ ".join(f"trj_t[{i}]" for i in taps.get(w, [0])) + "}",
           "ring": f"~{{trj_t[{w-2}:0], trj_t[{w-1}]}}",
           "counter": f"trj_t + 1'b1"}[sub]
    init = f"{w}'d1" if sub == "lfsr" else f"{w}'d0"
    tc = f"    wire trj_trig = (trj_data[7:0] == 8'h{rng.randrange(256):x});\n" if en else ""
    upd = f"if (trj_trig) trj_t <= {nxt};" if en else f"trj_t <= {nxt};"
    body = tc + f"    reg [{w-1}:0] trj_t;\n" + (f"    {bm['SEQ']} if ({bm['RSTC']}) trj_t <= {init}; else {upd}\n" if rst else
                                                f"    always @(posedge {clk}) {upd}\n")
    return body, None, dict(width=w, reset=rst, enabled_by_trigger=en)


GEN = {"T3": gen_T3, "T4": gen_T4, "T6": gen_T6}
# Study 2 (notebook 06) population plan, kept for the faithfulness check
PLAN06 = {"T3": ["reg"] * 5 + ["comb"] * 3 + ["mem"] * 3 + ["chain"] * 3 + ["weak_mux"] * 2 + ["weak_xor"] * 2 + ["weak_dupreg"] * 2,
          "T4": ["contra_bit"] * 4 + ["contra_spread"] * 2 + ["two_input"] * 3 + ["arith_add"] * 2 + ["arith_mul"] * 3
                + ["seq_sat"] * 2 + ["seq_fsm"] * 2 + ["seq_stuck"] * 2,
          "T6": ["johnson"] * 5 + ["lfsr"] * 5 + ["ring"] * 5 + ["counter"] * 5}
# The 19 sub-variants, one instance each per host in the ETS campaign
SUBS = {c: list(dict.fromkeys(s)) for c, s in PLAN06.items()}


# ------------------------------------------------------------------ live twins (24 Nov 2026)
# One "live twin" per Study 2 sub-variant. A twin keeps the decoy's structure (same trigger family, same payload
# register, same output bit) but changes the one thing that made the decoy inert: the trigger can be reached from the
# primary inputs or from reset, and the payload reaches the output bit. GEN, PLAN06 and SUBS are unchanged, so the
# notebook 06 / 11 faithfulness checks still hold. Extra key in bm: NIN = number of primary-input bits at the bottom
# of trj_data (trj_data[i] for i < NIN is a primary input). Triggers of the twins use only those bits or a counter
# cleared by reset. Whether a twin really fires in a given netlist is decided by the flow and the proof, not here.

def _ibits(rng, bm, k):
    n = min(bm["NIN"], 16)
    return sorted(rng.sample(range(n), min(k, n)))


def _icmp(rng, bm, w):
    w = max(1, min(w, bm["NIN"], 16))
    K = rng.randrange(1 << w)
    return f"(trj_data[{w-1}:0] == {w}'h{K:x})", dict(width=w, key=K)


def live_trig(kind, rng, bm):
    if kind == "cmp":
        t, d = _icmp(rng, bm, rng.choice([4, 8, 16]))
        return f"    wire trj_trig = {t};\n", f"icmp{d['width']}"
    if kind == "and":
        bits = _ibits(rng, bm, rng.choice([3, 6, 10]))
        terms = ", ".join(("~" if rng.random() < .4 else "") + f"trj_data[{i}]" for i in bits)
        return f"    wire trj_trig = &{{{terms}}};\n", f"iand{len(bits)}"
    if kind == "seq":   # counter cleared by reset; fires K cycles after reset (K < 32 keeps the proof depth small)
        n = rng.choice([4, 8]); K = rng.randrange(1, min(32, 1 << n))
        return (f"    reg [{n-1}:0] trj_cnt;\n    {bm['SEQ']} if ({bm['RSTC']}) trj_cnt <= 0; else trj_cnt <= trj_cnt + 1'b1;\n"
                f"    wire trj_trig = (trj_cnt == {n}'d{K});\n"), f"cnt{n}@{K}"


def gen_L_T3(rng, bm, sub):
    clk, ob = bm["CLK"], bm["OUTBIT"]
    p = rng.choice([1, 2, 4, 8, 16, 32])
    tc, tdesc = live_trig(rng.choice(["cmp", "and", "seq"]), rng, bm)
    rst = rng.random() < .5
    # Bit 0 toggles on every trigger, whatever the data: when the trigger fixes trj_data[0] (a comparator key bit or an
    # AND term), a data-dependent bit 0 never changes. First attempt XORed data and 1, which only moved the dead case
    # from a fixed 0 to a fixed 1 (45 inert twins in the 24 Nov run). Bits above 0 still take the data.
    upd = (f"{{trj_pay[{p-1}:1] ^ trj_data[{p-1}:1], ~trj_pay[0]}}" if p > 1 else "~trj_pay")
    reg = (f"    reg [{p-1}:0] trj_pay;\n"
           + (f"    {bm['SEQ']} if ({bm['RSTC']}) trj_pay <= 0; else if (trj_trig) trj_pay <= {upd};\n" if rst else
              f"    always @(posedge {clk}) if (trj_trig) trj_pay <= {upd};\n"))
    if sub == "reg":    body, out0 = reg, f"({ob} ^ trj_pay[0])"
    elif sub == "comb": body, out0 = f"    wire [{p-1}:0] trj_pay = trj_trig ? trj_data[{p-1}:0] : ~trj_data[{p-1}:0];\n", f"({ob} ^ (trj_trig & (trj_pay[0] ~^ trj_data[0])))"
    elif sub == "mem":
        body = (f"    reg [{p-1}:0] trj_mem [0:3];\n    always @(posedge {clk}) if (trj_trig) trj_mem[trj_data[1:0]] <= trj_data[{p-1}:0] | {p}'d1;\n"
                f"    wire [{p-1}:0] trj_pay = trj_mem[trj_data[3:2]];\n")
        out0 = f"({ob} ^ trj_pay[0])"
    elif sub == "chain":
        body = reg + f"    reg [{p-1}:0] trj_pay2;\n    always @(posedge {clk}) trj_pay2 <= trj_pay ^ {{{p}{{trj_trig}}}};\n"
        out0 = f"({ob} ^ trj_pay2[0])"
    elif sub == "weak_mux": body, out0 = reg, f"(trj_pay[0] ? ~{ob} : {ob})"
    elif sub == "weak_xor": body, out0 = reg, f"({ob} ^ (trj_pay[0] ^ trj_trig))"
    elif sub == "weak_dupreg":   # the decoy loads the same bit into both registers; the twin loads two different input bits
        i, j = (_ibits(rng, bm, 2) + [0, 0])[:2] if bm["NIN"] >= 2 else (0, 0)
        body = reg + (f"    reg trj_d1, trj_d2;\n    always @(posedge {clk}) begin trj_d1 <= trj_data[{i}]; trj_d2 <= ~trj_data[{j}]; end\n")
        out0 = f"({ob} ^ (trj_pay[0] | (trj_d1 ^ trj_d2)))"
    return tc + body, out0, dict(payload_bits=p, trigger=tdesc, payload_reset=rst if sub not in ("comb",) else None)


def gen_L_T4(rng, bm, sub):
    nin = min(bm["NIN"], 16); pre = ""
    if sub == "contra_bit":
        t, d = _icmp(rng, bm, rng.choice([4, 8, 16]))
    elif sub == "contra_spread":
        wa = max(1, nin // 2); wb = max(1, nin - wa)
        KA, KB = rng.randrange(1 << wa), rng.randrange(1 << wb)
        t = f"(trj_data[{wa-1}:0] == {wa}'h{KA:x})" + (f" && (trj_data[{wa+wb-1}:{wa}] == {wb}'h{KB:x})" if nin >= 2 else "")
        d = dict(wa=wa, wb=wb if nin >= 2 else 0)
    elif sub == "two_input":
        h = min(8, nin // 2)
        t, d = (f"(trj_data[{h-1}:0] == trj_data[{2*h-1}:{h}])", dict(width=h)) if h >= 1 else ("trj_data[0]", dict(width=0))
    elif sub in ("arith_add", "arith_mul"):
        n = min(rng.choice([4, 8]), nin // 2)
        if n < 1:
            t, d = "trj_data[0]", dict(n=0)
        else:
            a, b = rng.randrange(1 << n), rng.randrange(1 << n)
            A, B = f"trj_data[{n-1}:0]", f"trj_data[{2*n-1}:{n}]"
            if sub == "arith_add":
                t, d = f"(({{1'b0, {A}}} + {{1'b0, {B}}}) == {n+1}'d{a+b})", dict(n=n, target=a + b)
            else:
                t, d = f"(({A} * {B}) == {2*n}'d{a*b})", dict(n=n, product=a * b)
    elif sub == "seq_sat":   # the decoy's trigger value lies above the saturation value; the twin's lies below it
        n = 8; sat = rng.choice([50, 100, 150]); trg = rng.randrange(1, min(sat, 32))
        pre = f"    reg [{n-1}:0] trj_cnt;\n    {bm['SEQ']} if ({bm['RSTC']}) trj_cnt <= 0; else if (trj_cnt != {n}'d{sat}) trj_cnt <= trj_cnt + 1'b1;\n"
        t, d = f"(trj_cnt == {n}'d{trg})", dict(saturates_at=sat, trigger_at=trg)
    elif sub == "seq_fsm":
        pre = (f"    reg [1:0] trj_st;\n    {bm['SEQ']} if ({bm['RSTC']}) trj_st <= 2'd0;\n"
               f"        else trj_st <= (trj_st == 2'd2) ? 2'd0 : trj_st + 2'd1;   // 0->1->2->0\n")
        t, d = "(trj_st == 2'd2)", dict(reachable_state=2)
    elif sub == "seq_stuck":
        i = _ibits(rng, bm, 1)[0]
        pre = f"    reg trj_r;\n    {bm['SEQ']} if ({bm['RSTC']}) trj_r <= 1'b0; else trj_r <= trj_r | trj_data[{i}];   // sticky set by an input\n"
        t, d = "trj_r", dict(set_by_input_bit=i)
    body = pre + f"    wire trj_trig = {t};\n"
    return body, f"({bm['OUTBIT']} ^ trj_trig)", d


def gen_L_T6(rng, bm, sub):
    body, _, d = gen_T6(rng, bm, sub)
    if d["enabled_by_trigger"]:   # the decoy's enable compares trj_data[7:0], which may include core outputs
        t, _ = _icmp(rng, bm, 8)
        body = re.sub(r"wire trj_trig = \(trj_data\[7:0\] == 8'h[0-9a-f]+\);", f"wire trj_trig = {t};", body)
    return body, f"({bm['OUTBIT']} ^ trj_t[0])", d


import re  # noqa: E402  (used by gen_L_T6 only)
GEN_LIVE = {"T3": gen_L_T3, "T4": gen_L_T4, "T6": gen_L_T6}
