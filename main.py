import time
time.sleep(1)

import gc
gc.disable()

import machine
import esp32
import urequests
import json

from am2320 import AM2320
from bmp180 import BMP180
import config

am2320 = AM2320(i2c)
bmp180 = BMP180(i2c)
bmp180.oversample_sett = 0

last_send = 0
status_pin = machine.Pin(27, machine.Pin.OUT)
request_pin = machine.Pin(33, machine.Pin.OUT)

NVS = esp32.NVS('SAMPLES')
stored_samples = []
try:
    buffer = bytearray(1024*16)
    NVS.get_blob('samples', buffer)
    stored_samples = json.loads(buffer.decode())
except:
    pass

def get_token(token=None):
    refresh_token = None
    access_token = None
    expiration = None
    print('Getting new token...')
    try:
        gc.collect()
        request_pin.on()
        if token is None:
            payload = {
                    'grant_type': 'password',
                    'scope': 'trust',
                    'password': config.TB_PASS,
                    'username': config.TB_USER
            }
        else:
            payload = {
                'grant_type': 'refresh_token',
                'refresh_token': token
            }
        res = urequests.post(
            config.TB_HOST+'/oauth/token',
            data='&'.join([key+'='+value for key, value in payload.items()]),
            headers={
                'Authorization': 'Basic d2ViOnNlY3JldA==',
                'Content-Type': 'application/x-www-form-urlencoded'
            }
        )
        if res.status_code//100 != 2:
            print(res.status_code, res.text)
        else:
            refresh_token = res.json()['refresh_token']
            access_token = res.json()['access_token']
            expiration = res.json()['expires_in']+time.time()
    except Exception as e:
        print(e)
    finally:
        request_pin.off()
        try:
            res.close()
        except:
            pass
        gc.collect()
    return refresh_token, access_token, expiration

def run_iteration():
    global am2320, bmp180, last_send, status_pin, request_pin, stored_samples, NVS, refresh_token, access_token, expiration
    start_time = time.time()
    status_pin.off()
    retries = 0
    sleep = 0
    while True:
        if retries >= config.RETRIES_BEFORE_REBOOT:
            machine.reset()
        try:
            am2320.measure()
            am_tuple = (am2320.temperature(), am2320.humidity())
            bmp_tuple = (bmp180.temperature, bmp180.pressure, bmp180.altitude)
            break
        except:
            time.sleep_ms(sleep)
            retries += 1
            sleep += 1 if sleep == 0 else sleep
            continue
    
    
    time_tuple = time.gmtime()
    sample = {
        'mem_used': gc.mem_alloc(),
        'mem_free': gc.mem_free(),
        'am2320_temp': am_tuple[0],
        'am2320_humidity': am_tuple[1],
        'bmp180_temp': bmp_tuple[0],
        'bmp180_pressure': bmp_tuple[1],
        'bmp180_altitude': bmp_tuple[2],
        'timestamp': '{}-{:02}-{:02}T{:02}:{:02}:{:02}.{:03}Z'.format(*time_tuple[:7])
    }

    time_str = '{}.{:02}.{:02} {:02}:{:02}:{:02}'.format(*time_tuple[:6])
    print(time_str,
        '  > MEM: USED {:.2f} kB, FREE {:.2f} kB, {:.1%}'.format(gc.mem_alloc()/1000, gc.mem_free()/1000, gc.mem_alloc()/(gc.mem_alloc()+gc.mem_free())),
        '  > AM2320: {:.1f} C, {:.1f} %'.format(am_tuple[0], am_tuple[1]),
        '  > BMP180: {:.1f} C, {:.1f} Pa, {:.1f} m'.format(bmp_tuple[0], bmp_tuple[1], bmp_tuple[2]),
        sep='\n'
    )
    stored_samples.append(sample)
    try:
        blob = json.dumps(stored_samples).encode()
        try:
            NVS.erase_key('samples')
            NVS.commit()
            print('Erased old samples from NVS')
        except OSError:
            pass
        NVS.set_blob('samples', blob)
        NVS.commit()
        print('Saved samples to NVS, ', len(blob), ' bytes')
    except OSError:
        print('Failed to save samples to NVS')
        pass

    if (gc.mem_alloc() >= gc.mem_free()*3):
        used = gc.mem_alloc()
        print('Running GC...')
        gc.collect()
        print('Freed ', used-gc.mem_alloc(), 'B')

    if (time.time() - last_send)*1000 >= config.WAIT_BETWEEN_POSTS:
        if 'expiration' not in locals() or time.time() > expiration:
            if hasattr(config, 'TB_REFRESH_TOKEN'):
                refresh_token = config.TB_REFRESH_TOKEN
            if 'refresh_token' in locals():
                refresh_token, access_token, expiration = get_token(refresh_token)
            if 'access_token' not in locals() or access_token is None:
                refresh_token, access_token, expiration = get_token()
        try:
            gc.collect()
            print('Posting!')
            request_pin.on()
            res = urequests.post(
                '{}/api/v0/{}/write'.format(config.TB_HOST, config.TB_STREAM),
                json=[
                    dict(record, **{
                        '$type': 'weather_record',
                        'symbol': 'esp'+ubinascii.hexlify(wlan.config('mac')).decode()[:4],
                    })
                    for record in stored_samples
                ],
                headers={
                    'Authorization': 'bearer '+access_token,
                    'Content-Type': 'application/json'
                }
            )
            if res.status_code//100 != 2:
                print('Posting failed: ', res.status_code, res.text)
            else:
                print('Posted OK')
                stored_samples = []
        finally:
            request_pin.off()
            try:
                res.close()
            except:
                pass
            gc.collect()
            last_send = time.time()
    end_time = time.time()
    next_tick = (end_time-start_time)*1000 + config.WAIT
    time.sleep_ms(int(next_tick * 0.1))
    status_pin.on()
    time.sleep_ms(int(next_tick * 0.9))

while True:
    try: 
        run_iteration()
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(e)
        machine.reset()