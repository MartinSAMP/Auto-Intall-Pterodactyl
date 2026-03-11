#!/usr/bin/env python3
"""
Pterodactyl Auto Installer
Copyright (c) 2026 Martin
Production-ready installer with enterprise-grade security and reliability
"""

import os
import sys
import time
import json
import shutil
import getpass
import logging
import argparse
import hashlib
import secrets
import string
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass
from enum import Enum
import requests
import subprocess
import textwrap

LOG_DIR = Path("/var/log/pterodactyl-installer")
LOG_FILE = LOG_DIR / f"install-{time.strftime('%Y%m%d-%H%M%S')}.log"

def setup_logging():
    """Setup comprehensive logging"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

class Colors:
    """ANSI color codes"""
    GREEN = '\033[0;32m'
    RED = '\033[0;31m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    PURPLE = '\033[0;35m'
    NC = '\033[0m'

class OSInfo:
    """Operating System Information"""
    def __init__(self):
        self.distro = self._get_distro()
        self.codename = self._get_codename()
        self.version_id = self._get_version_id()
        self.supported = self._check_support()
        
    def _get_distro(self) -> str:
        try:
            return subprocess.run(
                ["lsb_release", "-is"], 
                capture_output=True, text=True, check=True
            ).stdout.strip()
        except:
            try:
                with open("/etc/os-release") as f:
                    for line in f:
                        if line.startswith("ID="):
                            return line.split("=")[1].strip().strip('"')
            except:
                return "unknown"
    
    def _get_codename(self) -> str:
        try:
            return subprocess.run(
                ["lsb_release", "-cs"],
                capture_output=True, text=True, check=True
            ).stdout.strip()
        except:
            return "unknown"
    
    def _get_version_id(self) -> str:
        try:
            return subprocess.run(
                ["lsb_release", "-rs"],
                capture_output=True, text=True, check=True
            ).stdout.strip()
        except:
            return "unknown"
    
    def _check_support(self) -> bool:
        """Check if OS is supported"""
        supported_combos = {
            "Ubuntu": ["focal", "jammy", "noble"],  # 20.04, 22.04, 24.04
            "Debian": ["bullseye", "bookworm"],     # 11, 12
        }
        
        if self.distro in supported_combos:
            return self.codename in supported_combos[self.distro]
        return False

@dataclass
class DatabaseConfig:
    """Database configuration"""
    name: str
    user: str
    password: str
    host: str = "127.0.0.1"
    port: int = 3306
    
    @classmethod
    def generate_secure(cls, name: str = "pterodactyl") -> "DatabaseConfig":
        """Generate secure random credentials"""
        return cls(
            name=name,
            user=name,
            password=generate_secure_password(24)
        )

@dataclass
class AdminConfig:
    """Admin user configuration"""
    email: str
    username: str
    password: str
    first_name: str = "Admin"
    last_name: str = "User"

def generate_secure_password(length: int = 16) -> str:
    """Generate cryptographically secure password"""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in "!@#$%^&*" for c in password)):
            return password

def colorize(text: str, color: str) -> str:
    """Add color to text"""
    return f"{color}{text}{Colors.NC}"

def run(cmd: str, silent: bool = False, check: bool = True, timeout: int = 300) -> subprocess.CompletedProcess:
    """
    Execute shell command with comprehensive error handling
    
    Args:
        cmd: Command to execute
        silent: If True, suppress command echo
        check: If True, raise exception on non-zero exit
        timeout: Command timeout in seconds
    """
    if not silent:
        print(colorize(f"-> {cmd}", Colors.BLUE))
    
    logger.debug(f"Executing: {cmd}")
    
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=True, 
            text=True,
            timeout=timeout,
            executable="/bin/bash"
        )
        
        if result.returncode != 0 and check:
            logger.error(f"Command failed: {cmd}")
            logger.error(f"STDOUT: {result.stdout}")
            logger.error(f"STDERR: {result.stderr}")
            raise subprocess.CalledProcessError(
                result.returncode, cmd, 
                output=result.stdout, 
                stderr=result.stderr
            )
        
        return result
        
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out after {timeout}s: {cmd}")
        raise

def ok(msg: str):
    """Print success message"""
    print(colorize(f"[+] {msg}", Colors.GREEN))
    logger.info(msg)

def err(msg: str, exit_code: int = 1):
    """Print error and exit"""
    print(colorize(f"[-] {msg}", Colors.RED))
    logger.error(msg)
    sys.exit(exit_code)

def warn(msg: str):
    """Print warning"""
    print(colorize(f"[!] {msg}", Colors.YELLOW))
    logger.warning(msg)

def info(msg: str):
    """Print info"""
    print(colorize(f"[i] {msg}", Colors.CYAN))
    logger.info(msg)

def progress_bar(current: int, total: int, label: str, width: int = 40):
    """Display progress bar"""
    if total == 0:
        return
    
    percentage = int(current * 100 / total)
    filled = int(current * width / total)
    empty = width - filled
    
    bar = f"{Colors.GREEN}{'█' * filled}{Colors.CYAN}{'░' * empty}{Colors.NC}"
    print(f"\r  [{bar}] {Colors.YELLOW}{percentage:3d}%{Colors.NC} - {label}", end="", flush=True)
    
    if current == total:
        print()

def validate_fqdn(fqdn: str) -> bool:
    """Validate FQDN format"""
    import re
    pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
    return bool(re.match(pattern, fqdn))

def validate_email(email: str) -> bool:
    """Validate email format"""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def validate_ip(ip: str) -> bool:
    """Validate IP address format"""
    import re
    pattern = r'^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'
    return bool(re.match(pattern, ip))

def secure_input(prompt: str, hidden: bool = False) -> str:
    """Secure input with validation retry"""
    while True:
        if hidden:
            value = getpass.getpass(colorize(prompt, Colors.CYAN))
        else:
            value = input(colorize(prompt, Colors.CYAN))
        
        if value.strip():
            return value.strip()
        warn("Input cannot be empty")

def check_root():
    """Verify running as root"""
    if os.geteuid() != 0:
        err("This script must be run as root (use sudo)")

def detect_os() -> OSInfo:
    """Detect and validate operating system"""
    info("Detecting operating system...")
    
    os_info = OSInfo()
    
    if not os_info.supported:
        err(f"Unsupported OS: {os_info.distro} {os_info.codename} ({os_info.version_id}). "
            f"Supported: Ubuntu 20.04/22.04/24.04, Debian 11/12")
    
    ok(f"OS detected: {os_info.distro} {os_info.codename} ({os_info.version_id})")
    logger.info(f"OS Info: {os_info}")
    return os_info

def backup_existing(path: Path) -> Optional[Path]:
    """Create backup of existing installation"""
    if not path.exists():
        return None
    
    backup_path = Path(f"/var/backups/pterodactyl-backup-{time.strftime('%Y%m%d-%H%M%S')}")
    info(f"Creating backup of existing installation to {backup_path}")
    
    try:
        shutil.copytree(path, backup_path, ignore=shutil.ignore_patterns(
            'node_modules', 'vendor', '.git'
        ))
        ok(f"Backup created: {backup_path}")
        return backup_path
    except Exception as e:
        warn(f"Backup failed: {e}")
        return None

def install_dependencies(os_info: OSInfo):
    """Install system dependencies"""
    info("Installing system dependencies...")
    
    steps = [
        ("Updating package lists", "apt update -y"),
        ("Upgrading packages", "apt upgrade -y -o Dpkg::Options::='--force-confold'"),
        ("Installing base dependencies", 
         "apt install -y curl tar unzip git redis-server ca-certificates apt-transport-https "
         "lsb-release gnupg2 software-properties-common openssl"),
        ("Installing additional tools",
         "apt install -y htop vim nano net-tools ufw fail2ban"),
    ]
    
    for i, (label, cmd) in enumerate(steps, 1):
        progress_bar(i, len(steps), label)
        try:
            run(cmd, silent=True, timeout=300)
        except subprocess.CalledProcessError as e:
            err(f"Failed to install dependencies: {e.stderr}")
    
    ok("Dependencies installed")

def install_php(os_info: OSInfo):
    """Install PHP 8.3 with optimizations"""
    info("Installing PHP 8.3...")
    
    run("curl -fsSL https://packages.sury.org/php/apt.gpg | "
        "gpg --dearmor -o /etc/apt/keyrings/sury-php.gpg", silent=True)
    
    run(f'echo "deb [signed-by=/etc/apt/keyrings/sury-php.gpg] '
        f'https://packages.sury.org/php/ {os_info.codename} main" | '
        f'tee /etc/apt/sources.list.d/php.list', silent=True)
    
    run("apt update -y", silent=True)
    
    extensions = [
        "php8.3-cli", "php8.3-fpm", "php8.3-mysql", "php8.3-pgsql",
        "php8.3-sqlite3", "php8.3-bcmath", "php8.3-mbstring", "php8.3-xml",
        "php8.3-curl", "php8.3-zip", "php8.3-gd", "php8.3-intl",
        "php8.3-redis", "php8.3-opcache"
    ]
    
    run(f"apt install -y {' '.join(extensions)}", silent=True, timeout=300)
    
    php_fpm_conf = Path("/etc/php/8.3/fpm/php.ini")
    if php_fpm_conf.exists():
        info("Optimizing PHP configuration...")
        
        optimizations = {
            "memory_limit": "512M",
            "max_execution_time": "300",
            "max_input_vars": "3000",
            "upload_max_filesize": "100M",
            "post_max_size": "100M",
            "opcache.enable": "1",
            "opcache.memory_consumption": "256",
            "opcache.interned_strings_buffer": "16",
            "opcache.max_accelerated_files": "20000",
            "opcache.revalidate_freq": "60",
            "opcache.fast_shutdown": "1"
        }
        
        content = php_fpm_conf.read_text()
        for key, value in optimizations.items():
            if key in ["opcache.enable", "opcache.memory_consumption"]:
                if key not in content:
                    content += f"\n{key}={value}\n"
            else:
                import re
                content = re.sub(
                    rf"^{key}\s*=.*$", 
                    f"{key} = {value}", 
                    content, 
                    flags=re.MULTILINE
                )
        
        php_fpm_conf.write_text(content)
        run("systemctl restart php8.3-fpm", silent=True)
    
    ok("PHP 8.3 installed and optimized")

def install_mariadb() -> bool:
    """Install and secure MariaDB"""
    info("Installing MariaDB...")
    
    run("apt install -y mariadb-server", silent=True, timeout=120)
    run("systemctl enable --now mariadb", silent=True)
    
    secure_cmds = [
        "DELETE FROM mysql.user WHERE User='';",
        "DELETE FROM mysql.user WHERE User='root' AND Host NOT IN ('localhost', '127.0.0.1', '::1');",
        "DROP DATABASE IF EXISTS test;",
        "DELETE FROM mysql.db WHERE Db='test' OR Db='test\\_%';",
        "FLUSH PRIVILEGES;"
    ]
    
    for cmd in secure_cmds:
        run(f'mysql -u root -e "{cmd}"', silent=True, check=False)
    
    ok("MariaDB installed and secured")
    return True

def setup_database(config: DatabaseConfig):
    """Setup database and user"""
    info("Setting up database...")
    
    result = run(
        f"mysql -u root -e \"SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA "
        f"WHERE SCHEMA_NAME='{config.name}'\"",
        silent=True,
        check=False
    )
    
    if config.name in result.stdout:
        warn(f"Database {config.name} already exists")
        response = input("Drop and recreate? (y/N): ").lower()
        if response == 'y':
            run(f"mysql -u root -e \"DROP DATABASE {config.name};\"", silent=True)
        else:
            info("Using existing database")
            return
    
    commands = [
        f"CREATE DATABASE {config.name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;",
        f"CREATE USER IF NOT EXISTS '{config.user}'@'{config.host}' IDENTIFIED BY '{config.password}';",
        f"GRANT ALL PRIVILEGES ON {config.name}.* TO '{config.user}'@'{config.host}';",
        "FLUSH PRIVILEGES;"
    ]
    
    for cmd in commands:
        run(f'mysql -u root -e "{cmd}"', silent=True)
    
    ok(f"Database {config.name} configured")
    logger.info(f"Database user created: {config.user}")

def install_composer():
    """Install Composer with signature verification"""
    info("Installing Composer...")
    
    if shutil.which("composer"):
        ok("Composer already installed")
        return
    
    installer_path = "/tmp/composer-setup.php"
    run(f"curl -fsSL https://getcomposer.org/installer -o {installer_path}", silent=True)
    
    try:
        expected_sig = requests.get(
            "https://composer.github.io/installer.sig",
            timeout=10
        ).text.strip()
        
        actual_sig = run(
            f"sha384sum {installer_path} | awk '{{print $1}}'",
            silent=True
        ).stdout.strip()
        
        if expected_sig != actual_sig:
            err("Composer installer signature verification failed")
        
        ok("Composer signature verified")
    except Exception as e:
        warn(f"Could not verify signature: {e}")
        response = input("Continue anyway? (y/N): ").lower()
        if response != 'y':
            sys.exit(1)
    
    run(f"php {installer_path} --install-dir=/usr/local/bin --filename=composer", silent=True)
    os.remove(installer_path)
    
    os.makedirs("/root/.composer/cache", exist_ok=True)
    
    ok("Composer installed")

def download_panel() -> Path:
    """Download and extract panel"""
    panel_path = Path("/var/www/pterodactyl")
    
    backup_existing(panel_path)
    
    info("Downloading Pterodactyl Panel...")
    
    panel_path.mkdir(parents=True, exist_ok=True)
    
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            run(
                f"curl -fsSL -o /tmp/panel.tar.gz "
                f"https://github.com/pterodactyl/panel/releases/latest/download/panel.tar.gz",
                silent=True,
                timeout=120
            )
            
            result = run("file /tmp/panel.tar.gz", silent=True)
            if "gzip compressed" not in result.stdout:
                raise Exception("Downloaded file is not a valid archive")
            
            break
        except Exception as e:
            if attempt == max_attempts:
                err(f"Failed to download panel after {max_attempts} attempts: {e}")
            warn(f"Download attempt {attempt} failed, retrying...")
            time.sleep(3)
    
    run(f"tar -xzf /tmp/panel.tar.gz -C {panel_path}", silent=True)
    os.remove("/tmp/panel.tar.gz")
    
    run(f"chown -R www-data:www-data {panel_path}", silent=True)
    
    ok(f"Panel downloaded to {panel_path}")
    return panel_path

def install_panel_dependencies(panel_path: Path):
    """Install PHP dependencies via Composer"""
    info("Installing PHP dependencies...")
    
    env = os.environ.copy()
    env["COMPOSER_ALLOW_SUPERUSER"] = "1"
    env["COMPOSER_HOME"] = "/root/.composer"
    env["COMPOSER_CACHE_DIR"] = "/root/.composer/cache"
    
    run(
        f"cd {panel_path} && composer install --no-dev --optimize-autoloader --no-interaction",
        silent=True,
        timeout=300
    )
    
    ok("Dependencies installed")

def configure_panel(panel_path: Path, db_config: DatabaseConfig, admin_config: AdminConfig, fqdn: str):
    """Configure panel environment"""
    info("Configuring panel...")
    
    env_file = panel_path / ".env"
    
    result = run(f"cd {panel_path} && php artisan key:generate --force --show", silent=True)
    app_key = result.stdout.strip()
    
    env_content = f"""APP_ENV=production
APP_KEY={app_key}
APP_DEBUG=false
APP_URL=https://{fqdn}
APP_TIMEZONE=UTC
APP_SERVICE_AUTHOR={admin_config.email}

LOG_CHANNEL=daily
LOG_DEPRECATIONS_CHANNEL=null
LOG_LEVEL=info

DB_CONNECTION=mysql
DB_HOST={db_config.host}
DB_PORT={db_config.port}
DB_DATABASE={db_config.name}
DB_USERNAME={db_config.user}
DB_PASSWORD={db_config.password}

REDIS_HOST=127.0.0.1
REDIS_PASSWORD=null
REDIS_PORT=6379

CACHE_DRIVER=redis
SESSION_DRIVER=redis
QUEUE_DRIVER=redis

MAIL_MAILER=smtp
MAIL_HOST=localhost
MAIL_PORT=25
MAIL_USERNAME=null
MAIL_PASSWORD=null
MAIL_ENCRYPTION=null
"""
    
    env_file.write_text(env_content)
    env_file.chmod(0o600)
    
    run(f"cd {panel_path} && php artisan migrate --force --seed", silent=True, timeout=120)
    
    run(
        f"cd {panel_path} && php artisan p:user:make "
        f"--email={admin_config.email} "
        f"--username={admin_config.username} "
        f"--password={admin_config.password} "
        f"--admin=1 "
        f"--no-interaction",
        silent=True
    )
    
    run(f"cd {panel_path} && php artisan storage:link", silent=True)
    
    ok("Panel configured")

def install_nginx(fqdn: str, panel_path: Path, ssl: bool = False):
    """Install and configure Nginx"""
    info("Installing Nginx...")
    
    run("apt install -y nginx", silent=True)
    
    default_site = Path("/etc/nginx/sites-enabled/default")
    if default_site.exists():
        default_site.unlink()
    
    php_socket = "unix:/run/php/php8.3-fpm.sock"
    
    security_headers = """
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
"""
    
    if ssl:
        nginx_conf = f"""server {{
    listen 80;
    server_name {fqdn};
    return 301 https://$host$request_uri;
}}

server {{
    listen 443 ssl http2;
    server_name {fqdn};
    root {panel_path}/public;
    index index.php;
    
    ssl_certificate /etc/letsencrypt/live/{fqdn}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{fqdn}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    
    {security_headers}
    
    location / {{
        try_files $uri $uri/ /index.php?$query_string;
    }}
    
    location ~ \\.php$ {{
        fastcgi_split_path_info ^(.+\\.php)(/.+)$;
        fastcgi_pass {php_socket};
        fastcgi_index index.php;
        include fastcgi_params;
        fastcgi_param PHP_VALUE "upload_max_filesize = 100M \\n post_max_size=100M";
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
        fastcgi_param HTTP_PROXY "";
        fastcgi_intercept_errors off;
        fastcgi_buffer_size 16k;
        fastcgi_buffers 4 16k;
        fastcgi_connect_timeout 300;
        fastcgi_send_timeout 300;
        fastcgi_read_timeout 300;
    }}
    
    location ~ /\\.ht {{
        deny all;
    }}
}}
"""
    else:
        # HTTP only
        nginx_conf = f"""server {{
    listen 80;
    server_name {fqdn};
    root {panel_path}/public;
    index index.php;
    
    {security_headers}
    
    location / {{
        try_files $uri $uri/ /index.php?$query_string;
    }}
    
    location ~ \\.php$ {{
        fastcgi_split_path_info ^(.+\\.php)(/.+)$;
        fastcgi_pass {php_socket};
        fastcgi_index index.php;
        include fastcgi_params;
        fastcgi_param PHP_VALUE "upload_max_filesize = 100M \\n post_max_size=100M";
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
        fastcgi_param HTTP_PROXY "";
        fastcgi_intercept_errors off;
        fastcgi_buffer_size 16k;
        fastcgi_buffers 4 16k;
        fastcgi_connect_timeout 300;
        fastcgi_send_timeout 300;
        fastcgi_read_timeout 300;
    }}
    
    location ~ /\\.ht {{
        deny all;
    }}
}}
"""
    
    config_path = Path(f"/etc/nginx/sites-available/pterodactyl.conf")
    config_path.write_text(nginx_conf)
    
    enabled_path = Path("/etc/nginx/sites-enabled/pterodactyl.conf")
    if enabled_path.exists():
        enabled_path.unlink()
    enabled_path.symlink_to(config_path)
    
    run("nginx -t", silent=True)
    run("systemctl restart nginx", silent=True)
    run("systemctl enable nginx", silent=True)
    
    ok("Nginx configured")

def setup_ssl(fqdn: str, email: str) -> bool:
    """Setup SSL with Let's Encrypt"""
    info("Setting up SSL...")
    
    try:
        import socket
        server_ip = requests.get("https://api.ipify.org", timeout=10).text.strip()
        domain_ip = socket.gethostbyname(fqdn)
        
        if domain_ip != server_ip:
            warn(f"Domain {fqdn} does not resolve to this server ({server_ip})")
            return False
    except Exception as e:
        warn(f"Could not verify DNS: {e}")
        return False
    
    run("apt install -y certbot", silent=True)
    
    run("systemctl stop nginx", silent=True)
    
    try:
        run(
            f"certbot certonly --standalone -d {fqdn} "
            f"--email {email} --agree-tos --non-interactive",
            silent=True,
            timeout=120
        )
        
        cron_job = "0 3 * * * certbot renew --quiet --nginx"
        existing_crontab = run("crontab -l 2>/dev/null || true", silent=True).stdout
        if cron_job not in existing_crontab:
            new_crontab = existing_crontab + f"\n{cron_job}\n"
            run(f"echo '{new_crontab}' | crontab -", silent=True)
        
        ok("SSL certificate generated")
        return True
        
    except subprocess.CalledProcessError:
        warn("SSL generation failed")
        run("systemctl start nginx", silent=True)
        return False

def setup_queue_worker(panel_path: Path):
    """Setup systemd queue worker"""
    info("Setting up queue worker...")
    
    service_content = f"""[Unit]
Description=Pterodactyl Queue Worker
After=redis-server.service

[Service]
User=www-data
Group=www-data
Restart=always
ExecStart=/usr/bin/php {panel_path}/artisan queue:work --queue=high,standard,low --sleep=3 --tries=3
StartLimitInterval=0

[Install]
WantedBy=multi-user.target
"""
    
    service_path = Path("/etc/systemd/system/pteroq.service")
    service_path.write_text(service_content)
    
    run("systemctl daemon-reload", silent=True)
    run("systemctl enable --now pteroq.service", silent=True)
    
    cron_cmd = f"* * * * * php {panel_path}/artisan schedule:run >> /dev/null 2>&1"
    existing_crontab = run("crontab -l 2>/dev/null || true", silent=True).stdout
    if cron_cmd not in existing_crontab:
        new_crontab = existing_crontab + f"\n{cron_cmd}\n"
        run(f"echo '{new_crontab}' | crontab -", silent=True)
    
    ok("Queue worker configured")

def configure_firewall():
    """Configure UFW firewall"""
    info("Configuring firewall...")
    
    try:
        result = run("which ufw", silent=True, check=False)
        if result.returncode != 0:
            warn("UFW not found, skipping firewall configuration")
            return
        
        run("ufw default deny incoming", silent=True)
        run("ufw default allow outgoing", silent=True)
        
        run("ufw allow 22/tcp comment 'SSH'", silent=True)
        
        run("ufw allow 80/tcp comment 'HTTP'", silent=True)
        run("ufw allow 443/tcp comment 'HTTPS'", silent=True)
        
        run("ufw allow 8080/tcp comment 'Wings Daemon'", silent=True)
        run("ufw allow 2022/tcp comment 'Wings SFTP'", silent=True)
        
        status = run("ufw status", silent=True).stdout
        if "Status: inactive" in status:
            run("echo 'y' | ufw enable", silent=True)
            ok("Firewall enabled and configured")
        else:
            ok("Firewall rules updated")
            
    except Exception as e:
        warn(f"Firewall configuration failed: {e}")

def save_credentials(panel_path: Path, db_config: DatabaseConfig, admin_config: AdminConfig, fqdn: str, ssl: bool):
    """Save credentials to secure file"""
    creds_file = panel_path / ".install_credentials"
    
    content = f"""# Pterodactyl Installation Credentials
# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}
# KEEP THIS FILE SECURE - DELETE AFTER SAVING TO PASSWORD MANAGER!

Panel URL:      https://{fqdn} (SSL: {'Enabled' if ssl else 'Disabled'})
Admin Email:    {admin_config.email}
Username:       {admin_config.username}
Password:       {admin_config.password}

Database:       {db_config.name}
DB User:        {db_config.user}
DB Password:    {db_config.password}
DB Host:        {db_config.host}:{db_config.port}

Installation Path: {panel_path}
Log File:       {LOG_FILE}

Security Notes:
1. Delete this file after saving credentials: rm {creds_file}
2. Change default admin email immediately after login
3. Enable 2FA in admin settings
4. Review firewall rules: ufw status verbose
"""
    
    creds_file.write_text(content)
    creds_file.chmod(0o600)
    
    info(f"Credentials saved to: {creds_file}")
    warn("DELETE THIS FILE after saving credentials to password manager!")

def panel_install():
    """Main panel installation flow"""
    print("\n" + "="*70)
    print("     PTERODACTYL PANEL INSTALLATION     ")
    print("="*70 + "\n")
    
    check_root()
    
    os_info = detect_os()
    
    print("\n" + colorize("Configuration", Colors.PURPLE))
    print("-" * 50)
    
    default_ip = requests.get("https://api.ipify.org", timeout=10).text.strip()
    fqdn_input = input(colorize(f"Enter FQDN or IP [default: {default_ip}]: ", Colors.CYAN)).strip()
    fqdn = fqdn_input if fqdn_input else default_ip
    
    use_ssl = False
    ssl_email = ""
    if not validate_ip(fqdn):
        ssl_choice = input(colorize("Configure SSL automatically? (Y/n): ", Colors.CYAN)).strip().lower()
        if ssl_choice in ['', 'y', 'yes']:
            while True:
                ssl_email = input(colorize("Enter email for Let's Encrypt: ", Colors.CYAN)).strip()
                if validate_email(ssl_email):
                    break
                warn("Invalid email format")
            use_ssl = True
    
    print("\n" + colorize("Admin User Configuration", Colors.PURPLE))
    admin_email = secure_input("Admin email: ")
    admin_username = secure_input("Admin username [admin]: ") or "admin"
    admin_password = secure_input("Admin password (auto-generate if empty): ", hidden=True)
    if not admin_password:
        admin_password = generate_secure_password(16)
        info(f"Generated admin password: {admin_password}")
    
    admin_config = AdminConfig(
        email=admin_email,
        username=admin_username,
        password=admin_password
    )
    
    db_config = DatabaseConfig.generate_secure("pterodactyl")
    
    print("\n" + colorize("Installation Summary:", Colors.PURPLE))
    print(f"  FQDN: {fqdn}")
    print(f"  SSL: {'Enabled' if use_ssl else 'Disabled'}")
    if use_ssl:
        print(f"  SSL Email: {ssl_email}")
    print(f"  Admin: {admin_config.username} ({admin_config.email})")
    print(f"  Database: {db_config.name}")
    
    confirm = input(colorize("\nProceed with installation? (y/N): ", Colors.YELLOW)).strip().lower()
    if confirm != 'y':
        err("Installation cancelled")
    
    install_dependencies(os_info)
    install_php(os_info)
    install_mariadb()
    setup_database(db_config)
    install_composer()
    panel_path = download_panel()
    install_panel_dependencies(panel_path)
    
    ssl_success = False
    if use_ssl:
        ssl_success = setup_ssl(fqdn, ssl_email)
    
    configure_panel(panel_path, db_config, admin_config, fqdn)
    install_nginx(fqdn, panel_path, ssl_success)
    setup_queue_worker(panel_path)
    configure_firewall()
    
    save_credentials(panel_path, db_config, admin_config, fqdn, ssl_success)
    
    print("\n" + colorize("="*70, Colors.GREEN))
    print(colorize("     INSTALLATION COMPLETE!", Colors.GREEN))
    print(colorize("="*70, Colors.GREEN))
    print(f"\n  Panel URL:      https://{fqdn}" if ssl_success else f"\n  Panel URL:      http://{fqdn}")
    print(f"  Admin Email:    {admin_config.email}")
    print(f"  Username:       {admin_config.username}")
    print(f"  Password:       [SECURED - see credentials file]")
    print(f"\n  Credentials:    {panel_path}/.install_credentials")
    print(f"  Log File:       {LOG_FILE}")
    print(colorize("\n  IMPORTANT: Delete credentials file after saving!", Colors.RED))
    print(colorize("  rm " + str(panel_path / ".install_credentials"), Colors.YELLOW))
    print("\n" + colorize("="*70, Colors.GREEN))

def phpmyadmin_install():
    """phpMyAdmin installation"""
    print("\n" + "="*70)
    print("     PHPMYADMIN INSTALLATION     ")
    print("="*70 + "\n")
    
    check_root()
    
    info("Installing phpMyAdmin...")
    run("apt update -y", silent=True)
    run("apt install -y phpmyadmin", silent=True)
    
    info("Configuring secure access...")
    
    random_port = secrets.randbelow(9000) + 1000
    
    conf = f"""
# phpMyAdmin - Secure Access Only via SSH Tunnel
# Access: ssh -L {random_port}:localhost:80 user@server
# Then: http://localhost:{random_port}/phpmyadmin

location /phpmyadmin {{
    # Localhost only - require SSH tunnel
    allow 127.0.0.1;
    deny all;
    
    # Additional basic auth
    auth_basic "Restricted Admin Area";
    auth_basic_user_file /etc/nginx/.pma_pass;
    
    root /usr/share/phpmyadmin;
    index index.php;
    
    location ~ ^/phpmyadmin/(.*\\.php)$ {{
        alias /usr/share/phpmyadmin/$1;
        fastcgi_pass unix:/run/php/php8.3-fpm.sock;
        fastcgi_param SCRIPT_FILENAME $request_filename;
        include fastcgi_params;
    }}
    
    location ~ /\\.ht {{
        deny all;
    }}
}}
"""
    
    snippets_dir = Path("/etc/nginx/snippets")
    snippets_dir.mkdir(parents=True, exist_ok=True)
    
    config_file = snippets_dir / "phpmyadmin.conf"
    config_file.write_text(conf)
    
    auth_file = Path("/etc/nginx/.pma_pass")
    if not auth_file.exists():
        info("Setting up basic authentication...")
        run("apt install -y apache2-utils", silent=True)
        
        auth_user = secure_input("phpMyAdmin auth username: ")
        run(f"htpasswd -cb /etc/nginx/.pma_pass {auth_user} {generate_secure_password(12)}", silent=True)
        info(f"Generated random password in {auth_file}")
        ok("Basic auth configured")
    
    nginx_conf = Path("/etc/nginx/sites-available/pterodactyl.conf")
    if nginx_conf.exists():
        content = nginx_conf.read_text()
        if "phpmyadmin.conf" not in content:
            content = content.rstrip()
            if content.endswith("}"):
                content = content[:-1] + "    include /etc/nginx/snippets/phpmyadmin.conf;\n}"
                nginx_conf.write_text(content)
                run("nginx -t && systemctl reload nginx", silent=True)
    
    ok("phpMyAdmin installed securely")
    print("\n" + colorize("Access Instructions:", Colors.CYAN))
    print(f"  1. Create SSH tunnel: ssh -L {random_port}:localhost:80 your-server")
    print(f"  2. Open browser: http://localhost:{random_port}/phpmyadmin")
    print(f"  3. Check auth file for credentials: sudo cat /etc/nginx/.pma_pass")
    print(colorize("\n  WARNING: Never expose phpMyAdmin to public internet!", Colors.RED))

def import_eggs():
    """Import game server eggs via API"""
    print("\n" + "="*70)
    print("     IMPORT GAME SERVER EGGS")
    print("="*70 + "\n")
    
    panel_url = secure_input("Panel URL (https://panel.example.com): ").rstrip("/")
    api_key = getpass.getpass(colorize("Application API key: ", Colors.CYAN))
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(
            f"{panel_url}/api/application/nests",
            headers=headers,
            timeout=10,
            verify=True
        )
        response.raise_for_status()
        nests_data = response.json()["data"]
        ok(f"Connected to panel. Found {len(nests_data)} nests.")
    except Exception as e:
        err(f"Failed to connect to panel: {e}")
    
    eggs_dir = Path("/tmp/pterodactyl-eggs")
    if eggs_dir.exists():
        shutil.rmtree(eggs_dir)
    
    info("Downloading official eggs repository...")
    run(f"git clone --depth 1 https://github.com/pterodactyl/eggs.git {eggs_dir}", 
        silent=True, timeout=60)
    
    nest_mapping = {}
    for nest in nests_data:
        nest_name = nest["attributes"]["name"].lower().replace(" ", "_")
        nest_mapping[nest_name] = nest["attributes"]["id"]
    
    egg_files = list(eggs_dir.rglob("egg-*.json"))
    info(f"Found {len(egg_files)} eggs in repository")
    
    categories = {}
    for egg_file in egg_files:
        category = egg_file.parent.parent.name
        if category not in categories:
            categories[category] = []
        categories[category].append(egg_file)
    
    print("\n" + colorize("Available Categories:", Colors.PURPLE))
    for i, category in enumerate(sorted(categories.keys()), 1):
        print(f"  {i}. {category.title()} ({len(categories[category])} eggs)")
    
    try:
        choice = int(secure_input("\nSelect category number: ")) - 1
        selected_category = sorted(categories.keys())[choice]
    except (ValueError, IndexError):
        err("Invalid selection")
    
    eggs = categories[selected_category]
    print(f"\nFound {len(eggs)} eggs in {selected_category}")
    
    import_mode = secure_input("Import (a)ll or (s)elect individually? [a]: ").lower() or "a"
    
    imported = 0
    failed = 0
    
    for egg_file in eggs:
        egg_name = egg_file.stem.replace("egg-", "").replace("_", " ").title()
        
        if import_mode == "s":
            confirm = secure_input(f"Import {egg_name}? (y/n/q): ").lower()
            if confirm == "q":
                break
            if confirm != "y":
                continue
        
        try:
            egg_data = json.loads(egg_file.read_text())
            
            egg_category = egg_data.get("meta", {}).get("category", selected_category)
            nest_id = None
            
            for nest_name, nid in nest_mapping.items():
                if egg_category.lower() in nest_name or nest_name in egg_category.lower():
                    nest_id = nid
                    break
            
            if not nest_id:
                nest_id = nests_data[0]["attributes"]["id"]
                warn(f"No nest match for {egg_name}, using default nest")
            
            response = requests.post(
                f"{panel_url}/api/application/nests/{nest_id}/eggs/import",
                headers=headers,
                json=egg_data,
                timeout=30,
                verify=True
            )
            
            if response.status_code in [200, 201, 204]:
                ok(f"Imported: {egg_name}")
                imported += 1
            elif response.status_code == 409:
                warn(f"Already exists: {egg_name}")
            else:
                err(f"Failed {egg_name}: {response.status_code}")
                failed += 1
                
        except Exception as e:
            err(f"Error importing {egg_name}: {e}")
            failed += 1
        
        time.sleep(0.5)  # Rate limiting
    
    print(f"\n{colorize('Import Complete:', Colors.GREEN)}")
    print(f"  Imported: {imported}")
    print(f"  Failed: {failed}")
    print(f"  Skipped: {len(eggs) - imported - failed}")

def install_docker():
    """Install Docker CE"""
    info("Installing Docker...")
    
    run("apt remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true", 
        silent=True, check=False)
    
    run("apt install -y ca-certificates curl gnupg lsb-release", silent=True)
    
    run("install -m 0755 -d /etc/apt/keyrings", silent=True)
    run("curl -fsSL https://download.docker.com/linux/ubuntu/gpg | "
        "gpg --dearmor -o /etc/apt/keyrings/docker.gpg", silent=True)
    
    os_info = detect_os()
    arch = run("dpkg --print-architecture", silent=True).stdout.strip()
    
    run(f'echo "deb [arch={arch} signed-by=/etc/apt/keyrings/docker.gpg] '
        f'https://download.docker.com/linux/ubuntu {os_info.codename} stable" | '
        f'tee /etc/apt/sources.list.d/docker.list > /dev/null', silent=True)
    
    run("apt update -y", silent=True)
    run("apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin",
        silent=True, timeout=180)
    
    run("systemctl enable --now docker", silent=True)
    
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        run(f"usermod -aG docker {sudo_user}", silent=True, check=False)
        info(f"Added {sudo_user} to docker group (relogin required)")
    
    ok("Docker installed")

def auto_node():
    """Automated Wings node setup"""
    print("\n" + "="*70)
    print("     WINGS DAEMON AUTO-SETUP")
    print("="*70 + "\n")
    
    check_root()
    os_info = detect_os()
    
    if not os_info.supported:
        err("Unsupported OS for Wings installation")
    
    install_docker()
    
    info("Installing Wings...")
    run("mkdir -p /etc/pterodactyl /var/run/wings", silent=True)
    
    wings_path = "/usr/local/bin/wings"
    
    for attempt in range(1, 4):
        try:
            run(f"curl -fsSL -o {wings_path} "
                f"https://github.com/pterodactyl/wings/releases/latest/download/wings_linux_amd64",
                silent=True, timeout=60)
            
            result = run(f"file {wings_path}", silent=True)
            if "ELF" in result.stdout:
                break
        except:
            if attempt == 3:
                err("Failed to download Wings binary")
            time.sleep(3)
    
    run(f"chmod +x {wings_path}", silent=True)
    
    print("\n" + colorize("Node Configuration", Colors.PURPLE))
    panel_url = secure_input("Panel URL: ").rstrip("/")
    api_key = getpass.getpass(colorize("Application API key: ", Colors.CYAN))
    
    node_name = secure_input("Node name: ")
    fqdn = secure_input("Node FQDN (node.example.com): ")
    
    if not validate_fqdn(fqdn):
        warn("Invalid FQDN format")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    try:
        loc_response = requests.get(
            f"{panel_url}/api/application/locations",
            headers=headers,
            timeout=10
        )
        locations = loc_response.json().get("data", [])
        if locations:
            location_id = locations[0]["attributes"]["id"]
        else:
            loc_create = requests.post(
                f"{panel_url}/api/application/locations",
                headers=headers,
                json={"short": "default", "long": "Default Location"},
                timeout=10
            )
            location_id = loc_create.json()["attributes"]["id"]
    except Exception as e:
        location_id = 1  
    
    node_config = {
        "name": node_name,
        "description": "Auto-provisioned node",
        "location_id": location_id,
        "fqdn": fqdn,
        "scheme": "https",
        "behind_proxy": False,
        "maintenance_mode": False,
        "memory": 8192,
        "memory_overallocate": -1,
        "disk": 256000,
        "disk_overallocate": -1,
        "upload_size": 100,
        "cpu": 100,
        "cpu_overallocate": 0,
        "daemon_base": "/var/lib/pterodactyl/volumes",
        "daemon_sftp": 2022,
        "daemon_listen": 8080
    }
    
    try:
        response = requests.post(
            f"{panel_url}/api/application/nodes",
            headers=headers,
            json=node_config,
            timeout=30
        )
        response.raise_for_status()
        node_data = response.json()["attributes"]
        ok(f"Node '{node_name}' created in panel")
    except Exception as e:
        err(f"Failed to create node: {e}")
    
    config_url = node_data["configuration"]["config_url"]
    try:
        config_response = requests.get(config_url, headers=headers, timeout=30)
        config_response.raise_for_status()
        
        config_path = Path("/etc/pterodactyl/config.yml")
        config_path.write_text(config_response.text)
        config_path.chmod(0o600)
        ok("Node configuration downloaded")
    except Exception as e:
        err(f"Failed to download node config: {e}")
    
    service_content = f"""[Unit]
Description=Pterodactyl Wings Daemon
After=docker.service network-online.target
Wants=docker.service

[Service]
Type=simple
User=root
WorkingDirectory=/etc/pterodactyl
LimitNOFILE=4096
PIDFile=/var/run/wings/daemon.pid
ExecStart={wings_path}
ExecStop=/bin/kill -s SIGTERM $MAINPID
Restart=on-failure
RestartSec=5s
StartLimitInterval=600
StartLimitBurst=3

[Install]
WantedBy=multi-user.target
"""
    
    service_path = Path("/etc/systemd/system/wings.service")
    service_path.write_text(service_content)
    
    run("systemctl daemon-reload", silent=True)
    run("systemctl enable --now wings", silent=True)
    
    time.sleep(2)
    
    status = run("systemctl is-active wings", silent=True, check=False)
    if status.stdout.strip() == "active":
        ok("Wings is running!")
    else:
        warn("Wings may have failed to start. Check: journalctl -u wings -n 50")
    
    print("\n" + colorize("Node Setup Complete:", Colors.GREEN))
    print(f"  Node: {node_name}")
    print(f"  FQDN: {fqdn}")
    print(f"  Config: /etc/pterodactyl/config.yml")
    print(f"  Service: systemctl status wings")
    print(f"  Logs: journalctl -u wings -f")

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Pterodactyl Auto-Deploy Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sudo python3 setup.py          # Interactive menu
  sudo python3 setup.py --panel    # Install panel only
  sudo python3 setup.py --wings    # Install wings only
  sudo python3 setup.py --full     # Full installation
        """
    )
    
    parser.add_argument("--panel", action="store_true", help="Install panel only")
    parser.add_argument("--wings", action="store_true", help="Install wings only")
    parser.add_argument("--full", action="store_true", help="Full installation (panel + wings)")
    parser.add_argument("--phpmyadmin", action="store_true", help="Install phpMyAdmin")
    parser.add_argument("--eggs", action="store_true", help="Import game eggs")
    parser.add_argument("--version", action="version", version="%(prog)s 2.0")
    
    args = parser.parse_args()
    
    print(colorize("""
 :::=======  :::====  :::====  :::==== ::: :::= ===
 ::: === === :::  === :::  === :::==== ::: :::=====
 === === === ======== =======    ===   === ========
 ===     === ===  === === ===    ===   === === ====
 ===     === ===  === ===  ===   ===   === ===  ===
                                                   
                                                                                
    """, Colors.CYAN))
    
    print("  Pterodactyl Installer v2.0 | Martin 2026")
    print(f"  Log: {LOG_FILE}\n")
    
    if args.panel:
        panel_install()
    elif args.wings:
        auto_node()
    elif args.full:
        panel_install()
        print("\n" + colorize("Waiting 30 seconds for panel to initialize...", Colors.YELLOW))
        time.sleep(30)
        auto_node()
    elif args.phpmyadmin:
        phpmyadmin_install()
    elif args.eggs:
        import_eggs()
    else:
        print(colorize("Main Menu:", Colors.PURPLE))
        print("  1. Install Panel")
        print("  2. Install phpMyAdmin ")
        print("  3. Import Game Eggs")
        print("  4. Auto Node Setup (Wings)")
        print("  5. Full Installation (Panel + Wings)")
        print("  0. Exit")
        
        try:
            choice = secure_input("\nSelect option: ")
            
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
                print("\n" + colorize("Waiting 30 seconds for panel to initialize...", Colors.YELLOW))
                time.sleep(30)
                auto_node()
            elif choice == "0":
                print("Exiting...")
                sys.exit(0)
            else:
                err("Invalid option")
        except KeyboardInterrupt:
            print("\n\nCancelled by user")
            sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception("Fatal error")
        err(f"Unexpected error: {str(e)}")
