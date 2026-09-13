"""Standalone review page server: python3 review_server.py runs/<run_dir> [port]"""
import sys, time
from pathlib import Path
from hinge_bot.review import Queue, serve_in_thread
run = Path(sys.argv[1]); port = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
serve_in_thread(Queue(run / "queue.json"), run, port)
print(f"review page: http://127.0.0.1:{port}/", flush=True)
while True: time.sleep(60)
