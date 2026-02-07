#!/usr/bin/env python3
import os
import sys
import time
import json
import shutil
import getpass
import requests
import subprocess
from pathlib import Path

def run(cmd, silent=False):
    if not silent:
        print(f"-> {cmd}")
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def ok(msg):
    print(f"[+] {msg}")

def err(msg):
    print(f"[-] {msg}")
    sys.exit(1)

def warn(msg):
    print(f"[!] {msg}")

def panel_install():
    print("\n=== Installing Pterodactyl Panel ===")
    
    if os.geteuid() != 0:
        err("Run as root (sudo)")
    
    distro = run("lsb_release -is", silent=True).stdout.strip()
    codename = run("lsb_release -cs", silent=True).stdout.strip()
    
    if distro != "Ubuntu" or codename not in ["jammy", "noble"]:
        err("Only Ubuntu 22.04/24.04 supported")
    
    ok("Updating system")
    run("apt update -y && apt upgrade -y")
    
    ok("Installing dependencies")
    run("apt install -y curl tar unzip git redis-server")
    
    ok("Installing PHP 8.3")
    run("curl -sS https://packages.sury.org/php/apt.gpg | gpg --dearmor | tee /etc/apt/keyrings/sury-php.gpg >/dev/null")
    run(f'echo "deb [signed-by=/etc/apt/keyrings/sury-php.gpg] https://packages.sury.org/php/ {codename} main" | tee /etc/apt/sources.list.d/php.list')
    run("apt update -y")
    run("apt install -y php8.3 php8.3-cli php8.3-fpm php8.3-mysql php8.3-pgsql php8.3-sqlite3 php8.3-bcmath php8.3-mbstring php8.3-xml php8.3-curl php8.3-zip php8.3-gd")
    
    ok("Installing MariaDB")
    run("apt install -y mariadb-server")
    run("mysql_secure_installation")
    
    print("\nCreate database for Pterodactyl:")
    db_name = input("Database name: ")
    db_user = input("Database user: ")
    db_pass = getpass.getpass("Database password: ")
    
    mysql_cmd = f"""
mysql -u root <<EOF
CREATE DATABASE {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER '{db_user}'@'127.0.0.1' IDENTIFIED BY '{db_pass}';
GRANT ALL PRIVILEGES ON {db_name}.* TO '{db_user}'@'127.0.0.1';
FLUSH PRIVILEGES;
EOF
"""
    run(mysql_cmd)
    
    ok("Installing Composer")
    run("curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer")
    
    ok("Downloading panel")
    if Path("/var/www/pterodactyl").exists():
        shutil.rmtree("/var/www/pterodactyl")
    run("mkdir -p /var/www/pterodactyl")
    run("cd /var/www/pterodactyl && curl -Lo panel.tar.gz https://github.com/pterodactyl/panel/releases/latest/download/panel.tar.gz")
    run("cd /var/www/pterodactyl && tar -xzvf panel.tar.gz && rm panel.tar.gz")
    run("chown -R www-data:www-data /var/www/pterodactyl/*")
    
    ok("Installing PHP dependencies")
    run("cd /var/www/pterodactyl && composer install --no-dev --optimize-autoloader")
    
    ok("Setting up env file")
    run("cd /var/www/pterodactyl && php artisan p:environment:setup")
    run(f"cd /var/www/pterodactyl && php artisan p:environment:database --host=127.0.0.1 --port=3306 --database={db_name} --username={db_user} --password={db_pass}")
    
    ok("Generating key")
    run("cd /var/www/pterodactyl && php artisan key:generate --force")
    
    ok("Running migrations")
    run("cd /var/www/pterodactyl && php artisan migrate --force")
    
    ok("Creating admin user")
    run("cd /var/www/pterodactyl && php artisan p:user:make")
    
    ok("Setting permissions")
    run("cd /var/www/pterodactyl && chown -R www-data:www-data /var/www/pterodactyl")
    run("cd /var/www/pterodactyl && chmod -R 755 storage bootstrap/cache")
    
    ok("Installing Nginx")
    run("apt install -y nginx")
    run("rm /etc/nginx/sites-enabled/default")
    run("curl -o /etc/nginx/sites-available/pterodactyl.conf https://raw.githubusercontent.com/pterodactyl/panel/gh-pages/nginx.sh | bash")
    run("ln -s /etc/nginx/sites-available/pterodactyl.conf /etc/nginx/sites-enabled/pterodactyl.conf")
    run("systemctl restart nginx")
    
    ok("Setting up queue worker")
    run("curl -o /etc/systemd/system/pteroq.service https://raw.githubusercontent.com/pterodactyl/panel/gh-pages/pteroq.service")
    run("systemctl daemon-reload")
    run("systemctl enable --now pteroq.service")
    
    ok("Panel installed! Login at https://your-domain.com")
    print("\nNext steps:")
    print("1. Setup SSL with certbot")
    print("2. Install Wings daemon on a node server")

def phpmyadmin_install():
    print("\n=== Installing phpMyAdmin (SECURE MODE) ===")
    
    if os.geteuid() != 0:
        err("Run as root (sudo)")
    
    ok("Installing phpMyAdmin")
    run("apt install -y phpmyadmin")
    
    ok("Configuring Nginx")
    conf = """
location /phpmyadmin {
    allow 127.0.0.1;
    deny all;
    
    auth_basic "Restricted";
    auth_basic_user_file /etc/nginx/.pma_pass;
    
    location ~ ^/(index|console|phpmyadmin)\.php$ {
        fastcgi_pass unix:/run/php/php8.3-fpm.sock;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
        include fastcgi_params;
    }
}
"""
    with open("/etc/nginx/snippets/phpmyadmin.conf", "w") as f:
        f.write(conf)
    
    ok("Setting up basic auth")
    user = input("Auth username: ")
    run(f"apt install -y apache2-utils")
    run(f"htpasswd -c /etc/nginx/.pma_pass {user}")
    
    ok("Reloading Nginx")
    run("nginx -t && systemctl reload nginx")
    
    warn("phpMyAdmin ONLY accessible via SSH tunnel:")
    print("ssh -L 8888:localhost:80 your-server")
    print("Then open http://localhost:8888/phpmyadmin")

def import_eggs():
    print("\n=== Importing Game Server Eggs ===")
    
    panel_url = input("Panel URL (https://panel.example.com): ").rstrip("/")
    api_key = getpass.getpass("Application API key (from Admin > API Credentials): ")
    
    eggs_dir = Path.home() / "eggs"
    if not eggs_dir.exists():
        ok("Downloading official eggs repo")
        run(f"git clone https://github.com/pterodactyl/eggs.git {eggs_dir}")
    
    nests = [d for d in eggs_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
    print("\nAvailable nests:")
    for i, nest in enumerate(nests):
        print(f"{i+1}. {nest.name}")
    
    choice = int(input("\nSelect nest number: ")) - 1
    selected_nest = nests[choice]
    
    eggs = list(selected_nest.rglob("*.json"))
    print(f"\nFound {len(eggs)} eggs in {selected_nest.name}")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    for egg_file in eggs:
        print(f"\nImporting {egg_file.name}...")
        try:
            egg_data = json.loads(egg_file.read_text())
            res = requests.post(
                f"{panel_url}/api/application/nests/1/eggs/import",
                headers=headers,
                json=egg_data,
                verify=True
            )
            if res.status_code in [200, 204, 409]:
                ok(f"Imported {egg_file.name}")
            else:
                err(f"Failed {egg_file.name}: {res.text}")
        except Exception as e:
            err(f"Error importing {egg_file.name}: {str(e)}")
        
        time.sleep(0.5)
    
    ok("All eggs imported!")

def auto_node():
    print("\n=== Auto Node Setup (Wings Daemon) ===")
    
    if os.geteuid() != 0:
        err("Run as root (sudo)")
    
    distro = run("lsb_release -is", silent=True).stdout.strip()
    codename = run("lsb_release -cs", silent=True).stdout.strip()
    
    if distro != "Ubuntu" or codename not in ["jammy", "noble"]:
        err("Only Ubuntu 22.04/24.04 supported")
    
    ok("Installing Docker")
    run("apt install -y ca-certificates curl gnupg")
    run("install -m 0755 -d /etc/apt/keyrings")
    run("curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg")
    run('echo "deb [arch=\"$(dpkg --print-architecture)\" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu '"$(. /etc/os-release && echo $VERSION_CODENAME)"' stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null')
    run("apt update -y")
    run("apt install -y docker-ce docker-ce-cli containerd.io")
    
    ok("Installing Wings")
    run("mkdir -p /etc/pterodactyl")
    run("curl -L -o /usr/local/bin/wings https://github.com/pterodactyl/wings/releases/latest/download/wings_linux_amd64")
    run("chmod u+x /usr/local/bin/wings")
    
    panel_url = input("Panel URL (https://panel.example.com): ").rstrip("/")
    node_name = input("Node name: ")
    fqdn = input("Node FQDN (node.yourdomain.com): ")
    
    print("\nCreating node in panel...")
    admin_email = input("Panel admin email: ")
    admin_pass = getpass.getpass("Panel admin password: ")
    
    login_res = requests.post(
        f"{panel_url}/api/application/auth/login",
        json={"email": admin_email, "password": admin_pass},
        verify=True
    )
    
    if login_res.status_code != 200:
        err("Failed to login to panel")
    
    token = login_res.json()["data"]["token"]
    
    node_res = requests.post(
        f"{panel_url}/api/application/nodes",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "name": node_name,
            "description": "Auto-provisioned node",
            "location_id": 1,
            "fqdn": fqdn,
            "scheme": "https",
            "memory": 8192,
            "memory_overallocate": 0,
            "disk": 256000,
            "disk_overallocate": 0,
            "upload_size": 100,
            "daemon_base": "/var/lib/pterodactyl/volumes",
            "daemon_sftp": 2022,
            "daemon_listen": 8080
        },
        verify=True
    )
    
    if node_res.status_code != 201:
        err(f"Failed to create node: {node_res.text}")
    
    node_data = node_res.json()["attributes"]
    config_url = node_data["configuration"]["config_url"]
    
    ok("Downloading node config")
    config_res = requests.get(config_url, verify=True)
    if config_res.status_code != 200:
        err("Failed to download config")
    
    with open("/etc/pterodactyl/config.yml", "w") as f:
        f.write(config_res.text)
    
    ok("Creating systemd service")
    service = """[Unit]
Description=Pterodactyl Wings Daemon
After=docker.service

[Service]
Type=simple
Restart=always
RestartSec=5s
ExecStart=/usr/local/bin/wings --config /etc/pterodactyl/config.yml
LimitNOFILE=4096

[Install]
WantedBy=multi-user.target
"""
    with open("/etc/systemd/system/wings.service", "w") as f:
        f.write(service)
    
    ok("Starting Wings")
    run("systemctl daemon-reload")
    run("systemctl enable --now wings.service")
    
    ok(f"Node {node_name} is online!")
    print(f"Check status: systemctl status wings")
    print(f"Logs: journalctl -u wings -n 50")

def main():
    print("Pterodactyl Auto-Deploy Tool")
    print("============================\n")
    
    print("1. Install Panel")
    print("2. Install phpMyAdmin (secure)")
    print("3. Import Eggs")
    print("4. Auto Node Setup (Wings)")
    print("5. All-in-One (Panel + Node)")
    
    choice = input("\nSelect option: ").strip()
    
    if choice == "1":
        panel_install()
    elif choice == "2":
        phpmyadmin_install()
    elif choice == "3":
        import_eggs()
    elif choice == "4":
        auto_node()
    elif choice == "5":
        panel_install()
        print("\n--- Wait 2 minutes for panel to settle ---")
        time.sleep(120)
        auto_node()
    else:
        err("Invalid option")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nCancelled by user")
        sys.exit(1)
    except Exception as e:
        err(f"Unexpected error: {str(e)}")
