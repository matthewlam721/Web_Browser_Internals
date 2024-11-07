import urllib.parse
import dukpy
import tkinter
import socket
from chepter8 import Element, HTMLParser, DEFAULT_STYLE_SHEET, Text, DocumentLayout, HEIGHT, WIDTH, VSTEP, SCROLL_STEP, Chrome, paint_tree, CSSParser
from past_browser import tree_to_list, cascade_priority, style, print_tree

EVENT_DISPATCH_JS = \
    "new Node(dukpy.handle).dispatchEvent(new Event(dukpy.type))"

RUNTIME_JS = open("runtime.js").read()


class JSContext:
    def __init__(self, tab, id_list=None):
        self.tab = tab
        self.id_list = id_list if id_list is not None else []
        self.node_to_handle = {}
        self.handle_to_node = {}

        self.interp = dukpy.JSInterpreter()
        self._export_js_functions()

        self._load_runtime_js()
        self.createIDNodes()

    def _export_js_functions(self):
        self.interp.export_function("log", print)
        self.interp.export_function("querySelectorAll", self.querySelectorAll)
        self.interp.export_function("getAttribute", self.getAttribute)
        self.interp.export_function("innerHTML_set", self.innerHTML_set)
        self.interp.export_function("getChildren", self.getChildren)
        self.interp.export_function("createElement", self.createElement)
        self.interp.export_function("appendChild", self.appendChild)
        self.interp.export_function("insertBefore", self.insertBefore)

    def _load_runtime_js(self):
        with open("runtime.js") as f:
            self.interp.evaljs(RUNTIME_JS)

    def run(self, code):
        return self.interp.evaljs(code)

    def createElement(self, tag):
        element = Element(tag, {}, None)
        return self.get_handle(element)

    def appendChild(self, parent_handle, child_handle):
        parent = self.handle_to_node[parent_handle]
        child = self.handle_to_node[child_handle]
        child.parent = parent
        if isinstance(child, Element):
            parent.children.append(child)
        self.tab.render()

    def insertBefore(self, parent_handle, child_handle, sibling_handle):
        parent = self.handle_to_node[parent_handle]
        child = self.handle_to_node[child_handle]

        if sibling_handle is None:
            if isinstance(child, Element):
                parent.children.append(child)
        else:
            sibling = self.handle_to_node[sibling_handle]
            index = parent.children.index(sibling)
            if isinstance(child, Element):
                parent.children.insert(index, child)

        child.parent = parent
        self.tab.render()

    def createIDNodes(self):
        for node in self.id_list:
            js_string = "{} = new Node ({})".format(node.attributes["id"], self.get_handle(node))
            self.interp.evaljs(js_string)

    def dispatch_event(self, event_type, element):
        handle = self.node_to_handle.get(element, -1)
        do_default = self.interp.evaljs(EVENT_DISPATCH_JS, type=event_type, handle=handle)
        return not do_default

    def get_handle(self, element):
        if element not in self.node_to_handle:
            handle = len(self.node_to_handle)
            self.node_to_handle[element] = handle
            self.handle_to_node[handle] = element
        else:
            handle = self.node_to_handle[element]
        return handle

    def querySelectorAll(self, selector_text):
        selector = CSSParser(selector_text).selector()
        nodes = [node for node in tree_to_list(self.tab.nodes, []) if selector.matches(node)]
        return [self.get_handle(node) for node in nodes]

    def getAttribute(self, handle, attr):
        element = self.handle_to_node[handle]
        attr_value = element.attributes.get(attr, None)
        return attr_value if attr_value else ""

    def innerHTML_set(self, handle, html_string):
        doc = HTMLParser("<html><body>" + html_string + "</body></html>").parse()
        new_nodes = doc.children[0].children
        element = self.handle_to_node[handle]

        for child in tree_to_list(element, []):
            if isinstance(child, Element) and "id" in child.attributes:
                self.removeIDNode(child)

        element.children = new_nodes
        for child in tree_to_list(element, []):
            if isinstance(child, Element) and "id" in child.attributes:
                self.id_list.append(child)

            for child in element.children:
                child.parent = element
        self.tab.render()
        self.createIDNodes()

    def removeIDNode(self, node):
        self.id_list.remove(node)
        js_string = "delete {}".format(node.attributes["id"])
        self.interp.evaljs(js_string)

    def getChildren(self, handle):
        element = self.handle_to_node[handle]
        return [self.get_handle(child) for child in element.children if isinstance(child, Element)]


class Tab:
    def __init__(self, tab_height, browser):
        self.url = None
        self.history = []
        self.tab_height = tab_height
        self.browser = browser
        self.focus = None
        self.rules = []

    def load(self, url, payload=None):
        self.scroll = 0
        self.url = url
        self.history.append(url)
        body = url.request(payload)
        self.nodes = HTMLParser(body).parse()

        id_list = []
        for node in tree_to_list(self.nodes, []):
            if isinstance(node, Element):
                if "id" in node.attributes:
                    id_list.append(node)

        self.js = JSContext(self, id_list)
        scripts = [node.attributes["src"] for node
                   in tree_to_list(self.nodes, [])
                   if isinstance(node, Element)
                   and node.tag == "script"
                   and "src" in node.attributes]
        for script in scripts:
            body = url.resolve(script).request()
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
            try:
                body = url.resolve(link).request()
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

                    url = self.url.resolve(elt.attributes["href"])
                    return self.load(url)
                elif elt.tag == "input":
                    elt.attributes["value"] = ""
                    if self.focus:
                        self.focus.is_focused = False
                    self.focus = elt
                    elt.is_focused = True
                    return self.render()
                elif elt.tag == "button":
                    while elt.parent:
                        if elt.tag == "form" and "action" in elt.attributes:
                            return self.submit_form(elt)
                        elt = elt.parent
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


class URL:
    def __init__(self, url):
        self.url = url
        self.scheme, url = url.split("://", 1)
        assert self.scheme in ["http", "https", "file", "about"]
        if self.scheme == "http":
            self.port = 80
        elif self.scheme == "https":
            self.port = 443
        elif self.scheme == "file":
            self.port = None
            self.path = url
            return

        if '#' in url:
            url, self.fragment = url.split('#', 1)
        else:
            self.fragment = None

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
        fragment_part = "" if self.fragment == None else ", fragment=" + self.fragment
        return "URL(scheme={}, host={}, port={}, path={!r}{})".format(
            self.scheme, self.host, self.port, self.path, fragment_part)

    def request(self, browser=None, payload=None, method=None):
        s = socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )

        if self.scheme == "https":
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            ctx.load_default_certs(ssl.Purpose.SERVER_AUTH)
            s = ctx.wrap_socket(s, server_hostname=self.host)
        s.connect((self.host, self.port))

        query = ""
        if method == None:
            method = "POST" if payload else "GET"
        if method == "GET" and payload:
            query = "?" + payload
        body = "{} {}{} HTTP/1.0\r\n".format(method, self.path, query)
        if payload:
            length = len(payload.encode("utf8"))
            body += "Content-Length: {}\r\n".format(length)
        body += "Host: {}\r\n".format(self.host)
        body += "\r\n" + (payload if payload else "")
        s.send(body.encode("utf8"))
        response = s.makefile("r", encoding="utf8", newline="\r\n")

        statusline = response.readline()
        version, status, explanation = statusline.split(" ", 2)

        response_headers = {}
        while True:
            line = response.readline()
            if line == "\r\n":
                break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()

        assert "transfer-encoding" not in response_headers
        assert "content-encoding" not in response_headers

        body = response.read()
        s.close()

        if self.scheme == "about":
            http_body = "<!doctype html>"
            for bookmark in browser.bookmarks:
                http_body += f'<a href="{bookmark}">{bookmark}</a><br>'
            return http_body

        return body

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
            return URL(self.scheme + "://" + self.host +
                       ":" + str(self.port) + url)

    def __str__(self):
        port_part = ":" + str(self.port)
        if self.scheme == "https" and self.port == 443:
            port_part = ""
        if self.scheme == "http" and self.port == 80:
            port_part = ""
        if (self.fragment != None):
            return self.scheme + "://" + self.host + port_part + self.path + "#" + self.fragment
        else:
            return self.scheme + "://" + self.host + port_part + self.path


if __name__ == "__main__":
    import wbemocks
    _ = wbemocks.socket.patch().start()
    _ = wbemocks.ssl.patch().start()

    url = wbemocks.socket.serve("<div id=alice><div>")
    this_browser = Browser()
    this_browser.new_tab(URL(url))
    js = this_browser.active_tab.js
    js.run("alice;")

    # import sys
    # Browser().new_tab(URL(sys.argv[1]))
    # tkinter.mainloop()
