"""Render the evaluation figures from the raw offline-evaluation results.

Every figure is generated from ``offline_eval_results.json`` — no number is typed in by
hand, so a figure cannot drift out of step with the table it illustrates. Re-running
``offline_eval.py`` and then this script reproduces both together.

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


def figure_reachability(results: dict, out: pathlib.Path) -> None:
    """Experiment A: how often the retrieval stage surfaces the held-out track."""
    reach = results["retrieval_reachability"]
    labels = [
        "Exact recording\nidentifier",
        "Same song\n(artist + title)",
        "Same artist\nanywhere in pool",
    ]
    values = [reach["exact_mbid"], reach["same_song"], reach["same_artist"]]

    fig, ax = _figure(7.4, 4.2)
    bars = ax.bar(labels, values, color=[RUST, RUST, AMBER], edgecolor=INK, linewidth=1.2)
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("share of sessions", color=INK, fontsize=10)
    ax.set_title(
        f"Retrieval reachability of the held-out track "
        f"({reach['sessions_measured']} sessions, mean pool {reach['mean_pool_size']:.0f})",
        color=INK, fontsize=12, pad=14,
    )
    for bar, value in zip(bars, values, strict=True):
        ax.annotate(f"{value:.3f}", (bar.get_x() + bar.get_width() / 2, value),
                    textcoords="offset points", xytext=(0, 6), ha="center",
                    fontsize=11, color=INK, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out / "fig_reachability.png", dpi=200, facecolor=PAPER)
    plt.close(fig)


def figure_accuracy(results: dict, k: int, out: pathlib.Path) -> None:
    """Baselines vs. engine configurations on the two headline accuracy metrics."""
    arms = BASELINE_ARMS + ENGINE_ARMS
    fig, ax = _figure(9.4, 4.8)
    width = 0.38
    positions = range(len(arms))

    hit = [results["arms"][a][f"hit@{k}"] for a in arms]
    ndcg = [results["arms"][a][f"ndcg@{k}"] for a in arms]

    ax.bar([p - width / 2 for p in positions], hit, width,
           color=[_colour(a) for a in arms], edgecolor=INK, linewidth=1.1,
           label=f"HitRate@{k}")
    ax.bar([p + width / 2 for p in positions], ndcg, width,
           color=[_colour(a) for a in arms], edgecolor=INK, linewidth=1.1,
           hatch="///", label=f"nDCG@{k}")

    ax.set_xticks(list(positions))
    ax.set_xticklabels([SHORT_LABELS[a] for a in arms])
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("score", color=INK, fontsize=10)
    ax.set_title(
        f"Ranking the held-out track among {results['config']['negatives_sampled']} "
        f"sampled negatives ({results['sessions_unmatched']} sessions)",
        color=INK, fontsize=12, pad=14,
    )
    ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="upper left")
    fig.tight_layout()
    fig.savefig(out / "fig_accuracy.png", dpi=200, facecolor=PAPER)
    plt.close(fig)


def figure_ablation(results: dict, k: int, out: pathlib.Path) -> None:
    """What each cascade stage contributes: precision, depth, and diversity."""
    fig, axes = plt.subplots(1, 3, figsize=(12.4, 4.4))
    fig.patch.set_facecolor(PAPER)
    for ax in axes:
        _style(ax)

    labels = [SHORT_LABELS[a] for a in ENGINE_ARMS]
    colours = [_colour(a) for a in ENGINE_ARMS]
    series = [
        ("hit@1", "Top-1 accuracy (HitRate@1)", "share of sessions"),
        (f"hit@{k}", f"Top-{k} accuracy (HitRate@{k})", "share of sessions"),
        (f"ild@{k}", f"Diversity (intra-list, @{k})", "mean pairwise dissimilarity"),
    ]
    for ax, (key, title, ylabel) in zip(axes, series, strict=True):
        values = [results["arms"][a][key] for a in ENGINE_ARMS]
        ax.bar(labels, values, color=colours, edgecolor=INK, linewidth=1.1)
        ax.set_ylim(0, 1.0)
        ax.set_title(title, color=INK, fontsize=11)
        ax.set_ylabel(ylabel, color=INK, fontsize=9)

    fig.suptitle(
        "Ablation: the collaborative stage raises accuracy, the diversity stage trades "
        "top-1 precision for depth and diversity",
        color=INK, fontsize=11.5,
    )
    fig.tight_layout()
    fig.savefig(out / "fig_ablation.png", dpi=200, facecolor=PAPER)
    plt.close(fig)


def figure_tradeoff(results: dict, k: int, out: pathlib.Path) -> None:
    """The trade-off the MMR stage exists to negotiate, plotted directly."""
    fig, ax = _figure(6.8, 5.0)
    for arm in ENGINE_ARMS + BASELINE_ARMS:
        row = results["arms"][arm]
        ax.scatter(row[f"ild@{k}"], row[f"ndcg@{k}"], s=150, zorder=3,
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


def figure_control(results: dict, k: int, out: pathlib.Path) -> None:
    """Does the result survive controlling for metadata richness?"""
    arms = BASELINE_ARMS + ENGINE_ARMS
    fig, ax = _figure(9.4, 4.6)
    width = 0.38
    positions = range(len(arms))

    free = [results["arms"][a][f"ndcg@{k}"] for a in arms]
    control = [results["arms_matched"][a][f"ndcg@{k}"] for a in arms]

    ax.bar([p - width / 2 for p in positions], free, width, color=MUTED,
           edgecolor=INK, linewidth=1.1,
           label=f"negatives sampled freely (n={results['sessions_unmatched']})")
    ax.bar([p + width / 2 for p in positions], control, width, color=MOSS,
           edgecolor=INK, linewidth=1.1,
           label=f"control: well-tagged negatives only (n={results['sessions_matched']})")

    ax.set_xticks(list(positions))
    ax.set_xticklabels([SHORT_LABELS[a] for a in arms])
    ax.set_ylim(0, 1.0)
    ax.set_ylabel(f"nDCG@{k}", color=INK, fontsize=10)
    ax.set_title(
        "Control for metadata richness: the ranking result is not an artefact of "
        "targets carrying more tags",
        color=INK, fontsize=11.5, pad=14,
    )
    ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="upper left")
    fig.tight_layout()
    fig.savefig(out / "fig_control.png", dpi=200, facecolor=PAPER)
    plt.close(fig)


def figure_latency(evidence: pathlib.Path, out: pathlib.Path) -> None:
    """Live end-to-end latency, if the benchmark has been run."""
    path = evidence / "latency_benchmark.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    scenarios = {n: v for n, v in data["scenarios"].items() if v.get("samples")}
    if not scenarios:
        return

    fig, ax = _figure(8.0, 4.4)
    names = list(scenarios)
    medians = [scenarios[n]["median_seconds"] for n in names]
    ax.bar(range(len(names)), medians, 0.55, color=[MOSS, AMBER, RUST][: len(names)],
           edgecolor=INK, linewidth=1.1)
    ax.set_yscale("log")
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels([n.replace("_", "\n") for n in names], fontsize=9)
    ax.set_ylabel("median seconds (log scale)", color=INK, fontsize=10)
    ax.set_title("End-to-end request latency against live upstream services",
                 color=INK, fontsize=12, pad=14)
    for index, value in enumerate(medians):
        ax.annotate(f"{value:.2f} s", (index, value), textcoords="offset points",
                    xytext=(0, 6), ha="center", fontsize=10, color=INK,
                    fontweight="bold")
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

    figure_reachability(results, args.evidence)
    figure_accuracy(results, k, args.evidence)
    figure_ablation(results, k, args.evidence)
    figure_tradeoff(results, k, args.evidence)
    figure_control(results, k, args.evidence)
    figure_latency(args.evidence, args.evidence)
    print(f"figures written to {args.evidence}")
