import sys
import time

from os.path import dirname, abspath

from core.audio.services import RemoteAudioBackend
from core.messagebus.message import Message
from core.util.log import LOG


sys.path.append(abspath(dirname(__file__)))
Mopidy = __import__('mopidypost').Mopidy


class MopidyService(RemoteAudioBackend):
    def _connect(self, message):
        """
            Callback method to connect to mopidy if server is not available
            at startup.
        """
        url = 'http://localhost:6680'
        if self.config is not None:
            url = self.config.get('url', url)
        try:
            self.mopidy = Mopidy(url)
        except Exception:
            if self.connection_attempts < 1:
                LOG.debug('Could not connect to server, will retry quietly')
            self.connection_attempts += 1
            time.sleep(10)
            self.bus.emit(Message('MopidyServiceConnect'))
            return

        LOG.info('Connected to mopidy server')

    def __init__(self, config, bus, name='mopidy'):
        self.connection_attempts = 0
        self.bus = bus
        self.config = config
        self.name = name

        self.mopidy = None
        self.bus.on('MopidyServiceConnect', self._connect)
        self.bus.emit(Message('MopidyServiceConnect'))

    def supported_uris(self):
        """
            Return supported uri's if mopidy server is found,
            otherwise return empty list indicating this service
            doesn't support anything.
        """
        if self.mopidy:
            return ['file', 'http', 'https', 'local', 'spotify', 'gmusic']
        else:
            return []

    def clear_list(self):
        self.mopidy.clear_list()

    def add_list(self, tracks):
        self.mopidy.add_list(tracks)

    def play(self, repeat=False):
        """ Start playback.

        TODO: Add repeat support.
        """
        self.mopidy.play()

    def stop(self):
        if self.mopidy.is_playing():
            self.mopidy.clear_list()
            self.mopidy.stop()
            return True
        else:
            return False

    def pause(self):
        self.mopidy.pause()

    def resume(self):
        self.mopidy.resume()

    def next(self):
        self.mopidy.next()

    def previous(self):
        self.mopidy.previous()

    def lower_volume(self):
        self.mopidy.lower_volume()

    def restore_volume(self):
        self.mopidy.restore_volume()

    def track_info(self):
        info = self.mopidy.currently_playing()
        ret = {}
        ret['name'] = info.get('name', '')
        if 'album' in info:
            ret['artist'] = info['album']['artists'][0]['name']
            ret['album'] = info['album'].get('name', '')
        else:
            ret['artist'] = ''
            ret['album'] = ''
        return ret


def load_service(base_config, bus):
    backends = base_config.get('backends', [])
    services = [(b, backends[b]) for b in backends
                if backends[b]['type'] == 'mopidy' and
                backends[b].get('active', True)]
    instances = [MopidyService(s[1], bus, s[0]) for s in services]
    return instances
