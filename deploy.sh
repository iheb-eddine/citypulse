#!/bin/bash
# Deploy CityPulse to VPS — run this ON the server as root
set -e

APP_DIR="/opt/citypulse"
DOMAIN="citypulse.help"

echo "=== Installing system deps ==="
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip nginx certbot python3-certbot-nginx

echo "=== Setting up app ==="
mkdir -p $APP_DIR
cd $APP_DIR

# Copy project files here first (rsync/scp/git clone)
if [ ! -f "requirements.txt" ]; then
    echo "ERROR: Copy project files to $APP_DIR first, then re-run."
    echo "  scp -r /path/to/citypulse/* root@$DOMAIN:$APP_DIR/"
    exit 1
fi

python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
pip install -q pillow

# Copy .env if not present
if [ ! -f ".env" ]; then
    echo "ERROR: Copy your .env file to $APP_DIR/.env"
    exit 1
fi

# Seed data
python seed_data/seed.py

echo "=== Creating systemd service ==="
cat > /etc/systemd/system/citypulse.service << 'EOF'
[Unit]
Description=CityPulse FastAPI App
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/citypulse
Environment=PATH=/opt/citypulse/.venv/bin:/usr/bin
ExecStart=/opt/citypulse/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable citypulse
systemctl restart citypulse

echo "=== Configuring nginx ==="
cat > /etc/nginx/sites-available/citypulse << EOF
server {
    listen 80;
    server_name $DOMAIN;

    client_max_body_size 12M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

ln -sf /etc/nginx/sites-available/citypulse /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo "=== Getting SSL certificate ==="
certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m admin@$DOMAIN || echo "SSL setup failed — site works on HTTP"

echo ""
echo "=== Done! ==="
echo "  http://$DOMAIN"
echo "  systemctl status citypulse  — check app"
echo "  journalctl -u citypulse -f  — view logs"
