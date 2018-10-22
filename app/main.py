#!/usr/bin/env python3

import serial
import time
import sys
import os
import json
import signal
from datetime import datetime
import modbus_tk
import modbus_tk.defines as cst
from modbus_tk import modbus_rtu


def getenv():
    conf = {
        'serial': {
            'device': os.environ.get('UART_DEVICE', '/dev/ttyUSB0'),
            'baudrate': os.environ.get('UART_BAUD', 19200),
            "bytesize": os.environ.get('UART_BYTESIZE', 8),
            "parity": os.environ.get('UART_PARITY', "N"),
            "stopbits": os.environ.get('UART_STOPBITS', 1)
        },
        'ec133': {
            'addr': os.environ.get('EC133_ADDR', 1),
            'timeout': os.environ.get('EC133_TIMEOUT', 0.2),
            'command_topics': {
                'ch0': os.environ.get('CH0_COMMAND', ''),
                'ch1': os.environ.get('CH1_COMMAND', ''),
                'ch2': os.environ.get('CH2_COMMAND', '')
            },
            'state_topics': {
                'ch0': os.environ.get('CH0_STATE', ''),
                'ch1': os.environ.get('CH1_STATE', ''),
                'ch2': os.environ.get('CH2_STATE', '')
            }
        },
        'mqtt': {
            'address': os.environ.get('MQTT_ADDR', '127.0.0.1'),
            'port': os.environ.get('MQTT_PORT', 1883),
            'username': os.environ.get('MQTT_USER', None),
            'password': os.environ.get('MQTT_PASS', None)
        }
    }

    return conf


class SignalHandler:
    signum = False

    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, signum, frame):
        self.signum = signum


class Ec133:

    def __init__(self):

def main():
    """
    Main routine
    """

    conf = getenv()

    sig_handler = SignalHandler()

    while True:
        if (sig_handler.signum == signal.Signals['SIGINT'].value
                or sig_handler.signum == signal.Signals['SIGTERM'].value):
            break

        time.sleep(0.01)

    print("Stopping now on %s ..." % (signal.Signals(sig_handler.signum)).name)



if __name__ == "__main__":
    main()
