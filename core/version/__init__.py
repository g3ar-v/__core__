__version__ = "2.0.0"


class VersionManager:
    @staticmethod
    def get():
        return {"coreVersion": __version__, "enclosureVersion": None}
