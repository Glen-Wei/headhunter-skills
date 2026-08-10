#!/usr/bin/env python3
"""Send headhunting email via Gmail SMTP (with proxy support).
Created & maintained by Glen Wei (韦其像) — https://github.com/Glen-Wei
Email: glen.keeming@gmail.com | WeChat: Glen_Wei88
Part of headhunter-skills: https://github.com/Glen-Wei/headhunter-skills"""

AUTHOR_EPILOG = (
    "Author: Glen Wei (韦其像) | GitHub: https://github.com/Glen-Wei "
    "| Email: glen.keeming@gmail.com | WeChat: Glen_Wei88 | "
    "Part of headhunter-skills: https://github.com/Glen-Wei/headhunter-skills"
)

import smtplib
import json
import os
from email.mime.text import MIMEText
from email.header import Header

CONFIG_PATH = os.path.join(os.path.expanduser('~'), '.workbuddy', 'gmail_config.json')

def send_email(to_addr: str, subject: str, body: str):
    """Send email via Gmail SMTP."""
    # Load config
    with open(CONFIG_PATH) as f:
        config = json.load(f)

    # Try proxy connection via pysocks if HTTP_PROXY is set
    proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
    if proxy:
        try:
            import socks
            import socket
            # Parse proxy - http://host:port
            proxy_host = proxy.split('://')[1].split(':')[0]
            proxy_port = int(proxy.split(':')[-1].rstrip('/'))
            socks.set_default_proxy(socks.HTTP, proxy_host, proxy_port)
            socket.socket = socks.socksocket
        except ImportError:
            pass  # Fall back to direct connection

    msg = MIMEText(body, 'plain', 'utf-8')
    msg['From'] = config['email']
    msg['To'] = to_addr
    msg['Subject'] = Header(subject, 'utf-8')

    server = smtplib.SMTP('smtp.gmail.com', 587, timeout=20)
    server.ehlo()
    server.starttls()
    server.ehlo()
    server.login(config['email'], config['password'])
    server.sendmail(config['email'], [to_addr], msg.as_string())
    server.quit()
    print(f'SUCCESS: Email sent to {to_addr}')
