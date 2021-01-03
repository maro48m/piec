from machine import Pin, SPI, PWM, ADC
import utils
import utime
import usocket as socket
import select
import max7219
import sensors

import gc
import web

class Piec:
    def __init__(self):
        self.servo_pin = Pin(int(utils.get_config("servo_pin", 4)))
        self.servo = PWM(self.servo_pin, freq=50)
        self.sock = None
        utils.log_message('INIT 1')
        self.lh = -1
        self.lm = -1
        self.ltm = -1
        self.lum = -1
        self.time_update = 0

        self.spi = SPI(1, baudrate=10000000, polarity=0, phase=0)
        self.display_pin = Pin(int(utils.get_config("wyswietlacz_pin", 15)), Pin.OUT)
        self.display = max7219.Matrix8x8(self.spi, self.display_pin, 1)
        self.display.brightness(0)
        self.display.fill(0)
        self.display.show()

        self.button = Pin(utils.get_config("przycisk_pin", 5), Pin.IN, Pin.PULL_UP)
        self.btn_val = 1

        self.joy_val = 500
        self.edit_temp = 0

        self.state = 1  # 0-sleep, 1 - display, 2 - edit
        self.edit_state = 0
        self.adc = ADC(0)

        self.termometr = sensors.sensory()

        utils.wifi_disconnect()

    def led_write_number(self, val, move=0, dots=None):
        if dots is None:
            dots = []
        digits = {1: 48, 2: 109, 3: 121, 4: 51, 5: 91, 6: 95, 7: 112, 8: 127, 9: 123, 0: 126}
        values = []
        while val > 0:
            d = int(val % 10)
            val = int(val / 10)
            v = digits[d]
            values.append(v)
        values.reverse()
        pos = 8 - move
        i = len(values)
        for d in values:
            if dots.count(i) > 0:
                d += 128

            self.display._write(pos, d)
            pos -= 1
            i -= 1

    def set_temperature(self, new_temp, zapisz=True):
        czas = utils.czas()
        if zapisz is True:
            utils.set_config("piec_ostatnia_aktualizacja", czas)
        curr_temp = int(utils.get_config("piec_temperatura"))

        if curr_temp < new_temp <= (int(utils.get_config("piec_temperatura_max", 90)) - 5):
            set_temp = new_temp + 5
            self.servo.duty(utils.map_temp_to_servo(set_temp))
            utime.sleep_ms(1000)

        utils.log_message('SET TEMPERATURE: %s' % (str(new_temp)))
        self.servo.duty(utils.map_temp_to_servo(new_temp))
        utils.set_config("piec_temperatura", int(new_temp))
        if zapisz is True:
            utils.save_to_hist(new_temp, 'piec.hist')

        utime.sleep_ms(150)

        if self.state > 0:
            self.led_write_number(new_temp)

    def save_times(self, times):
        tms = {}
        # times = times.replace("%3A", ":").replace("%20-%20", " - ")
        while times != '':
            r = times[0:10]
            if r != '':
                key = r.split(' - ')[0]
                val = r.split(' - ')[1]
                tms[key] = int(val)
            times = times[10:]
        utils.set_config("piec_czasy", tms)

    def web_save(self, temp, times):
        tmp = int(temp)
        curr_tmp = int(utils.get_config("piec_temperatura", tmp))
        if tmp != curr_tmp:
            self.set_temperature(int(tmp))
        self.save_times(times)

    def handle_timer(self):
        times = utils.get_config("piec_czasy", {})
        if self.time_update == 0 and utils.wifi_connected():
            utils.settime()
            self.time_update = 1

        (y, m, d, hh, mm, ss, wd, yd) = utime.localtime(utime.time() + 1 * 3600)
        if self.lh == hh and self.lm == mm:
            return
        self.lh = hh
        self.lm = mm

        for t in times:
            th = t.split(':')[0]
            tm = int(t.split(':')[1])
            if th == '**':
                th = str(hh)
            if int(th) == hh and tm == mm:
                tmp = times[t]
                utils.log_message('HANDLE TIME %2d:%2d - %s' % (int(th), int(tm), tmp))
                self.set_temperature(int(tmp))
        if mm % 5 == 0 and self.ltm != mm:
            self.termometr.pomiar_temperatury(True)
            self.ltm = mm

        if mm % 20 == 0 and self.lum != mm and utils.wifi_connected():
            utils.settime()
            self.lum = mm

    def handle_web(self, conn, addr):
        conn.settimeout(0.5)
        gc.collect()
        request = b''
        while True:
            buf = b''
            try:
                buf = conn.recv(128)
            except Exception as erar:
                pass
            request += buf
            if buf == b'':
                break

        conn.settimeout(None)
        url = web.parse_request(request)
        utils.log_message('WEB REQUEST')
        utils.log_message(request)
        handled = False
        if url.find("/save") > -1:
            temp = int(url[url.find("temp=") + len("temp="):url.find("&tempEnd")])
            times = url[url.find("times=") + len("times="):url.find("&timesEnd")]
            self.web_save(temp, times)
        elif url.find("/api/") > -1:
            handled = web.handle_api(conn, url)
        elif url.find("/hist/termo") > -1:
            conn.sendall(web.get_header('text/html'))
            web.send_file(conn, 'hist_termo.html', 'r')
            handled = True
        elif url.find("/hist/piec") > -1:
            conn.sendall(web.get_header('text/html'))
            web.send_file(conn, 'hist_piec.html', 'r')
            handled = True
        elif url.find("/logs") > -1:
            conn.sendall(web.get_header('text/html'))
            web.send_file(conn, 'logs.html', 'r')
            handled = True
        if not handled:
            conn.sendall(web.get_header('text/html'))
            web.send_file(conn, 'index.html')
        utils.log_message('WEB REQUEST DONE')
        utime.sleep(1)
        conn.close()

    def handle_joystick(self):
        if self.edit_temp == 0:
            self.edit_temp = int(utils.get_config("piec_temperatura", 0))
        if self.state in (2, 3, 4, 5):
            val = self.adc.read()
            if val <= 200:
                if self.edit_temp < int(utils.get_config("piec_temperatura_max", 90)):
                    self.edit_temp += 1
                    self.led_write_number(self.edit_temp)
                utime.sleep_ms(150)
            if val >= 900:
                if self.edit_temp > int(utils.get_config("piec_temperatura_min", 30)):
                    self.edit_temp -= 1
                    self.led_write_number(self.edit_temp)
                utime.sleep_ms(150)
            self.joy_val = val

    def handle_button(self, pin):
        if self.btn_val == 1 and pin.value() == 0:
            self.state += 1
            if self.state == 1:
                curr_temp = int(utils.get_config("piec_temperatura", 0))
                self.led_write_number(curr_temp)
            if self.state == 2:
                self.edit_temp = int(utils.get_config("piec_temperatura", 0))
            if self.state == 3:
                self.state = 1
                curr_temp = int(utils.get_config("piec_temperatura", 0))
                if self.edit_temp != curr_temp:
                    self.set_temperature(int(self.edit_temp))
                    self.led_write_number(self.edit_temp)
                self.edit_temp = 0
                self.display._write(5, 0)
        self.btn_val = pin.value()

    def init_wifi(self):
        if utils.wifi_connected() is False:

            utils.wifi_connect()
            if utils.wifi_connected() is True:
                try:
                    if self.sock is not None:
                        self.sock.close()
                    self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    self.sock.bind(('', 80))
                    self.sock.listen(5)
                except OSError as err:
                    self.sock.close()
                    utils.log_message('SOCKET ERROR')
                    utils.log_exception(err)
                    utils.wifi_disconnect()

    def run(self):
        wifid = 0
        while True:
            if self.state < 2:
                self.init_wifi()
                if utils.wifi_connected():
                    r, w, err = select.select((self.sock,), (), (), 5)
                    if r:
                        for readable in r:
                            try:
                                conn, addr = self.sock.accept()
                                self.handle_web(conn, addr)
                            except OSError as error:
                                utils.log_message('WEB ERROR')
                                utils.log_exception(error)
                                conn.close()
                else:
                    wifid += 1
                    utils.log_message('WIFI DOWN')
                    if wifid > 10:
                        utils.log_message('WIFI RECONNECT')
                        utils.wifi_disconnect()
                        wifid = 0

                self.handle_timer()

                t = self.termometr.pomiar_temperatury()
                self.led_write_number(int(round(t * 10)), 5, [2])

            else:
                if self.edit_state % 2 == 0:
                    self.display._write(5, 79)
                else:
                    self.display._write(5, 0)
                self.edit_state += 1
                if self.edit_state > 100:
                    self.edit_state = 0

            self.handle_joystick()
            self.handle_button(self.button)
            utils.log_message('FREE MEMORY: %s' % (str(gc.mem_free())))

utils.load_config()
utils.wifi_disconnect()

while True:
    try:
        p = Piec()
        p.set_temperature(int(utils.get_config("piec_temperatura", 40)), False)
        utils.log_message('RUN')
        p.run()
    except Exception as err:
        utils.log_message('GENERAL EXCEPTION')
        utils.log_exception(err)

    gc.collect()
    utils.log_message('CRASH!')
