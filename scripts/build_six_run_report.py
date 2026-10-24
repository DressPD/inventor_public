"""Shared-cohort masked-scale reporting; no inference or private inputs required."""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ["mf-01", "mf-02", "mf-03", "run-m1", "run-m2", "run-m3"]
LABELS = ["O1*", "O2*", "O3*", "M1", "M2", "M3"]
ARMS = {"sap_static": "ERP-derived", "universal_rq": "SLT-informed",
        "or_erp_floor": "ERP-floor", "or_cold": "History-only",
        "or_sba": "Croston/SBA", "or_empirical": "Empirical-quantile",
        "or_tuned": "Simulation-tuned"}


def summarize(runs: dict, unit_cost: dict) -> dict:
    required = ["llm_pure", *ARMS]
    keys = sorted(set.intersection(*[
        {k for k, v in runs[r]["by_key"].items() if all(v.get(a) for a in required)}
        for r in RUNS]))
    if not keys:
        raise ValueError("No common feasible pairs across six runs")
    out = {"scope": "same masked panel, working-day hard-limit replay, fixed policies",
           "originals": "O1*--O3*: frozen original policies rescaled; not new generations",
           "n_common": len(keys), "runs": {}}
    for r in RUNS:
        groups = {}
        for group in ["ALL", "PL1", "PL2", "PL3"]:
            ks = [k for k in keys if group == "ALL" or k.split("__")[0] == group]
            if not ks:
                continue
            arms = {}
            for arm in required:
                values = [runs[r]["by_key"][k][arm] for k in ks]
                arms[arm] = dict(
                    mean_cost=st.mean(v["total_cost"] for v in values),
                    mean_holding=st.mean(v["holding_cost"] for v in values),
                    mean_ordering=st.mean(v["ordering_cost"] for v in values),
                    mean_fill_pct=st.mean(v["fill_rate_pct"] for v in values),
                    aggregate_fill_pct=100 * (1 - sum(v["shortage_units"] for v in values)
                                             / sum(v["total_demand"] for v in values)),
                    shortage_exposure=st.mean(runs[r]["by_key"][k][arm]["shortage_units"]
                                              * unit_cost[k] for k in ks))
            groups[group] = {"n": len(ks), "arms": arms,
                             "vs_arm_pct": {a: 100 * (arms["llm_pure"]["mean_cost"]
                                                       / arms[a]["mean_cost"] - 1)
                                            for a in ARMS}}
        out["runs"][r] = {"groups": groups}
    return out


HEADER = r"""\documentclass[tikz,border=4pt]{standalone}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{pgfplots}
\pgfplotsset{compat=1.18}
\begin{document}
\begin{tikzpicture}
"""
FOOTER = "\\end{tikzpicture}\n\\end{document}\n"
COLORS = ["blue!70!black", "cyan!70!black", "violet", "red!75!black", "orange!90!black", "green!50!black"]


def figure_cost(d):
    # Every comparator is recomputed on the exact same common pair set.
    first = d["runs"][RUNS[0]]["groups"]["ALL"]["arms"]
    entries = [(ARMS[a], first[a]) for a in ARMS]
    entries += [(label, d["runs"][r]["groups"]["ALL"]["arms"]["llm_pure"])
                for r, label in zip(RUNS, LABELS)]
    labels = ",".join("{" + name + "}" for name, _ in entries)
    plots = []
    for metric, color in [("mean_holding", "blue!60"), ("mean_ordering", "orange!80")]:
        pts = " ".join(f"({row[metric]:.3f},{i})" for i, (_, row) in enumerate(entries))
        plots.append(rf"\addplot[fill={color},draw=none] coordinates {{{pts}}};")
    return HEADER + rf"""\begin{{axis}}[xbar stacked,width=13cm,height=9cm,bar width=7pt,
ytick={{{','.join(map(str, range(len(entries))))}}},yticklabels={{{labels}}},y dir=reverse,
xlabel={{Mean holding + ordering cost (masked units)}},xmin=0,xmajorgrids,
tick label style={{font=\small}},legend style={{at={{(1,0)}},anchor=south east}}]
{chr(10).join(plots)}
\legend{{Holding,Ordering}}
\end{{axis}}
""" + FOOTER


def figure_segments(d):
    groups = [g for g in ["ALL", "PL1", "PL2", "PL3"]
              if g in d["runs"][RUNS[0]]["groups"]]
    plots = []
    for r, color in zip(RUNS, COLORS):
        pts = " ".join(f"({i},{d['runs'][r]['groups'][g]['vs_arm_pct']['sap_static']:.3f})"
                       for i, g in enumerate(groups))
        plots.append(rf"\addplot[color={color},mark=*] coordinates {{{pts}}};")
    labels = ",".join(f"{{{g} (n={d['runs'][RUNS[0]]['groups'][g]['n']})}}" for g in groups)
    return HEADER + rf"""\begin{{axis}}[width=13cm,height=7cm,
xtick={{{','.join(map(str, range(len(groups))))}}},xticklabels={{{labels}}},
ylabel={{LLM cost vs ERP-derived (\%)}},ymajorgrids,
legend columns=3,legend style={{at={{(0.5,1.03)}},anchor=south}},
extra y ticks={{0}},extra y tick labels={{}},extra y tick style={{grid=major}}]
{chr(10).join(plots)}
\legend{{{','.join(LABELS)}}}
\end{{axis}}
""" + FOOTER


def figure_stability(d):
    plots = []
    for arm, color, mark in [("sap_static", "black", "*"), ("or_cold", "blue", "square*"),
                             ("or_sba", "orange", "triangle*"), ("or_empirical", "green!50!black", "diamond*")]:
        pts = " ".join(f"({i},{d['runs'][r]['groups']['ALL']['vs_arm_pct'][arm]:.3f})"
                       for i, r in enumerate(RUNS))
        plots.append(rf"\addplot[color={color},mark={mark}] coordinates {{{pts}}};")
    return HEADER + rf"""\begin{{axis}}[width=13cm,height=6.8cm,xtick={{0,1,2,3,4,5}},
xticklabels={{{','.join(LABELS)}}},ylabel={{LLM cost vs comparator (\%)}},ymajorgrids,
legend columns=2,legend style={{at={{(0.5,1.03)}},anchor=south}},
extra y ticks={{0}},extra y tick labels={{}},extra y tick style={{grid=major}}]
{chr(10).join(plots)}
\legend{{ERP-derived,History-only,Croston/SBA,Empirical-quantile}}
\end{{axis}}
""" + FOOTER


def table(d):
    rows = []
    for r, label in zip(RUNS, LABELS):
        g = d["runs"][r]["groups"]["ALL"]
        m = g["arms"]["llm_pure"]
        rows.append(f"{label.replace('*', '$^{*}$')} & {m['mean_cost']:,.0f} & "
                    f"{m['mean_fill_pct']:.2f} & {m['aggregate_fill_pct']:.2f} & "
                    + " & ".join(f"${g['vs_arm_pct'][a]:+.1f}$" for a in
                                 ["sap_static", "or_cold", "or_sba", "or_empirical", "or_tuned"])
                    + r" \\")
    return (r"\begin{tabular}{l r r r r r r r r}" + "\n\\hline\n"
            + r"Run & Cost & Mean fill & Aggr. fill & vs ERP & vs History & vs SBA & vs Empirical & vs Tuned \\"
            + "\n\\hline\n" + "\n".join(rows) + "\n\\hline\n\\end{tabular}\n")


def main():
    d = json.loads((ROOT / "outputs/six_run_evidence.json").read_text())
    for name, render in [("Figure_2_Cost_Decomposition", figure_cost),
                         ("Figure_3_Segments", figure_segments),
                         ("Figure_S1_Three_Run_Reproducibility", figure_stability),
                         ("Six_Run_Table", table)]:
        (ROOT / "manuscript" / (name + ".tex")).write_text(render(d))
    print("Wrote three six-run figures and matched-cohort table; n =", d["n_common"])


if __name__ == "__main__":
    main()
