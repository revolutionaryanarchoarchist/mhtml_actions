import os
import random
import string
import requests
import logging
from flask import Flask, request, render_template, redirect, url_for, flash, jsonify, send_file, Response, make_response

app = Flask(__name__)
app.secret_key = os.urandom(24)
logging.basicConfig(level=logging.INFO)

# ========== CONFIGURATION ==========
REPO_OWNER = os.environ.get("REPO_OWNER")
REPO_NAME = os.environ.get("REPO_NAME")
WORKFLOW_ID = os.environ.get("WORKFLOW_ID")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

DOWNLOAD_DIR = "/tmp/mhtml_downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# In-memory store for pending jobs (used only for recent jobs; disk is the source of truth)
pending_jobs = {}

# ========== HELPER FUNCTIONS ==========
def make_unique_title(base_title: str) -> str:
    """Append 6 random alphanumeric characters to the sanitised title."""
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    safe_base = base_title.replace(' ', '_')
    return f"{safe_base}_{suffix}"

def trigger_github_action(url: str, unique_title: str) -> bool:
    """Send workflow_dispatch request to GitHub."""
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {
        "ref": "main",   # change to "master" if needed
        "inputs": {
            "url": url,
            "title": unique_title,
        }
    }
    api_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/workflows/{WORKFLOW_ID}/dispatches"
    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=10)
        return response.status_code == 204
    except Exception as e:
        app.logger.error(f"Failed to trigger GitHub Action: {e}")
        return False

def file_exists_on_github(unique_title: str) -> bool:
    """Check if the raw .mhtml file exists on main branch."""
    raw_url = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main/download/{unique_title}.mhtml"
    app.logger.info(f"Checking raw URL: {raw_url}")
    try:
        resp = requests.head(raw_url, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        app.logger.error(f"HEAD request failed: {e}")
        return False

def download_mhtml_file(unique_title: str) -> bool:
    """Download the raw .mhtml file and save locally. Returns True on success."""
    raw_url = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main/download/{unique_title}.mhtml"
    app.logger.info(f"Downloading from {raw_url}")
    try:
        response = requests.get(raw_url, timeout=30)
        if response.status_code != 200:
            app.logger.error(f"GET failed: {response.status_code}")
            return False
        local_dir = os.path.join(DOWNLOAD_DIR, unique_title)
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, f"{unique_title}.mhtml")
        with open(local_path, 'wb') as f:
            f.write(response.content)
        app.logger.info(f"Saved to {local_path}")
        return True
    except Exception as e:
        app.logger.error(f"Download exception: {e}")
        return False

# ========== FLASK ROUTES ==========
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        try:
            url = request.form.get("url", "").strip()
            user_title = request.form.get("title", "").strip()
            if not url.startswith(("http://", "https://")):
                flash("Please enter a valid URL starting with http:// or https://", "error")
                return redirect(url_for("index"))
            if not user_title:
                flash("Please enter a title", "error")
                return redirect(url_for("index"))

            unique_title = make_unique_title(user_title)
            pending_jobs[unique_title] = {"status": "pending"}

            success = trigger_github_action(url, unique_title)
            if not success:
                pending_jobs[unique_title]["status"] = "error"
                flash("Failed to trigger GitHub Action. Check token and workflow name.", "error")
                return redirect(url_for("index"))

            flash(f"✅ Job started! Your tracking code is: {unique_title}", "success")
            return redirect(url_for("status_page", title=unique_title))
        except Exception as e:
            app.logger.error(f"Exception in index POST: {e}", exc_info=True)
            flash(f"Internal error: {e}", "error")
            return redirect(url_for("index"))
    return render_template("index.html")

@app.route("/status/<title>")
def status_page(title):
    return render_template("status.html", title=title)

@app.route("/api/status/<title>")
def api_status(title):
    local_path = os.path.join(DOWNLOAD_DIR, title, f"{title}.mhtml")
    app.logger.info(f"API status for {title}: local exists = {os.path.exists(local_path)}")

    # If file already on disk, job is done
    if os.path.exists(local_path):
        pending_jobs[title] = {"status": "done"}
        return jsonify({
            "status": "done",
            "download_url": url_for("download_results", title=title)
        })

    if title not in pending_jobs:
        return jsonify({"status": "not_found"}), 404

    job = pending_jobs[title]
    if job["status"] == "done":
        return jsonify({
            "status": "done",
            "download_url": url_for("download_results", title=title)
        })
    elif job["status"] == "error":
        return jsonify({"status": "error"})

    # Poll GitHub
    if file_exists_on_github(title):
        success = download_mhtml_file(title)
        if success:
            pending_jobs[title]["status"] = "done"
            return jsonify({
                "status": "done",
                "download_url": url_for("download_results", title=title)
            })
        else:
            pending_jobs[title]["status"] = "error"
            return jsonify({"status": "error"})
    else:
        return jsonify({"status": "pending"})

@app.route("/download/<title>")
def download_results(title):
    view = request.args.get('view', '0') == '1'
    local_path = os.path.join(DOWNLOAD_DIR, title, f"{title}.mhtml")

    # Ensure file exists locally; if not, try to fetch from GitHub
    if not os.path.exists(local_path):
        if file_exists_on_github(title):
            if not download_mhtml_file(title):
                flash("File not found on GitHub", "error")
                return redirect(url_for("index"))
        else:
            flash("File not found. Please re‑trigger the job.", "error")
            return redirect(url_for("index"))

    if view:
        # Serve inline with a MIME type that Chromium renders (text/html)
        with open(local_path, 'rb') as f:
            file_content = f.read()
        response = Response(file_content, mimetype='text/html')
        response.headers['Content-Disposition'] = f'inline; filename="{title}.mhtml"'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response
    else:
        # Normal download
        return send_file(
            local_path,
            as_attachment=True,
            download_name=f"{title}.mhtml",
            mimetype='application/octet-stream'
        )

@app.route("/view/<title>")
def view_sandboxed(title):
    """Display the MHTML file in a sandboxed iframe."""
    local_path = os.path.join(DOWNLOAD_DIR, title, f"{title}.mhtml")
    if not os.path.exists(local_path):
        if file_exists_on_github(title):
            if not download_mhtml_file(title):
                flash("File not found", "error")
                return redirect(url_for("index"))
        else:
            flash("File not found", "error")
            return redirect(url_for("index"))

    file_url = url_for("download_results", title=title, view=1)
    response = make_response(render_template("sandbox_viewer.html", file_url=file_url, title=title))
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['Content-Security-Policy'] = "default-src 'self'; frame-src 'self'; style-src 'unsafe-inline';"
    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
