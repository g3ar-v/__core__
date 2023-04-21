from mycroft import MycroftSkill
from mycroft.util import LOG


class FinishedBootingSkill(MycroftSkill):
    # The constructor of the skill, which calls MycroftSkill's constructor
    def __init__(self):
        super(FinishedBootingSkill, self).__init__(name="FinishedBootingSkill")

    def initialize(self):
        self.add_event("mycroft.skills.initialized", self.handle_boot_finished)
        LOG.debug('add event handle boot finished')

    def handle_boot_finished(self):
        self.speak_dialog('finished.booting')
        LOG.debug('finished booting')


# The "create_skill()" method is used to create an instance of the skill.
# Note that it's outside the class itself.
def create_skill():
    return FinishedBootingSkill()
