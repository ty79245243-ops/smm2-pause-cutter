"""Rotating local error logs. No transmission or telemetry."""
from pathlib import Path
from logging.handlers import RotatingFileHandler
import logging,os,sys

logger=logging.getLogger('smm2_pause_cutter')

class PrivateFormatter(logging.Formatter):
    def format(self,record):
        text=super().format(record)
        home=str(Path.home())
        return text.replace(home,'<user>').replace(home.replace('\\','/'),'<user>')

def configure(version):
    folder=Path(os.environ.get('SMM2_PAUSE_CUTTER_LOG_DIR') or
                str(Path(os.environ.get('LOCALAPPDATA') or Path.home())/'SMM2PauseCutter'/'logs'))
    try:
        folder.mkdir(parents=True,exist_ok=True)
        handler=RotatingFileHandler(folder/'app.log',maxBytes=1024*1024,backupCount=2,encoding='utf-8')
        handler.setFormatter(PrivateFormatter('%(asctime)s %(levelname)s %(message)s'))
        logger.addHandler(handler);logger.setLevel(logging.INFO)
        logger.info('Application %s; Python %s',version,sys.version.split()[0])
        return folder/'app.log'
    except OSError:
        logger.addHandler(logging.NullHandler());return None
