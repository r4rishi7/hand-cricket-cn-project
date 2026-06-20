import socket as x
import threading
import sys
import os
import ssl
from pathlib import Path

# Guards ssl_sock.send() against being called concurrently from the main
# thread (typing) and a recv() happening in the receive thread. SSLSocket
# isn't guaranteed thread-safe for simultaneous operations, so a lock
# around writes (and reads, for symmetry) keeps things deterministic.
_sock_lock = threading.Lock()


def receive_messages(sock):
    while True:
        try:
            data = sock.recv(4096)
            if not data:
                print("\n[Disconnected from server]")
                break
            print(data.decode(errors="ignore"), end="", flush=True)
        except Exception:
            break
    # sys.exit(0) here would only raise SystemExit in *this* thread, since
    # it's a daemon thread — the main thread would stay parked at input()
    # forever. os._exit() terminates the whole process immediately.
    os._exit(0)


def start_client(host, port):
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.check_hostname = False  # self-signed cert, no real hostname to match
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    cert_path = Path(__file__).resolve().parent / "certs" / "server.crt"
    ctx.load_verify_locations(cafile=str(cert_path))

    raw = x.socket(x.AF_INET, x.SOCK_STREAM)
    try:
        raw.connect((host, port))
        ssl_sock = ctx.wrap_socket(raw, server_hostname=host)
    except ssl.SSLError as e:
        print(f"[SSL] Handshake failed: {e}")
        raw.close()
        return
    except Exception as e:
        print(f"Failed to connect: {e}")
        raw.close()
        return

    print(f"[SSL] Connected to {host}:{port}")
    print(f"[TLS] {ssl_sock.version()} / {ssl_sock.cipher()[0]}")

    t = threading.Thread(target=receive_messages, args=(ssl_sock,), daemon=True)
    t.start()

    while True:
        try:
            msg = input()
        except (KeyboardInterrupt, SystemExit, EOFError):
            break

        # The server reads the stream as newline-delimited messages — every
        # command MUST end in "\n" or it can get coalesced with whatever is
        # sent next. This is the actual fix for the original bug.
        try:
            with _sock_lock:
                ssl_sock.sendall((msg + "\n").encode())
        except (ssl.SSLError, OSError) as e:
            print(f"[Send failed, connection likely closed: {e}]")
            break

        if msg.strip().upper() == "EXIT":
            break

    try:
        ssl_sock.close()
    except Exception:
        pass


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python client.py <host> <port>")
        sys.exit(1)
    start_client(sys.argv[1], int(sys.argv[2]))