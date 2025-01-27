import os
import signal

from src.configuring.prime import Config


wsgi_app = Config.sgi.WSGI_APP
bind = f"{Config.sgi.HOST}:{Config.sgi.PORT}"
workers = int(Config.sgi.WORKERS_COUNT)
worker_class = Config.sgi.WORKER_CLASS
reload = bool(Config.sgi.AUTO_RELOAD)
timeout = int(Config.sgi.TIMEOUT)

def worker_int(worker):
    os.kill(worker.pid, signal.SIGINT)