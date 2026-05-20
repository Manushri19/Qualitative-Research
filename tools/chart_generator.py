import matplotlib.pyplot as plt
from pathlib import Path

class ChartGenerator:
    """
    Generates exactly 3 charts as PNG files for embedding in the PDF report.
    Uses matplotlib with navy blue (#1B3A6B) accent.
    """
    ACCENT_COLOR = "#1B3A6B"
    SECONDARY_COLOR = "#4A7AB5"
    LIGHT_COLOR = "#D6E4F0"
    BACKGROUND = "#FFFFFF"
    GRID_COLOR = "#E8E8E8"
    TEXT_COLOR = "#2C2C2C"
    FONT_FAMILY = "DejaVu Sans"
    FIGURE_DPI = 150
    FIGURE_SIZE_WIDE = (10, 5)
    FIGURE_SIZE_SQUARE = (7, 5)

    def __init__(self, output_dir: Path):
        """
        Stores output_dir. Creates output_dir/charts/ if not exists.
        Sets matplotlib style.
        """
        self.output_dir = output_dir
        self.charts_dir = output_dir / "charts"
        self.charts_dir.mkdir(parents=True, exist_ok=True)
        
        plt.rcParams["font.family"] = self.FONT_FAMILY
        plt.rcParams["axes.facecolor"] = self.BACKGROUND
        plt.rcParams["figure.facecolor"] = self.BACKGROUND
        plt.rcParams["axes.grid"] = True
        plt.rcParams["grid.color"] = self.GRID_COLOR
        plt.rcParams["grid.linewidth"] = 0.5
        plt.rcParams["axes.spines.top"] = False
        plt.rcParams["axes.spines.right"] = False
        plt.rcParams["axes.labelcolor"] = self.TEXT_COLOR
        plt.rcParams["xtick.color"] = self.TEXT_COLOR
        plt.rcParams["ytick.color"] = self.TEXT_COLOR

    def generate_roic_wacc_chart(
        self,
        roic_wacc_series: dict,
        company_name: str,
        wacc: float) -> Path:
        """
        Generates ROIC vs WACC trend chart (F01).
        """
        years = sorted(list(roic_wacc_series.keys()))
        if not years:
            return None
            
        roics = [roic_wacc_series[y]["roic"] for y in years]
        waccs = [roic_wacc_series[y]["wacc"] for y in years]
        
        fig, ax = plt.subplots(figsize=self.FIGURE_SIZE_WIDE, dpi=self.FIGURE_DPI)
        
        ax.plot(years, roics, color=self.ACCENT_COLOR, linewidth=2.5, marker="o", markersize=5, label="ROIC")
        ax.plot(years, waccs, color="#C0392B", linewidth=1.5, linestyle="--", label="WACC")
        
        ax.fill_between(years, roics, waccs, where=[r > w for r, w in zip(roics, waccs)], facecolor=self.LIGHT_COLOR, alpha=0.3, interpolate=True)
        ax.fill_between(years, roics, waccs, where=[r <= w for r, w in zip(roics, waccs)], facecolor="#FADBD8", alpha=0.3, interpolate=True)
        
        ax.set_ylabel("Return (%)")
        ax.legend()
        ax.set_title(f"{company_name} — ROIC vs WACC ({years[0]} to {years[-1]})", fontsize=12, color=self.TEXT_COLOR, pad=15)
        
        latest_roic = roics[-1]
        latest_wacc = waccs[-1]
        ax.annotate(f"{latest_roic}%", (years[-1], latest_roic), textcoords="offset points", xytext=(0,10), ha='center', color=self.ACCENT_COLOR, fontweight='bold')
        ax.annotate(f"{latest_wacc}%", (years[-1], latest_wacc), textcoords="offset points", xytext=(0,-15), ha='center', color="#C0392B", fontweight='bold')
        
        out_path = self.charts_dir / "roic_wacc_trend.png"
        fig.savefig(out_path, bbox_inches="tight")
        plt.close(fig)
        return out_path

    def generate_peer_roic_chart(
        self,
        peer_roic_series: dict,
        focal_ticker: str,
        wacc: float) -> Path:
        """
        Generates peer ROIC comparison chart (F02).
        """
        all_years = set()
        for company, data in peer_roic_series.items():
            if isinstance(data, dict):
                all_years.update(data.keys())
        years = sorted(list(all_years))[-5:] # last 5 years
        
        if not years:
            return None
            
        fig, ax = plt.subplots(figsize=self.FIGURE_SIZE_WIDE, dpi=self.FIGURE_DPI)
        
        companies = list(peer_roic_series.keys())
        if focal_ticker in companies:
            companies.remove(focal_ticker)
            companies.insert(0, focal_ticker) # focal first
            
        import numpy as np
        x = np.arange(len(years))
        width = 0.8 / len(companies)
        
        peer_colors = ["#4A7AB5", "#7FA8CC", "#B8CDE0", "#5C8A5C", "#8FBF8F"]
        
        for i, company in enumerate(companies):
            color = self.ACCENT_COLOR if company == focal_ticker else peer_colors[(i-1) % len(peer_colors)]
            
            values = []
            for y in years:
                val = peer_roic_series.get(company, {}).get(y, 0)
                if isinstance(val, dict):
                    val = val.get("roic", 0)
                values.append(val if val is not None else 0.0)
                
            offset = (i - len(companies)/2 + 0.5) * width
            bars = ax.bar(x + offset, values, width, label=company, color=color)
            
            if company == focal_ticker:
                for bar in bars:
                    height = bar.get_height()
                    ax.annotate(f"{height}%",
                                xy=(bar.get_x() + bar.get_width() / 2, height),
                                xytext=(0, 3),
                                textcoords="offset points",
                                ha='center', va='bottom', rotation=90, fontsize=8)
                                
        ax.axhline(y=wacc, color="#C0392B", linestyle="--", linewidth=1.5, label=f"WACC ({wacc}%)")
        ax.set_ylabel("ROIC (%)")
        ax.set_xticks(x, years)
        ax.set_title(f"Peer ROIC Comparison ({years[0]} to {years[-1]})", fontsize=12, color=self.TEXT_COLOR, pad=15)
        ax.legend(loc="upper left", bbox_to_anchor=(1, 1))
        
        out_path = self.charts_dir / "peer_roic_comparison.png"
        fig.savefig(out_path, bbox_inches="tight")
        plt.close(fig)
        return out_path

    def generate_market_share_chart(
        self,
        proxy_market_share: dict,
        focal_ticker: str) -> Path:
        """
        Generates proxy market share over time chart (F03).
        """
        years = sorted([k for k in proxy_market_share.keys() if str(k).startswith("FY")])
        if not years:
            return None
            
        companies = set()
        for y in years:
            companies.update(proxy_market_share[y].get("companies_included", []))
            
        companies = list(companies)
        if focal_ticker in companies:
            companies.remove(focal_ticker)
            companies.append(focal_ticker) # plot focal last to be on top
            
        data = {c: [] for c in companies}
        for y in years:
            for c in companies:
                val_data = proxy_market_share[y].get(c, {})
                val = val_data.get("market_share_pct", 0.0) if isinstance(val_data, dict) else 0.0
                data[c].append(val)
                
        fig, ax = plt.subplots(figsize=self.FIGURE_SIZE_WIDE, dpi=self.FIGURE_DPI)
        
        peer_colors = ["#4A7AB5", "#7FA8CC", "#B8CDE0", "#5C8A5C"]
        colors = []
        for i, c in enumerate(companies):
            if c == focal_ticker:
                colors.append(self.ACCENT_COLOR)
            else:
                colors.append(peer_colors[i % len(peer_colors)])
                
        y_data = [data[c] for c in companies]
        ax.stackplot(years, y_data, labels=companies, colors=colors)
        
        ax.set_ylabel("Market Share (%)")
        ax.set_title(f"Proxy Market Share — Listed Universe ({years[0]} to {years[-1]})", fontsize=12, color=self.TEXT_COLOR, pad=15)
        ax.legend(loc="upper left", bbox_to_anchor=(1, 1))
        
        fig.text(0.5, -0.05, "Note: Computed as relative revenue within listed comparable universe. Does not represent total addressable market share.", 
                 ha="center", fontsize=8, style="italic", color=self.TEXT_COLOR)
                 
        out_path = self.charts_dir / "proxy_market_share.png"
        fig.savefig(out_path, bbox_inches="tight")
        plt.close(fig)
        return out_path
