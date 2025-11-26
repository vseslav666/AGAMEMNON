#install

sudo dnf update
sudo dnf install tacacs
sudo dnf install python3-pip

pip install tacacs_plus


mkdir /etc/tac_plus/
mkdir /var/log/tac_plus/



CONF_FILE="/etc/tac_plus/tac_plus.conf"

cat > /etc/tac_plus/tac_plus.conf << 'EOF'
key = "secretkey123"

user = admin {
    login = cleartext "admin123"
    service = exec {
        priv-lvl = 15
    }
}

user = user1 {
    login = cleartext "password123"
    service = exec {
        priv-lvl = 1
    }
}

host = default {
    key = "secretkey123"
}
EOF


touch /var/log/tac_plus/tac_plus.log


cat > /usr/lib/systemd/system/tac_plus.service << 'EOF'


[Unit]
Description=TACACS+ IPv4 Daemon
After=network.target
After=crond.service
ConditionPathExists=/etc/tac_plus/tac_plus.conf

[Service]
LimitCORE=16G
StandardOutput=null

ExecStartPre=/usr/sbin/tac_plus \
  -C /etc/tac_plus/tac_plus.conf \
  -P

ExecStart=/usr/sbin/tac_plus \
  -C /etc/tac_plus/tac_plus.conf \
  -G

ExecReload=/bin/kill -HUP $MAINPID

Restart=always

[Install]
WantedBy=multi-user.target
EOF




systemctl enable tac_plus.service
systemctl start tac_plus.service