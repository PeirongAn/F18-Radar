import os
import sys


SERVER_DIR = os.path.dirname(os.path.dirname(__file__))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from joystick.joystick_websocket_controller import JoystickWebSocketController


class FakeJoystick:
    def __init__(self, pressed=None):
        self.pressed = set(pressed or [])

    def get_numaxes(self):
        return 2

    def get_numbuttons(self):
        return 8

    def get_numhats(self):
        return 1

    def get_axis(self, index):
        return 0.0

    def get_hat(self, index):
        return (0, 0)

    def get_button(self, index):
        return 1 if index in self.pressed else 0


def test_physical_button3_is_backend_button2_and_triggers_change():
    controller = JoystickWebSocketController()
    controller.joystick = FakeJoystick()
    released = controller._read_joystick()
    assert released["buttons"]["button2"] is False
    assert controller._has_significant_change(released) is True

    controller.joystick = FakeJoystick({2})
    pressed = controller._read_joystick()
    assert pressed["buttons"]["button2"] is True
    assert controller._has_significant_change(pressed) is True

    controller.joystick = FakeJoystick()
    released_again = controller._read_joystick()
    assert controller._has_significant_change(released_again) is True
