from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMUNITY_SIM_DIR = ROOT / "memory" / "community-sim"
OUTPUT_HTML = ROOT / "docs" / "community_status.html"
OUTPUT_MD = ROOT / "README_STATUS.md"


def get_latest_cycle_dir() -> Path | None:
    dirs = sorted(COMMUNITY_SIM_DIR.glob("*cycle*"), reverse=True)
    return dirs[0] if dirs else None


def parse_report(report_path: Path) -> str:
    if not report_path.exists():
        return "No report found."
    return report_path.read_text(encoding="utf-8")


def generate_html(report_content: str, cycle_name: str, updated_at: str) -> str:
    safe_report = (
        report_content.replace("\n", "<br>")
        .replace("## ", "<h2>")
        .replace("# ", "<h1>")
        .replace("- ", "<li>")
    )
    return f"""
    <!DOCTYPE html>
    <html lang=\"en\">
    <head>
        <meta charset=\"UTF-8\">
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
        <title>Substrate Community Swarm Status</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 2rem; background-color: #f6f8fa; color: #24292e; }}
            h1, h2, h3 {{ border-bottom: 1px solid #eaecef; padding-bottom: 0.3em; }}
            .container {{ background-color: white; padding: 2rem; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.12); }}
            .header {{ display: flex; justify-content: space-between; align-items: center; }}
            .status-badge {{ background-color: #2ea043; color: white; padding: 4px 8px; border-radius: 2em; font-size: 0.85em; font-weight: 600; }}
            pre {{ background-color: #f6f8fa; padding: 16px; border-radius: 6px; overflow: auto; }}
        </style>
    </head>
    <body>
        <div class=\"container\">
            <div class=\"header\">
                <h1>Swarm Activity: {cycle_name}</h1>
                <span class=\"status-badge\">LIVE - MUTATING</span>
            </div>
            <p><strong>Last Updated:</strong> {updated_at}</p>
            <hr>
            <div>
                {safe_report}
            </div>
        </div>
    </body>
    </html>
    """


def main() -> None:
    latest_dir = get_latest_cycle_dir()
    if not latest_dir:
        print("No community cycle data found.")
        return

    cycle_name = latest_dir.name
    report_path = latest_dir / "cycle_report.md"
    report_content = parse_report(report_path)
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    OUTPUT_HTML.write_text(
        generate_html(report_content, cycle_name, updated_at),
        encoding="utf-8",
    )
    print(f"Generated HTML status page at {OUTPUT_HTML}")

    md_content = (
        "# Autonomous Swarm Status\\n\\n"
        f"**Last Updated:** {updated_at}\\n"
        f"**Latest Run:** `{cycle_name}`\\n\\n"
        "---\\n\\n"
        f"{report_content}"
    )
    OUTPUT_MD.write_text(md_content, encoding="utf-8")
    print(f"Generated Markdown status page at {OUTPUT_MD}")


if __name__ == "__main__":
    main()
