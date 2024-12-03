#!/usr/bin/env python3

import base64
import subprocess
import sys
import re

from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

PORT = 80
USERNAME = open(os.path.expanduser('~/KSIEMGOWY_HTTP_LOGIN')).read().strip()
PASSWORD = open(os.path.expanduser('~/KSIEMGOWY_HTTP_PASSWORD')).read().strip()


def replace_function(match):
    email = match.group(0)
    return f'<a href="/?who={email}">{email}</a>'


class BasicAuthHandler(BaseHTTPRequestHandler):

    def skladki(self, path, who=None, mode_raw=None):
        cmd = [] if who is None else [who]

        mode = "_csv" if mode_raw == "csv" else ""
        result = subprocess.check_output(["dues" + mode] + cmd)
        if mode_raw == "csv":
            return result
        h = b"""
        <form action="/">Szukaj: <input name="who"><input type="submit"></span>
        """
        if '?' in path:
            csv_add = '&mode=csv'
        else:
            csv_add = '?mode=csv'
        h += f'<a href="{path}{csv_add}">CSV</a><pre>'.encode()
        # replace e-mails with links to them
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        result = re.sub(email_pattern, replace_function, result.decode()).encode()
        return h + result

    def do_GET(self):
        # Sprawdzenie nagłówka autoryzacji
        auth_header = self.headers.get("Authorization")
        if auth_header is None or not self.authenticate(auth_header):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Protected"')
            self.end_headers()
            self.wfile.write(b"Unauthorized")
        else:
            self.send_response(200)

            query_components = parse_qs(urlparse(self.path).query)
            who = query_components.get("who", [None])[0]
            mode = query_components.get("mode", [None])[0]
            self.send_header("Content-type", "text/csv" if mode == 'csv' else 'text/html')
            self.end_headers()

            # sys.stderr.write(f"{query_components=}\n")

            self.wfile.write(self.skladki(self.path, who, mode))

    def authenticate(self, auth_header):
        auth_method, encoded_credentials = auth_header.split(" ", 1)
        if auth_method.lower() != "basic":
            return False

        decoded_credentials = base64.b64decode(encoded_credentials).decode(
            "utf-8"
        )
        username, password = decoded_credentials.split(":", 1)

        return username == USERNAME and password == PASSWORD

    def log_message(self, format, *args):
        return  # Disable logging


def run(server_class=HTTPServer, handler_class=BasicAuthHandler):
    server_address = ("", PORT)
    httpd = server_class(server_address, handler_class)
    print(f"Starting server on port {PORT}...")
    httpd.serve_forever()


if __name__ == "__main__":
    run()
