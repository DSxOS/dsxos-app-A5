import logging
import requests
from datetime import datetime, timezone

class RemoteLogger:
    def __init__(self, log_file='logger.log', remote_url=None):
        self.remote_url = remote_url

        # Local logger
        self.logger = logging.getLogger('RemoteLogger')
        self.logger.setLevel(logging.INFO)
        
        # Log to file
        fh = logging.FileHandler(log_file)
        fh.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)

    def log(self, message, level='info'):
        """
        Logib sõnumi lokaalselt ja saadab kauglogisse (kui URL määratud).
        :param message: logiteade
        :param level: 'info', 'warning', 'error'
        """
        log_method = getattr(self.logger, level, self.logger.info)
        log_method(message)

        if self.remote_url:
            try:
                payload = {
                    "timestamp": datetime.now(timezone.utc),
                    "level": level,
                    "message": message
                }
                headers = {"Content-Type": "application/json"}
                requests.post(self.remote_url, json=payload, headers=headers, timeout=5)
            except Exception as e:
                self.logger.warning(f"Failed to send log: {e}")
