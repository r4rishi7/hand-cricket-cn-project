import socket
import threading
import sys


def receive_messages(sock):
    """Background thread: print every message the server sends."""
    while True:
        try:
            data = sock.recv(4096)
            if not data:
                print("\n[Server closed the connection]")
                break
            print(data.decode(), end="", flush=True)
        except Exception:
            break
    # When server disconnects, exit cleanly
    sys.exit(0)


def start_client(host: str, port: int):
    conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        conn.connect((host, port))
    except Exception as e:
        print(f"[Error] Could not connect to {host}:{port} - {e}")
        conn.close()
        return

    print(f"Connected to {host}:{port}")

    # -- Receive thread ----------------------------------------------------
    t = threading.Thread(target=receive_messages, args=(conn,), daemon=True)
    t.start()

    # -- Send loop -----------------------------------------------------------
    while True:
        try:
            msg = input()  # blocks here waiting for user input
            if not msg:
                continue
            conn.sendall(msg.encode())
            if msg.strip().upper() == "EXIT":
                break
        except (EOFError, KeyboardInterrupt):
            break

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python client.py <host> <port>")
        sys.exit(1)
    start_client(sys.argv[1], int(sys.argv[2]))