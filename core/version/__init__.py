__version__ = "3.0.0"


class VersionManager:
    @staticmethod
    def get():
        return {"coreVersion": __version__, "enclosureVersion": None}
