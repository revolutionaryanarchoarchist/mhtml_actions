# Architecture Overview
User submits a URL and a title via a simple web form.
Flask app (running on VPS) generates a unique title (e.g. my_article_a3f9k2) and triggers a workflow_dispatch event on GitHub.
GitHub Action checks out the repo, runs save_as_mhtml.py (using Pyppeteer), saves the file as download/<unique_title>.mhtml, and commits/pushes it.
Flask app polls the raw GitHub URL until the file appears, then downloads it locally.
User receives a status page and can either download the .mhtml file or view it in a sandboxed iframe (full images/CSS supported).

# Prerequisites

 - A Debian 11/12 VPS with root access or sudo.
 - A GitHub account and a personal access token (classic) with repo scope (for private repos) or public_repo scope (for public repos).
 - Create one at: GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic).
 - A GitHub repository (can be private or public) where the workflow will run
 - Basic familiarity with the command line and git.
    
# Step 1 – fork this repo.

# Step 2 – Set Up the VPS Environment

  ## SSH into your Debian VPS and run:
        sudo apt update && sudo apt upgrade -y
        sudo apt install -y python3 python3-pip nginx git
  ## Clone your repository and create a virtual environment:
       git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git /opt/mhtml-trigger
       cd /opt/mhtml-trigger
       python3 -m venv venv
       source venv/bin/activate
       pip install flask requests gunicorn pyppeteer
# step 3 - Configure systemd & Nginx

  ## Create a systemd service
  Create /etc/systemd/system/mhtml-trigger.service:
  
       [Unit]
       Description=MHTML Trigger Service
       After=network.target
  
       [Service]
       User=root
       WorkingDirectory=/opt/mhtml-trigger
       Environment="GITHUB_TOKEN=ghp_your_token_here"
       Environment="REPO_OWNER=your_github_username"
       Environment="REPO_NAME=your_repository_name"
       Environment="WORKFLOW_ID=mhtml_downloader.yml"
       ExecStart=/opt/mhtml-trigger/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 app:app
       Restart=always

       [Install]
       WantedBy=multi-user.target
  enable the deamon:
  
       sudo systemctl daemon-reload
       sudo systemctl enable mhtml-trigger
       sudo systemctl start mhtml-trigger
       sudo systemctl status mhtml-trigger   # should show "active (running)"



  ##  Configure Nginx as reverse proxy
  Create /etc/nginx/sites-available/mhtml-trigger:

      server {
        listen 80;
        server_name your_domain_or_IP;

        location / {
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            client_max_body_size 10M;
        }
     }

  Enable the site and test:

    sudo ln -s /etc/nginx/sites-available/mhtml-trigger /etc/nginx/sites-enabled/
    sudo nginx -t
    sudo systemctl reload nginx

 ## (Optional) Set up HTTPS with Let’s Encrypt

    sudo apt install certbot python3-certbot-nginx
    sudo certbot --nginx -d your_domain.com

# Step 5 – Test the Whole Pipeline

  - Visit http://your_vps_ip (or your domain).
  - Enter a URL (e.g. https://example.com) and a title (e.g. testpage).
  - Submit the form – you should see a flash message with a tracking code (e.g. testpage_k7x9b2).
  - The status page will automatically poll every 5 seconds. Meanwhile, the GitHub Action runs. You can watch it at https://github.com/YOUR_USERNAME/YOUR_REPO/actions.
  - Once the action finishes (usually 10–30 seconds), the status page will show Download and View in sandboxed viewer buttons.
  - Click View – the page should open in an iframe with full CSS, images, and scripts (sandboxed).
  - Click Download to save the .mhtml file.


 the credit for the core of this project and the general idea of using gihub actions goes to [Kurdeus/Meli-Action](https://github.com/Kurdeus/Meli-Action)
  
