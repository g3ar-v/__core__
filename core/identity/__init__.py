import json
import time
import os

from core.filesystem import FileSystemAccess
from core.util.log import LOG
from core.util.combo_lock import ComboLock
identity_lock = ComboLock('/tmp/identity-lock')


class DeviceIdentity:
    def __init__(self, **kwargs):
        self.uuid = kwargs.get("uuid", "")
        self.access = kwargs.get("access", "")
        self.refresh = kwargs.get("refresh", "")
        self.expires_at = kwargs.get("expires_at", 0)

    def is_expired(self):
        return self.refresh and 0 < self.expires_at <= time.time()

    def has_refresh(self):
        return self.refresh != ""


class IdentityManager:
    __identity = None

    @staticmethod
    def _load():
        LOG.debug('Loading identity')
        try:
            identity_dir = FileSystemAccess('identity')
            if identity_dir.exists('identity2.json'):
                with identity_dir.open('identity2.json', 'r') as f:
                    IdentityManager.__identity = DeviceIdentity(**json.load(f))
            else:
                IdentityManager.__identity = DeviceIdentity()
        except Exception as e:
            LOG.exception(f'Failed to load identity file: {repr(e)}')
            IdentityManager.__identity = DeviceIdentity()

    @staticmethod
    def load(lock=True):
        try:
            if lock:
                identity_lock.acquire()
                IdentityManager._load()
        finally:
            if lock:
                identity_lock.release()
        return IdentityManager.__identity

    @staticmethod
    def save(login=None, lock=True):
        LOG.debug('Saving identity')
        if lock:
            identity_lock.acquire()
        try:
            if login:
                IdentityManager._update(login)
            with FileSystemAccess('identity').open('identity2.json', 'w') as f:
                json.dump(IdentityManager.__identity.__dict__, f)
                f.flush()
                os.fsync(f.fileno())
        finally:
            if lock:
                identity_lock.release()

    @staticmethod
    def _update(login=None):
        LOG.debug('Updaing identity')
        login = login or {}
        expiration = login.get("expiration", 0)
        IdentityManager.__identity.uuid = login.get("uuid", "")
        IdentityManager.__identity.access = login.get("accessToken", "")
        IdentityManager.__identity.refresh = login.get("refreshToken", "")
        IdentityManager.__identity.expires_at = time.time() + expiration

    @staticmethod
    def update(login=None, lock=True):
        if lock:
            identity_lock.acquire()
        try:
            IdentityManager._update()
        finally:
            if lock:
                identity_lock.release()

    @staticmethod
    def get():
        if not IdentityManager.__identity:
            IdentityManager.load()
        return IdentityManager.__identity
