# Production Deployment Guide

This guide covers deploying the Substrate Deploy System in a production environment.

## Architecture Overview

For production, we recommend:

```
┌─────────────────────────────────────────────────────┐
│              Load Balancer (nginx/caddy)            │
│              - SSL/TLS termination                  │
│              - Rate limiting                        │
└──────────────────────┬──────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
   ┌────▼────┐   ┌────▼────┐   ┌────▼────┐
   │Control  │   │Control  │   │Control  │
   │Panel 1  │   │Panel 2  │   │Panel N  │
   └────┬────┘   └────┬────┘   └────┬────┘
        │              │              │
        └──────────────┼──────────────┘
                       │
              ┌────────▼────────┐
              │  Shared Database│
              │  (PostgreSQL)   │
              └─────────────────┘
```

## Prerequisites

- Linux server (Ubuntu 22.04+ recommended)
- Docker 24.0+
- Docker Compose 2.20+
- Domain name with DNS configured
- SSL certificate (Let's Encrypt)
- PostgreSQL 15+ (for production database)
- Reverse proxy (nginx/caddy)

## Step 1: Server Setup

### Install Docker

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo apt install docker-compose-plugin -y

# Add user to docker group
sudo usermod -aG docker $USER
```

### Configure Firewall

```bash
# Allow SSH
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Enable firewall
sudo ufw enable
```

## Step 2: Database Setup

### Install PostgreSQL

```bash
sudo apt install postgresql postgresql-contrib -y
```

### Create Database and User

```bash
sudo -u postgres psql
```

```sql
CREATE DATABASE substrate_deploy;
CREATE USER substrate WITH PASSWORD 'your-secure-password';
GRANT ALL PRIVILEGES ON DATABASE substrate_deploy TO substrate;
\q
```

### Configure PostgreSQL for Remote Access

Edit `/etc/postgresql/15/main/postgresql.conf`:
```ini
listen_addresses = 'localhost,your-server-ip'
```

Edit `/etc/postgresql/15/main/pg_hba.conf`:
```
host    substrate_deploy    substrate    your-server-ip/32    md5
```

Restart PostgreSQL:
```bash
sudo systemctl restart postgresql
```

## Step 3: Deploy Control Panel

### Clone Repository

```bash
git clone https://github.com/your-org/substrate-deploy-system.git
cd substrate-deploy-system
```

### Configure Environment

Create `.env` file:

```bash
# Database
DATABASE_URL=postgresql://substrate:your-secure-password@host.docker.internal:5432/substrate_deploy

# Security
SECRET_KEY=$(openssl rand -hex 32)

# Optional: Custom domain
CONTROL_PANEL_DOMAIN=deploy.your-domain.com
```

### Update Docker Compose

Edit `docker/docker-compose.yml`:

```yaml
version: '3.8'

services:
  control-panel:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    ports:
      - "127.0.0.1:8080:8080"  # Bind to localhost only
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - SECRET_KEY=${SECRET_KEY}
    volumes:
      - control-panel-data:/app/data
    restart: always
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    extra_hosts:
      - "host.docker.internal:host-gateway"

volumes:
  control-panel-data:
```

### Build and Start

```bash
# Build image
docker compose -f docker/docker-compose.yml build

# Start services
docker compose -f docker/docker-compose.yml up -d

# Check status
docker compose -f docker/docker-compose.yml ps
```

## Step 4: Configure Reverse Proxy

### Install nginx

```bash
sudo apt install nginx -y
```

### Configure SSL with Let's Encrypt

```bash
sudo apt install certbot python3-certbot-nginx -y
```

### Create nginx Configuration

Create `/etc/nginx/sites-available/substrate-deploy`:

```nginx
server {
    listen 80;
    server_name deploy.your-domain.com;

    location / {
        return 301 https://$server_name$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name deploy.your-domain.com;

    # SSL certificates
    ssl_certificate /etc/letsencrypt/live/deploy.your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/deploy.your-domain.com/privkey.pem;

    # SSL settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;

        # Rate limiting
        limit_req zone=api burst=20 nodelay;
    }

    # Health check endpoint (no rate limit)
    location /health {
        proxy_pass http://127.0.0.1:8080;
        limit_req zone=api burst=100 nodelay;
    }
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/substrate-deploy /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Obtain SSL Certificate

```bash
sudo certbot --nginx -d deploy.your-domain.com
```

## Step 5: Configure Agents

### Update Agent Configuration

On each agent machine, configure the agent to use HTTPS:

```bash
python agent.py --control-panel-url https://deploy.your-domain.com
```

### Agent Service (systemd)

Create `/etc/systemd/system/substrate-agent.service`:

```ini
[Unit]
Description=Substrate Deploy Agent
After=network.target

[Service]
Type=simple
User=substrate
WorkingDirectory=/opt/substrate-agent
ExecStart=/usr/bin/python3 /opt/substrate-agent/agent.py --control-panel-url https://deploy.your-domain.com
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable substrate-agent
sudo systemctl start substrate-agent
```

## Step 6: Monitoring and Logging

### Prometheus Setup

Install Prometheus:

```bash
sudo apt install prometheus -y
```

Configure `/etc/prometheus/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'substrate-deploy'
    static_configs:
      - targets: ['localhost:8080']
    metrics_path: '/metrics'
```

Restart Prometheus:

```bash
sudo systemctl restart prometheus
```

### Grafana Setup

Install Grafana:

```bash
sudo apt install grafana -y
sudo systemctl enable grafana-server
sudo systemctl start grafana-server
```

Access Grafana at `http://your-server:3000` (default: admin/admin)

### Log Management

Configure log rotation:

Create `/etc/logrotate.d/substrate-agent`:

```
/var/log/substrate-agent/*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    create 0640 substrate substrate
    sharedscripts
    postrotate
        systemctl reload substrate-agent
    endscript
}
```

## Step 7: Backup and Recovery

### Database Backup

Create backup script `/opt/scripts/backup-db.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/opt/backups/postgresql"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

sudo -u postgres pg_dump substrate_deploy | gzip > $BACKUP_DIR/substrate_deploy_$DATE.sql.gz

# Keep only last 30 days
find $BACKUP_DIR -name "*.sql.gz" -mtime +30 -delete
```

Schedule with cron:

```bash
sudo crontab -e
```

Add:
```
0 2 * * * /opt/scripts/backup-db.sh
```

### Restore from Backup

```bash
# Stop control panel
docker compose -f docker/docker-compose.yml down

# Restore database
gunzip -c backup.sql.gz | sudo -u postgres psql substrate_deploy

# Start control panel
docker compose -f docker/docker-compose.yml up -d
```

## Step 8: Security Hardening

### Firewall Rules

```bash
# Allow only necessary ports
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP (for redirects)
sudo ufw allow 443/tcp  # HTTPS

# Deny all other incoming
sudo ufw default deny incoming

# Allow outgoing
sudo ufw default allow outgoing

sudo ufw enable
```

### Fail2Ban

Install and configure Fail2Ban:

```bash
sudo apt install fail2ban -y
```

Create `/etc/fail2ban/jail.local`:

```ini
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true

[nginx-http-auth]
enabled = true
```

```bash
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### Regular Updates

```bash
# Create update script
cat > /opt/scripts/update-system.sh << 'EOF'
#!/bin/bash
cd /opt/substrate-deploy-system
git pull
docker compose -f docker/docker-compose.yml build
docker compose -f docker/docker-compose.yml up -d
EOF

chmod +x /opt/scripts/update-system.sh
```

Schedule weekly updates:

```bash
0 3 * * 0 /opt/scripts/update-system.sh
```

## Step 9: High Availability (Optional)

For high availability, deploy multiple control panel instances:

### Load Balancer Configuration

```nginx
upstream substrate_deploy {
    server control-panel-1:8080;
    server control-panel-2:8080;
    server control-panel-3:8080;
}

server {
    listen 443 ssl;
    server_name deploy.your-domain.com;

    location / {
        proxy_pass http://substrate_deploy;
        # ... other settings
    }
}
```

### Database Replication

Set up PostgreSQL replication:
- Primary: Read/Write
- Replicas: Read-only
- Use pgBouncer for connection pooling

## Step 10: Performance Tuning

### Docker Resources

Edit `docker-compose.yml`:

```yaml
services:
  control-panel:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

### Database Tuning

Edit `postgresql.conf`:

```ini
max_connections = 200
shared_buffers = 2GB
effective_cache_size = 6GB
work_mem = 16MB
maintenance_work_mem = 512MB
```

### nginx Tuning

Edit `nginx.conf`:

```nginx
worker_processes auto;
worker_connections 4096;

http {
    keepalive_timeout 65;
    client_max_body_size 100M;
    
    gzip on;
    gzip_types text/plain application/json application/javascript text/css;
}
```

## Monitoring Checklist

- [ ] Control panel health checks passing
- [ ] All agents reporting online
- [ ] Database connections healthy
- [ ] SSL certificate valid
- [ ] Backup jobs running
- [ ] Log rotation working
- [ ] Resource usage within limits
- [ ] Error rates acceptable
- [ ] Response times acceptable

## Troubleshooting

### Control Panel Not Starting

```bash
# Check logs
docker compose -f docker/docker-compose.yml logs

# Check database connection
docker compose -f docker/docker-compose.yml exec control-panel python -c "import os; from sqlalchemy import create_engine; engine = create_engine(os.getenv('DATABASE_URL')); engine.connect()"
```

### Agents Cannot Connect

```bash
# Test from agent machine
curl -v https://deploy.your-domain.com/health

# Check DNS resolution
nslookup deploy.your-domain.com

# Check SSL certificate
openssl s_client -connect deploy.your-domain.com:443
```

### High Resource Usage

```bash
# Check Docker stats
docker stats

# Check database connections
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity;"

# Check nginx connections
sudo netstat -an | grep :443 | wc -l
```

## Support

For production issues:
1. Check logs: `docker compose logs`, `/var/log/substrate-agent/`
2. Review metrics: Prometheus/Grafana
3. Check documentation: `docs/`
4. Open GitHub issue with details

## Compliance

### Audit Logging

Enable audit logging in control panel:

```python
# Add to main.py
import logging
audit_logger = logging.getLogger('audit')
audit_handler = logging.FileHandler('/var/log/substrate-deploy/audit.log')
audit_logger.addHandler(audit_handler)
```

### Data Retention

Configure data retention policies:

```python
# Delete old deployments after 90 days
DELETE FROM deployments WHERE started_at < NOW() - INTERVAL '90 days';
```

### Access Control

Implement role-based access control (RBAC):
- Admin: Full access
- Operator: Deploy and monitor
- Viewer: Read-only access

## Conclusion

Your Substrate Deploy System is now production-ready with:
- ✅ HTTPS encryption
- ✅ Database persistence
- ✅ Monitoring and logging
- ✅ Backup and recovery
- ✅ Security hardening
- ✅ High availability (optional)
- ✅ Performance tuning

Regular maintenance:
- Weekly: Check logs and metrics
- Monthly: Review and update
- Quarterly: Security audit
- Yearly: Architecture review
