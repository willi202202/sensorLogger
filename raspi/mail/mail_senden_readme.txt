msmtp + mailutils installation:
sudo apt install msmtp msmtp-mta mailutils

erstelle file:
sudo nano /etc/msmtprc
sudo chown root:root /etc/msmtprc
sudo chmod 600 /etc/msmtprc

erstelle aliase:
sudo nano /etc/msmtp_aliases
sudo chmod 644 /etc/msmtp_aliases

set manual mode:
sudo update-alternatives --config mailx

testen:
echo "TEST DEFAULT" | msmtp -v -a default roman.willi@gmx.ch
echo "Mailrc-Test" | mail -s "Mailrc" roman.willi@gmx.ch

log anschauen:
tail -n 40 /var/log/msmtp.log
cat /var/log/msmtp.log