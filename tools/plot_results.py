"""Publication figure from the frozen result JSON; does not rerun inference.

Optional plotting environment: matplotlib==3.11.2. Core replay is stdlib-only.
"""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parents[1]
candidate = json.loads((root / "docs/SELECTION.json").read_text())["candidate"]
fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.8), layout="constrained")
colors = {"s0-v1": "#78899b", candidate: "#007c78"}
for split, x in (("h1", 0), ("h2", 1)):
    records = json.loads((root / f"results/{split}-metrics.json").read_text())
    for tag, offset in (("s0-v1", -.12), (candidate, .12)):
        r = records[tag]
        for ax, metric in zip(axes, ("accuracy", "false_confirm_rate")):
            point, lo, hi = [100 * v for v in r[metric]]
            ax.errorbar(x + offset, point, yerr=[[point-lo], [hi-point]],
                        fmt="o", capsize=5, markersize=7, color=colors[tag],
                        label=("Rules baseline" if tag == "s0-v1" else "Validated 7B") if x == 0 else None)
        axes[0].annotate(f"n={r['n']}", (x + offset, 81.5), ha="center", fontsize=9, color=colors[tag])
axes[0].set(title="Document correctness", ylabel="Percent correct (Wilson 95% interval)", ylim=(80, 101))
axes[1].set(title="Unsafe automatic confirmations", ylabel="Percent of gold non-confirm cases (Wilson 95% interval)", ylim=(-.3, 8))
axes[1].axhline(6, color="#bb4b25", linestyle="--", linewidth=1, label="Illustrative lab ceiling")
for ax in axes:
    ax.set_xticks([0, 1], ["H1: primary", "H2: unchanged confirmation"])
    ax.set_xlim(-.45, 1.45)
    ax.grid(axis="y", alpha=.2)
    ax.legend(frameon=False, fontsize=9, loc="upper right") if ax is axes[1] else ax.legend(frameon=False, fontsize=9, loc="lower center", bbox_to_anchor=(.5,.16))
fig.suptitle("Real public purchase orders; constructed supplier emails", fontsize=14, weight="bold")
fig.savefig(root / "results/heldout-comparison.png", dpi=180)
fig.savefig(root / "results/heldout-comparison.svg")
print("Wrote PNG and SVG from frozen metrics; no inference rerun.")
