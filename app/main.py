#!/usr/bin/python3

import serial
import time
import os
import sys
import json
import signal
import threading
import math
from datetime import datetime
import modbus_tk.defines as cst
from modbus_tk import modbus_rtu
import paho.mqtt.publish as publish
import paho.mqtt.client as subscribe


def msg(text):
    """
    Function that prints timestamped messages on stdout

    :param text: Message body
    :return: It does not need to return anything
    """
    print("%s : %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"), text))


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
            'linearization': {
                'active': bool(os.environ.get('LINEARIZE', True)),
                'range': float(os.environ.get('LINEARIZE_RANGE', 255)),
                'offset': float(os.environ.get('LINEARIZE_OFFSET', 0.05)),
                'tau': float(os.environ.get('LINEARIZE_TAU', 0.55))
            },
            'command_topics': {
                '0': os.environ.get('CH0_COMMAND', ''),
                '1': os.environ.get('CH1_COMMAND', ''),
                '2': os.environ.get('CH2_COMMAND', ''),
                '3': os.environ.get('CHTG_COMMAND', '')
            },
            'state_topics': {
                '0': os.environ.get('CH0_STATE', ''),
                '1': os.environ.get('CH1_STATE', ''),
                '2': os.environ.get('CH2_STATE', ''),
                '3': os.environ.get('CHTG_STATE', '')
            }
        },
        'mqtt': {
            'address': os.environ.get('MQTT_ADDR', '127.0.0.1'),
            'port': os.environ.get('MQTT_PORT', 1883),
            'username': os.environ.get('MQTT_USER', None),
            'password': os.environ.get('MQTT_PASS', None),
            'qos': os.environ.get('MQTT_QOS', int(1))
        }
    }

    return conf


class Ec133:

    def __init__(self, serconf, ecconf, callback=None):
        self.serconf = serconf
        self.ecconf = ecconf
        self.ser = None
        self.rtu = None
        self.reinit_count = 3
        self.callback = callback
        self.brightness = [255] * 3
        self.register = [255] * 3
        self.chstate = ["ON"] * 3
        self.lock = threading.Lock()
        self.tgstate = "ON"
        self.tgbrightness = [0] * 3
        self.tgchstate = ["OFF"] * 3

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

    def _linearize(self, ch):

        linconf = self.ecconf.get('linearization')

        if linconf.get('active', False) is False:
            return

        ch = int(ch)
        new = self.register

        if self.register[ch] < 10:
            return

        # f(x) = range*(1-offset)*exp(-(1-(x/range))/tau) + range*offset
        exponent = (-1 * (1 - (float(new[ch]) / linconf['range']))) / linconf['tau']
        new[ch] = int(linconf['range']
                      * (1 - linconf['offset'])
                      * math.exp(exponent)
                      + (linconf['range'] * linconf['offset'])
                      )

        msg("Linearized as : %s" % str(new))
        self.register = new

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

        if ch == 3:
            if self.tgstate == "ON":
                # it is on , we are goint to off but first store curent settings
                self.tgbrightness = self.brightness
                self.tgstate = "OFF"
                self.tgchstate = self.chstate
                self.chstate = ["OFF"] * 3
            else:
                # it is off , we are goint to restore settings
                self.brightness = self.tgbrightness
                self.tgstate = "ON"
                self.chstate = self.tgchstate

            msg("Toggle command %s" % self.tgstate)
            for i in range(0, 3):
                payload['state'] = self.chstate[i]
                payload.pop('brightness', None)
                self._send(client, userdata, message, payload, i)

            return

        self._send(client, userdata, message, payload, ch)


    def _send(self, client, userdata, message, payload, ch):

        self.lock.acquire(blocking=True, timeout=-1)

        msg("Channel%s command: %s" % (ch, payload))

        if payload.get("brightness", False):
            self.brightness[ch] = int(payload['brightness'])
        else:
            payload['brightness'] = int(self.brightness[ch])

        if payload.get('state', 'ON') == 'ON':
            self.register[ch] = int(self.brightness[ch])
            self.tgstate = "ON"
            self.chstate[ch] = "ON"
        else:
            self.register[ch] = int(0)
            self.chstate[ch] = "OFF"

        self._linearize(ch)

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
            # raise e
        else:
            time.sleep(0.02)
            self.lock.release()
            if bool(self.callback) and ch < 3:
                self.callback(ch, payload)


class Mqtt:

    def __init__(self, mqconf, command_topics, state_topics, callback):
        self.mqconf = mqconf
        self.ctopics = command_topics
        self.stopics = state_topics
        self.callback = callback
        self.consumers = [None] * 4

    def __del__(self):
        msg("Stopping all mq connections")
        for h in self.consumers:
            if bool(h):
                del h

    class Consumer:

        def __init__(self, mqconf, channel, topic, msg_callback):
            self.mqconf = mqconf
            self.channel = str(channel)
            self.topic = topic
            self.msg_callback = msg_callback

            self.conn = subscribe.Client()
            self.conn.on_message = self.msg_callback
            self.conn.on_connect = self._on_connect
            self.conn.on_disconnect = self._on_disconnect
            self.conn.user_data_set({'channel': self.channel})

            if self.mqconf['username'] is not None:
                self.conn.username_pw_set(self.mqconf['username'],
                                          password=self.mqconf['password'])

            self._connect()
            # subscribe is executed via _on_connect
            self.conn.loop_start()

        def __del__(self):
            if bool(self.conn):
                msg("Channel%s : Closing connection" % self.channel)
                self.conn.loop_stop()
                self.conn.disconnect()
                del self.conn

        def _connect(self, depth=0):
            try:
                self.conn.connect(self.mqconf['address'], port=self.mqconf['port'], keepalive=15)
            except Exception as e:
                msg("Channel%s : Connection failed : %s" % (self.channel, str(e)))
                depth += 1
                if depth <= 60:
                    msg("Channel%s : Waiting 10 seconds before reconnecting ..." % self.channel)
                    time.sleep(10)
                    self._connect(depth)
                else:
                    msg("Channel%s : Reconnecting was failing for too long ..." % self.channel)
                    raise e

        def _subscribe(self):
            try:
                self.conn.subscribe(self.topic, qos=self.mqconf['qos'])
            except Exception as e:
                msg("Channel%s: Subscription exception : %s" % (self.channel, str(e)))
                raise e

        def _on_connect(self, client, userdata, flags, rc):
            msg("Channel%s : Connected" % self.channel)
            self._subscribe()

        def _on_disconnect(self, client, userdata, rc):
            msg("Channel%s : Disconnected" % self.channel)

    def consume_all(self):
        for ch, topic in self.ctopics.items():
            try:
                c = self.Consumer(self.mqconf, ch, topic, self.callback)
            except Exception as e:
                raise e
            else:
                self.consumers[int(ch)] = c

    def postback(self, ch, payload):
        auth = None
        if self.mqconf['username'] is not None:
            auth = {'username': self.mqconf['username'],
                    'password': self.mqconf['password']
                    }

        # homeassistant lack proper typing
        # on the other side json module is constantly puting double quotation marks around ints ...
        payload_str = "{\"state\": \"%s\", \"brightness\": %s}" % (payload['state'], payload['brightness'])

        try:
            publish.single(self.stopics[str(ch)],
                           hostname=self.mqconf['address'],
                           port=self.mqconf['port'],
                           auth=auth,
                           payload=payload_str,
                           qos=self.mqconf['qos'],
                           keepalive=15,
                           retain=True)
        except Exception as e:
            msg("Unable to send channel%s state update : %s" % (ch, e))
        else:
            msg("Channel%s state: %s" % (ch, payload_str))


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
    try:
        ec.connect()
    except Exception as e:
        msg(str(e))
        sys.exit(-1)

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
