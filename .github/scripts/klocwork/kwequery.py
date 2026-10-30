'''
  Script: kwequery.py
  Desc: Emenda Klocwork export to csv or xml
  Developed By: www.emenda.com
  Last Updated: 29th November 2018

  v3.3
  - Auth fallback for modern Validate servers: when the plain
    ~/.klocwork/ltoken file has no entry for the target server (its token is
    in the encrypted tokens.jks keystore instead), the token is now fetched
    automatically via the `kwauth --print-auth-info` CLI (locate kwauth via
    the KLOCWORK_KWAUTH env var or PATH). No more manual token extraction.
  - Security: the outgoing POST body (which contains the ltoken) is no longer
    printed unconditionally to stdout. Request debug logging is now gated
    behind the KLOCWORK_DEBUG env var and always redacts the ltoken value.
  - Fixed SyntaxWarning (invalid escape sequences) in the xml pretty-printer
    regex by using raw strings.
  v3.2
  - Extracted parse_klocwork_ndjson() so kw_export.py/kw_update.py/kw_migrate.py
    can reuse response parsing instead of duplicating it (no behaviour change)
  v3.1
  - When producing a csv output it now ensures all records have the same keys
  v3.0
  - Fixed regex on line 244 for project names to accept '-'
  v2.9
  - Fixed curl query and support for 'ao'
  v2.8
  - Option to manually enter the ltoken key
  v2.7
  - Moved decoding into class
  v2.6
  - Improved error messages and return codes
  v2.5
  - Added "additional_options" option for manual entry of optional API options
  v2.4
  - Project/url handled by class
  v2.3
  - No longer require project in url when running projects action
  v2.2
  - Removed ssl certificate validation for py 2.x
  v2.1
  - Support for KLOCWORK_LTOKEN env var
  v2.0
  - Charmed
  v1.9
  - Support for hyphen in project name
  v1.8
    - Removed need for username
  v1.8
    - Removed need for username
  v1.7
    - Add option to use curl
  v1.6
    - Changed prints to v3.x supported
  v1.5
    - Corrected regex to handle '-' in hostname
  v1.4
    - Fixed open file failure output
  v1.3
    - Check API response and set line sep accordingly
  v1.2
    - Made csv header first letter upper case
    - Changed xml output to use tag values rather than attributes
    - Improved json conversion handling, try/catch to ouput offenses
  v1.1
    - Corrected regex to handle '-' in server or project name
'''

import os
import sys
import re
import datetime
import argparse
import socket
import json
import xml.etree.ElementTree as ET
from xml.dom.minidom import parseString
import subprocess
if sys.version_info >= (3, 0):
    import urllib.parse
    import urllib.request
else:
    import urllib
    import urllib2
    import ssl


parser = argparse.ArgumentParser(prog="kwequery",
                                 description="Klocwork query to csv or xml")
parser.add_argument('-u', "--url", nargs='?', required=True,
                    metavar="project url", help="(mandatory) http[s]://<server>:<port>/<project>")
parser.add_argument("--curl", action="store_true", default=False,
                    help="(optional) Use curl rather than python url query")
parser.add_argument('-a', "--action", nargs='?', default="search", metavar="query",
                    help="(optional) Klocwork action e.g. 'search' for issues (default), 'metrics' for metrics")
parser.add_argument('-ao', "--additional_options", nargs='?', default=None, metavar="opts",
                    help="(optional) Additional command options i.e. {'view':'myView', 'limit':'2'}")
parser.add_argument('-q', "--query", nargs='?', default="",
                    metavar="query", help="(mandatory) Klocwork search query, e.g. severity:1-3")
parser.add_argument('-f', "--format", nargs='?', default='csv',
                    metavar="format", help="(optional) Output format 'xml'/'csv'(default)/'txt'")
parser.add_argument('-o', "--out", nargs='?', default=os.getcwd() + os.sep + "kwequery.csv",
                    metavar="output", help="(mandatory if format is specified) output file. Default is kwequery.csv")
parser.add_argument('-l', "--ltoken", nargs='?', default=None,
                    metavar="ltoken key", help="(mandatory if user name is specified) Manually define the Klocwork ltoken key")
parser.add_argument("--user", nargs='?', default=None,
                    metavar="user name", help="(optional) Required if manually defining ltoken key")


class KwConnection:
    def __init__(self, url, ltoken=None, user=None):
        self.url = re.sub(r'^(https?://[\w.-]+:\d*)/.*$', r'\1', url)
        self.project = None
        # Project name may contain '/' (Validate stream paths, e.g.
        # 'Traveo-2/Aravalli_s3p_e4m') as well as '.', so capture the whole
        # remaining path after host:port rather than just [\w-]+.
        m = re.match(r'^https?://[\w.-]+:\d*/(.+)$', url)
        if m:
            self.project = m.group(1)
        self.server = re.sub(r'^https?://([\w.-]+):\d*$', r'\1', self.url)
        if self.server == "localhost":
            self.server = socket.gethostname()
            self.url = self.url.replace("localhost", self.server)
        self.port = re.sub(r'^https?://[\w.-]+:(\d*)$', r'\1', self.url)
        self.api = self.url + "/review/api"
        self.user = user
        if ltoken:
            self.ltoken = ltoken
        else:
            self.ltoken = self._get_ltoken()
            if not self.ltoken:
                # Modern Validate/Klocwork servers store the token in the
                # encrypted tokens.jks keystore (referenced by
                # ~/.klocwork/credentials), NOT the plain-text
                # ~/.klocwork/ltoken file the scan above reads - so that scan
                # finds nothing for such a server. Fall back to asking the
                # kwauth CLI for the token (it knows how to read the keystore).
                self.ltoken = self._get_ltoken_via_kwauth()
        if not self.ltoken:
            print("ERROR: No Klocwork token found please run \"kwauth --url %s\"" % self.url)
            sys.exit(1)

    def search(self, action, query=None, opts=None):
        vals = {"action": action,
                "user": self.user}
        if self.project:
            vals["project"] = self.project
        if query:
            vals["query"] = query
        if opts:
            opts.update(vals)  # Odd processing to ensure opts don't overwrite existing vals
            vals = opts
        return self._query(vals)

    def _query(self, vals):
        vals["ltoken"] = self.ltoken
        self._debug_log(vals)
        if sys.version_info >= (3, 0):
            data = urllib.parse.urlencode(vals)
            request = urllib.request.Request(self.api, str.encode(data))
            try:
                response = urllib.request.urlopen(request)
                return self.decode(response.read().decode("utf-8"))
            except urllib.request.HTTPError as e:
                print("ERROR: HTTP Connection Error code: %s" % str(e))
                sys.exit(1)
            except urllib.request.URLError as e:
                print("ERROR: URL Error: %s" % str(e))
                sys.exit(1)
        else:
            data = urllib.urlencode(vals)
            request = urllib2.Request(self.api, data)
            try:
                response = urllib2.urlopen(request, context=ssl._create_unverified_context())
                return self.decode(response.read().decode("utf-8"))
            except urllib2.HTTPError as e:
                print("ERROR: HTTP Connection Error code: %s" % str(e))
                sys.exit(1)
            except urllib2.URLError as e:
                print("ERROR: URL Error: %s" % str(e))
                sys.exit(1)

    @staticmethod
    def _debug_log(vals):
        """Print the outgoing POST parameters for debugging, gated behind the
        KLOCWORK_DEBUG env var and with the secret ltoken value redacted so it
        is never echoed to stdout/logs."""
        if not os.environ.get("KLOCWORK_DEBUG"):
            return
        redacted = {k: ("***redacted***" if k == "ltoken" else v) for k, v in vals.items()}
        print("DEBUG: POST action=%s params=%s" % (vals.get("action"), redacted))

    def _get_ltoken(self):
        if os.environ.get("KLOCWORK_LTOKEN"):
            token_file = os.environ["KLOCWORK_LTOKEN"]
        else:
            home = os.path.expanduser("~")
            if not home:
                home = os.environ['USERPROFILE']
            if not home:
                print("ERROR: Unable to determine user home directory to locate ltoken")
                sys.exit(1)
            token_file = os.path.join(home, ".klocwork", "ltoken")
        if not os.path.isfile(token_file):
            # No plain ltoken file at all - let the caller try the kwauth
            # keystore fallback instead of hard-failing here.
            return ''
        ltoken_file = open_file(token_file, 'r')
        for line in ltoken_file:
            line_split = line.strip().split(';')
            if line_split[0].lower() == self.server.lower() \
                    and line_split[1].lower() == self.port.lower():
                self.user = line_split[2]
                ltoken = str(line_split[3])
                ltoken_file.close()
                return ltoken
        ltoken_file.close()
        return ''

    def _get_ltoken_via_kwauth(self):
        """Fallback auth for modern Validate/Klocwork servers whose token lives
        in the encrypted tokens.jks keystore (not the plain
        ~/.klocwork/ltoken file): ask the `kwauth` CLI to print this server's
        auth info and parse the token out of it. Returns '' (never raises) if
        kwauth is missing or fails, so the caller can emit the standard
        "run kwauth" hint.

        The kwauth executable is resolved from the KLOCWORK_KWAUTH env var (an
        explicit full path to kwauth/kwauth.exe); otherwise plain 'kwauth' is
        expected on PATH. As a side effect, self.user is populated from the
        returned username when it wasn't supplied explicitly."""
        exe = os.environ.get("KLOCWORK_KWAUTH") or "kwauth"
        try:
            proc = subprocess.run(
                [exe, "--url", self.url, "--print-auth-info"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=True, timeout=30)
        except (OSError, ValueError, subprocess.SubprocessError):
            return ''
        if proc.returncode != 0 or not proc.stdout:
            return ''
        try:
            info = json.loads(proc.stdout.strip())
        except ValueError:
            return ''
        token = info.get("token") or ''
        if token and not self.user:
            self.user = info.get("username")
        return token

    @staticmethod
    def decode(output):
        output = output.replace("\u003d", "=")
        output = output.replace("\u0027", "'")
        return output


# This is used to ensure the csv headings are aligned correctly, by inserting empty values
def even_out_dict(result_dict):
    keys = []
    for result in result_dict:
        for key in result.keys():
            if key not in keys:
                keys.append(key)
    for i, s in enumerate(result_dict):
        for key in keys:
            if key not in s.keys():
                result_dict[i][key] = ''
    return result_dict


def create_csv(result_dict):
    delim = ';'
    csv = ""
    result_dict = even_out_dict(result_dict)
    keys = result_dict[0].keys()
    for key in keys:
        csv += str(key.title()).rstrip() + delim
    csv = csv.rstrip(delim) + '\n'
    for line in result_dict:
        for val in line.values():
            csv += str(val).rstrip() + delim
        csv = csv.rstrip(delim) + '\n'
    return csv


def create_xml(result_dict):
    xml = ET.Element('issues')
    for line in result_dict:
        issue = ET.SubElement(xml, 'issue')
        for key in line:
            ET.SubElement(issue, key).text = str(line[key])
    return re.sub(r'>\n\s+([^<>\s].*?)\n\s+</', r'>\g<1></', parseString(ET.tostring(xml)).toprettyxml())


def open_file(name, x):
    try:
        # Force UTF-8 for text modes so Klocwork issue data containing non-Latin
        # characters (e.g. full-width '\u3002') doesn't crash on Windows, where
        # open() would otherwise default to the cp1252 codec.
        if 'b' in x:
            f = open(name, x)
        else:
            f = open(name, x, encoding='utf-8')
    except IOError as e:
        sys.exit("ERROR: %s" % str(e))
    return f


def opts_to_dict(opts):
    opts = opts.replace("'", '"')
    try:
        opts = json.loads(opts)
    except:
        e = sys.exc_info()[0]
        print("ERROR: Invalid option format: %s" % opts)
        print("ERROR: %s" % str(e))
        sys.exit(1)

    return opts


def parse_klocwork_ndjson(result):
    """Parse a raw Klocwork API response (newline-delimited JSON, one issue per
    line) into a list of dicts, converting 13-digit millisecond '*date*' fields
    into 'DD-MM-YYYY HH:MM:SS' strings. Returns [] if the server reported no
    records. Exits the process on malformed JSON (mirrors original kwequery
    behaviour), so callers can treat a non-empty return as fully parsed.

    This is shared by kwequery.py, kw_export.py, kw_update.py and
    kw_migrate.py - keep it here as the single source of truth for response
    parsing rather than duplicating it in each script.
    """
    if not result or len(result) == 0 or result[0] == "":
        return []
    linesep = '\r\n'
    if linesep not in result:
        linesep = '\n'
    lines = result.rstrip().split(linesep)
    result_dict = []
    for line in lines:
        line = line.rstrip()
        if not line:
            continue
        try:
            result_dict.append(json.loads(line))
        except ValueError:
            print("ERROR: Error reading json:")
            print("ERROR: \"%s\"" % line)
            sys.exit(1)
    for idx, row in enumerate(result_dict):
        for key in row.keys():
            if "date" in key \
                    and len("%s" % result_dict[idx][key]) == 13:
                s = result_dict[idx][key] / 1000.0
                result_dict[idx][key] = \
                    datetime.datetime.fromtimestamp(s).strftime('%d-%m-%Y %H:%M:%S')
    return result_dict


def main():
    args = parser.parse_args()
    if not args.format == 'xml' and not args.format == 'csv' and not args.format == 'txt':
        print("ERROR: Invalid format specified (xml/csv): %s" % args.format)
        sys.exit(1)
    no_project_actions = ["projects"]  # List of actions that do not require project
    if args.action in no_project_actions:
        if not re.match(r'^https?://[\w.-]+:\d*', args.url):
            print("ERROR: Invalid url: %s" % args.url)
            print("ERROR: http[s]://<server>:<port>")
            sys.exit(1)
    elif not re.match(r'^https?://[\w.-]+:\d*/.+$', args.url):
        print("ERROR: Invalid url: %s" % args.url)
        print("ERROR: http[s]://<server>:<port>/<project>")
        sys.exit(1)
    if args.ltoken and not args.user:
        print("ERROR: When defining ltoken key the '--user' option is required")
        sys.exit(1)

    opts = None
    if args.additional_options:
        opts = opts_to_dict(args.additional_options)

    kwdb = KwConnection(args.url, args.ltoken, args.user)
    if args.curl:
        query = "&query=" + args.query if args.query else ""
        additional_opts = ""
        if args.additional_options:
            for key in opts:
                additional_opts += "&%s=%s" % (key, opts[key])
        cmd = "curl -k --data \"action=%s&user=%s&project=%s%s%s\" %s/review/api" \
              % (args.action, kwdb.user, kwdb.project, query, additional_opts, kwdb.url)
        p = subprocess.Popen(cmd, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        output, err = p.communicate()
        result = kwdb.decode(output.decode("utf-8"))
    else:
        result = kwdb.search(args.action, args.query, opts)

    if not result or len(result) == 0 or result[0] == "":
        print("INFO: No Records Found")
        sys.exit(0)
    result_dict = parse_klocwork_ndjson(result)
    if not result_dict:
        print("INFO: No Records Found")
        sys.exit(0)
    if args.format == 'xml':
        output = create_xml(result_dict)
        # Do not rename as the specified output file may not be kwequery.
        #if args.out.endswith('.csv'):
            #args.out = 'kwequery.xml'
    else:
        output = create_csv(result_dict)
    out_file = open_file(args.out, 'w')
    out_file.write(output)
    out_file.close()


if __name__ == '__main__':
    main()
