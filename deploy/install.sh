
set -euo pipefail

N=6
APP_USER=mywebapp
APP_DIR=/opt/mywebapp
CONF_DIR=/etc/mywebapp
DB_NAME=mywebapp
DB_USER=mywebapp
APP_PORT=5200
DEFAULT_PASSWORD=12345678

log() { echo "==> $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run as root: sudo ./deploy/install.sh"

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f "$REPO_DIR/app/mywebapp.py" ]] || die "app/mywebapp.py not found in $REPO_DIR"

DEFAULT_USER="${DEFAULT_USER:-${SUDO_USER:-}}"

log "Installing packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y nginx mariadb-server python3 python3-venv python3-pip curl openssl sudo

log "Creating users"
create_login_user() {
    local name=$1 admin=$2
    if ! id "$name" >/dev/null 2>&1; then
        useradd --create-home --shell /bin/bash "$name"
        echo "$name:$DEFAULT_PASSWORD" | chpasswd
        chage -d 0 "$name"
    fi
    if [[ $admin == yes ]]; then
        usermod -aG sudo "$name"
    fi
}
create_login_user student yes
create_login_user teacher yes
create_login_user operator no

if ! id "$APP_USER" >/dev/null 2>&1; then
    useradd --system --user-group --no-create-home \
        --shell /usr/sbin/nologin "$APP_USER"
fi

log "Creating /home/student/gradebook"
echo "$N" > /home/student/gradebook
chown student:student /home/student/gradebook
chmod 644 /home/student/gradebook

log "Configuring MariaDB"
cat > /etc/mysql/mariadb.conf.d/99-mywebapp.cnf <<'EOF'
[mysqld]
bind-address = 127.0.0.1
port = 3306
EOF
systemctl enable mariadb
systemctl restart mariadb

install -d -m 750 -o root -g "$APP_USER" "$CONF_DIR"
if [[ -f "$CONF_DIR/db.env" ]]; then
    source "$CONF_DIR/db.env"
else
    DB_PASSWORD="$(openssl rand -hex 16)"
fi
cat > "$CONF_DIR/db.env" <<EOF
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
DB_NAME=$DB_NAME
EOF
chown root:"$APP_USER" "$CONF_DIR/db.env"
chmod 640 "$CONF_DIR/db.env"

mysql <<EOF
CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4;
CREATE USER IF NOT EXISTS '$DB_USER'@'127.0.0.1' IDENTIFIED BY '$DB_PASSWORD';
CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASSWORD';
ALTER USER '$DB_USER'@'127.0.0.1' IDENTIFIED BY '$DB_PASSWORD';
ALTER USER '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASSWORD';
GRANT ALL PRIVILEGES ON \`$DB_NAME\`.* TO '$DB_USER'@'127.0.0.1';
GRANT ALL PRIVILEGES ON \`$DB_NAME\`.* TO '$DB_USER'@'localhost';
FLUSH PRIVILEGES;
EOF

log "Deploying application to $APP_DIR"
install -d -m 755 "$APP_DIR"
install -m 644 "$REPO_DIR"/app/mywebapp.py "$REPO_DIR"/app/migrate.py \
    "$REPO_DIR"/app/server.py "$REPO_DIR"/app/requirements.txt "$APP_DIR"/
[[ -d "$APP_DIR/venv" ]] || python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

log "Installing systemd units"
install -m 644 "$REPO_DIR/deploy/mywebapp.service" /etc/systemd/system/mywebapp.service
install -m 644 "$REPO_DIR/deploy/mywebapp.socket" /etc/systemd/system/mywebapp.socket
systemctl daemon-reload
systemctl enable --now mywebapp.socket
systemctl try-restart mywebapp.service || true

log "Waiting for the application to become ready"
ready=no
for _ in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:$APP_PORT/health/ready" >/dev/null 2>&1; then
        ready=yes
        break
    fi
    sleep 1
done
if [[ $ready != yes ]]; then
    systemctl status mywebapp.service --no-pager || true
    die "application did not become ready"
fi

log "Configuring nginx"
install -m 644 "$REPO_DIR/deploy/nginx-mywebapp.conf" /etc/nginx/sites-available/mywebapp
ln -sf /etc/nginx/sites-available/mywebapp /etc/nginx/sites-enabled/mywebapp
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable nginx
systemctl restart nginx

log "Installing sudoers rules for operator"
tmp="$(mktemp)"
install -m 440 "$REPO_DIR/deploy/sudoers-operator" "$tmp"
visudo -cf "$tmp" || { rm -f "$tmp"; die "invalid sudoers file"; }
install -m 440 -o root -g root "$tmp" /etc/sudoers.d/operator
rm -f "$tmp"

log "Smoke tests"
curl -fsS -o /dev/null -w "nginx / -> %{http_code}\n" -H "Accept: text/html" http://127.0.0.1/
curl -fsS -o /dev/null -w "nginx /notes -> %{http_code}\n" -H "Accept: application/json" http://127.0.0.1/notes
curl -sS -o /dev/null -w "nginx /health/alive (expected 404) -> %{http_code}\n" http://127.0.0.1/health/alive

case "$DEFAULT_USER" in
    ""|root|student|teacher|operator|"$APP_USER")
        log "No default user to lock (DEFAULT_USER='${DEFAULT_USER}')"
        ;;
    *)
        if id "$DEFAULT_USER" >/dev/null 2>&1; then
            log "Locking default user: $DEFAULT_USER"
            usermod -L "$DEFAULT_USER"
            chage -E 0 "$DEFAULT_USER"
            usermod -s /usr/sbin/nologin "$DEFAULT_USER"
        fi
        ;;
esac

log "Done. Application is available on http://<VM-IP>/"