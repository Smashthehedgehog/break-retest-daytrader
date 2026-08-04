#!/usr/bin/env bash
# Deployment walkthrough for break-retest-daytrader on a fresh Amazon Linux 2023 EC2
# instance (t3.micro, us-east-1). Run as ec2-user after SSH'ing in.
#
# This is meant to be read and run step-by-step, NOT piped into bash blindly -- steps
# 6-7 are interactive (you paste secrets / unit file contents into an editor). See
# README.md's "Deploying to AWS EC2" section for the full walkthrough and context.

set -euo pipefail

REPO_DIR="$HOME/break-retest-daytrader"
ENV_FILE="/etc/break-retest-daytrader.env"

# --- 1. OS packages ------------------------------------------------------------
sudo dnf update -y
sudo dnf install -y git

if sudo dnf list available python3.12 &>/dev/null; then
    sudo dnf install -y python3.12
    PYBIN=python3.12
else
    sudo dnf install -y python3.11
    PYBIN=python3.11
fi

# --- 2. Clone the repo (public -- HTTPS, no deploy key needed) -----------------
git clone https://github.com/Smashthehedgehog/break-retest-daytrader.git "$REPO_DIR"
cd "$REPO_DIR"

# --- 3. Fresh venv + dependencies -----------------------------------------------
"$PYBIN" -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# --- 4. Swapfile safety net (t3.micro has only 1GiB RAM) ------------------------
if [ ! -f /swapfile ]; then
    sudo dd if=/dev/zero of=/swapfile bs=1M count=1024
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile swap swap defaults 0 0' | sudo tee -a /etc/fstab
fi

# --- 5. Suppress Streamlit's first-run interactive prompt -----------------------
mkdir -p "$HOME/.streamlit"
cat > "$HOME/.streamlit/credentials.toml" <<'EOF'
[general]
email = ""
EOF

# --- 6. Secrets file (root-owned -- systemd/PID 1 reads it as root before ------
#        dropping privileges, so the service user never needs read access) ------
echo ""
echo "Now create $ENV_FILE with your own values. Example content (see .env.example):"
echo ""
cat <<'EOF'
ALPACA_API_KEY=your_paper_key_here
ALPACA_SECRET_KEY=your_paper_secret_here
TRADING_MODE=paper
I_UNDERSTAND_LIVE_RISK=false
TICKER=SPY
BASE_RISK=50.00
REWARD_RATIO=2.0
PROFIT_BUFFER_TARGET=200.00
SCALED_RISK=100.00
DB_PATH=/home/ec2-user/break-retest-daytrader/trade_history.db
EOF
echo ""
echo "Run:"
echo "  sudo touch $ENV_FILE && sudo chmod 600 $ENV_FILE && sudo nano $ENV_FILE"
echo "paste the above (with your real keys), save, then continue."
read -rp "Press Enter once $ENV_FILE is created... "
sudo chown root:root "$ENV_FILE"
sudo chmod 600 "$ENV_FILE"

# --- 7. Install systemd units ----------------------------------------------------
sudo cp "$REPO_DIR/deploy/break-retest-bot.service" /etc/systemd/system/
sudo cp "$REPO_DIR/deploy/break-retest-dashboard.service" /etc/systemd/system/

# --- 8. Activate -------------------------------------------------------------------
sudo systemctl daemon-reload
sudo systemctl enable --now break-retest-bot.service
sudo systemctl enable --now break-retest-dashboard.service

echo ""
echo "Done. Check status with:"
echo "  sudo systemctl status break-retest-bot.service break-retest-dashboard.service"
echo "  sudo journalctl -u break-retest-bot.service -f"
echo ""
echo "View the dashboard from your local machine via SSH tunnel (never expose 8501 publicly):"
echo "  ssh -L 8501:localhost:8501 ec2-user@<this-instance-public-ip>"
echo "  then open http://localhost:8501 locally"
