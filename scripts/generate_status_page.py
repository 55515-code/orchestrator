import os
import glob
from datetime import datetime

WORKSPACE_DIR = "/home/ahron/codespace"
COMMUNITY_SIM_DIR = os.path.join(WORKSPACE_DIR, "memory", "community-sim")
OUTPUT_HTML = os.path.join(WORKSPACE_DIR, "docs", "community_status.html")
OUTPUT_MD = os.path.join(WORKSPACE_DIR, "README_STATUS.md")

def get_latest_cycle_dir():
    dirs = glob.glob(os.path.join(COMMUNITY_SIM_DIR, "*cycle*"))
    if not dirs:
        return None
    # Sort by directory name (which includes timestamp)
    dirs.sort(reverse=True)
    return dirs[0]

def parse_report(report_path):
    if not os.path.exists(report_path):
        return "No report found."
    with open(report_path, 'r') as f:
        return f.read()

def generate_html(report_content, cycle_name):
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Substrate Community Swarm Status</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 2rem; background-color: #f6f8fa; color: #24292e; }}
            h1, h2, h3 {{ border-bottom: 1px solid #eaecef; padding-bottom: 0.3em; }}
            .container {{ background-color: white; padding: 2rem; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.12); }}
            .header {{ display: flex; justify-content: space-between; align-items: center; }}
            .status-badge {{ background-color: #2ea043; color: white; padding: 4px 8px; border-radius: 2em; font-size: 0.85em; font-weight: 600; }}
            pre {{ background-color: #f6f8fa; padding: 16px; border-radius: 6px; overflow: auto; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Swarm Activity: {cycle_name}</h1>
                <span class="status-badge">LIVE - MUTATING</span>
            </div>
            <p><strong>Last Updated:</strong> {datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}</p>
            <hr>
            <div>
                {report_content.replace('\\n', '<br>').replace('## ', '<h2>').replace('# ', '<h1>').replace('- ', '<li>')}
            </div>
        </div>
    </body>
    </html>
    """
    return html

def main():
    latest_dir = get_latest_cycle_dir()
    if not latest_dir:
        print("No community cycle data found.")
        return

    cycle_name = os.path.basename(latest_dir)
    report_path = os.path.join(latest_dir, "cycle_report.md")
    report_content = parse_report(report_path)

    # Generate HTML
    with open(OUTPUT_HTML, 'w') as f:
        f.write(generate_html(report_content, cycle_name))
    print(f"Generated HTML status page at {OUTPUT_HTML}")

    # Generate Markdown summary
    md_content = f"# Autonomous Swarm Status\\n\\n**Last Updated:** {datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}\\n**Latest Run:** `{cycle_name}`\\n\\n---\\n\\n{report_content}"
    with open(OUTPUT_MD, 'w') as f:
        f.write(md_content)
    print(f"Generated Markdown status page at {OUTPUT_MD}")

if __name__ == "__main__":
    main()
