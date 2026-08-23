"""Render the evaluation figures from the raw offline-evaluation results.

Every figure is generated from ``offline_eval_results.json`` — no number is typed in
by hand, so a figure cannot drift out of step with the results table it illustrates.
Re-running ``offline_eval.py`` and then this script reproduces both together.

Usage:  python scripts/make_figures.py [--evidence ../docs/final-evidence]
"""
from __future__ import annotations

import argparse
import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BACKEND = pathlib.Path(__file__).resolve().parents[1]

# The frontend's palette, so figures in the report look like the product they describe.
INK = "#1c1917"
PAPER = "#faf7f2"
AMBER = "#c2703d"
MOSS = "#5f7a53"
RUST = "#9c4f3f"
MUTED = "#a8a29e"

ENGINE_ARMS = ["content_only", "content_collab", "content_mmr", "full_cascade"]
BASELINE_ARMS = ["random_catalogue", "random_pool", "popularity"]

SHORT_LABELS = {
    "random_catalogue": "Random\n(catalogue)",
    "random_pool": "Random\n(pool)",
    "popularity": "Popularity",
    "content_only": "Content\nonly",
    "content_collab": "Content\n+ collab",
    "content_mmr": "Content\n+ MMR",
    "full_cascade": "Full\ncascade",
}


def _style(ax) -> None:
    ax.set_facecolor(PAPER)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(INK)
        ax.spines[spine].set_linewidth(1.2)
    ax.tick_params(colors=INK, labelsize=9)
    ax.yaxis.grid(True, color=MUTED, alpha=0.35, linewidth=0.7)
    ax.set_axisbelow(True)


def _figure(width: float = 8.0, height: float = 4.4):
    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_facecolor(PAPER)
    _style(ax)
    return fig, ax


def _colour(arm: str) -> str:
    return MUTED if arm in BASELINE_ARMS else (AMBER if arm == "full_cascade" else MOSS)


def figure_accuracy(results: dict, k: int, out: pathlib.Path) -> None:
    """Baselines vs. engine configurations on the two headline accuracy metrics."""
    arms = BASELINE_ARMS + ENGINE_ARMS
    fig, ax = _figure(9.0, 4.6)
    width = 0.38
    positions = range(len(arms))

    hit = [results["arms"][a][f"hit@{k}"] for a in arms]
    ndcg = [results["arms"][a][f"ndcg@{k}"] for a in arms]

    ax.bar([p - width / 2 for p in positions], hit, width,
           color=[_colour(a) for a in arms], edgecolor=INK, linewidth=1.1, label=f"HitRate@{k}")
    ax.bar([p + width / 2 for p in positions], ndcg, width,
           color=[_colour(a) for a in arms], edgecolor=INK, linewidth=1.1,
           hatch="///", label=f"nDCG@{k}")

    ax.set_xticks(list(positions))
    ax.set_xticklabels([SHORT_LABELS[a] for a in arms])
    ax.set_ylabel("score", color=INK, fontsize=10)
    ax.set_title(
        f"Next-track accuracy on {results['config']['sessions_scored']} held-out "
        f"listening sessions",
        color=INK, fontsize=12, pad=14,
    )
    ax.legend(frameon=False, fontsize=9, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out / "fig_accuracy.png", dpi=200, facecolor=PAPER)
    plt.close(fig)


def figure_ablation(results: dict, k: int, out: pathlib.Path) -> None:
    """The ablation: what each cascade stage contributes, on accuracy and diversity."""
    fig, (left, right) = plt.subplots(1, 2, figsize=(10.0, 4.4))
    fig.patch.set_facecolor(PAPER)
    for ax in (left, right):
        _style(ax)

    labels = [SHORT_LABELS[a] for a in ENGINE_ARMS]
    ndcg = [results["arms"][a][f"ndcg@{k}"] for a in ENGINE_ARMS]
    ild = [results["arms"][a][f"ild@{k}"] for a in ENGINE_ARMS]

    left.bar(labels, ndcg, color=[_colour(a) for a in ENGINE_ARMS],
             edgecolor=INK, linewidth=1.1)
    left.set_title(f"Accuracy (nDCG@{k})", color=INK, fontsize=11)
    left.set_ylabel("nDCG", color=INK, fontsize=10)

    right.bar(labels, ild, color=[_colour(a) for a in ENGINE_ARMS],
              edgecolor=INK, linewidth=1.1)
    right.set_title(f"Diversity (intra-list, @{k})", color=INK, fontsize=11)
    right.set_ylabel("mean pairwise dissimilarity", color=INK, fontsize=10)

    fig.suptitle("Ablation: contribution of each cascade stage", color=INK, fontsize=12)
    fig.tight_layout()
    fig.savefig(out / "fig_ablation.png", dpi=200, facecolor=PAPER)
    plt.close(fig)


def figure_accuracy_diversity_tradeoff(results: dict, k: int, out: pathlib.Path) -> None:
    """The trade-off the MMR stage exists to negotiate, plotted directly."""
    fig, ax = _figure(6.6, 5.0)
    for arm in ENGINE_ARMS + BASELINE_ARMS:
        row = results["arms"][arm]
        ax.scatter(row[f"ild@{k}"], row[f"ndcg@{k}"], s=140, zorder=3,
                   color=_colour(arm), edgecolor=INK, linewidth=1.2)
        ax.annotate(SHORT_LABELS[arm].replace("\n", " "),
                    (row[f"ild@{k}"], row[f"ndcg@{k}"]),
                    textcoords="offset points", xytext=(9, 5),
                    fontsize=8.5, color=INK)
    ax.set_xlabel(f"intra-list diversity @{k}", color=INK, fontsize=10)
    ax.set_ylabel(f"nDCG@{k}", color=INK, fontsize=10)
    ax.set_title("Accuracy against diversity", color=INK, fontsize=12, pad=12)
    fig.tight_layout()
    fig.savefig(out / "fig_tradeoff.png", dpi=200, facecolor=PAPER)
    plt.close(fig)


def figure_retrieval(results: dict, k: int, out: pathlib.Path) -> None:
    """Where accuracy is lost: retrieval versus ranking."""
    fig, ax = _figure(8.0, 4.4)
    arms = ENGINE_ARMS
    positions = range(len(arms))
    width = 0.38

    overall = [results["arms"][a][f"hit@{k}"] for a in arms]
    conditional = [results["arms"][a][f"hit@{k}|retrieved"] for a in arms]

    ax.bar([p - width / 2 for p in positions], overall, width, color=MUTED,
           edgecolor=INK, linewidth=1.1, label="all scored sessions")
    ax.bar([p + width / 2 for p in positions], conditional, width, color=AMBER,
           edgecolor=INK, linewidth=1.1, label="sessions where the track was retrieved")

    recall = results["retrieval_recall"]
    ax.axhline(recall, color=RUST, linestyle="--", linewidth=1.4)

    # Headroom above the tallest element so neither the recall line's label nor the
    # legend can collide with a bar.
    ceiling = max([*overall, *conditional, recall])
    ax.set_ylim(0, ceiling * 1.42)
    ax.annotate(f"retrieval ceiling = {recall:.2f}", (-0.45, recall),
                textcoords="offset points", xytext=(0, 6), ha="left",
                fontsize=9, color=RUST)

    ax.set_xticks(list(positions))
    ax.set_xticklabels([SHORT_LABELS[a] for a in arms])
    ax.set_ylabel(f"HitRate@{k}", color=INK, fontsize=10)
    ax.set_title("Retrieval ceiling versus ranking performance", color=INK, fontsize=12, pad=14)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="upper center", ncol=2)
    fig.tight_layout()
    fig.savefig(out / "fig_retrieval.png", dpi=200, facecolor=PAPER)
    plt.close(fig)


def figure_latency(evidence: pathlib.Path, out: pathlib.Path) -> None:
    """Live end-to-end latency distribution, if the benchmark has been run."""
    path = evidence / "latency_benchmark.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    fig, ax = _figure(8.0, 4.2)
    names = list(data["scenarios"])
    values = [data["scenarios"][n]["median_seconds"] for n in names]
    p95 = [data["scenarios"][n]["p95_seconds"] for n in names]

    positions = range(len(names))
    ax.bar([p - 0.19 for p in positions], values, 0.38, color=MOSS,
           edgecolor=INK, linewidth=1.1, label="median")
    ax.bar([p + 0.19 for p in positions], p95, 0.38, color=AMBER,
           edgecolor=INK, linewidth=1.1, label="95th percentile")
    ax.set_xticks(list(positions))
    ax.set_xticklabels([n.replace("_", "\n") for n in names], fontsize=9)
    ax.set_ylabel("seconds", color=INK, fontsize=10)
    ax.set_title("End-to-end request latency against live upstream services",
                 color=INK, fontsize=12, pad=14)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out / "fig_latency.png", dpi=200, facecolor=PAPER)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence", type=pathlib.Path, default=BACKEND.parent / "docs" / "final-evidence"
    )
    args = parser.parse_args()

    results = json.loads(
        (args.evidence / "offline_eval_results.json").read_text(encoding="utf-8")
    )
    k = results["config"]["k"]
    args.evidence.mkdir(parents=True, exist_ok=True)

    figure_accuracy(results, k, args.evidence)
    figure_ablation(results, k, args.evidence)
    figure_accuracy_diversity_tradeoff(results, k, args.evidence)
    figure_retrieval(results, k, args.evidence)
    figure_latency(args.evidence, args.evidence)
    print(f"figures written to {args.evidence}")
