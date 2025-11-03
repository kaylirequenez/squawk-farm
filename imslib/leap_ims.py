#####################################################################
#
# This software is to be used for MIT's class Interactive Music Systems only.
# Since this file may contain answers to homework problems, you MAY NOT release it publicly.
#
#####################################################################

import threading
from collections import namedtuple

import leap
import numpy as np

from imslib.core import register_terminate_func

# LeapHand data members
LeapHand = namedtuple("LeapHand", ["id", "type", "palm_pos", "fingers"])


def leap_vec_to_numpy(leap_pos):
    "Convert leap's position vector to a numpy vector"
    return np.array((leap_pos.x, leap_pos.y, leap_pos.z))


def to_LeapHand(leap_hand):
    """Convert the native leap hand data structure into an easier-to-use IMS structure - LeapHand"""

    id = leap_hand.id
    hand_type = "left" if str(leap_hand.type) == "HandType.Left" else "right"
    palm_pos = leap_vec_to_numpy(leap_hand.palm.position)
    fingers = [
        leap_vec_to_numpy(leap_hand.digits[n].distal.next_joint) for n in range(5)
    ]

    return LeapHand(id, hand_type, palm_pos, fingers)


class LeapInterface:
    """
    An object that simplifies getting data for Ultraleap's Leap Motion 2.0
    """

    def __init__(self):
        # create the connection, setting it to NOT auto-poll and desktop mode.
        self.connection = leap.Connection()
        self.connection.connect(auto_poll=False)
        self.connection.set_tracking_mode(leap.TrackingMode.Desktop)

        # create a thread to grab leap data
        self.poll_thread = threading.Thread(target=self._poll_loop)
        self.running = True

        # hands data that is updated by the polling thread
        self.hands = []

        # for a clean shutdown, we need to tell the system to shutdown this thread nicely
        register_terminate_func(self._stop)

        # start the thread
        self.poll_thread.start()

    def status(self):
        """Get a useful status message from the leap driver. Returns a string that is one of:
        'not ready', 'device connected', or 'no device'"""

        if self.connection.get_status() != leap.enums.ConnectionStatus.Connected:
            return "not ready"
        else:
            devices = self.connection.get_devices()
            if len(devices):
                return "device connected"
            else:
                return "no device"

    def get_hands(self):
        """Returns the list of visible hands. Either 0, 1, or 2 in length"""
        return self.hands

    def _stop(self):
        self.running = False

    def _poll_loop(self):
        while self.running:
            try:
                evt = self.connection.poll(timeout=1)

                if evt.type == leap.EventType.Tracking:
                    self.hands = [to_LeapHand(h) for h in evt.hands]

            # a timeout error happens when the device is not connected.
            except leap.exceptions.LeapTimeoutError:
                pass

            # print any other exception if it happens
            except leap.LeapError as exc:
                print(type(exc))
