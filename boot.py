import time
time.sleep(1)

import gc
gc.disable()

import machine
import ubinascii

import config

machine.Pin(27, machine.Pin.OUT).off()
machine.Pin(14, machine.Pin.OUT).off()

sensor_status = machine.PWM(machine.Pin(27), freq=1, duty=0)
wifi_status = machine.PWM(machine.Pin(14), freq=1, duty=0)

print('Looking for sensors...')
sensor_status.duty(512)
i2c = machine.I2C(1)
attempts = 0
while True:
    time.sleep(1)
    scan = i2c.scan()
    print('Scanned: ', scan)
    if 92 in scan and 119 in scan:
        break
    if attempts >= config.RETRIES_BEFORE_REBOOT:
        machine.reset()

print('Found all sensors, scan finished!')
sensor_status.duty(1023)

import network
import ntptime

wlan = network.WLAN(network.STA_IF)

def get_wifi():
    import esp32
    SSIDb, PASSb = bytearray(256), bytearray(256)
    storage = esp32.NVS('WIFI')

    try: 
        storage.get_blob('SSID', SSIDb)
    except OSError:
        print('Failed to read SSID, setting SSID from config...')
        storage.set_blob('SSID', config.WLAN_SSID)
        storage.commit()
        SSIDb = config.WLAN_SSID.encode()
    try: 
        storage.get_blob('PASS', PASSb)
    except OSError:
        print('Failed to read PASS, setting PASS from config...')
        storage.set_blob('PASS', config.WLAN_PASS)
        storage.commit()
        PASSb = config.WLAN_PASS.encode()


    return (SSIDb.decode(), PASSb.decode())

def write_wifi(SSID, PASS):
    import esp32
    SSIDb, PASSb = bytearray(SSID), bytearray(PASS)
    storage = esp32.NVS('WIFI')

    storage.set_blob('SSID', SSIDb)
    storage.set_blob('PASS', PASSb)
    storage.commit()
    machine.reset()

def network_monitoring():
    global wlan, wifi_status
    SSID, PASS = get_wifi()
    print('Connecting to ', SSID)
    wlan.active(True)
    wlan.connect(SSID, PASS)
    
    status = False
    wifi_status.duty(512)
    last_alive = time.time()
    while True:
        time.sleep(1)
        if wlan.isconnected():
            last_alive = time.time()
            if status == False:
                wifi_status.duty(1023)
                print('WIFI connected!')
                status = True
                while True:
                    try:
                        ntptime.settime()
                        time_tuple = time.gmtime()
                        time_str = '{}.{:02}.{:02} {:02}:{:02}:{:02}'.format(*time_tuple[:6])
                        print('Set NTP time to ', time_str)
                        break
                    except:
                        continue
        else:
            if time.time() - last_alive > config.NO_WIFI_BEFORE_AP:
                break
            if status == True:
                wifi_status.duty(512)
                print('WIFI disconnected!')
                status = False
    wlan.active(False)
    
    print('WiFi connection failed, enabling access point...')
    wifi_status.freq(4)
    wifi_status.duty(512)
    access_point = network.WLAN(network.AP_IF)
    access_point.active(True)
    access_point.config(essid=config.AP_SSID, password=config.AP_PASS)
    access_point.config(authmode=3)
    time.sleep(config.AP_WAIT)
    print('AP did not receive a config, rebooting...')
    machine.reset()


import _thread
_thread.start_new_thread(network_monitoring, (), {})

import webrepl

webrepl.start(password=config.WEBREPL_PASS)

print('WebREPL started...')

while True:
    time.sleep(1)
    if wlan.isconnected():
        break

SSID, _ = get_wifi()
print('Connected to', SSID, '!')
print('MAC:', ubinascii.hexlify(wlan.config('mac')).decode())

sensor_status.deinit()
machine.Pin(27, machine.Pin.OUT).on()

print('boot.py finished. Handing off to main...')
