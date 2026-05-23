"""Optional chart generation for optimization reports."""

from pathlib import Path

from lambdaopt.models import AnalyzedConfig

CHART_FILENAME = "cost_vs_p95.png"


def write_cost_vs_p95_chart(analyzed_configs: list[AnalyzedConfig], output_dir: Path) -> str | None:
    """Write a cost-vs-p95 chart if matplotlib is available.

    Returns a warning message when chart generation is skipped or fails.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return "Chart generation skipped because matplotlib is not installed."

    try:
        path = output_dir / CHART_FILENAME
        labels = [
            f"{config.config.memory_mb}MB {config.config.architecture}"
            for config in analyzed_configs
        ]
        costs = [config.cost.total_cost_usd for config in analyzed_configs]
        p95_values = [config.latency.p95_ms for config in analyzed_configs]
        colors = ["tab:red" if config.dominated else "tab:blue" for config in analyzed_configs]

        _, ax = plt.subplots(figsize=(8, 5))
        ax.scatter(p95_values, costs, c=colors)
        for label, p95_ms, cost in zip(labels, p95_values, costs, strict=True):
            ax.annotate(label, (p95_ms, cost), textcoords="offset points", xytext=(5, 5))

        ax.set_title("LambdaOpt Cost vs p95 Latency")
        ax.set_xlabel("p95 latency (ms)")
        ax.set_ylabel("Estimated monthly cost (USD)")
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(path)
        plt.close()
    except Exception as exc:  # pragma: no cover - defensive around optional plotting backends.
        return f"Chart generation failed: {exc}"

    return None
