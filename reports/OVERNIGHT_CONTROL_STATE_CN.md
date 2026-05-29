# Overnight Control State

- workspace = `/opt/lpbot/lp-bot-v3-origin-check`
- git_head = `b0439792f8bf69fb371f34c5e734934e1c81db54`
- git_status = `?? reports/`
- allowed_shadow_daemon = `/opt/lpbot/lp-bot-v3/bin/lpbot-shadow --config=/opt/lpbot/lp-bot-v3/configs/config.shadow.toml`

## Process Snapshot

```text
lpbot    1949037  0.0  0.0  20296  6020 ?        Ss   10:11   0:00 /usr/lib/systemd/systemd --user
lpbot    1949038  0.0  0.0  21156  2716 ?        S    10:11   0:00 (sd-pam)
lpbot    2207510  0.0  0.2 1122928 29148 ?       Ssl  12:54   0:06 PM2 v7.0.1: God Daemon (/home/lpbot/.pm2)
dhcpcd   2727143  3.3  0.8 254788 102572 ?       Ss   18:16   0:03 postgres: main: lpbot lpbot_shadow 172.19.0.1(57996) idle
root     2730126  1.0  0.0  14744 10540 ?        Ss   18:17   0:00 sshd: lpbot [priv]
lpbot    2730270  0.0  0.0  15000  7136 ?        S    18:17   0:00 sshd: lpbot@notty
lpbot    2730320 32.4  0.2  41576 26412 ?        Ss   18:17   0:00 python3 /tmp/overnight_lifecycle_audit.py
dhcpcd   2730325  6.8  0.1 253732 18824 ?        Ss   18:17   0:00 postgres: main: lpbot lpbot_shadow 172.19.0.1(57054) idle
lpbot    2730335  700  0.0  12752  5316 ?        R    18:17   0:00 ps aux
lpbot    3778947  1.4  0.2 2070424 29380 ?       Ssl  May25  71:03 /opt/lpbot/lp-bot-v3/bin/lpbot-shadow --config=/opt/lpbot/lp-bot-v3/configs/config.shadow.toml
```
