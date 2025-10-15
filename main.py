import gc

import utils
import devices
import uasyncio
import utime


class Piec:
    def __init__(self):
        self.STATES = {'SLEEP': 0, 'DISPLAY': 1, 'EDIT': 2}
        self.DEFAULT_TEMP = 40
        self.state = self.STATES['DISPLAY']
        self._init_state_vars()
        
        self.devices = devices.Devices()
        self.curr_temp = 0       
        self.devices.write_display(5, 0)
        

        self.btn_task = None
        self.joy_task = None
        self.display_task = None
        self.web_task = None
        self.timer_task = None
        self.wifi_task = None
        self.lcd_task = None
        self.thermo_task = None
        
        
    
    def _init_state_vars(self):
        """Initialize state variables with defaults to reduce memory allocation"""
        self.lh = self.lm = self.ltm = self.lum = -1
        self.time_update = 0
        self.btn_val = 1
        self.joy_val = 500
        self.edit_temp = 0
        self.disp_state = self.lcd_state = self.edit_state = 0
        
        self.state = self.STATES['DISPLAY']

        

    async def set_temperature(self, new_temp, zapisz=True):
        """Optimized temperature setting with improved error handling"""
        try:
            czas = utils.czas() if zapisz else None
            curr_temp = int(utils.get_config("piec_temperatura"))
            temp_max = int(utils.get_config("piec_temperatura_max", 90))
            temp_min = int(utils.get_config("piec_temperatura_min", 30))
            temp_wg = int(utils.get_config("piec_temperatura_wg", 5))
            temp_wd = int(utils.get_config("piec_temperatura_wd", 2))

            # Validate temperature range
            if not temp_min <= new_temp <= temp_max:
                return False

            # Optimize servo movement logic
            if curr_temp < new_temp <= (temp_max - temp_wg):
                await self._move_servo_with_adjustment(new_temp + temp_wg)
            elif curr_temp > new_temp >= (temp_min + temp_wd):
                await self._move_servo_with_adjustment(new_temp - temp_wd)

            await self._finalize_temp_setting(new_temp, zapisz, czas)
            return True
            
        except Exception as e:
            print(f"Error setting temperature: {e}")
            return False

    def save_times(self, times):
        tms = {}
        print('save times', times)
        while times != '':
            r = times[0:10]
            times = times[10:]
            if r != '':
                key = r.split(" - ")[0]
                val = r.split(" - ")[1]
                tms[key] = int(val)
        print('save times done', tms)
        utils.set_config("piec_czasy", tms)
        del tms

    async def web_save(self, temp, times):
        tmp = int(temp)
        curr_tmp = int(utils.get_config("piec_temperatura", tmp))
        if tmp != curr_tmp:
            await self.set_temperature(int(tmp))
        self.save_times(times)

    async def handle_timer(self):
        while 1:
            times = utils.get_config("piec_czasy", {})
            if self.time_update == 0 and utils.wifi_connected():
                utils.settime()
                self.time_update = 1

            (y, m, d, hh, mm, ss, wd, yd) = utils.dst_time()

            if y > 2000:
                if not (self.lh == hh and self.lm == mm):
                    self.lh = hh
                    self.lm = mm

                    for t in times:
                        th = t.split(':')[0]
                        tm = int(t.split(':')[1])
                        if th == '**':
                            th = str(hh)
                        if int(th) == hh and tm == mm:
                            tmp = times[t]
                            curr_tmp = int(utils.get_config("piec_temperatura", tmp))
                            if int(tmp) != curr_tmp:
                                await self.set_temperature(int(tmp))
                    del times

                    if utils.get_config('piec_historia_termometru', True):
                        if mm % int(utils.get_config("piec_historia_termometru_czas", 5)) == 0 and self.ltm != mm:
                            await self.devices.thermometer_value(utils.get_config('piec_historia_termometru', True))
                            self.ltm = mm

                    if mm % 20 == 0 and self.lum != mm and utils.wifi_connected():
                        utils.settime()
                        self.lum = mm
            await uasyncio.sleep(30)

    async def handle_joystick(self):
        while 1:
            # utils.log_message('HANDLE JOYSTICK')
            if self.edit_temp == 0:
                self.edit_temp = int(utils.get_config("piec_temperatura", 0))
            if self.state in (2, 3, 4, 5):
                if self.devices.lcd_light > 0:
                    self.devices.lcd_light = 0
                val = self.devices.joy_val()
                if val <= 200:
                    if self.edit_temp < int(utils.get_config("piec_temperatura_max", 90)):
                        self.edit_temp += 1
                        self.devices.led_write_number(self.edit_temp)
                    await uasyncio.sleep_ms(150)
                if val >= 900:
                    if self.edit_temp > int(utils.get_config("piec_temperatura_min", 30)):
                        self.edit_temp -= 1
                        self.devices.led_write_number(self.edit_temp)
                    await uasyncio.sleep_ms(150)
                self.joy_val = val
                await uasyncio.sleep_ms(10)
            else:
                await uasyncio.sleep_ms(500)

    async def _move_servo_with_adjustment(self, temp):
        """Helper method for servo movement with delay"""
        await self.devices.move_servo(utils.map_temp_to_servo(temp))
        await uasyncio.sleep_ms(1000)

    async def _finalize_temp_setting(self, temp, zapisz, czas):
        """Helper method to finalize temperature setting"""
        await self.devices.move_servo(utils.map_temp_to_servo(temp))
        utils.set_config("piec_temperatura", int(temp))
        
        if zapisz and utils.get_config("piec_historia_temperatury", True):
            if utils.dst_time()[0] > 2000:
                utils.set_config("piec_ostatnia_aktualizacja", czas, False)
                await utils.save_to_hist(temp, "piec.hist")

    async def handle_button(self):
        """Optimized button handler with state machine"""
        while True:
            val = self.devices.button_value()
            
            if self.btn_val == 1 and val == 0:
                if self.devices.lcd_light != -1:
                    await self._handle_button_press()
                self.devices.lcd_backlight(0)

            self.btn_val = val
            await uasyncio.sleep_ms(150)

    async def _handle_button_press(self):
        """Separate button press logic for clarity"""
        self.state += 1
        if self.state == self.STATES['DISPLAY']:
            await self._update_display_state()
        elif self.state == self.STATES['EDIT']:
            await self._enter_edit_state()
        elif self.state > self.STATES['EDIT']:
            await self._save_edit_state()
            self.state = self.STATES['DISPLAY']
            
    async def _update_display_state(self):
        """Handle display state updates"""
        curr_temp = int(utils.get_config("piec_temperatura", self.DEFAULT_TEMP))
        self.devices.led_write_number(curr_temp)
        self.devices.led_write_number(None, 2)
        self.devices.led_write_number(None, 3)

    async def _enter_edit_state(self):
        """Initialize edit state"""
        self.lcd_state = 0
        self.edit_temp = int(utils.get_config("piec_temperatura", self.DEFAULT_TEMP))
        self.devices.led_write_number(self.edit_temp)
        self.devices.led_write_number(None, 2)
        self.devices.led_write_number(None, 3)
    
    async def _save_edit_state(self):
        """Save changes from edit state"""
        curr_temp = int(utils.get_config("piec_temperatura", self.DEFAULT_TEMP))
        if self.edit_temp != curr_temp:
            await self.set_temperature(int(self.edit_temp))
            self.devices.led_write_number(self.edit_temp)
    

    async def handle_wifi(self):
        while 1:
            # utils.log_message('HANDLE WIFI')
            if utils.wifi_connected() is False:
                try:
                    utils.wifi_connect()
                except Exception as err:
                    pass

            await uasyncio.sleep(30)

    async def handle_display(self):
        while 1:
            if self.devices.display is None:
                return
            try:
                if self.state < 2:
                    self.devices.led_write_number(int(round(self.curr_temp * 10)), 5, [2])
                    dd = [1] if self.disp_state % 2 else []
                    if self.disp_state <= 40:
                        curr_temp = int(utils.get_config("piec_temperatura", 0))
                        self.devices.led_write_number(curr_temp, 0, dd)
                        self.devices.led_write_number(None, 2)
                        self.devices.led_write_number(None, 3)
                    elif 40 < self.disp_state <= 80:
                        val = utils.wifi_signal()
                        self.devices.led_write_number(val, 0, dd)
                    elif 80 < self.disp_state <= 120:
                        (y, m, d, hh, mm, ss, wd, yd) = utils.dst_time()
                        if hh < 10:
                            self.devices.led_write_number(0, 0, [])
                            if len(dd) == 1:
                                dd = [0]
                            self.devices.led_write_number(hh, 1, dd)
                        else:
                            self.devices.led_write_number(hh, 0, dd)
                        if mm < 10:
                            self.devices.led_write_number(0, 2, [])
                            self.devices.led_write_number(mm, 3, [])
                        else:
                            self.devices.led_write_number(mm, 2, [])

                    await self.devices.move_servo(
                        utils.map_temp_to_servo(int(utils.get_config("piec_temperatura", 40))))
                    self.disp_state += 1
                    if self.disp_state > 120:
                        self.disp_state = 0
                else:
                    if self.edit_state % 2 == 0:
                        self.devices.write_display(5, 79)
                    else:
                        self.devices.write_display(5, 0)
                    self.edit_state += 1
                    if self.edit_state > 100:
                        self.edit_state = 0
            except Exception as err:
                pass
            await uasyncio.sleep_ms(500)

    async def handle_lcd(self):
        while 1:
            wait = 500
            if self.devices.lcd is None:
                return
            try:
                if self.devices.lcd_light != -1:
                    text = utils.czas(False, True, False)
                    self.devices.write_lcd_at_pos(text, 0, 0)
                    if self.curr_temp < 10:
                        self.devices.write_lcd_at_pos(" %1.1f" % self.curr_temp, 7, 0)
                    else:
                        self.devices.write_lcd_at_pos("%02.1f" % self.curr_temp, 7, 0)
                    self.devices.write_lcd_char_at_pos(chr(7), 11, 0)
                    self.devices.write_lcd_at_pos("C", 12, 0)
                    ws = 0
                    if utils.wifi_signal() >= -30:
                        ws = 4
                    elif utils.wifi_signal() >= -67:
                        ws = 3
                    elif utils.wifi_signal() >= -70:
                        ws = 2
                    elif utils.wifi_signal() >= -80:
                        ws = 1
                    elif utils.wifi_signal() >= -90:
                        ws = 0
                    self.devices.write_lcd_char_at_pos(chr(ws), 15, 0)

                    if self.state < 2:
                        if self.lcd_state < 20:
                            if self.lcd_state == 0:
                                self.devices.write_lcd_at_pos("Piec:           ", 0, 1)
                                self.devices.write_lcd_at_pos("o", 9, 1)
                                ctemp = int(utils.get_config("piec_temperatura", 0))
                                self.devices.write_lcd_at_pos("%02d" % ctemp, 6, 1)
                                ctime = utils.get_config('piec_ostatnia_aktualizacja', '')
                                self.devices.write_lcd_at_pos(ctime[11:16], 11, 1)
                        elif self.lcd_state < 40:
                            if self.lcd_state == 20:
                                self.devices.write_lcd_at_pos("Nast.:          ", 0, 1)
                                self.devices.write_lcd_at_pos("o", 9, 1)
                                (ntime, ntemp) = self.find_next_temp()
                                if ntemp <= -1:
                                    self.lcd_state = 40
                                else:
                                    self.devices.write_lcd_at_pos("%02d" % ntemp, 6, 1)
                                    self.devices.write_lcd_at_pos(ntime, 11, 1)

                        self.lcd_state += 1
                        if self.lcd_state >= 40:
                            self.lcd_state = 0
                    else:
                        if self.lcd_state == 0:
                            self.devices.write_lcd_at_pos("Zmiana na:      ", 0, 1)
                            self.lcd_state = -1
                        elif self.lcd_state > 0:
                            self.lcd_state = 0
                        self.devices.write_lcd_at_pos("%02d" % self.edit_temp, 11, 1)
                        wait = 250
            except Exception as err:
                print(err)
            if wait == 500:
                if self.devices.lcd_light != -1:
                    self.devices.lcd_light_tick()
            await uasyncio.sleep_ms(wait)

    async def handle_thermometer(self):
        while 1:
            self.curr_temp = await self.devices.thermometer_value()
            await uasyncio.sleep_ms(500)
    
    async def handle_gc(self):
        while 1:
            gc.collect()
            await uasyncio.sleep_ms(250)

    def find_next_temp(self):
        times = utils.get_config("piec_czasy", {})
        if len(times) == 0:
            return "", -1
        tdt = []
        ttt = {}
        (curr_y, curr_m, curr_d, curr_hh, curr_mm, curr_ss, curr_wd, curr_yd) = utils.dst_time()
        rp = -1
        rt = ""
        if curr_y > 2000:
            cdt = utime.mktime((curr_y, curr_m, curr_d, curr_hh, curr_mm, 0, 0, 0))
            for t in times:
                th = t.split(':')[0]
                tm = int(t.split(':')[1])
                tmp = times[t]
                if th == '**':
                    dt = utime.mktime((curr_y, curr_m, curr_d, curr_hh+1, tm, 0, 0, 0))
                    tdt.append(dt)
                    ttt[dt] = tmp
                    th = curr_hh
                else:
                    th = int(th)

                if th < curr_hh or (th == curr_hh and tm < curr_mm):
                    dt = utime.mktime((curr_y, curr_m, curr_d+1, th, tm, 0, 0, 0))
                elif th == curr_hh and tm == curr_mm:
                    ctime = utils.get_config('piec_ostatnia_aktualizacja', '')
                    ctime = ctime[11:16]
                    rt = "%02d:%02d" % (curr_hh, curr_mm)
                    if ctime != rt:
                        dt = utime.mktime((curr_y, curr_m, curr_d, th, tm, 0, 0, 0))
                else:
                    dt = utime.mktime((curr_y, curr_m, curr_d, th, tm, 0, 0, 0))
                tdt.append(dt)
                ttt[dt] = tmp
            ntdt = [item for item in tdt if item >= cdt]
            closest = sorted(ntdt, key=lambda d: (d - cdt))[0]
            (curr_y, curr_m, curr_d, curr_hh, curr_mm, curr_ss,
             
             
             
             curr_wd, curr_yd) = utime.localtime(closest)
            rt = "%02d:%02d" % (curr_hh, curr_mm)
            rp = ttt[closest]
        return rt, rp


    async def start_ftp(self):
        import uftpd
        uftpd.stop()
        uftpd.start(21, 0, False)
        await uasyncio.sleep_ms(500)

    async def start_webserver(self):
        import web
        web.start(self)
        await uasyncio.sleep_ms(500)

    def run(self):
        """Optimized run method with improved task management"""
        loop = uasyncio.get_event_loop()
        
        # Create task list for better management
        tasks = [
            self._create_task(self.set_temperature(int(utils.get_config("piec_temperatura", self.DEFAULT_TEMP)), False)),
            self._create_task(self.handle_timer()),
            self._create_task(self.handle_button()),
            self._create_task(self.handle_joystick()),
            self._create_task(self.handle_thermometer()),
            self._create_task(self.handle_lcd()),
            self._create_task(self.handle_display()),
            self._create_task(self.handle_wifi()),
            self._create_task(self.start_webserver()),
            self._create_task(self.start_ftp()),
            self._create_task(self.handle_gc())
        ]
        
        # Schedule all tasks
        for task in tasks:
            loop.create_task(task)
            
        loop.run_forever()

    def _create_task(self, coro):
        """Helper method to create tasks with error handling"""
        async def wrapped_task():
            try:
                await coro
            except Exception as e:
                print(f"Task error: {e}")
                gc.collect()
        return wrapped_task()


utils.load_config()
utils.wifi_disconnect()

while True:
    p = Piec()
    p.run()
