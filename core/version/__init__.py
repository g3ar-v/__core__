__version__ = "1.2.1"


class VersionManager:
    @staticmethod
    def get():
        return {"coreVersion": __version__, "enclosureVersion": None}
