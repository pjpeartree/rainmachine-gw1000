# Personal weather station Ecowitt devices parser for the RainMachine sprinkler controller.
#
# This parser was created to avoid the use of cloud solutions, like WUnderground.com or
# Ecowitt.net (API not available yet). The parser establishes a direct connection between
# the Ecowitt and the RainMachine devices. You can still use WUnderground too but now you
# have two sources in case either one decides to change something or has a problem.
#
# Author: Pedro J. Pereira <pjpeartree@gmail.com>
#
# 20200209:
#   - Initial version using data from a GW1000 with WH3000SE sensor array
# 20200902:
#   - Check device name to avoid detection of unsupported local consoles.
#   - Try to find the device within 5 retries.
#   - Update discover socket timeout to 2 seconds.
#   - Reduce the arithmetic effort by using cumulative numerical total divided by number of observations.
#   - Store values with an UTC timestamp instead of a local timestamp.
# 20200903:
#   - Adding Battery Temperature sensor ids.
# 20200904:
#   - Increase the default min and max temperatures.
#   - Fix day max wind sensor byte size.
#   - New helper function to report observations into rainmachine.
#   - Move lived ata new day check into the perform function, for better code readability.
#
# LICENSE: GNU General Public License v3.0
# GitHub: https://github.com/pjpeartree/rainmachine-ecowitt
#

import socket
import struct
import time
import json
from datetime import datetime
from os import path

from RMParserFramework.rmParser import RMParser
from RMUtilsFramework.rmLogging import log
from RMUtilsFramework.rmTimeUtils import rmGetStartOfDay, rmGetStartOfDayUtc


class ECOWITT(RMParser):
    parserName = 'Ecowitt Parser'
    parserDescription = 'Ecowitt live personal weather station data feed'
    parserForecast = False
    parserHistorical = True
    parserEnabled = False
    parserDebug = False
    parserInterval = 60  # seconds
    # Device network settings
    IP_ADDRESS = 'IP Address'
    PORT = '_Port'
    DEVICE_NAME = '_Device Name'
    OBSERVATION_COUNTER = 'observations'
    # A collection of observations for the current day
    observations = {OBSERVATION_COUNTER: 0,
                    RMParser.dataType.TEMPERATURE: 0,
                    RMParser.dataType.MAXTEMP: -100,
                    RMParser.dataType.MINTEMP: 100,
                    RMParser.dataType.RH: 0,
                    RMParser.dataType.MAXRH: 0,
                    RMParser.dataType.MINRH: 100,
                    RMParser.dataType.WIND: 0,
                    RMParser.dataType.SOLARRADIATION: 0,
                    RMParser.dataType.RAIN: 0,
                    RMParser.dataType.PRESSURE: 0,
                    RMParser.dataType.TIMESTAMP: 0}
    params = {IP_ADDRESS: 'auto discover', PORT: 45000, DEVICE_NAME: 'unknown'}
    # Current execution start of day timestamp
    liveDataTimestamp = 0

    # noinspection PyUnusedLocal
    def isEnabledForLocation(self, tz, lat, lon):
        try:
            # Check if the current ip is valid
            socket.inet_aton(str(self.params.get(self.IP_ADDRESS)))
            return self.parserEnabled
        except socket.error:
            # The current ip is invalid, we need to try to discover the device.
            return False

    def perform(self):
        # Try to connect, and if it fail try to auto discover the device
        if self._connect() or self._discover():
            # Successfully connected to the Ecowitt device, let's retrieve live data
            live_data = self._get_live_data()
            # Load current observations
            self._load_observations()
            # Check if the live data is for a new day
            if rmGetStartOfDay(self.liveDataTimestamp) != rmGetStartOfDay(
                    self.observations[RMParser.dataType.TIMESTAMP]):
                # Add the observations of yesterday
                self._report_observations()
                self._reset_observations()
            # Parser live data and add observations
            self._parse_live_data(live_data)
            self._report_observations()
            # Save current day sensor observations
            self._save_observations()

    # Connect to the Ecowitt device on the local network
    def _connect(self):
        try:
            # Check if the current ip is valid
            socket.inet_aton(str(self.params.get(self.IP_ADDRESS)))
        except socket.error:
            # The current ip is invalid, we need to try to discover the device.
            return False
        try:
            # Create a client to connect to the local network device
            self.connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.connection.settimeout(10)
            self.connection.connect((str(self.params.get(self.IP_ADDRESS)), self.params.get(self.PORT)))
            return True
        except socket.error:
            self._log_error('Error: unable to connect to the Ecowitt local network device')
            self.connection.close()
            return False

    # Discover the Ecowitt device on the local network.
    def _discover(self):
        try:
            # Create a socket to send and receive the CMD_BROADCAST command.
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(2)
            sock.bind(('', 59387))
        except socket.error:
            self._log_error('Error: unable to listening for discover packet')
            return False
        # Packet Format: HEADER, CMD_BROADCAST, SIZE, CHECKSUM
        packet = '\xff\xff\x12\x03\x15'
        # Try to find the device within 5 retries
        for n in range(5):
            try:
                # Sent a CMD_BROADCAST command
                sock.sendto(packet, ('255.255.255.255', 46000))
                packet = sock.recv(1024)
                # Check device name to avoid detection of other local Ecowiit/Ambient consoles
                device_name = packet[18:len(packet) - 1]
                if device_name.startswith('GW'):
                    self.params[self.DEVICE_NAME] = device_name
                    self.params[self.IP_ADDRESS] = '%d.%d.%d.%d' % struct.unpack('>BBBB', packet[11:15])
                    self.params[self.PORT] = struct.unpack('>H', packet[15: 17])[0]
                    return self._connect()
                else:
                    self.lastKnownError = 'Error: Unsupported local console: {}'.format(device_name)
            except socket.error:
                self.lastKnownError = 'Error: unable to find Ecowitt device on local network'
        self._log_error(self.lastKnownError)
        return False

    # Get current live conditions from the GW1000 device
    def _get_live_data(self):
        try:
            # Packet Format: HEADER, CMD_GW1000_LIVE_DATA, SIZE, CHECKSUM
            packet = '\xFF\xFF\x27\x03\x2A'
            # Send the command CMD_GW1000_LIVE_DATA to the local network device
            self.connection.sendall(packet)
            live_data = self.connection.recv(1024)
            now = datetime.now()
            self.liveDataTimestamp = time.mktime(now.timetuple()) + now.microsecond / 1e6
            return live_data
        except socket.error:
            self._log_error('Error: unable to retrieve live data from the local network device')
        finally:
            self.connection.close()

    # Parse Live Data packet by iterate over sensors
    def _parse_live_data(self, packet):
        data = packet[5: len(packet) - 1]
        index = 0
        size = len(data)
        while index < size:
            index = self._read_sensor(data, index)

    def _read_sensor(self, data, index):
        switcher = {
            b'\x01': (self._ignore_sensor, 2),  # Indoor Temperature (C), size in bytes:2
            b'\x02': (self._outdoor_temperature, 2),  # Outdoor Temperature (C), size in bytes:2
            b'\x03': (self._ignore_sensor, 2),  # Dew point (C), size in bytes:2
            b'\x04': (self._ignore_sensor, 2),  # Wind chill (C), size in bytes:2
            b'\x05': (self._ignore_sensor, 2),  # Heat index (C), size in bytes:2
            b'\x06': (self._ignore_sensor, 1),  # Indoor Humidity (%), size in bytes:1
            b'\x07': (self._outdoor_humidity, 1),  # Outdoor Humidity (%), size in bytes:1
            b'\x08': (self._ignore_sensor, 2),  # Absolutely Barometric (hpa), size in bytes:2
            b'\x09': (self._relative_barometric, 2),  # Relative Barometric (hpa), size in bytes:2
            b'\x0A': (self._ignore_sensor, 2),  # Wind Direction (360), size in bytes:2
            b'\x0B': (self._wind_speed, 2),  # Wind Speed (m/s), size in bytes:2
            b'\x0C': (self._ignore_sensor, 2),  # Gust Speed (m/s), size in bytes:2
            b'\x0D': (self._ignore_sensor, 2),  # Rain Event (mm), size in bytes:2
            b'\x0E': (self._ignore_sensor, 2),  # Rain Rate (mm/h), size in bytes:2
            b'\x0F': (self._ignore_sensor, 2),  # Rain hour (mm), size in bytes:2
            b'\x10': (self._rain_day, 2),  # Rain Day (mm), size in bytes:2
            b'\x11': (self._ignore_sensor, 2),  # Rain Week (mm), size in bytes:2
            b'\x12': (self._ignore_sensor, 4),  # Rain Month (mm), size in bytes:4
            b'\x13': (self._ignore_sensor, 4),  # Rain Year (mm), size in bytes:4
            b'\x14': (self._ignore_sensor, 4),  # Rain Totals (mm), size in bytes:4
            b'\x15': (self._light, 4),  # Light  (lux), size in bytes:4
            b'\x16': (self._ignore_sensor, 2),  # UV  (uW/m2), size in bytes:2
            b'\x17': (self._ignore_sensor, 1),  # UVI (0-15 index), size in bytes:1
            b'\x18': (self._ignore_sensor, 6),  # Date and time, size in bytes:6
            b'\x19': (self._ignore_sensor, 2),  # Day max_wind (m/s), size in bytes:2
            b'\x1A': (self._ignore_sensor, 2),  # Temperature 1 (C), size in bytes:2
            b'\x1B': (self._ignore_sensor, 2),  # Temperature 2 (C), size in bytes:2
            b'\x1C': (self._ignore_sensor, 2),  # Temperature 3 (C), size in bytes:2
            b'\x1D': (self._ignore_sensor, 2),  # Temperature 4 (C), size in bytes:2
            b'\x1E': (self._ignore_sensor, 2),  # Temperature 5 (C), size in bytes:2
            b'\x1F': (self._ignore_sensor, 2),  # Temperature 6 (C), size in bytes:2
            b'\x20': (self._ignore_sensor, 2),  # Temperature 7 (C), size in bytes:2
            b'\x21': (self._ignore_sensor, 2),  # Temperature 8 (C), size in bytes:2
            b'\x22': (self._ignore_sensor, 1),  # Humidity 1 0-100%, size in bytes:1
            b'\x23': (self._ignore_sensor, 1),  # Humidity 2 0-100%, size in bytes:1
            b'\x24': (self._ignore_sensor, 1),  # Humidity 3 0-100%, size in bytes:1
            b'\x25': (self._ignore_sensor, 1),  # Humidity 4 0-100%, size in bytes:1
            b'\x26': (self._ignore_sensor, 1),  # Humidity 5 0-100%, size in bytes:1
            b'\x27': (self._ignore_sensor, 1),  # Humidity 6 0-100%, size in bytes:1
            b'\x28': (self._ignore_sensor, 1),  # Humidity 7 0-100%, size in bytes:1
            b'\x29': (self._ignore_sensor, 1),  # Humidity 8 0-100%, size in bytes:1
            b'\x2A': (self._ignore_sensor, 2),  # PM2.5 1 (ug/m3), size in bytes:2
            b'\x2B': (self._ignore_sensor, 2),  # Soil Temperature_1 (C), size in bytes:2
            b'\x2C': (self._ignore_sensor, 1),  # Soil Moisture_1 (%), size in bytes:1
            b'\x2D': (self._ignore_sensor, 2),  # Soil Temperature_2 (C), size in bytes:2
            b'\x2E': (self._ignore_sensor, 1),  # Soil Moisture_2 (%), size in bytes:1
            b'\x2F': (self._ignore_sensor, 2),  # Soil Temperature_3 (C), size in bytes:2
            b'\x30': (self._ignore_sensor, 1),  # Soil Moisture_3 (%), size in bytes:1
            b'\x31': (self._ignore_sensor, 2),  # Soil Temperature_4 (C), size in bytes:2
            b'\x32': (self._ignore_sensor, 1),  # Soil Moisture_4 (%), size in bytes:1
            b'\x33': (self._ignore_sensor, 2),  # Soil Temperature_5 (C), size in bytes:2
            b'\x34': (self._ignore_sensor, 1),  # Soil Moisture_5 (%), size in bytes:1
            b'\x35': (self._ignore_sensor, 2),  # Soil Temperature_6 (C), size in bytes:2
            b'\x36': (self._ignore_sensor, 1),  # Soil Moisture_6 (%), size in bytes:1
            b'\x37': (self._ignore_sensor, 2),  # Soil Temperature_7 (C), size in bytes:2
            b'\x38': (self._ignore_sensor, 1),  # Soil Moisture_7 (%), size in bytes:1
            b'\x39': (self._ignore_sensor, 2),  # Soil Temperature_8 (C), size in bytes:2
            b'\x3A': (self._ignore_sensor, 1),  # Soil Moisture_8 (%), size in bytes:1
            b'\x3B': (self._ignore_sensor, 2),  # Soil Temperature_9 (C), size in bytes:2
            b'\x3C': (self._ignore_sensor, 1),  # Soil Moisture_9 (%), size in bytes:1
            b'\x3D': (self._ignore_sensor, 2),  # Soil Temperature_10 (C), size in bytes:2
            b'\x3E': (self._ignore_sensor, 1),  # Soil Moisture_10 (%), size in bytes:1
            b'\x3F': (self._ignore_sensor, 2),  # Soil Temperature_11 (C), size in bytes:2
            b'\x40': (self._ignore_sensor, 1),  # Soil Moisture_11 (%), size in bytes:1
            b'\x41': (self._ignore_sensor, 2),  # Soil Temperature_12 (C), size in bytes:2
            b'\x42': (self._ignore_sensor, 1),  # Soil Moisture_12 (%), size in bytes:1
            b'\x43': (self._ignore_sensor, 2),  # Soil Temperature_13 (C), size in bytes:2
            b'\x44': (self._ignore_sensor, 1),  # Soil Moisture_13 (%), size in bytes:1
            b'\x45': (self._ignore_sensor, 2),  # Soil Temperature_14 (C), size in bytes:2
            b'\x46': (self._ignore_sensor, 1),  # Soil Moisture_14 (%), size in bytes:1
            b'\x47': (self._ignore_sensor, 2),  # Soil Temperature_15 (C), size in bytes:2
            b'\x48': (self._ignore_sensor, 1),  # Soil Moisture_15 (%), size in bytes:1
            b'\x49': (self._ignore_sensor, 2),  # Soil Temperature_16 (C), size in bytes:2
            b'\x4A': (self._ignore_sensor, 1),  # Soil Moisture_16 (%), size in bytes:1
            b'\x4C': (self._ignore_sensor, 16),  # All_sensor lowbatt, size in bytes:16
            b'\x4D': (self._ignore_sensor, 2),  # 24h_avg pm25_ch1 (ug/m3), size in bytes:2
            b'\x4E': (self._ignore_sensor, 2),  # 24h_avg pm25_ch2 (ug/m3), size in bytes:2
            b'\x4F': (self._ignore_sensor, 2),  # 24h_avg pm25_ch3 (ug/m3), size in bytes:2
            b'\x50': (self._ignore_sensor, 2),  # 24h_avg pm25_ch4 (ug/m3), size in bytes:2
            b'\x51': (self._ignore_sensor, 2),  # PM2.5 2 (ug/m3), size in bytes:2
            b'\x52': (self._ignore_sensor, 2),  # PM2.5 3 (ug/m3), size in bytes:2
            b'\x53': (self._ignore_sensor, 2),  # PM2.5 4 (ug/m3), size in bytes:2
            b'\x58': (self._ignore_sensor, 1),  # Leak ch1 , size in bytes:1
            b'\x59': (self._ignore_sensor, 1),  # Leak ch2 , size in bytes:1
            b'\x5A': (self._ignore_sensor, 1),  # Leak ch3 , size in bytes:1
            b'\x5B': (self._ignore_sensor, 1),  # Leak ch4 , size in bytes:1
            b'\x60': (self._ignore_sensor, 1),  # Lightning distance 1-40KM, size in bytes:1
            b'\x61': (self._ignore_sensor, 4),  # Lightning detected_time (UTC), size in bytes:4
            b'\x62': (self._ignore_sensor, 4),  # Lightning power_time (UTC), size in bytes: 4
            b'\x63': (self._ignore_sensor, 3),  # Battery Temperature 1 (C), size in bytes: 3
            b'\x64': (self._ignore_sensor, 3),  # Battery Temperature 2 (C), size in bytes: 3
            b'\x65': (self._ignore_sensor, 3),  # Battery Temperature 3 (C), size in bytes: 3
            b'\x66': (self._ignore_sensor, 3),  # Battery Temperature 4 (C), size in bytes: 3
            b'\x67': (self._ignore_sensor, 3),  # Battery Temperature 5 (C), size in bytes: 3
            b'\x68': (self._ignore_sensor, 3),  # Battery Temperature 6 (C), size in bytes: 3
            b'\x69': (self._ignore_sensor, 3),  # Battery Temperature 7 (C), size in bytes: 3
            b'\x6A': (self._ignore_sensor, 3)  # Battery Temperature 8 (C), size in bytes: 3
        }
        sensor_id = data[index]
        sensor_reader, size = switcher.get(sensor_id, (self._unknown_sensor, 1))
        sensor_reader(data, index, size)
        return index + 1 + size

    def _outdoor_temperature(self, data, index, size):
        outdoor_temperature = read_int(data[index + 1: index + 1 + size], False, size) / 10.0  # Sensor Unit: degC
        self.observations[RMParser.dataType.TEMPERATURE] += outdoor_temperature  # RainMachine Unit: degC
        # Check if the outdoor_temperature is a new maximum
        if outdoor_temperature > self.observations[RMParser.dataType.MAXTEMP]:
            self.observations[RMParser.dataType.MAXTEMP] = outdoor_temperature
        # Check if the outdoor_temperature is a new minimum
        if outdoor_temperature < self.observations[RMParser.dataType.MINTEMP]:
            self.observations[RMParser.dataType.MINTEMP] = outdoor_temperature

    def _outdoor_humidity(self, data, index, size):
        outdoor_humidity = read_int(data[index + 1: index + 1 + size], False, size)  # Sensor Unit: %
        self.observations[RMParser.dataType.RH] += outdoor_humidity  # RainMachine Unit: %
        # Check if the outdoor_humidity is a new maximum
        if outdoor_humidity > self.observations[RMParser.dataType.MAXRH]:
            self.observations[RMParser.dataType.MAXRH] = outdoor_humidity
        # Check if the outdoor_humidity is a new minimum
        if outdoor_humidity < self.observations[RMParser.dataType.MINRH]:
            self.observations[RMParser.dataType.MINRH] = outdoor_humidity

    def _relative_barometric(self, data, index, size):
        relative_barometric = read_int(data[index + 1: index + 1 + size], False, size)  # Sensor Unit: dPa
        relative_barometric /= 100.0  # Conversion from dPa to kPa
        self.observations[RMParser.dataType.PRESSURE] += relative_barometric  # RainMachine Unit: kPa

    def _wind_speed(self, data, index, size):
        wind_speed = read_int(data[index + 1: index + 1 + size], False, size) / 10.0  # Sensor Unit: m/s
        self.observations[RMParser.dataType.WIND] += wind_speed  # RainMachine Unit: m/s

    def _rain_day(self, data, index, size):
        rain_day = read_int(data[index + 1: index + 1 + size], False, size) / 10.0  # Sensor Unit: mm
        # Preventive check, the rain amount should be cumulative and always bigger that the previous value.
        if rain_day > self.observations[RMParser.dataType.RAIN]:
            self.observations[RMParser.dataType.RAIN] = rain_day  # RainMachine Unit: mm

    def _light(self, data, index, size):
        light = read_int(data[index + 1: index + 1 + size], False, size) / 10.0  # Sensor Unit: lux
        solar_radiation = float(light) * 0.0079  # Convert lux into w/m2, 0.0079 is the ratio at sunlight spectrum
        solar_radiation *= 0.0036  # Convert w/m2 to MJ/m2/h, 1 W/m2 = 1 J/m2/Sec
        self.observations[RMParser.dataType.SOLARRADIATION] += solar_radiation  # RainMachine Unit: MJ/m2/day

    # noinspection PyMethodMayBeStatic,PyUnusedLocal
    def _ignore_sensor(self, data, index, size):
        log.debug('Ignoring Sensor Id: %02x' % ord(data[index]))

    # noinspection PyMethodMayBeStatic,PyUnusedLocal
    def _unknown_sensor(self, data, index, size):
        log.debug('Unknown Sensor Id found: %02x' % ord(data[index]))

    # Helper function to load in memory the observation data
    def _load_observations(self):
        if path.exists('observations.json'):
            try:
                self.observations = json.load(open('observations.json'))
            except IOError:
                self._log_error('Error: unable to load the Ecowiit parser data file')
        else:
            self._reset_observations()
        # Backward compatibility check for observation data file
        if ECOWITT.OBSERVATION_COUNTER not in self.observations:
            self._reset_observations()

    # Helper function to save the sensor observations data to disk.
    def _save_observations(self):
        try:
            json.dump(self.observations, open('observations.json', 'w'))
        except IOError:
            self._log_error('Error: unable to save the Ecowitt parser data file')

    # Helper function to reset the observation data
    def _reset_observations(self):
        self.observations = ECOWITT.observations
        self.observations[RMParser.dataType.TIMESTAMP] = self.liveDataTimestamp

    # Helper function to add observations
    def _report_observations(self):
        # Yesterday start of the day timestamp in UTC
        ts = rmGetStartOfDayUtc(self.observations[RMParser.dataType.TIMESTAMP])
        # Increment the number of observations
        self.observations[ECOWITT.OBSERVATION_COUNTER] += 1
        observations_counter = self.observations[ECOWITT.OBSERVATION_COUNTER]
        # Add the daily average temperature
        self.addValue(RMParser.dataType.TEMPERATURE, ts,
                      self.observations[RMParser.dataType.TEMPERATURE] / observations_counter)
        # Add the daily max temperature
        self.addValue(RMParser.dataType.MAXTEMP, ts, self.observations[RMParser.dataType.MAXTEMP])
        # Add the daily max temperature
        self.addValue(RMParser.dataType.MINTEMP, ts, self.observations[RMParser.dataType.MINTEMP])
        # Add the daily average humidity
        self.addValue(RMParser.dataType.RH, ts, self.observations[RMParser.dataType.RH] / observations_counter)
        # Add the daily max humidity
        self.addValue(RMParser.dataType.MAXRH, ts, self.observations[RMParser.dataType.MAXRH])
        # Add the daily min humidity
        self.addValue(RMParser.dataType.MINRH, ts, self.observations[RMParser.dataType.MINRH])
        # Add the daily average relative barometric pressure
        self.addValue(RMParser.dataType.PRESSURE, ts,
                      self.observations[RMParser.dataType.PRESSURE] / observations_counter)
        # Add the daily average wind speed
        self.addValue(RMParser.dataType.WIND, ts,
                      self.observations[RMParser.dataType.WIND] / observations_counter)
        # Add the daily rain amount
        self.addValue(RMParser.dataType.RAIN, ts, self.observations[RMParser.dataType.RAIN])
        # Add the daily average solar radiation
        self.addValue(RMParser.dataType.SOLARRADIATION, ts,
                      self.observations[RMParser.dataType.SOLARRADIATION] / observations_counter)
        log.debug(self.observations)

    # Helper function to log errors
    def _log_error(self, message, packet=None):
        if packet is not None:
            self.lastKnownError = message + ' ' + ''.join('\\x%02X' % ord(b) for b in packet)
        else:
            self.lastKnownError = message
        log.error(self.lastKnownError)


# Helper function to return an Integer from a network packet as BigEndian with different sizes, signed or unsigned.
def read_int(data, unsigned, size):
    if size == 1 and unsigned:
        return struct.unpack('>B', data[0:size])[0]
    elif size == 1 and not unsigned:
        return struct.unpack('>b', data[0:size])[0]
    elif size == 2 and unsigned:
        return struct.unpack('>H', data[0:size])[0]
    elif size == 2 and not unsigned:
        return struct.unpack('>h', data[0:size])[0]
    elif size == 4 and unsigned:
        return struct.unpack('>I', data[0:size])[0]
    elif size == 4 and not unsigned:
        return struct.unpack('>i', data[0:size])[0]
