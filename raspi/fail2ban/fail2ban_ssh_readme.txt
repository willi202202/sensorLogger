installation:
sudo apt install fail2ban

Konfiguration:
sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local
sudo -E gedit /etc/fail2ban/jail.local &
sudo nano /etc/fail2ban/jail.local &

Handling:
sudo systemctl status fail2ban
sudo fail2ban-client status sshd
sudo fail2ban-client unban --all
sudo systemctl stop fail2ban
sudo systemctl restart fail2ban
sudo journalctl -u fail2ban.service
sudo journalctl -u fail2ban.service --since "1 minute ago"

pcmanfm&

abfragen:
sudo fail2ban-client get sshd bantime
sudo fail2ban-client get sshd maxretry
sudo fail2ban-client get sshd findtime
sudo fail2ban-client get sshd action
who
cat .bash_history
sudo journalctl -u ssh.service


ssh keygenerierung:
ssh-keygen -t ed25519 -f ~/.ssh/raspi_key
ssh-copy-id -i ~/.ssh/raspi_key.pub raspiroman@192.168.1.100
ssh-copy-id -i ~/.ssh/raspi_key.pub raspiroman@roman.willi.my.to
sudo nano /etc/ssh/sshd_config
	PasswordAuthentication no
	PermitRootLogin no
sudo nano /etc/ssh/sshd_config.d/50-cloud-init.conf
	PasswordAuthentication no
sudo systemctl restart ssh
verbinden:
ssh -i ~/.ssh/raspi_key raspiroman@roman.willi.my.to


Check files:
sudo find / \
    -path /proc -prune -o \
    -path /sys -prune -o \
    -path /dev -prune -o \
    -path /run -prune -o \
    -path /tmp -prune -o \
    -path /var/cache -prune -o \
    -path /var/log -prune -o \
    -type f \
    -newermt "2025-11-27 23:30:00" \
    ! -newermt "2025-11-28 10:00:00" \
    -exec ls -ld --time-style=full-iso {} + 2>/dev/null | sort -k6,7