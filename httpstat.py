# coding: utf-8

import os
import json
import sys
import tempfile
import subprocess


curl_format = """{
"time_namelookup": "%{time_namelookup}",
"time_connect": "%{time_connect}",
"time_appconnect": "%{time_appconnect}",
"time_pretransfer": "%{time_pretransfer}",
"time_redirect": "%{time_redirect}",
"time_starttransfer": "%{time_starttransfer}",
"time_total": "%{time_total}"
}"""

https_template = """
  DNS Lookup   TCP Connection   SSL handshake   Server Processing   Content Transfer
[   {a000}   |    {a001}      |     {a002}    |      {a003}       |     {a004}       ]
             |                |               |                   |                  |
    namelookup:{b000}         |               |                   |                  |
                        connect:{b001}        |                   |                  |
                                    pretransfer:{b002}            |                  |
                                                      starttransfer:{b003}           |
                                                                                 total:{b004}
"""[1:]

http_template = """
  DNS Lookup   TCP Connection   Server Processing   Content Transfer
[   {a000}   |    {a001}      |      {a003}       |     {a004}       ]
             |                |                   |                  |
    namelookup:{b000}         |                   |                  |
                        connect:{b001}            |                  |
                                      starttransfer:{b003}           |
                                                                 total:{b004}
"""[1:]


def make_color(code):
    def color_func(s):
        tpl = '\x1b[{}m{}\x1b[0m'
        return tpl.format(code, s)
    return color_func


red = make_color(31)
green = make_color(32)
yellow = make_color(33)
blue = make_color(34)
magenta = make_color(35)
cyan = make_color(36)

bold = make_color(1)
underline = make_color(4)

grayscale = {(i - 232): make_color('38;5;' + str(i)) for i in xrange(232, 256)}


def main():
    url = sys.argv[1]
    if url.startswith('https://'):
        template = https_template
    else:
        template = http_template

    # tempfile for output
    bodyf = tempfile.NamedTemporaryFile(delete=False)
    bodyf.close()

    headerf = tempfile.NamedTemporaryFile(delete=False)
    headerf.close()

    # run cmd
    cmd = ['curl', '-w', curl_format, '-D', headerf.name, '-o', bodyf.name, '-s', url]
    output = subprocess.check_output(cmd)

    # parse output
    d = json.loads(output)
    for k in d:
        d[k] = int(float(d[k]) * 1000)

    # calculate ranges
    d.update(
        range_dns=d['time_namelookup'],
        range_connection=d['time_connect'] - d['time_namelookup'],
        range_ssl=d['time_pretransfer'] - d['time_connect'],
        range_server=d['time_starttransfer'] - d['time_pretransfer'],
        range_transfer=d['time_total'] - d['time_starttransfer'],
    )

    # print header & body summary
    with open(headerf.name, 'r') as f:
        headers = f.read().strip()
    # remote header file
    os.remove(headerf.name)

    for loop, line in enumerate(headers.split('\n')):
        if loop == 0:
            p1, p2 = tuple(line.split('/'))
            print green(p1) + grayscale[14]('/') + cyan(p2)
        else:
            pos = line.find(':')
            print grayscale[14](line[:pos + 1]) + cyan(line[pos + 1:])

    print
    print '{} stored in: {}'.format(green('Body'), bodyf.name)

    # print stat

    def fmta(s):
        return cyan('{:>4}ms'.format(s))

    def fmtb(s):
        return cyan('{:<6}'.format(str(s) + 'ms'))

    stat = template.format(
        # a
        a000=fmta(d['range_dns']),
        a001=fmta(d['range_connection']),
        a002=fmta(d['range_ssl']),
        a003=fmta(d['range_server']),
        a004=fmta(d['range_transfer']),
        # b
        b000=fmtb(d['time_namelookup']),
        b001=fmtb(d['time_connect']),
        b002=fmtb(d['time_pretransfer']),
        b003=fmtb(d['time_starttransfer']),
        b004=fmtb(d['time_total']),
    )
    print
    print stat


if __name__ == '__main__':
    main()