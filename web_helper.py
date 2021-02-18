def get_header(mime_type):
    return "HTTP/1.1 200OK\n" + "Content-Type: %s\n" % mime_type + "Connection: close\n\n"


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
    body = b''
    hdr = True
    for line in lines[1:]:
        if hdr:
            if line == b'':
                hdr = False
            else:
                line = unquote(line)
                hdr = line.split(b': ')
                if len(hdr) == 2:
                    headers[hdr[0].decode('ascii')] = hdr[1].decode('ascii')
        else:
            body += line+b'\r\n'

    ret["headers"] = headers
    ret["body"] = body
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
