import sys
from server import start_server
from client import start_client

if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("Usage:\n  python main.py server\n  python main.py client [server_ip]")
        sys.exit(1)
    port=12345
    if sys.argv[1].lower() == "server":
        start_server("0.0.0.0", port)
    elif sys.argv[1].lower() == "client":
        host = sys.argv[2] if len(sys.argv) > 2 else "localhost"
        start_client(host, port)
    else:
        print("Use 'server' or 'client'")