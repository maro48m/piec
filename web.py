import utils
import json
import sensors
import sys
import ure as re

import picoweb

piec = None
app = None


def save_piec(req, resp):
    global piec
    req.parse_qs()
    temp = int(req.form["temp"])
    times = req.form["times"]
    if piec is not None:
        piec.web_save(temp, times)
        yield from resp.awrite('{"result":"Dane zapisane"}'.encode('utf-8'))
    else:
        yield from resp.awrite('{"result":"Błąd zapisu"}'.encode('utf-8'))


def handle_api(req, resp):
    print(req.path)
    if req.path.find("/api/dane.json") > -1:
        yield from picoweb.start_response(resp, content_type='application/json')
        termometr = sensors.Sensory()
        dane = utils.get_data()
        dane["termometr"] = await termometr.pomiar_temperatury()
        del termometr
        yield from resp.awrite(json.dumps(dane).encode('utf-8'))

    elif req.path.find("/api/clear/logs") > -1:
        yield from picoweb.start_response(resp, content_type='application/json')
        await utils.remove_hist(4)
        yield from resp.awrite('{"result":"Historia wyczyszczona"}'.encode('utf-8'))
    elif req.path.find("/api/clear/hist_piec") > -1:
        yield from picoweb.start_response(resp, content_type='application/json')
        await utils.remove_hist(1)
        yield from resp.awrite('{"result":"Historia wyczyszczona"}'.encode('utf-8'))
    elif req.path.find("/api/clear/hist_termo") > -1:
        yield from picoweb.start_response(resp, content_type='application/json')
        await utils.remove_hist(2)
        yield from resp.awrite('{"result":"Historia wyczyszczona"}'.encode('utf-8'))
    elif req.path.find("/api/clear/all") > -1:
        yield from picoweb.start_response(resp, content_type='application/json')
        await utils.remove_hist(7)
        yield from resp.awrite('{"result":"Historia wyczyszczona"}'.encode('utf-8'))
    elif req.path.find("/api/params_get.json") > -1:
        yield from picoweb.start_response(resp, content_type='application/json')
        yield from resp.awrite(json.dumps(utils.config).encode('utf-8'))
    elif req.path.find("/api/params_save") > -1:
        # utils.update_config(request["body"].decode('utf-8'))
        yield from picoweb.start_response(resp, content_type='application/json')
        yield from resp.awrite('{"result":"Parametry zapisane"}'.encode('utf-8'))
    elif req.path.find("/api/logs") > -1:
        yield from app.sendfile(resp, 'log.txt', content_type='text/plain')
    elif req.path.find("/api/hist_piec") > -1:
        yield from app.sendfile(resp, 'piec.hist', content_type='text/plain')
    elif req.path.find("/api/hist_termo") > -1:
        yield from app.sendfile(resp, 'termometr.hist', content_type='text/plain')
    elif req.path.find("/api/chart.json") > -1:
        yield from send_chart_data2(resp)
    elif req.path.find("/api/reboot") > -1:
        yield from resp.awrite('{"response":"Urządzenie się restartuje. Konieczne przeładowanie strony"}'.encode('utf-8'))
        yield from resp.aclose()
        import uasyncio
        await uasyncio.sleep_ms(500)
        import machine
        machine.reset()
    return True


async def send_chart_data2(writer):
    cmax = 40
    if sys.platform == 'esp32':
        cmax = 120

    for i in range(1, 3):
        if i == 1:
            file_name = 'termometr.hist'
            data = """[{"name": "Termometr", "data": ["""
            termometr = sensors.Sensory()
            curr = await termometr.pomiar_temperatury()
            del termometr
            sqr = False
        else:
            file_name = 'piec.hist'
            data = """{"name": "Piec", "data": ["""
            curr = int(utils.get_config("piec_temperatura", 40))
            sqr = True

        prev = None
        writer.write(data.encode('utf-8'))
        await writer.drain()

        data = ""
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
                            data += (json.dumps(dp) + ',')

                        prev = d[1]
                        d[0] += " GMT"
                        data += (json.dumps(d) + ',')
                        c += 1

                        if c == cmax:
                            writer.write(data.encode('utf-8'))
                            await writer.drain()
                            c = 0
                            del data
                            data = ""

                fi.close()
        except Exception as eee:
            # utils.log_message('BLAD ODCZYTU PLIKU %s' % file_name, 2)
            utils.log_exception(eee, 2)
            pass

        if sqr:
            d = [utils.czas(True) + ' GMT', prev]
            data += (json.dumps(d) + ',')

        d = [utils.czas(True) + ' GMT', curr]
        data += (json.dumps(d))

        writer.write(data.encode('utf-8'))
        del data

        await writer.drain()

        if i == 1:
            writer.write("""]},""".encode('utf-8'))
        else:
            writer.write("""]}]""".encode('utf-8'))

        await writer.drain()
        utils.unlock_file(file_name)


ROUTES = [
    ("/", lambda req, resp: (yield from app.sendfile(resp, "index.html"))),
    ("/hist/termo", lambda req, resp: (yield from app.sendfile(resp, "hist_termo.html"))),
    ("/hist/piec", lambda req, resp: (yield from app.sendfile(resp, "hist_piec.html"))),
    ("/params", lambda req, resp: (yield from app.sendfile(resp, "params.html"))),
    ("/logs", lambda req, resp: (yield from app.sendfile(resp, "logs.html"))),
    ("/save", save_piec),
    (re.compile("^/api/(.+)"), handle_api),
]


def set_piec(p):
    global piec
    piec = p


def start():
    global app
    app = picoweb.WebApp(__name__, ROUTES)
    app.run(debug=-1, port=80, host='0.0.0.0')
