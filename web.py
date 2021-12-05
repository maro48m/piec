import gc
import utils
import json
import sensors
import ure as re
import picoweb

piec = None


def handle_api(req, resp):
    print(req.path)
    if req.path.find("/api/dane.json") > -1:
        yield from picoweb.start_response(resp, content_type='application/json',
                                          headers={"Access-Control-Allow-Origin": "*"})
        termometr = sensors.Sensory()
        dane = utils.get_data()
        dane["termometr"] = await termometr.pomiar_temperatury()
        del termometr
        yield from resp.awrite(json.dumps(dane).encode('utf-8'))
    elif req.path.find("/api/clear_hist") > -1:
        yield from picoweb.start_response(resp, content_type='application/json',
                                          headers={"Access-Control-Allow-Origin": "*"})
        await utils.remove_hist()
        yield from resp.awrite('{"result":"Historia wyczyszczona"}'.encode('utf-8'))
    elif req.path.find("/api/params_get.json") > -1:
        yield from picoweb.start_response(resp, content_type='application/json',
                                          headers={"Access-Control-Allow-Origin": "*"})
        cfg = utils.config
        aliases = cfg["aliases"]
        alt = ''
        for a in sorted(aliases):
            if alt != '':
                alt += "\n"
            alt += a + "=" + aliases[a]

        cfg["alt"] = alt
        yield from resp.awrite(json.dumps(cfg).encode('utf-8'))
    elif req.path.find("/api/params_save") > -1:
        yield from picoweb.start_response(resp, content_type='application/json',
                                          headers={"Access-Control-Allow-Origin": "*"})
        yield from save_params(req, resp)
    elif req.path.find("/api/chart.json") > -1:
        yield from picoweb.start_response(resp, content_type='application/json',
                                          headers={"Access-Control-Allow-Origin": "*"})
        yield from send_chart_data(req, resp)
    elif req.path.find("/api/chart_series.json") > -1:
        yield from picoweb.start_response(resp, content_type='application/json',
                                          headers={"Access-Control-Allow-Origin": "*"})
        yield from get_series_names(resp)
    elif req.path.find("/api/reboot") > -1:
        yield from picoweb.start_response(resp, content_type='application/json',
                                          headers={"Access-Control-Allow-Origin": "*"})
        yield from resp.awrite(
            '{"response":"Urządzenie się restartuje. Konieczne przeładowanie strony"}'.encode('utf-8'))
        yield from resp.aclose()
        import uasyncio
        await uasyncio.sleep_ms(500)
        import machine
        machine.reset()
    elif req.path.find("/api/remote_termo") > -1:
        yield from picoweb.start_response(resp, content_type='application/json',
                                          headers={"Access-Control-Allow-Origin": "*"})
        yield from save_remote_termo(req, resp)

    return True


async def save_params(req, resp):
    await picoweb.start_response(resp, content_type='application/json',
                                 headers={"Access-Control-Allow-Origin": "*"})
    size = int(req.headers[b"Content-Length"])
    data = await req.reader.readexactly(size)
    data_txt = data.decode('utf-8')
    params = json.loads(data_txt)
    atmp = params["aliases"]
    aliases = {}
    for al in atmp.split("\n"):
        if al != '':
            key = al.split("=")[0]
            val = al.split("=")[1]
            aliases[key] = val
    print(aliases)
    params["aliases"] = aliases
    print(params)
    utils.update_config(params)
    res = {"result": "Dane zapisane"}
    await resp.awrite(json.dumps(res).encode('utf-8'))
    await resp.drain()


async def save_remote_termo(req, resp):
    req.parse_qs()
    temp = int(req.form["term"])
    name = req.form["name"]
    await utils.save_to_hist(temp, name)
    res = {"result": "Done"}
    print(res)
    await resp.awrite(json.dumps(res).encode('utf-8'))
    await resp.drain()


def save_piec(req, resp):
    global piec
    req.parse_qs()
    temp = int(req.form["temp"])
    times = req.form["times"]
    print(times)
    yield from picoweb.start_response(resp, content_type='application/json',
                                      headers={"Access-Control-Allow-Origin": "*"})
    print(piec)
    if piec is not None:
        await piec.web_save(temp, times)
        print('ws')
        res = {"result": "Dane zapisane", "times": times}
        yield from resp.awrite(json.dumps(res).encode('utf-8'))
    else:
        print('now')
        yield from resp.awrite('{"result":"Błąd zapisu"}'.encode('utf-8'))


async def send_chart_data(req, writer):
    cmax = 10
    sqr = False
    req.parse_qs()
    file_name = req.form["file"]
    aliases = utils.get_config("aliases", {})
    data_alias = ""
    gc.collect(generation=2)
    if file_name == 'termometr.hist':
        termometr = sensors.Sensory()
        curr = await termometr.pomiar_temperatury()
        data_alias = "Piec - termometr"
        del termometr
    elif file_name == 'piec.hist':
        curr = int(utils.get_config("piec_temperatura", 40))
        data_alias = "Piec - temperatura"
        sqr = True
    else:
        data_alias = aliases[file_name]
        curr = None
    prev = None
    data = """{"name": "%s", "data": [""" % data_alias
    await writer.awrite(data.encode('utf-8'))
    await writer.drain()
    data = ""
    tc = 0
    try:
        await utils.lock_file(file_name)

        with open(file_name, 'r') as fi:
            c = 0

            data = ""

            while 1:
                buf = fi.readline()
                if str(buf) == '':
                    break
                else:
                    d = buf.rstrip().split(" - ")

                    if sqr and prev is not None:
                        dp = buf.rstrip().split(" - ")
                        dp[1] = prev
                        dp[0] += " GMT"
                        if tc != 0:
                            data += ","
                        else:
                            tc = 1
                        data += json.dumps(dp)

                    prev = d[1]
                    d[0] += " GMT"
                    if tc != 0:
                        data += ","
                    else:
                        tc = 1
                    data += json.dumps(d)
                    c += 1

                    if c == cmax:
                        await writer.awrite(data.encode('utf-8'))
                        await writer.drain()
                        c = 0
                        del data
                        gc.collect()
                        data = ""

            fi.close()
            print('1')
            utils.unlock_file(file_name)
    except Exception as eee:
        print('e')
        utils.log_exception(eee, 1)

    if utils.dst_time()[0] > 2000 and curr is not None:
        czas = utils.czas(True)
        if sqr:
            d = [czas + ' GMT', prev]
            if tc != 0:
                data += ","
            else:
                tc = 1
            data += (json.dumps(d))

        d = [czas + ' GMT', curr]
        if tc != 0:
            data += ","
        data += json.dumps(d)

    await writer.awrite(data.encode('utf-8'))
    del data

    await writer.drain()

    await writer.awrite("""]}""".encode('utf-8'))

    await writer.drain()
    print('f')
    utils.unlock_file(file_name)


async def get_series_names(resp):
    r = {"series": [{"name": "piec.hist", "alias": "Piec - temperatura"},
                    {"name": "termometr.hist", "alias": "Piec - termometr"}]}
    aliases = utils.get_config("aliases", {})
    print(aliases)
    for fn in aliases:
        fa = aliases[fn]
        print(fn, fa)
        if fn != "":
            r["series"].append({"name": fn, "alias": fa})
    print(r)
    await resp.awrite(json.dumps(r).encode('utf-8'))
    await resp.drain()


ROUTES = [
    ("/", lambda req, resp: (yield from app.sendfile(resp, "index.html"))),
    ("/params", lambda req, resp: (yield from app.sendfile(resp, "params.html"))),
    ("/save", save_piec),
    (re.compile("^/api/(.+)"), handle_api),
]

app = picoweb.WebApp(__name__, ROUTES)


def start(p):
    global app
    global piec
    piec = p
    app.run(debug=-1, port=80, host='0.0.0.0')
