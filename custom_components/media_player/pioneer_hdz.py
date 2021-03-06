"""
Support for Pioneer Network Receivers.
For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/media_player.pioneer/
"""
import logging
import telnetlib

import voluptuous as vol

from homeassistant.components.media_player import (
    SUPPORT_PAUSE, SUPPORT_SELECT_SOURCE, MediaPlayerDevice, PLATFORM_SCHEMA,
    SUPPORT_TURN_OFF, SUPPORT_TURN_ON, SUPPORT_VOLUME_MUTE, SUPPORT_VOLUME_SET,
    SUPPORT_PLAY)
from homeassistant.const import (
    CONF_HOST, STATE_OFF, STATE_ON, STATE_UNKNOWN, CONF_NAME, CONF_PORT,
    CONF_TIMEOUT)
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = 'Pioneer AVR HDZone'
DEFAULT_PORT = 8103   # telnet default 8102. Some Pioneer AVRs use 8102
DEFAULT_TIMEOUT = None

SUPPORT_PIONEER = SUPPORT_PAUSE | SUPPORT_VOLUME_SET | SUPPORT_VOLUME_MUTE | \
                  SUPPORT_TURN_ON | SUPPORT_TURN_OFF | \
                  SUPPORT_SELECT_SOURCE | SUPPORT_PLAY

### EDITED HIS SOURCE NAME TABLE OUT
### BELOW I USE THE pioneer.py METHOD OF GETTING SOURCE NAMES
### SOURCE NAMES ARE SAME ACROSS ZONES
#CONF_SOURCE_NAMES = 'source_names'
#DEFAULT_SOURCE_NAMES = {'Phono': '00', 'CD': '01', 'TUNER': '02', 'DVD': '04', 'TV': '05', 'SAT/CBL': '06', \
#                        'MULTI CH IN': '12', 'DVR/BDR': '15', 'iPod/USB': '17', 'HDMI 1': '19', 'HDMI 2': '20', \
#                        'HDMI 3': '21', 'HDMI 4': '22', 'HDMI 5': '23', 'HDMI 6': '24', 'HDMI 7': '34', \
#                        'Internet Radio': '38', 'Spotify': '53', 'Pandora': '41', 'Media Server': '44', 'BT Audio': '33'
#                       }

MAX_VOLUME = 81
MAX_SOURCE_NUMBERS = 36

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): cv.socket_timeout,
# cannot provide source name in schema as the table is gone
#    vol.Optional(CONF_SOURCE_NAMES, default=DEFAULT_SOURCE_NAMES): {cv.string: cv.string},
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the Pioneer platform."""
# this is not usable either because table is gone
#    source_names = config.get(CONF_SOURCE_NAMES)

    pioneer_hdz = PioneerDevice(
        config.get(CONF_NAME), config.get(CONF_HOST), config.get(CONF_PORT),
# duplicated the line to save original and remove source_names
#        config.get(CONF_TIMEOUT), source_names)
        config.get(CONF_TIMEOUT))

    if pioneer_hdz.update():
        add_devices([pioneer_hdz])


class PioneerDevice(MediaPlayerDevice):
    """Representation of a Pioneer device."""

    def __init__(self, name, host, port, timeout):
# duplicated line to save orig and remove source_names
#    def __init__(self, name, host, port, timeout, source_names):
        """Initialize the Pioneer device."""
        self._name = name
        self._host = host
        self._port = port
        self._timeout = timeout
        self._pwstate = 'ZEP1'
        self._volume = 0
        self._muted = False
        self._selected_source = ''
#        self._source_name_to_number = source_names
        self._source_name_to_number = {}
        self._source_number_to_name = {}

    @classmethod
    def telnet_request(cls, telnet, command, expected_prefix):
        """Execute `command` and return the response."""
        try:
            telnet.write(command.encode("ASCII") + b"\r")
        except telnetlib.socket.timeout:
            _LOGGER.debug("Pioneer command %s timed out", command)
            return None

        # The receiver will randomly send state change updates, make sure
        # we get the response we are looking for
        for _ in range(3):
            result = telnet.read_until(b"\r\n", timeout=0.2).decode("ASCII") \
                .strip()
            if result.startswith(expected_prefix):
                return result

        return None

    def telnet_command(self, command):
        """Establish a telnet connection and sends command."""
        try:
            try:
                telnet = telnetlib.Telnet(
                    self._host, self._port, self._timeout)
            except (ConnectionRefusedError, OSError):
                _LOGGER.warning("Pioneer %s refused connection", self._name)
                return
            telnet.write(command.encode("ASCII") + b"\r")
            telnet.read_very_eager()  # skip response
            telnet.close()
        except telnetlib.socket.timeout:
            _LOGGER.debug(
                "Pioneer %s command %s timed out", self._name, command)

    def update(self):
        """Get the latest details from the device."""
        try:
            telnet = telnetlib.Telnet(self._host, self._port, self._timeout)
        except (ConnectionRefusedError, OSError):
            _LOGGER.warning("Pioneer %s refused connection", self._name)
            return False

        pwstate = self.telnet_request(telnet, "?ZEP", "ZEP")
        if pwstate:
            self._pwstate = pwstate

        volume_str = self.telnet_request(telnet, "?HZV", "XV")
        self._volume = int(volume_str[2:]) / MAX_VOLUME if volume_str else None

        muted_value = self.telnet_request(telnet, "?HZM", "HZMUT")
        self._muted = (muted_value == "HZMUT0") if muted_value else None

        # Build the source name dictionaries if necessary
        if not self._source_name_to_number:
            for i in range(MAX_SOURCE_NUMBERS):

### previous dev used his table definition for source names... and left this loop in, but it did nothing
### stole the below from pioneer.py default component that queries source 01 to max/60 for source names
### since source names are same across zones, this gets all the default source names like the pioneer component does
                result = self.telnet_request(
                    telnet, "?RGB" + str(i).zfill(2), "RGB")

                if not result:
                    continue

                source_name = result[6:]
                source_number = str(i).zfill(2)
### above this line is from pioneer.py default component

                self._source_name_to_number[source_name] = source_number
                self._source_number_to_name[source_number] = source_name

        source_number = self.telnet_request(telnet, "?ZEA", "ZEA")

        if source_number:
            self._selected_source = self._source_number_to_name \
                .get(source_number[3:])
        else:
            self._selected_source = None

        telnet.close()
        return True

    @property
    def name(self):
        """Return the name of the device."""
        return self._name

    @property
    def state(self):
        """Return the state of the device."""
        if self._pwstate == "ZEP1":
            return STATE_OFF
        if self._pwstate == "ZEP0":
            return STATE_ON

        return STATE_UNKNOWN

    @property
    def volume_level(self):
        """Volume level of the media player (0..1)."""
        return self._volume

    @property
    def is_volume_muted(self):
        """Boolean if volume is currently muted."""
        return self._muted

    @property
    def supported_features(self):
        """Flag media player features that are supported."""
        return SUPPORT_PIONEER

    @property
    def source(self):
        """Return the current input source."""
        return self._selected_source

    @property
    def source_list(self):
        """List of available input sources."""
        return list(self._source_name_to_number.keys())

    @property
    def media_title(self):
        """Title of current playing media."""
        return self._selected_source

    def turn_off(self):
        """Turn off media player."""
        self.telnet_command("ZEF")

    def volume_up(self):
        """Volume up media player."""
        self.telnet_command("HZU")

    def volume_down(self):
        """Volume down media player."""
        self.telnet_command("HZD")

    def set_volume_level(self, volume):
        """Set volume level, range 0..1."""
        # 60dB max
        self.telnet_command(str(round(volume * MAX_VOLUME)).zfill(2) + "HZV")

    def mute_volume(self, mute):
        """Mute (true) or unmute (false) media player."""
        self.telnet_command("HZMO" if mute else "HZMF")

    def turn_on(self):
        """Turn the media player on."""
        self.telnet_command("ZEZ")

    def select_source(self, source):
        """Select input source."""
        self.telnet_command(self._source_name_to_number.get(source) + "ZEA")
