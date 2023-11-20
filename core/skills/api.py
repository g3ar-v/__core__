"""Skill Api

The skill api allows skills interact with eachother over the message bus
just like interacting with any other object.
"""
from core.messagebus.message import Message


class SkillApi:
    """SkillApi providing a simple interface to exported methods from skills

    Methods are built from a method_dict provided when initializing the skill.
    """

    bus = None

    @classmethod
    def connect_bus(cls, core_bus):
        """Registers the bus object to use."""
        cls.bus = core_bus

    def __init__(self, method_dict):
        self.method_dict = method_dict
        for key in method_dict:

            def get_method(k):
                def method(*args, **kwargs):
                    m = self.method_dict[k]
                    data = {"args": args, "kwargs": kwargs}
                    method_msg = Message(m["type"], data)
                    response = SkillApi.bus.wait_for_response(method_msg)
                    if response and response.data and "result" in response.data:
                        return response.data["result"]
                    else:
                        return None

                return method

            self.__setattr__(key, get_method(key))

    @staticmethod
    def get(skill):
        """Generate api object from skill id.
        Args:
            skill (str): skill id for target skill

        Returns:
            SkillApi
        """
        public_api_msg = "{}.public_api".format(skill)
        api = SkillApi.bus.wait_for_response(Message(public_api_msg))
        if api:
            return SkillApi(api.data)
        else:
            return None
