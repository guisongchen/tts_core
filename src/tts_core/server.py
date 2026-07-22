import argparse
import logging
import os
import signal
import socket
import sys
import threading
import time

import uvicorn

from .api import app
from .config import HOST, PORT, SOCKET_PATH

logger = logging.getLogger("tts_core")


def _wait_for_socket(path: str, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if os.path.exists(path):
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                    s.connect(path)
                    return True
            except OSError:
                pass
        time.sleep(0.1)
    return False


def main():
    parser = argparse.ArgumentParser(description="TTSCore HTTP daemon")
    parser.add_argument(
        "--tcp",
        action="store_true",
        help=f"Listen on TCP {HOST}:{PORT} instead of Unix socket",
    )
    parser.add_argument(
        "--wait-ready",
        action="store_true",
        help="Print a ready message once the socket is accepting connections",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    if not args.tcp and os.path.exists(SOCKET_PATH):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                s.connect(SOCKET_PATH)
            logger.error("TTSCore is already running on %s", SOCKET_PATH)
            sys.exit(1)
        except (OSError, ConnectionRefusedError):
            os.unlink(SOCKET_PATH)

    config = uvicorn.Config(
        app,
        host=HOST if args.tcp else None,
        port=PORT if args.tcp else None,
        uds=None if args.tcp else SOCKET_PATH,
        log_level="info",
    )
    server = uvicorn.Server(config)

    def handle_signal(signum, frame):
        logger.info("Received signal %s, shutting down...", signum)
        server.should_exit = True

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        if args.wait_ready:
            def notify_ready():
                if args.tcp:
                    logger.info("TTSCore daemon ready (TCP mode)")
                    return
                ok = _wait_for_socket(SOCKET_PATH, timeout=10.0)
                if ok:
                    logger.info("TTSCore daemon ready")
                else:
                    logger.error("TTSCore daemon failed to start within timeout")
                    os._exit(1)

            threading.Thread(target=notify_ready, daemon=True).start()

        server.run()
    finally:
        if not args.tcp:
            try:
                os.unlink(SOCKET_PATH)
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main())
