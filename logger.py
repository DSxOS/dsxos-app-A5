# logger.py

import logging
import requests
import json
import time

class LokiHandler(logging.Handler):
    def __init__(self, url, tags=None, level=logging.NOTSET):
        super().__init__(level)
        self.url = url
        self.tags = tags or {}

    def emit(self, record):
        try:
            log_entry = self.format(record)
            ts = str(int(time.time() * 1e9))  # nanoseconds timestamp
            payload = {
                "streams": [
                    {
                        "stream": self.tags,
                        "values": [[ts, log_entry]],
                    }
                ]
            }
            response = requests.post(
                self.url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=5,
            )
            response.raise_for_status()
        except Exception as e:
            print(f"[LokiHandler] Failed to send log to Loki: {e}")

def setup_logger(app_name="A5Runner", log_file="query.log", loki_url=None, loki_tags=None, level=logging.INFO):
    logger = logging.getLogger(app_name)
    logger.setLevel(level)
    logger.handlers = []  # Clear existing handlers if rerun

    # File Handler
    fh = logging.FileHandler(log_file)
    fh.setLevel(level)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)

    # Console Handler
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(ch)

    # Loki Handler (optional)
    if loki_url:
        loki_handler = LokiHandler(url=loki_url, tags=loki_tags)
        loki_handler.setLevel(level)
        loki_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(loki_handler)

    return logger
