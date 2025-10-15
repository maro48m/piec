import gc
import utils
import json
import sensors
import ure as re
import picoweb
import utime
from micropython import const

# Constants
CHUNK_SIZE = const(512)
CACHE_TIMEOUT = const(30)  # 30 seconds
MAX_HIST_CHUNK = const(10)  # Maximum number of history entries to process at once

class WebServer:
    def __init__(self, piec_controller):
        self.piec = piec_controller
        self.cache = {}
        self._setup_routes()

    def _setup_routes(self):
        self.ROUTES = [
            ("/", self._serve_index),
            ("/params", self._serve_params),
            ("/save", self.save_piec),
            (re.compile("^/api/(.+)"), self.handle_api)
        ]
        self.app = picoweb.WebApp(__name__, self.ROUTES)

    async def _serve_index(self, req, resp):
        await self.app.sendfile(resp, "index.html")

    async def _serve_params(self, req, resp):
        await self.app.sendfile(resp, "params.html")

    async def handle_api(self, req, resp):
        gc.collect()  # Ensure we have memory for processing
        
        if req.path.find("/api/dane.json") > -1:
            await self._handle_dane_json(req, resp)
        elif req.path.find("/api/clear_hist") > -1:
            await self._handle_clear_hist(req, resp)
        elif req.path.find("/api/params_get.json") > -1:
            await self._handle_params_get(req, resp)
        elif req.path.find("/api/params_save") > -1:
            await self._handle_params_save(req, resp)
        elif req.path.find("/api/piec.hist") > -1:
            await self._handle_hist_file(req, resp, 'piec.hist')
        elif req.path.find("/api/termo.hist") > -1:
            await self._handle_hist_file(req, resp, 'termometr.hist')
        elif req.path.find("/api/chart.json") > -1:
            await self._handle_chart_json(req, resp)
        elif req.path.find("/api/chart_series.json") > -1:
            await self._handle_chart_series(req, resp)
        elif req.path.find("/api/reboot") > -1:
            await self._handle_reboot(req, resp)
        elif req.path.find("/api/remote_termo") > -1:
            await self._handle_remote_termo(req, resp)
        return True

    async def _handle_dane_json(self, req, resp):
        await self._json_response(resp)
        
        cache_key = 'dane_json'
        cached_data = self._get_cache(cache_key)
        if cached_data:
            await resp.awrite(cached_data)
            return

        termometr = sensors.Sensory()
        dane = utils.get_data()
        dane["termometr"] = await termometr.pomiar_temperatury()
        del termometr
        
        json_data = json.dumps(dane)
        self._set_cache(cache_key, json_data)
        await resp.awrite(json_data.encode('utf-8'))

    async def _handle_clear_hist(self, req, resp):
        await self._json_response(resp)
        await utils.remove_hist()
        await resp.awrite('{"result":"Historia wyczyszczona"}'.encode('utf-8'))

    async def _handle_params_get(self, req, resp):
        await self._json_response(resp)
        cfg = utils.config.copy()  # Make a copy to avoid modifying original
        aliases = cfg["aliases"]
        alt = '\n'.join(f"{k}={v}" for k, v in sorted(aliases.items()))
        cfg["alt"] = alt
        await resp.awrite(json.dumps(cfg).encode('utf-8'))

    async def _handle_params_save(self, req, resp):
        size = int(req.headers[b"Content-Length"])
        data = await req.reader.readexactly(size)
        params = json.loads(data.decode('utf-8'))
        
        # Process aliases
        aliases = {}
        for line in params["aliases"].split("\n"):
            if line.strip():
                key, value = line.split("=", 1)
                aliases[key.strip()] = value.strip()
        params["aliases"] = aliases
        
        utils.update_config(params)
        await self._json_response(resp)
        await resp.awrite('{"result":"Dane zapisane"}'.encode('utf-8'))

    async def _handle_hist_file(self, req, resp, filename):
        await utils.lock_file(filename)
        try:
            with open(filename, 'r') as f:
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    await resp.awrite(chunk.encode('utf-8'))
                    await resp.drain()
                    gc.collect()
        finally:
            utils.unlock_file(filename)

    async def _handle_chart_json(self, req, resp):
        await self._json_response(resp)
        req.parse_qs()
        file_name = req.form["file"]
        await self._stream_chart_data(resp, file_name)

    async def _stream_chart_data(self, resp, file_name):
        gc.collect()
        aliases = utils.get_config("aliases", {})
        data_alias = ""
        curr_value = None
        
        # Determine data source and current value
        if file_name == 'termometr.hist':
            termometr = sensors.Sensory()
            curr_value = await termometr.pomiar_temperatury()
            data_alias = "Piec - termometr"
            del termometr
        elif file_name == 'piec.hist':
            curr_value = int(utils.get_config("piec_temperatura", 40))
            data_alias = "Piec - temperatura"
        else:
            data_alias = aliases.get(file_name, "")

        # Write header
        await resp.awrite(f'{{"name": "{data_alias}", "data": ['.encode('utf-8'))
        
        # Stream historical data
        first_entry = True
        try:
            await utils.lock_file(file_name)
            with open(file_name, 'r') as f:
                prev_value = None
                while True:
                    lines = []
                    # Read chunk of lines
                    for _ in range(MAX_HIST_CHUNK):
                        line = f.readline()
                        if not line:
                            break
                        lines.append(line.rstrip())
                    
                    if not lines:
                        break
                        
                    # Process chunk
                    for line in lines:
                        if not first_entry:
                            await resp.awrite(','.encode('utf-8'))
                        else:
                            first_entry = False
                            
                        date, value = line.split(" - ")
                        entry = f'["{date} GMT",{value}]'
                        await resp.awrite(entry.encode('utf-8'))
                        prev_value = value
                    
                    await resp.drain()
                    gc.collect()
                    
            # Add current value if available
            if curr_value is not None:
                if not first_entry:
                    await resp.awrite(','.encode('utf-8'))
                current_time = utils.czas(True)
                await resp.awrite(f'["{current_time} GMT",{curr_value}]'.encode('utf-8'))
                
        finally:
            utils.unlock_file(file_name)
            await resp.awrite(']}'.encode('utf-8'))

    async def _handle_chart_series(self, resp):
        series = [
            {"name": "piec.hist", "alias": "Piec - temperatura"},
            {"name": "termometr.hist", "alias": "Piec - termometr"}
        ]
        
        aliases = utils.get_config("aliases", {})
        for name, alias in aliases.items():
            if name:
                series.append({"name": name, "alias": alias})
                
        await self._json_response(resp)
        await resp.awrite(json.dumps({"series": series}).encode('utf-8'))

    async def _handle_reboot(self, req, resp):
        await self._json_response(resp)
        await resp.awrite(
            '{"response":"Urządzenie się restartuje. Konieczne przeładowanie strony"}'.encode('utf-8'))
        await resp.aclose()
        import machine
        machine.reset()

    async def _handle_remote_termo(self, req, resp):
        req.parse_qs()
        temp = int(req.form["term"])
        name = req.form["name"]
        await utils.save_to_hist(temp, name)
        await self._json_response(resp)
        await resp.awrite('{"result":"Done"}'.encode('utf-8'))

    async def save_piec(self, req, resp):
        req.parse_qs()
        temp = int(req.form["temp"])
        times = req.form["times"]
        
        await self._json_response(resp)
        if self.piec is not None:
            await self.piec.web_save(temp, times)
            await resp.awrite(json.dumps({
                "result": "Dane zapisane",
                "times": times
            }).encode('utf-8'))
        else:
            await resp.awrite('{"result":"Błąd zapisu"}'.encode('utf-8'))

    async def _json_response(self, resp):
        await picoweb.start_response(resp, content_type='application/json',
                                   headers={"Access-Control-Allow-Origin": "*"})

    def _get_cache(self, key):
        if key in self.cache:
            data, timestamp = self.cache[key]
            if utime.time() - timestamp < CACHE_TIMEOUT:
                return data
            del self.cache[key]
        return None

    def _set_cache(self, key, data):
        self.cache[key] = (data, utime.time())
        # Clean old cache entries
        now = utime.time()
        self.cache = {k: v for k, v in self.cache.items() 
                     if now - v[1] < CACHE_TIMEOUT}

    def start(self, host='0.0.0.0', port=80):
        self.app.run(debug=-1, port=port, host=host)

def start(piec_controller):
    server = WebServer(piec_controller)
    server.start()
