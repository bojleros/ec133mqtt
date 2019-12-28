# ec133mqtt

Mqtt connector for Enterius EC-133MB over rs485.


## Description

I have started this project since i wanted to connect my led dimmer with some home automation. Older project (ec133gw) was a relatively simple api gateway which was successfully used for a couple of months. It was ideal for usage with limited number of clients. Since i wanted to start with home assistant i needed more complex stuff.

## Initial assumptions

This project sends Modbus RTU messages over rs485 serial line. You can use various converters but USB<=>RS485 should be the most popular nowadays. EC-133MB accepts Modbus RTU frames according to the available documentation (unfortunately available only in Polish) and sends state updates. By design dimmer can be used for RGB 12V leds or 3 independent channels to control brightness of different light zones. Since my application does not use RGB i have runned into a problem with controllers (like home assistant) who were unable to control 3 channel dimmer without using RGB widgets. I wanted independent control of every channel so the only choice for me was to use dedicated sliders and buttons for every channel separately. This implies having a two separate topics (for commands and status) for each channel what makes six topics in total.


**I do not need RGB support at all! Feel free to submit your PR if you like to .**


## Configuration of environment

### Make sure you have a mqtt broker up and running.

You can use whatever image or installation method you like. To get it up qickly you can use one of my imagess https://github.com/bojleros/docker-mosquitto (look for dockeehub for armhf and x86_64 images).

### Prepare environment and start the docker image

This software is configured via environmental variables. I am trying to keep them self descriptive as much as i can:
https://github.com/bojleros/ec133mqtt/blob/master/app/main.py#L28

This is an example of environmental file:
```
# cat /ec133mqtt/env
CH0_COMMAND=lights/main_room/sofa/cmd
CH1_COMMAND=lights/main_room/table/cmd
CH2_COMMAND=lights/main_room/tv/cmd
CHTG_COMMAND=lights/main_room/tgcmd
CH0_STATE=lights/main_room/sofa/state
CH1_STATE=lights/main_room/table/state
CH2_STATE=lights/main_room/tv/state
CHTG_STATE=lights/main_room/tv/state-not-used
MQTT_ADDR=broker.localner
MQTT_USER=test
MQTT_PASS=test
```

As you can see each channel is given two topics. One for commands and second for state updates. It is designed to work with Home Assistant mqtt_json lights.
CHTG is a special case. As my living room has two entrances i wanted to implement a stair switch configuration. You can controll it by sending empty json here, payload is meaningles.

**Please plan your topic names carefully. Read MQTT manuals first.**


Let's start docker container that uses rs485 converter on /dev/ttyUSB0 and runs on arm7 (Rpi2 , possibly Rpi3):

```
docker run -d --device=/dev/ttyUSB0 --name ec133mqtt  --env-file /ec133mqtt/env bojleros/ec133mqtt-armhf:latest
```

In case of troubles use `docker logs ec133gw`.


### Configure your Home Assistant

First follow current configuration to get Hass running. Then make sure you have mqtt broker and mqtt_lights configured:

```
mqtt:
  broker: broker.localnet
  port: 1883
  keepalive: 15
  client_id: hass-clientid
  username: test
  password: test

light:
  - platform: mqtt_json
    name: "Main room TV"
    command_topic: "lights/main_room/tv/cmd"
    state_topic: "lights/main_room/tv/state"
    brightness: true
    qos: 1
    retain: true

  - platform: mqtt_json
    name: "Main room table"
    command_topic: "lights/main_room/table/cmd"
    state_topic: "lights/main_room/table/state"
    brightness: true
    qos: 1
    retain: true

  - platform: mqtt_json
    name: "Main room sofa"
    command_topic: "lights/main_room/sofa/cmd"
    state_topic: "lights/main_room/sofa/state"
    brightness: true
    qos: 1
    retain: true
```

### Setup any different mqtt clients you want ...


## Additional features

I do like to use retained messages since it restores light state after service restart. It is also much more easier to refresh status of sliders and buttons that way when new client kicks in. That's quite important if you are going to control your lights from remote location but unfortunately we cannot assure that each command message will contain all necessary fields (state and brightness).

There goes an edge case 1:

1. Channel brightness was set with a message `{'brightness': 123}`
2. Channel was off with message `{'state': 'OFF'}`
3. Channel was turned on again by `{'state': 'ON'}`
4. Now ec133mqtt gets restarted and reconnects command topics. It is not going to store its state using volumes and files since it is very dull method. We are going to use retained message instead but whoa ... we have to turn on the lights but no idea about target brightness at all !

There goes edge case 2:

1. Let's use one of popular android mqtt dashboards.
2. You are setting up one slider and button for every channel.
3. Slider uses 'brightness' field and button uses 'state'.
4. Both slider and button are using two topics , one for commands and one for state.
5. Slider and button are not aware of state of it's partner !
6. We are unable to send frame that always contain both field.
7. Edge case 1 , paragraph 4 becomes concern.

If we are considering updation of a sliders and buttons problem is solved. Current version of ec133mqtt always sends state updates with both keys available. It does not cover problem with updating state of ec133mqtt after restart therefore i it is likely that partial command messages are going to be:

1. Received from mqtt without changing the dimmer registers.
2. Having missing keys restored using a current state of dimmer.
3. Republished into the command topic by the ec133mqtt itself.
4. Processed as a fully

No further ideas so far.
