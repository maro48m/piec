import gc

import utils
import json
import sensors
import sys


def get_header(mime_type):
    return ("HTTP/1.1 200OK\n" + "Content-Type: %s\n" % mime_type + "Connection: close\n\n").encode('utf-8')


def url_params(url):
    params_dict = {}

    params_arr = url.split('?')
    if len(params_arr) > 1:
        params_arr = params_arr[1].split('&')
        for p in params_arr:
            p = p.split('=')
            params_dict[p[0]] = p[1]
    del params_arr
    return params_dict


def parse_request(request):
    ret = {"url": "", "method": ""}
    if request == b'':
        return ret

    lines = request.split(b'\r\n')

    urls = lines[0].split(b' ')
    ret["url"] = unquote(urls[1]).decode('ascii')
    ret["method"] = unquote(urls[0]).decode('ascii')
    ret["proto"] = unquote(urls[2]).decode('ascii')

    del urls

    headers = {}
    bd = b''
    hdr = True
    for line in lines[1:]:
        if hdr:
            if line == b'':
                hdr = False
            else:
                line = unquote(line)
                hd = line.split(b': ')
                if len(hd) == 2:
                    headers[hd[0].decode('ascii')] = hd[1].decode('ascii')
        else:
            bd += line + b'\r\n'

    ret["headers"] = headers
    if "Content-Type" in ret["headers"].keys() and bd != b'':
        ct = ret["headers"]["Content-Type"]
        boundary = ct.split('boundary=')[1].encode('ascii')
        tb = bd.split(b'--' + boundary)
        body = {}

        for elem in tb:
            if elem == b'':
                continue
            elems = elem.split(b'\r\n\r\n')
            keys = elems[0]
            if keys not in (b'--', b''):
                keys = keys.split(b';')
                key = b''
                for k in keys:
                    if k.split(b'=')[0].strip(b' ') == b'name':
                        key = k.split(b'=')[1].strip(b'"')
                        break
                val = elems[1][:-2]
                if key != b'file':
                    body[key.decode('ascii')] = val.decode('ascii')
                else:
                    body[key.decode('ascii')] = val

        ret["body"] = body
        del bd

    del lines
    del hdr
    return ret


_hextobyte_cache = None


def unquote(string):
    """unquote('abc%20def') -> b'abc def'."""
    global _hextobyte_cache

    # Note: strings are encoded as UTF-8. This is only an issue if it contains
    # unescaped non-ASCII characters, which URIs should not.
    if not string:
        return b''

    if isinstance(string, str):
        string = string.encode('utf-8')

    bits = string.split(b'%')
    if len(bits) == 1:
        return string

    res = [bits[0]]
    append = res.append

    # Build cache for hex to char mapping on-the-fly only for codes
    # that are actually used
    if _hextobyte_cache is None:
        _hextobyte_cache = {}

    for item in bits[1:]:
        try:
            code = item[:2]
            char = _hextobyte_cache.get(code)
            if char is None:
                char = _hextobyte_cache[code] = bytes([int(code, 16)])
            append(char)
            append(item[2:])
        except KeyError:
            append(b'%')
            append(item)

    return b''.join(res)


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
