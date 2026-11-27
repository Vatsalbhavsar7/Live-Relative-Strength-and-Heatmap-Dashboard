"""
tcp_bridge.py
-------------
Zero-Sudo TCP Bridge for MySQL:
Allows client devices on LAN/Wi-Fi to connect to MySQL on a Linux server without
requiring sudo privileges or modifying /etc/mysql/mysql.conf.d/mysqld.cnf.
Listens on an unprivileged port (default: 3307 on 0.0.0.0) and proxies traffic to 127.0.0.1:3306.
"""

import socket
import threading
from typing import Optional

_bridge_running = False
_bridge_server: Optional[socket.socket] = None


def _forward_stream(source: socket.socket, destination: socket.socket) -> None:
    try:
        while True:
            data = source.recv(8192)
            if not data:
                break
            destination.sendall(data)
    except Exception:
        pass
    finally:
        try:
            source.close()
        except Exception:
            pass
        try:
            destination.close()
        except Exception:
            pass


def start_tcp_bridge(
    listen_host: str = "0.0.0.0",
    listen_port: int = 3307,
    target_host: str = "127.0.0.1",
    target_port: int = 3306,
) -> bool:
    """
    Starts the non-root TCP bridge in a background daemon thread.
    Returns True if successfully started or already active.
    """
    global _bridge_running, _bridge_server

    if _bridge_running:
        return True

    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((listen_host, listen_port))
        server.listen(15)
        _bridge_server = server
        _bridge_running = True
    except Exception:
        # If port 3307 is already listening or bound, consider it active
        return False

    def _accept_loop():
        global _bridge_running
        while _bridge_running:
            try:
                client_sock, _ = server.accept()
                remote_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                remote_sock.connect((target_host, target_port))
                t1 = threading.Thread(target=_forward_stream, args=(client_sock, remote_sock), daemon=True)
                t2 = threading.Thread(target=_forward_stream, args=(remote_sock, client_sock), daemon=True)
                t1.start()
                t2.start()
            except Exception:
                if not _bridge_running:
                    break

    thread = threading.Thread(target=_accept_loop, daemon=True, name="ZeroSudoTCPBridge")
    thread.start()
    return True


def stop_tcp_bridge() -> None:
    """Cleanly stops the TCP bridge listener."""
    global _bridge_running, _bridge_server
    _bridge_running = False
    if _bridge_server:
        try:
            _bridge_server.close()
        except Exception:
            pass
        _bridge_server = None
