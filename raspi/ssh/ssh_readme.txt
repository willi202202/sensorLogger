schüssel erstellen:
sudo ssh-keygen -t ed25519

schlüssel koperen auf raspi:
ssh-copy-id -i ~/.ssh/raspi_key.pub raspiroman@192.168.1.203

anmelden:
ssh -i ~/.ssh/raspi_key raspiroman@192.168.1.203
oder mit port:
ssh -i ~/.ssh/raspi_key raspiroman@192.168.1.203 -p 4422
oder mit log:
ssh -i ~/.ssh/raspi_key raspiroman@192.168.1.203 -v -p 4422


set PasswordAuthentication auf "no" in file:
ebenfalls Port auf 4422 (oder files kopieren):
Deaktivieren von unnötigen Funktionen:
sudo nano /etc/ssh/sshd_config.d/50-cloud-init.conf
sudo nano /etc/ssh/sshd_config

start stop etc.:
sudo systemctl enable ssh.service
sudo systemctl disable ssh.service
sudo systemctl stop ssh.service
sudo systemctl start ssh.service
sudo systemctl restart ssh.service

check status:
sudo systemctl status ssh
sudo journalctl -u ssh.service

alle einstellungen anzeigen:
sudo sshd -T
