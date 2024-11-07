import socket
import tkinter
import dukpy
import ssl
import urllib
from chepter9 import EVENT_DISPATCH_JS
from chepter8 import HEIGHT, WIDTH, VSTEP, SCROLL_STEP, Chrome, HTMLParser, Element, DEFAULT_STYLE_SHEET, DocumentLayout, paint_tree, CSSParser, Text
from past_browser import tree_to_list, cascade_priority, style, print_tree
COOKIE_JAR = {}


class URL:
    def __init__(self, url):
        self.url = url
        self.scheme, url = url.split("://", 1)
        self.referrer_policy = None

        # Ensure the scheme is one of the accepted types
        assert self.scheme in ["http", "https", "file", "about"]

        # Set port and secure flag based on scheme
        if self.scheme == "http":
            self.port = 80
        elif self.scheme == "https":
            self.port = 443
            self.secure = True
        elif self.scheme == "file":
            self.port = None
            self.path = url
            return

        # Handle fragments
        if '#' in url:
            url, self.fragment = url.split('#', 1)
        else:
            self.fragment = None

        # Handle bookmarks
        if self.scheme == "about":
            self.port = "None"
            self.host = "None"
            self.path = "bookmarks"
        else:
            if "/" not in url:
                url = url + "/"
            self.host, url = url.split("/", 1)
            self.path = "/" + url
            if ":" in self.host:
                self.host, port = self.host.split(":", 1)
                self.port = int(port)

    def __repr__(self):
        fragment_part = "" if self.fragment is None else ", fragment=" + self.fragment
        return f"URL(scheme={self.scheme}, host={self.host}, port={self.port}, path={self.path!r}{fragment_part})"

    def request(self, top_level_url, payload=None):
        s = socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
        s.connect((self.host, self.port))

        try:
            if self.scheme == "https":
                ctx = ssl.create_default_context()
                s = ctx.wrap_socket(s, server_hostname=self.host)
        except ssl.SSLCertVerificationError:
            self.secure = False
            return {"Content-Type": "text/plain"}, "Secure Connection Failed"

        method = "POST" if payload else "GET"
        request = self._build_request(method, top_level_url, payload)
        s.send(request.encode("utf8"))

        response_headers, content = self._read_response(s)
        s.close()

        return response_headers, content

    def _build_request(self, method, top_level_url, payload):
        request = f"{method} {self.path} HTTP/1.0\r\n"
        request += f"Host: {self.host}\r\n"

        if self.host in COOKIE_JAR:
            cookie, params = COOKIE_JAR[self.host]
            allow_cookie = self._should_allow_cookie(method, top_level_url, params)
            if allow_cookie:
                request += f"Cookie: {cookie}\r\n"

        if payload:
            content_length = len(payload.encode("utf8"))
            request += f"Content-Length: {content_length}\r\n"

        should_send_referrer = self._should_send_referrer(top_level_url)
        if should_send_referrer:
            request += f"Referer: {top_level_url}\r\n"

        request += "\r\n"
        if payload:
            request += payload

        return request

    def _should_allow_cookie(self, method, top_level_url, params):
        allow_cookie = True
        if top_level_url and params.get("samesite", "none") == "lax":
            if method != "GET":
                allow_cookie = self.host == top_level_url.host
        return allow_cookie

    def _should_send_referrer(self, top_level_url):
        return top_level_url is not None and \
               top_level_url.referrer_policy != "no-referrer" and \
               (top_level_url.referrer_policy != "same-origin" or top_level_url.origin() == self.origin())

    def _read_response(self, s):
        response = s.makefile("r", encoding="utf8", newline="\r\n")

        statusline = response.readline()
        version, status, explanation = statusline.split(" ", 2)

        response_headers = self._read_response_headers(response)

        if "set-cookie" in response_headers:
            self._handle_set_cookie(response_headers)

        if "referrer-policy" in response_headers:
            self.referrer_policy = response_headers["referrer-policy"]

        assert "transfer-encoding" not in response_headers
        assert "content-encoding" not in response_headers

        content = response.read()
        if self.scheme == "https" and self.secure:
            content = "\N{lock}" + content

        return response_headers, content

    def _read_response_headers(self, response):
        response_headers = {}
        while True:
            line = response.readline()
            if line == "\r\n":
                break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()
        return response_headers

    def _handle_set_cookie(self, response_headers):
        cookie = response_headers["set-cookie"]
        params = {}
        if ";" in cookie:
            cookie, rest = cookie.split(";", 1)
            for param in rest.split(";"):
                if '=' in param:
                    param, value = param.split("=", 1)
                else:
                    value = "true"
                params[param.strip().casefold()] = value.casefold()
        COOKIE_JAR[self.host] = (cookie, params)

    def resolve(self, url):
        if "://" in url:
            return URL(url)
        if not url.startswith("/"):
            dir, _ = self.path.rsplit("/", 1)
            while url.startswith("../"):
                _, url = url.split("/", 1)
                if "/" in dir:
                    dir, _ = dir.rsplit("/", 1)
            url = dir + "/" + url
        if url.startswith("//"):
            return URL(self.scheme + ":" + url)
        else:
            return URL(self.scheme + "://" + self.host + ":" + str(self.port) + url)

    def __str__(self):
        port_part = ":" + str(self.port)
        if self.scheme == "https" and self.port == 443:
            port_part = ""
        if self.scheme == "http" and self.port == 80:
            port_part = ""
        if self.fragment is not None:
            return f"{self.scheme}://{self.host}{port_part}{self.path}#{self.fragment}"
        else:
            return f"{self.scheme}://{self.host}{port_part}{self.path}"

    def origin(self):
        return f"{self.scheme}://{self.host}:{self.port}"





class JSContext:
    def __init__(self, tab):
        self.tab = tab

        self.interp = dukpy.JSInterpreter()
        self.interp.export_function("log", print)
        self.interp.export_function("querySelectorAll",
                                    self.querySelectorAll)
        self.interp.export_function("getAttribute",
                                    self.getAttribute)
        self.interp.export_function("innerHTML_set", self.innerHTML_set)
        self.interp.export_function("XMLHttpRequest_send",
                                    self.XMLHttpRequest_send)
        self.interp.export_function("get_cookies", self.getCookies)
        self.interp.export_function("set_cookies", self.setcookies)

        with open("runtime.js") as f:
            self.interp.evaljs(f.read())

        self.node_to_handle = {}
        self.handle_to_node = {}

    def run(self, code):
        return self.interp.evaljs(code)

    def createElement(self, tag):
        elt = Element(tag, {}, None)
        return self.get_handle(elt)

    def getCookies(self):
        cookies = COOKIE_JAR.get(self.tab.url.host, ("", {}))
        if "httponly" in cookies[1]:
            return ""
        return cookies[0]

    def setcookies(self, cookies):
        cookiesjar = COOKIE_JAR.get(self.tab.url.host, ("", {}))
        if "httponly" in cookiesjar[1]:
            return
        params = {}
        if ";" in cookies:
            cookies, rest = cookies.split(";", 1)
            for param in rest.split(";"):
                if '=' in param:
                    param, value = param.split("=", 1)
                else:
                    value = "true"
                params[param.strip().casefold()] = value.casefold()
        COOKIE_JAR[self.tab.url.host] = (cookies, params)

    def appendChild(self, parentHandle, childHandle):
        parent = self.handle_to_node[parentHandle]
        child = self.handle_to_node[childHandle]
        child.parent = parent
        if isinstance(child, Element):
            parent.children.append(child)
        self.tab.render()

    def insertBefore(self, parent, child, sibling):
        parent_elt = self.handle_to_node[parent]
        child_elt = self.handle_to_node[child]

        if sibling is None:
            if isinstance(child_elt, Element):
                parent_elt.children.append(child_elt)
        else:
            sibling_elt = self.handle_to_node[sibling]
            index = parent_elt.children.index(sibling_elt)
            parent_elt.children.insert(index, child_elt)

        child_elt.parent = parent_elt
        self.tab.render()

    def createIDNodes(self):
        for node in self.id_list:
            # Build str nodeID = handle
            javascript_string = "{} = new Node ({})".format(
                node.attributes["id"], self.get_handle(node))
            self.interp.evaljs(javascript_string)

    def dispatch_event(self, type, elt):
        handle = self.node_to_handle.get(elt, -1)
        do_default = self.interp.evaljs(
            EVENT_DISPATCH_JS, type=type, handle=handle)
        return not do_default

    def get_handle(self, elt):
        if elt not in self.node_to_handle:
            handle = len(self.node_to_handle)
            self.node_to_handle[elt] = handle
            self.handle_to_node[handle] = elt
        else:
            handle = self.node_to_handle[elt]
        return handle

    def querySelectorAll(self, selector_text):
        selector = CSSParser(selector_text).selector()
        nodes = [node for node
                 in tree_to_list(self.tab.nodes, [])
                 if selector.matches(node)]
        return [self.get_handle(node) for node in nodes]

    def getAttribute(self, handle, attr):
        elt = self.handle_to_node[handle]
        attr = elt.attributes.get(attr, None)
        return attr if attr else ""

    def innerHTML_set(self, handle, s):
        doc = HTMLParser("<html><body>" + s + "</body></html>").parse()
        new_nodes = doc.children[0].children
        elt = self.handle_to_node[handle]

        for child in tree_to_list(elt, []):
            if isinstance(child, Element):
                if "id" in child.attributes:
                    self.removeIDNode(child)

        elt.children = new_nodes
        for child in tree_to_list(elt, []):
            if isinstance(child, Element):
                if "id" in child.attributes:
                    self.id_list.append(child)

            for child in elt.children:
                child.parent = elt
        self.tab.render()
        self.createIDNodes()

    def removeIDNode(self, node):
        self.id_list.remove(node)
        # Build str nodeID = handle
        javascript_string = "delete {}".format(node.attributes["id"])
        self.interp.evaljs(javascript_string)

    def getChildren(self, handle):
        elt = self.handle_to_node[handle]
        return [self.get_handle(child) for child in elt.children if isinstance(child, Element)]

    def XMLHttpRequest_send(self, method, url, body):
        full_url = self.tab.url.resolve(url)
        if not self.tab.allowed_request(full_url):
            raise Exception("Cross-origin XHR blocked by CSP")
        headers, out = full_url.request(self.tab.url, body)
        if full_url.origin() != self.tab.url.origin():
            raise Exception("Cross-origin XHR request not allowed")
        return out


class Tab:
    def __init__(self, tab_height, browser):
        self.url = None
        self.history = []
        self.tab_height = tab_height
        self.browser = browser
        self.focus = None
        self.rules = []

    def allowed_request(self, url):
        return self.allowed_origins == None or \
            url.origin() in self.allowed_origins

    def load(self, url, payload=None):
        headers, body = url.request(self.url, payload)
        self.scroll = 0
        self.url = url
        self.history.append(url)

        self.allowed_origins = None
        if "content-security-policy" in headers:
            csp = headers["content-security-policy"].split()
            if len(csp) > 0 and csp[0] == "default-src":
                self.allowed_origins = []
                for origin in csp[1:]:
                    self.allowed_origins.append(URL(origin).origin())

        self.nodes = HTMLParser(body).parse()

        self.js = JSContext(self)
        scripts = [node.attributes["src"] for node
                   in tree_to_list(self.nodes, [])
                   if isinstance(node, Element)
                   and node.tag == "script"
                   and "src" in node.attributes]
        for script in scripts:
            script_url = url.resolve(script)
            if not self.allowed_request(script_url):
                print("Blocked script", script, "due to CSP")
                continue
            header, body = script_url.request(url)
            try:
                self.js.run(body)
            except dukpy.JSRuntimeError as e:
                print("Script", script, "crashed", e)

        self.rules = DEFAULT_STYLE_SHEET.copy()
        links = [node.attributes["href"]
                 for node in tree_to_list(self.nodes, [])
                 if isinstance(node, Element)
                 and node.tag == "link"
                 and node.attributes.get("rel") == "stylesheet"
                 and "href" in node.attributes]
        for link in links:
            style_url = url.resolve(link)
            if not self.allowed_request(style_url):
                print("Blocked style", link, "due to CSP")
                continue
            try:
                header, body = style_url.request(url)
            except:
                continue
            self.rules.extend(CSSParser(body).parse())
        self.render()

    def render(self):
        style(self.nodes, sorted(self.rules, key=cascade_priority))
        self.document = DocumentLayout(self.nodes)
        self.document.layout()
        self.display_list = []
        paint_tree(self.document, self.display_list)

    def click(self, x, y):
        self.focus = None
        y += self.scroll
        objs = [obj for obj in tree_to_list(self.document, [])
                if obj.x <= x < obj.x + obj.width
                and obj.y <= y < obj.y + obj.height]
        if not objs:
            return
        elt = objs[-1].node
        do_default = True
        while elt:
            default = self.js.dispatch_event("click", elt)
            event = self.js.interp.evaljs("dispatchEvent;")
            propagate = event["should_propagate"]
            if default:
                do_default = False
            if not propagate:
                break
            elt = elt.parent

        if do_default:
            elt = objs[-1].node
            while elt:
                if isinstance(elt, Text):
                    pass
                elif elt.tag == "a" and "href" in elt.attributes:
                    # if self.js.dispatch_event("click", elt):
                    #     return
                    # else:
                    #     self.js.dispatch_event("click", elt)
                    url = self.url.resolve(elt.attributes["href"])
                    return self.load(url)
                elif elt.tag == "input":
                    # if self.js.dispatch_event("click", elt):
                    #     return
                    elt.attributes["value"] = ""
                    if self.focus:
                        self.focus.is_focused = False
                    self.focus = elt
                    elt.is_focused = True
                    return self.render()
                elif elt.tag == "button":
                    # if self.js.dispatch_event("click", elt):
                    #     return
                    while elt.parent:
                        if elt.tag == "form" and "action" in elt.attributes:
                            return self.submit_form(elt)
                        elt = elt.parent
                # else:
                    # if self.js.dispatch_event("click", elt):
                    #     return
                elt = elt.parent

    def scroll_to(self, id):
        for obj in tree_to_list(self.document, []):
            if isinstance(obj.node, Element):
                if obj.node.attributes.get("id") == id:
                    self.scroll = obj.y
                    return

    def draw(self, canvas, offset):
        for cmd in self.display_list:
            if cmd.rect.top > self.scroll + self.tab_height:
                continue
            if cmd.rect.bottom < self.scroll:
                continue
            cmd.execute(self.scroll - offset, canvas)

    def scrolldown(self):
        max_y = max(
            self.document.height + 2*VSTEP - self.tab_height, 0)
        self.scroll = min(self.scroll + SCROLL_STEP, max_y)

    def middleClick(self, x, y, browser):
        y += self.scroll
        objs = [obj for obj in tree_to_list(self.document, [])
                if obj.x <= x < obj.x + obj.width
                and obj.y <= y < obj.y + obj.height]
        if not objs:
            return
        elt = objs[-1].node
        while elt:
            if isinstance(elt, Text):
                pass
            elif elt.tag == "a" and "href" in elt.attributes:
                url = self.url.resolve(elt.attributes["href"])
                browser.new_tab(url)
                browser.active_tab = self
                return
            elt = elt.parent

    # chapter8-enterkey
    def enter(self):
        if self.focus:
            elt = self.focus.parent
            while elt:
                if elt.tag == "form" and "action" in elt.attributes:
                    return self.submit_form(elt)
                else:
                    elt = elt.parent

    def go_back(self):
        if len(self.history) > 1:
            self.history.pop()
            back = self.history.pop()
            self.load(back)

    def __repr__(self):
        return "Tab(history={})".format(self.history)

    def submit_form(self, elt):
        if self.js.dispatch_event("submit", elt):
            return
        inputs = [node for node in tree_to_list(elt, [])
                  if isinstance(node, Element)
                  and node.tag == "input"
                  and "name" in node.attributes]

        body = ""
        for input in inputs:
            name = input.attributes["name"]
            value = input.attributes.get("value", "")
            name = urllib.parse.quote(name)
            value = urllib.parse.quote(value)
            body += "&" + name + "=" + value
        body = body[1:]

        url = self.url.resolve(elt.attributes["action"])
        self.load(url, body)

    def keypress(self, char):
        if self.focus:
            if self.js.dispatch_event("keydown", self.focus):
                return
            self.focus.attributes["value"] += char
            self.render()


class Browser:
    def __init__(self):
        self.window = tkinter.Tk()
        self.canvas = tkinter.Canvas(
            self.window,
            width=WIDTH,
            height=HEIGHT,
            bg="white",
        )
        self.canvas.pack()

        self.window.bind("<Down>", self.handle_down)
        self.window.bind("<Button-1>", self.handle_click)
        self.window.bind("<Key>", self.handle_key)
        self.window.bind("<Return>", self.handle_enter)
        self.window.bind("<BackSpace>", self.handle_backspace)
        self.window.bind("<Button-2>", self.handle_middle_click)
        # chapter8-enterkey
        self.window.bind("<Return>", self.handle_enter)

        self.tabs = []
        self.active_tab = None
        self.focus = None
        self.chrome = Chrome(self)
        self.bookmarks = []

    def handle_middle_click(self, e):
        if e.y < self.chrome.bottom:
            pass
        else:
            tab_y = e.y - self.chrome.bottom
            self.active_tab.middleClick(e.x, tab_y, self)
        self.draw()

    def handle_backspace(self, e):
        self.chrome.backspace()
        self.draw()

    def handle_down(self, e):
        self.active_tab.scrolldown()
        self.draw()

    def handle_click(self, e):
        if e.y < self.chrome.bottom:
            self.focus = None
            self.chrome.click(e.x, e.y)
        else:
            self.focus = "content"
            self.chrome.blur()
            tab_y = e.y - self.chrome.bottom
            self.active_tab.click(e.x, tab_y)
        self.draw()

    def handle_key(self, e):
        if len(e.char) == 0:
            return
        if not (0x20 <= ord(e.char) < 0x7f):
            return
        if self.chrome.keypress(e.char):
            self.draw()
        elif self.focus == "content":
            self.active_tab.keypress(e.char)
            self.draw()

    def handle_enter(self, e):
        # chapter8-enterkey
        if self.focus == 'content':
            self.active_tab.enter()
        else:
            self.chrome.enter()
        self.draw()

    def new_tab(self, url):
        new_tab = Tab(HEIGHT - self.chrome.bottom, self)
        new_tab.load(url)
        self.active_tab = new_tab
        self.tabs.append(new_tab)
        self.draw()

    def draw(self):
        self.canvas.delete("all")
        self.active_tab.draw(self.canvas, self.chrome.bottom)
        for cmd in self.chrome.paint():
            cmd.execute(0, self.canvas)


if __name__ == "__main__":
    import wbemocks
    _ = wbemocks.socket.patch().start()
    _ = wbemocks.ssl.patch().start()
    wbemocks.NORMALIZE_FONT = True

    url = "http://wbemocks.wbemocks.chapter10-new-inputs/"
    page = """<!doctype html>
    <form action="/tricky" method=POST>
      <p>Not hidden: <input name=visible value=1></p>
      <p>Hidden: <input type=hidden name=invisible value=doNotShowMe></p>
      <p><button>Submit!</button></p>
    </form>"""
    wbemocks.socket.respond_ok(url, page)
    wbemocks.socket.respond(
        url + "tricky", b"HTTP/1.0 200 OK\r\n\r\nEmpty", "POST")

    this_browser = Browser()
    this_browser.new_tab(URL(url))
    print_tree(this_browser.tabs[0].document)
