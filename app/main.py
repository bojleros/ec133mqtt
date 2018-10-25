#!/usr/bin/python3

import serial
import time
import sys
import os
import json
import signal
import threading
from datetime import datetime
import modbus_tk
import modbus_tk.defines as cst
from modbus_tk import modbus_rtu
import paho.mqtt.publish as publish
import paho.mqtt.client as mqtt


def msg(text):
    print("%s : %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"), text))


def sigh(signum, frame):
    return


def getenv():
    conf = {
        'serial': {
            'port': os.environ.get('UART_PORT', '/dev/ttyUSB0'),
            'baudrate': os.environ.get('UART_BAUD', 19200),
            "bytesize": os.environ.get('UART_BYTESIZE', 8),
            "parity": os.environ.get('UART_PARITY', "N"),
            "stopbits": os.environ.get('UART_STOPBITS', 1)
        },
        'ec133': {
            'addr': os.environ.get('EC133_ADDR', 1),
            'timeout': os.environ.get('EC133_TIMEOUT', 0.2),
            'command_topics': {
                '0': os.environ.get('CH0_COMMAND', ''),
                '1': os.environ.get('CH1_COMMAND', ''),
                '2': os.environ.get('CH2_COMMAND', '')
            },
            'state_topics': {
                '0': os.environ.get('CH0_STATE', ''),
                '1': os.environ.get('CH1_STATE', ''),
                '2': os.environ.get('CH2_STATE', '')
            }
        },
        'mqtt': {
            'address': os.environ.get('MQTT_ADDR', '127.0.0.1'),
            'port': os.environ.get('MQTT_PORT', 1883),
            'username': os.environ.get('MQTT_USER', None),
            'password': os.environ.get('MQTT_PASS', None),
            'qos': os.environ.get('MQTT_QOS', int(0))
        }
    }

    return conf


class Ec133:

    def __init__(self, serconf, ecconf, callback=False):
        self.serconf = serconf
        self.ecconf = ecconf
        self.ser = False
        self.rtu = False
        self.reinit_count = 3
        self.callback = callback
        self.brightness = [255, 255, 255]
        self.register = [255, 255, 255]
        self.lock = threading.Lock()

    def __del__(self):
        msg("Closing serial device")
        if bool(self.rtu):
            del self.rtu
        if bool(self.ser):
            del self.ser

    def set_callback(self, callback):
        self.callback = callback

    def connect(self):
        """
        Method that establishes connection with encmods on the other end of a
        serial line. By default it has 3 retries.
        """
        i = self.reinit_count
        while i > 0:
            try:
                self.ser = serial.Serial(**self.serconf)
            except Exception as e:
                msg("Serial init attempt #%s failed" % i)
                time.sleep(0.2)
                i -= 1
                if i == 0:
                    raise e
            else:
                msg("Serial line opened")
                i = 0

        try:
            self.rtu = modbus_rtu.RtuMaster(self.ser)
            self.rtu.set_timeout(float(self.ecconf['timeout']))
        except Exception as e:
            msg("Unable to initialize RTU master")
            raise e

    def set_channel(self, client, userdata, message):

        ch = int(userdata['channel'])

        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except Exception as e:
            msg("Channel%s : Malformed json message : %s" % (ch, e))
            return

        if type(payload) is not dict:
            msg("Channel%s : mqtt_json format expected , got %s!" % (ch, type(payload)))
            return

        self.lock.acquire(blocking=True, timeout=-1)

        msg("Channel%s command: %s" % (ch, payload))

        if payload.get("brightness", False):
            self.brightness[ch] = int(payload['brightness'])
        else:
            payload['brightness'] = int(self.brightness[ch])

        if payload.get('state', 'ON') == 'ON':
            self.register[ch] = int(self.brightness[ch])
        else:
            self.register[ch] = int(0)

        try:
            self.rtu.execute(self.ecconf['addr'],
                             cst.WRITE_MULTIPLE_REGISTERS,
                             ch,
                             output_value=[self.register[ch]]
                             )
        except Exception as e:
            msg(str(e))
            time.sleep(0.2)
            self.lock.release()
            self.set_channel(client, userdata, message)
            #raise e
        else:
            time.sleep(0.02)
            if bool(self.callback):

                self.callback(ch, json.dumps(payload))
            self.lock.release()


class Mqtt:

    def __init__(self, mqconf, command_topics, state_topics, callback):
        self.mqconf = mqconf
        self.ctopics = command_topics
        self.stopics = state_topics
        self.callback = callback
        self.connhandlers = []

    def __del__(self):
        msg("Stopping all mq connections")
        for h in self.connhandlers:
            h.loop_stop()
            h.disconnect()

    def _consume_topic(self, channel):
        c = mqtt.Client()
        c.on_message = self.callback
        c.user_data_set({'channel': channel})
        if self.mqconf['username'] != None:
            c.username_pw_set(self.mqconf['username'], password=self.mqconf['password'])
        c.connect(self.mqconf['address'], port=self.mqconf['port'], keepalive=15)
        c.subscribe(self.ctopics[channel], qos=self.mqconf['qos'])
        c.loop_start()
        self.connhandlers.append(c)

    def consume_all(self):
        for ch, topic in self.ctopics.items():
            self._consume_topic(ch)

    def postback(self, ch, payload):
        auth = None
        if self.mqconf['username'] != None:
            auth = {'username': self.mqconf['username'],
                    'password': self.mqconf['password']
                    }

        try:
            publish.single(self.stopics[str(ch)],
                           hostname=self.mqconf['address'],
                           port=self.mqconf['port'],
                           auth=auth,
                           payload=payload,
                           qos=self.mqconf['qos'],
                           keepalive=15,
                           retain=True)
        except Exception as e:
            msg("Unable to send channel%s state update : %s" % (ch, e))
        else:
            msg("Channel%s state: %s" % (ch, payload))


def main():
    """
    Main routine
    """

    # signals are only used to break out of signal.pause()
    signal.signal(signal.SIGINT, (lambda signum, frame: None))
    signal.signal(signal.SIGTERM, (lambda signum, frame: None))

    msg("Start ...")
    conf = getenv()

    msg("Connect ec133")
    ec = Ec133(conf['serial'], conf['ec133'])
    ec.connect()

    msg("Consume mqtt topics")
    mq = Mqtt(conf['mqtt'], conf['ec133']['command_topics'],
              conf['ec133']['state_topics'], ec.set_channel)
    mq.consume_all()
    ec.set_callback(mq.postback)

    signal.pause()

    msg("Stopping now on signal ...")
    del mq
    del ec


if __name__ == "__main__":
    main()
