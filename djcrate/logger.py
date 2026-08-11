import os
import sys
import logging

app_data_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'DJ Crate')
os.makedirs(app_data_dir, exist_ok=True)
log_path = os.path.join(app_data_dir, 'dj_crate.log')

logger = logging.getLogger('DJCrate')
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Prevent duplicate handlers
if not logger.handlers:
    fh = logging.FileHandler(log_path, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

def exception_hook(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = exception_hook
