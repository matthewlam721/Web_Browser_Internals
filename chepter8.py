from ast import List
import socket
import ssl
import tkinter
import tkinter.font
import urllib.parse
import server
from chepter7 import style, Rect, DrawRect, DrawLine, BLOCK_ELEMENTS, DrawOutline, get_font
from past_browser import cascade_priority, print_tree, tree_to_list, DescendantSelector

WIDTH, HEIGHT = 800, 600
HSTEP, VSTEP = 13, 18
SCROLL_STEP = 100
Emoji_Dictionary = {}


class CSSParser:
    def __init__(self, s):
        self.s = s
        self.i = 0

    def whitespace(self):
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1

    def literal(self, literal):
        if not (self.i < len(self.s) and self.s[self.i] == literal):
            raise Exception("Parsing error")
        self.i += 1

    def word(self):
        start = self.i
        while self.i < len(self.s):
            if self.s[self.i].isalnum() or self.s[self.i] in "#-.%":
                self.i += 1
            else:
                break
        if not (self.i > start):
            raise Exception("Parsing error")
        return self.s[start:self.i]

    def pair(self):
        prop = self.word()

        self.whitespace()
        self.literal(":")
        self.whitespace()
        if prop.casefold() == "font":
            i = self.i
            self.ignore_until([";", "}"])
            val = self.s[i:self.i].strip()
        else:
            val = self.word()
        return prop.casefold(), val

    def ignore_until(self, chars):
        while self.i < len(self.s):
            if self.s[self.i] in chars:
                return self.s[self.i]
            else:
                self.i += 1
        return None

    def body(self):
        pairs = {}
        while self.i < len(self.s) and self.s[self.i] != "}":
            try:
                prop, val = self.pair()
                if (prop == "font"):
                    split_values = val.split()
                    if len(split_values) == 1:
                        pairs["font-family"] = split_values[0]

                    elif len(split_values) == 2:
                        pairs["font-size"] = split_values[0]
                        pairs["font-family"] = split_values[1]

                    elif len(split_values) == 3:
                        if split_values[0] == "italic":
                            pairs["font-style"] = split_values[0]
                        else:
                            pairs["font-weight"] = split_values[0]
                        pairs["font-size"] = split_values[1]
                        pairs["font-family"] = split_values[2]

                    elif len(split_values) == 4:
                        pairs["font-style"] = split_values[0]
                        pairs["font-weight"] = split_values[1]
                        pairs["font-size"] = split_values[2]
                        pairs["font-family"] = split_values[3]

                    elif len(split_values) > 4:
                        pairs["font-style"] = split_values[0]
                        pairs["font-weight"] = split_values[1]
                        pairs["font-size"] = split_values[2]
                        font_family = """ """     .join(split_values[3:])
                        pairs["font-family"] = font_family

                else:
                    pairs[prop] = val
                self.whitespace()
                self.literal(";")
                self.whitespace()
            except Exception:
                why = self.ignore_until([";", "}"])
                if why == ";":
                    self.literal(";")
                    self.whitespace()
                else:
                    break
        return pairs

    def selector(self):
        word = self.word()
        if word[0] == ".":
            out = ClassSelector(word[1:])
        else:
            out = TagSelector(word.casefold())
        self.whitespace()
        while self.i < len(self.s) and self.s[self.i] != "{":
            tag = self.word()
            if tag[0] == ".":
                descendant = ClassSelector(tag[1:])
            else:
                descendant = TagSelector(tag.casefold())
            out = DescendantSelector(out, descendant)
            self.whitespace()
        return out

    def parse(self):
        rules = []
        while self.i < len(self.s):
            try:
                self.whitespace()
                selector = self.selector()
                self.literal("{")
                self.whitespace()
                body = self.body()
                self.literal("}")
                rules.append((selector, body))
            except Exception:
                why = self.ignore_until(["}"])
                if why == "}":
                    self.literal("}")
                    self.whitespace()
                else:
                    break
        return rules


class Element:
    def __init__(self, tag, attributes, parent):
        self.tag = tag
        self.attributes = attributes
        self.children = []
        self.parent = parent
        self.style = {}
        self.is_focused = False

    def __repr__(self):
        attrs = [" " + k + "=\"" + v + "\"" for k,
                 v in self.attributes.items()]
        attr_str = ""
        for attr in attrs:
            attr_str += attr
        return "<" + self.tag + attr_str + ">"

    def parse_style_attributes(self):
        # Parse the 'style' attribute and return a dictionary of style properties
        style = self.attributes.get('style', '')
        return dict(item.split(':') for item in style.split(';') if item)


class Text:
    def __init__(self, text, parent):
        self.text = text
        self.children = []
        self.parent = parent
        self.style = {}
        self.is_focused = False

    def __repr__(self):
        return repr(self.text)


class URL:
    def __init__(self, url):
        self.url = url
        # (http)://(example.org)(/index.html)
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

        # chapter7-fragments
        if '#' in url:
            url, self.fragment = url.split('#', 1)
        else:
            self.fragment = None

        # chapter7-bookmarks
        if self.scheme == "about":
            self.port = "None"
            self.host = "None"
            self.path = "bookmarks"
        else:
            if "/" not in url:
                url = url + "/"
            self.host, url = url.split("/", 1)
            self.path = "/" + url
            # http://example.org:8080/index.html
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

        # chapter8-get-forms
        query = ""
        if method == "GET" and payload:
            query = "?" + payload
        if not method and payload:
            method = "POST"
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

        # chapter7-bookmarks
        # Build http body if the scheme is "about"
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


browser = open("browser.css")
DEFAULT_STYLE_SHEET = CSSParser(browser.read()).parse()

INPUT_WIDTH_PX = 200


class InputLayout:
    def __init__(self, node, parent, previous):
        self.node = node
        self.children = []
        self.parent = parent
        self.previous = previous
        self.x = None
        self.y = None
        self.width = None
        self.height = None
        self.font = None
        self.type = "text"
        # chapter8-checkboxes
        if self.node.tag == "input" and self.node.attributes.get("type", "text") == "checkbox":
            self.type = "checkbox"
        elif self.node.tag == "button":
            self.type = "button"
        # notetake
        elif self.node.tag == "input" and "Hidden" in self.previous.word:
            self.type = "hidden"
        else:
            self.type = "text"

    def layout(self):
        weight = self.node.style["font-weight"]
        style = self.node.style["font-style"]
        family = self.node.style["font-family"]
        if style == "normal":
            style = "roman"
        size = int(float(self.node.style["font-size"][:-2]) * .75)
        self.font = get_font(size, weight, style, family)

        # chapter8-checkboxes
        if self.node.tag == "input" and self.node.attributes.get("type", "text") == "checkbox":
            self.width = 16
            self.height = 16  # Set the height to 16 for checkboxes
            # notetake
        elif self.type == "hidden":
            self.width = 0.0
            self.height = 0.0
        else:
            self.width = INPUT_WIDTH_PX
            # Set the height based on the font size for other inputs
            self.height = self.font.metrics("linespace")

        if self.previous:
            space = self.previous.font.measure(" ")
            self.x = self.previous.x + space + self.previous.width
        # notetake
        # elif self.type == "hidden":
        #     self.height = 0.0
        else:
            self.x = self.parent.x

        self.y = 20.25

        if self.node.tag == 'button':
            firstchild = None
            for a in self.node.children:
                if (isinstance(a, Text) and a.text != "Submit!") or not isinstance(a, Text):
                    if a == self.node.children[0]:
                        child = BlockLayout(a, self, None)
                        firstchild = child
                        self.children.append(child)
                        child.layout()
                    else:
                        if isinstance(a, Element):
                            if a.tag == "b":
                                a.style["font-weight"] = "bold"
                                text = "bold"
                            elif a.tag == "i":
                                a.style["font-style"] = "italic"
                                text = "italic"
                            LineLayout = firstchild.children[0]
                            child = TextLayout(
                                a, text, LineLayout, LineLayout.children[-1])
                            LineLayout.children.append(child)
                            LineLayout.layout()
                            child.layout()
                        else:
                            LineLayout = firstchild.children[0]
                            child = TextLayout(
                                a, a.text, LineLayout, LineLayout.children[-1])
                            LineLayout.children.append(child)
                            LineLayout.layout()
                            child.layout()

    def should_paint(self):
        return True

    def self_rect(self):
        return Rect(self.x, self.y,
                    self.x + self.width, self.y + self.height)

    def paint(self):
        cmds = []
        # notetake
        if self.type == "hidden":
            return cmds

        # Default color is yellow
        bgcolor = self.node.style.get("background-color", "lightblue")
        # If the node is a button, change the color to orange
        if self.node.tag == "button":
            bgcolor = "orange"
        if bgcolor != "transparent":
            rect = DrawRect(self.self_rect(), bgcolor)
            cmds.append(rect)

        if self.node.tag == "input":
            # notetake
            if self.node.attributes.get("type", "text") == "password":
                text = "*" * len(self.node.attributes.get("value", ""))
            else:
                text = self.node.attributes.get("value", "")
        elif self.node.tag == "button":
            if len(self.node.children) == 1 and \
               isinstance(self.node.children[0], Text):
                text = self.node.children[0].text
            else:
                # print("Ignoring HTML contents inside button")
                text = ""
        else:
            # chapter8-checkboxes
            # rect = DrawOutline(self.self_rect().insect(3), "black", thickness=1)
            rect = DrawOutline(self.self_rect(), "black", thickness=1)
            # def insect(self, padding):
            #     return Rect(self.left + padding, self.top + padding,
            #                 self.right - padding, self.bottom - padding)
            cmds.append(rect)
            if "checked" in self.node.attributes:
                rect = DrawRect(self.self_rect(), "red")
                cmds.append(rect)
            text = ""

        color = self.node.style["color"]
        if self.node.tag != "button":
            cmds.append(
                DrawText(self.x, self.y, text, self.font, color))

        if self.node.is_focused:
            cx = self.x + self.font.measure(text)
            cmds.append(DrawLine(
                cx, self.y, cx, self.y + self.height, "black", 1))
        return cmds

    def __repr__(self):
        # chapter8-checkboxes
        if self.node.tag == "input" and self.node.attributes.get("type", "text") == "checkbox":
            if "checked" in self.node.attributes:
                extra = ", checked"
            else:
                extra = ", unchecked"
        else:
            extra = ""
        return "InputLayout(x={}, y={}, width={}, height={}, tag={}{})".format(
            self.x, self.y, self.width, self.height, self.node.tag, extra)


class DocumentLayout:
    def __init__(self, node):
        self.x = None
        self.y = None
        self.width = None
        self.height = None
        self.node = node
        self.parent = None
        self.children = []
        self.display_list = []

    def layout(self):
        child = BlockLayout(self.node, self, None)
        self.children.append(child)
        self.display_list = child.display_list
        self.width = WIDTH - 2*HSTEP
        self.x = HSTEP
        self.y = VSTEP
        child.layout()
        self.height = child.height

    def paint(self):
        return []

    def __repr__(self):
        return "DocumentLayout()"

    def should_paint(self):
        return True


class LineLayout:
    def __init__(self, node, parent, previous):
        self.node = node
        self.parent = parent
        self.previous = previous
        self.children = []
        self.x = None
        self.y = None
        self.width = None
        self.height = None

    def layout(self):
        self.width = self.parent.width
        self.x = self.parent.x

        if self.previous:
            self.y = self.previous.y + self.previous.height
        else:
            self.y = self.parent.y

        for word in self.children:
            word.layout()

        if not self.children:
            self.height = 0
            return

        max_ascent = max([word.font.metrics("ascent")
                          for word in self.children])
        baseline = self.y + 1.25 * max_ascent
        for word in self.children:
            word.y = baseline - word.font.metrics("ascent")
        max_descent = max([word.font.metrics("descent")
                           for word in self.children])
        self.height = 1.25 * (max_ascent + max_descent)

    def paint(self):
        return []

    def __repr__(self):
        return "LineLayout(x={}, y={}, width={}, height={})".format(
            self.x, self.y, self.width, self.height)

    def should_paint(self):
        return True


class TextLayout:
    def __init__(self, node, word, parent, previous):
        self.node = node
        self.word = word
        self.children = []
        self.parent = parent
        self.previous = previous
        self.x = None
        self.y = None
        self.width = None
        self.height = None
        self.font = None

    def layout(self):
        weight = self.node.style["font-weight"]
        style = self.node.style["font-style"]
        family = self.node.style["font-family"]
        if style == "normal":
            style = "roman"
        size = int(float(self.node.style["font-size"][:-2]) * .75)
        self.font = get_font(size, weight, style, family)

        self.width = self.font.measure(self.word)

        if self.previous:
            space = self.previous.font.measure(" ")
            self.x = self.previous.x + space + self.previous.width
        else:
            self.x = self.parent.x

        self.height = self.font.metrics("linespace")

    def paint(self):
        color = self.node.style["color"]
        return [DrawText(self.x, self.y, self.word, self.font, color)]

    def __repr__(self):
        return ("TextLayout(x={}, y={}, width={}, height={}, " +
                "word={})").format(
            self.x, self.y, self.width, self.height, self.word)

    def should_paint(self):
        return True


class BlockLayout:
    weight = "normal"
    style = "roman"
    INLINE_ELEMENTS = ["b", "i", "em", "span", "a"]

    def __init__(self, node, parent=None, previous=None):
        self.x = None
        self.y = None
        self.width = None
        self.height = None
        self.node = node
        self.parent = parent
        self.previous = previous
        self.children = []
        self.display_list = []
        self.cursor_x = 0
        self.cursor_y = 0
        self.weight = "normal"
        self.style = "roman"
        self.size = 16
        self.line = []
        self.center = False
        self.superscript = False
        self.abbr = False
        self.height_of_first_line = 0

        if isinstance(node, Element):
            self.nodes = [node]
        else:
            self.nodes = node

        if not isinstance(self.nodes, List):
            self.nodes = [node]
        else:
            self.nodes = node

    def layout(self):
        self.width = self.parent.width
        self.x = self.parent.x

        if self.previous:
            self.y = self.previous.y + self.previous.height
        else:
            self.y = self.parent.y

        mode = self.layout_mode()
        if mode == "block":
            previous = None
            for child in self.node.children:
                next = BlockLayout(child, self, previous)
                self.children.append(next)
                previous = next
        else:
            self.new_line()
            self.recurse(self.node)

        for child in self.children:
            child.layout()

        self.height = sum([child.height for child in self.children])

    def recurse(self, node):
        if isinstance(node, Text):
            for word in node.text.split():
                self.word(node, word)
        else:
            if not isinstance(node, Element):
                return
            if node.tag == "br":
                self.new_line()
            elif node.tag == "input" or node.tag == "button":
                self.input(node)
            else:
                for child in node.children:
                    self.recurse(child)

    def input(self, node):
        w = INPUT_WIDTH_PX
        if self.cursor_x + w > self.width:
            self.new_line()
        line = self.children[-1]
        previous_word = line.children[-1] if line.children else None
        input = InputLayout(node, line, previous_word)
        line.children.append(input)

        weight = node.style["font-weight"]
        style = node.style["font-style"]
        family = node.style["font-family"]
        if style == "normal":
            style = "roman"
        size = int(float(node.style["font-size"][:-2]) * .75)
        font = get_font(size, weight, style, family)

        self.cursor_x += w + font.measure(" ")

    def should_paint(self):
        return isinstance(self.node, Text) or \
            (self.node.tag != "input" and self.node.tag != "button")

    def new_line(self):
        self.cursor_x = 0
        last_line = self.children[-1] if self.children else None
        new_line = LineLayout(self.node, self, last_line)
        self.children.append(new_line)

    def word(self, node, word):
        weight = node.style["font-weight"]
        style = node.style["font-style"]
        family = node.style["font-family"]
        if style == "normal":
            style = "roman"
        size = int(float(node.style["font-size"][:-2]) * .75)
        font = get_font(size, weight, style, family)

        w = font.measure(word)
        if self.cursor_x + w > self.width:
            self.new_line()
        line = self.children[-1]
        previous_word = line.children[-1] if line.children else None
        text = TextLayout(node, word, line, previous_word)
        line.children.append(text)
        self.cursor_x += w + font.measure(" ")

    def self_rect(self):
        return Rect(self.x, self.y,
                    self.x + self.width, self.y + self.height)

    def paint(self):
        cmds = []
        bgcolor = self.node.style.get("background-color",
                                      "transparent")
        if bgcolor != "transparent":
            rect = DrawRect(self.self_rect(), bgcolor)
            cmds.append(rect)
        return cmds

    def __repr__(self):
        return "BlockLayout(x={}, y={}, width={}, height={})".format(
            self.x, self.y, self.width, self.height)

    def layout_mode(self):
        if isinstance(self.node, Text):
            return "inline"
        elif any([isinstance(child, Element) and
                  child.tag in BLOCK_ELEMENTS
                  for child in self.node.children]):
            return "block"
        elif self.node.children or self.node.tag == "input":
            return "inline"
        else:
            return "block"


def paint_tree(layout_object, display_list):
    if layout_object.should_paint():
        display_list.extend(layout_object.paint())

    for child in layout_object.children:
        paint_tree(child, display_list)


class Tab:
    def __init__(self, tab_height, browser):
        self.url = None
        self.history = []
        self.tab_height = tab_height
        self.browser = browser
        self.focus = None

    def load(self, url, payload=None, method="GET"):
        self.scroll = 0
        self.url = url
        self.history.append(url)
        # chapter8-get-forms
        body = url.request(browser=self.browser,
                           payload=payload, method=method)
        self.nodes = HTMLParser(body).parse()

        self.rules = DEFAULT_STYLE_SHEET.copy()
        links = [node.attributes["href"]
                 for node in tree_to_list(self.nodes, [])
                 if isinstance(node, Element)
                 and node.tag == "link"
                 and node.attributes.get("rel") == "stylesheet"
                 and "href" in node.attributes]
        for link in links:
            try:
                body = url.resolve(link).request(self.browser)
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
        while elt:
            if isinstance(elt, Text):
                pass
            elif elt.tag == "a" and "href" in elt.attributes:
                url = self.url.resolve(elt.attributes["href"])
                return self.load(url)
            elif elt.tag == "input":
                # chapter8-checkboxes
                if elt.attributes.get("type", "text") == "checkbox":
                    if "checked" in elt.attributes:
                        del elt.attributes["checked"]
                    else:
                        elt.attributes["checked"] = "sure"
                    if self.focus:
                        self.focus.is_focused = False
                    self.focus = elt
                    elt.is_focused = True
                    return self.render()
                else:
                    elt.attributes["value"] = ""
                    if self.focus:
                        self.focus.is_focused = False
                    self.focus = elt
                    elt.is_focused = True
                    return self.render()
            elif elt.tag == "button":
                while elt:
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
        inputs = [node for node in tree_to_list(elt, [])
                  if isinstance(node, Element)
                  and node.tag == "input"
                  and "name" in node.attributes]

        body = ""
        for input in inputs:
            name = input.attributes["name"]
            name = urllib.parse.quote(name)
            # chapter8-checkboxes
            if "checked" in input.attributes:
                value = input.attributes.get("value", "on")
                value = urllib.parse.quote(value)
                body += "&" + name + "=" + value
            elif input.attributes.get("type", "text") != "checkbox":
                value = input.attributes.get("value", "")
                value = urllib.parse.quote(value)
                body += "&" + name + "=" + value
            else:
                pass

        body = body[1:]

        url = self.url.resolve(elt.attributes["action"])
        method = elt.attributes.get("method", "GET")
        self.load(url, body, method)

    def keypress(self, char):
        if self.focus:
            self.focus.attributes["value"] += char
            self.render()


class Chrome:
    def __init__(self, browser):
        self.browser = browser
        self.focus = None
        self.address_bar = ""

        self.font = get_font(20, "normal", "roman", "Times")
        self.font_height = self.font.metrics("linespace")

        self.padding = 5
        self.tabbar_top = 0
        self.tabbar_bottom = self.font_height + 2*self.padding

        plus_width = self.font.measure("+") + 2*self.padding
        self.newtab_rect = Rect(
            self.padding, self.padding,
            self.padding + plus_width,
            self.padding + self.font_height)

        self.urlbar_top = self.tabbar_bottom
        self.urlbar_bottom = self.urlbar_top + \
            self.font_height + 2*self.padding

        back_width = self.font.measure("<") + 2*self.padding
        self.back_rect = Rect(
            self.padding,
            self.urlbar_top + self.padding,
            self.padding + back_width,
            self.urlbar_bottom - self.padding)

        self.address_rect = Rect(
            self.back_rect.top + self.padding,
            self.urlbar_top + self.padding,
            WIDTH - self.padding,
            self.urlbar_bottom - self.padding)

        self.bottom = self.urlbar_bottom

        # chapter7-bookmarks
        self.address_rect = Rect(
            self.back_rect.top + self.padding,
            self.urlbar_top + self.padding,
            WIDTH - self.padding * 2 - 20,
            self.urlbar_bottom - self.padding,
        )
        self.bookmarks_rect = Rect(
            self.address_rect.right + self.padding,
            self.urlbar_top + self.padding,
            WIDTH - self.padding,
            self.urlbar_bottom - self.padding,
        )

    def backspace(self):
        if self.focus == "address bar":
            self.address_bar = self.address_bar[:-1]

    def tab_rect(self, i):
        tabs_start = self.newtab_rect.right + self.padding
        tab_width = self.font.measure("Tab X") + 2*self.padding
        return Rect(
            tabs_start + tab_width * i, self.tabbar_top,
            tabs_start + tab_width * (i + 1), self.tabbar_bottom)

    def paint(self):
        cmds = []
        cmds.append(DrawRect(
            Rect(0, 0, WIDTH, self.bottom),
            "white"))
        cmds.append(DrawLine(
            0, self.bottom, WIDTH,
            self.bottom, "black", 1))

        cmds.append(DrawOutline(self.newtab_rect, "black", 1))
        cmds.append(DrawText(
            self.newtab_rect.left + self.padding,
            self.newtab_rect.top,
            "+", self.font, "black"))

        for i, tab in enumerate(self.browser.tabs):
            bounds = self.tab_rect(i)
            cmds.append(DrawLine(
                bounds.left, 0, bounds.left, bounds.bottom,
                "black", 1))
            cmds.append(DrawLine(
                bounds.right, 0, bounds.right, bounds.bottom,
                "black", 1))
            cmds.append(DrawText(
                bounds.left + self.padding, bounds.top + self.padding,
                "Tab {}".format(i), self.font, "black"))

            if tab == self.browser.active_tab:
                cmds.append(DrawLine(
                    0, bounds.bottom, bounds.left, bounds.bottom,
                    "black", 1))
                cmds.append(DrawLine(
                    bounds.right, bounds.bottom, WIDTH, bounds.bottom,
                    "black", 1))

        cmds.append(DrawOutline(self.back_rect, "black", 1))
        cmds.append(DrawText(
            self.back_rect.left + self.padding,
            self.back_rect.top,
            "<", self.font, "black"))

        cmds.append(DrawOutline(self.address_rect, "black", 1))
        if self.focus == "address bar":
            cmds.append(DrawText(
                self.address_rect.left + self.padding,
                self.address_rect.top,
                self.address_bar, self.font, "black"))
            w = self.font.measure(self.address_bar)
            cmds.append(DrawLine(
                self.address_rect.left + self.padding + w,
                self.address_rect.top,
                self.address_rect.left + self.padding + w,
                self.address_rect.bottom,
                "red", 1))
        else:
            url = str(self.browser.active_tab.url)
            cmds.append(DrawText(
                self.address_rect.left + self.padding,
                self.address_rect.top,
                url, self.font, "black"))

        # chapter7-bookmarks
        if str(self.browser.active_tab.url) in self.browser.bookmarks:
            cmds.append(DrawRect(self.bookmarks_rect, "yellow"))
        cmds.append(DrawOutline(self.bookmarks_rect, "black", 1))

        return cmds

    def click(self, x, y):
        self.focus = None
        if self.newtab_rect.containsPoint(x, y):
            self.browser.new_tab(URL("https://browser.engineering/"))
        elif self.back_rect.containsPoint(x, y):
            self.browser.active_tab.go_back()
        elif self.address_rect.containsPoint(x, y):
            self.focus = "address bar"
            self.address_bar = ""
        # chapter7-bookmarks
        elif self.bookmarks_rect.containsPoint(x, y):
            if str(self.browser.active_tab.url) in self.browser.bookmarks:
                self.browser.bookmarks.remove(str(self.browser.active_tab.url))
            else:
                self.browser.bookmarks.append(str(self.browser.active_tab.url))
        else:
            for i, tab in enumerate(self.browser.tabs):
                if self.tab_rect(i).containsPoint(x, y):
                    self.browser.active_tab = tab
                    break

    def keypress(self, char):
        if self.focus == "address bar":
            self.address_bar += char

    def enter(self):
        if self.focus == "address bar":
            self.browser.active_tab.load(URL(self.address_bar))
            self.focus = None

    def keypress(self, char):
        if self.focus == "address bar":
            self.address_bar += char
            return True
        return False

    def blur(self):
        self.focus = None


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


class HTMLParser:
    def __init__(self, body):
        self.body = body
        self.unfinished = []

    def parse(self):
        text = ""
        in_tag = False
        for c in self.body:
            if c == "<":
                in_tag = True
                if text:
                    self.add_text(text)
                text = ""
            elif c == ">":
                in_tag = False
                self.add_tag(text)
                text = ""
            else:
                text += c
        if not in_tag and text:
            self.add_text(text)
        return self.finish()

    def get_attributes(self, text):
        parts = text.split()
        tag = parts[0].casefold()
        attributes = {}
        for attrpair in parts[1:]:
            if "=" in attrpair:
                key, value = attrpair.split("=", 1)
                if len(value) > 2 and value[0] in ["'", "\""]:
                    value = value[1:-1]
                attributes[key.casefold()] = value
            else:
                attributes[attrpair.casefold()] = ""
        return tag, attributes

    def add_text(self, text):
        if text.isspace():
            return
        self.implicit_tags(None)
        parent = self.unfinished[-1]
        node = Text(text, parent)
        parent.children.append(node)

    SELF_CLOSING_TAGS = [
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    ]

    def add_tag(self, tag):
        tag, attributes = self.get_attributes(tag)
        if tag.startswith("!"):
            return
        self.implicit_tags(tag)

        if tag.startswith("/"):
            if len(self.unfinished) == 1:
                return
            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(node)
        elif tag in self.SELF_CLOSING_TAGS:
            parent = self.unfinished[-1]
            node = Element(tag, attributes, parent)
            parent.children.append(node)
        else:
            parent = self.unfinished[-1] if self.unfinished else None
            node = Element(tag, attributes, parent)
            self.unfinished.append(node)

    HEAD_TAGS = [
        "base", "basefont", "bgsound", "noscript",
        "link", "meta", "title", "style", "script",
    ]

    def implicit_tags(self, tag):
        while True:
            open_tags = [node.tag for node in self.unfinished]
            if open_tags == [] and tag != "html":
                self.add_tag("html")
            elif open_tags == ["html"] \
                    and tag not in ["head", "body", "/html"]:
                if tag in self.HEAD_TAGS:
                    self.add_tag("head")
                else:
                    self.add_tag("body")
            elif open_tags == ["html", "head"] and \
                    tag not in ["/head"] + self.HEAD_TAGS:
                self.add_tag("/head")
            else:
                break

    def finish(self):
        if not self.unfinished:
            self.implicit_tags(None)
        while len(self.unfinished) > 1:
            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(node)
        return self.unfinished.pop()


class DrawText:
    def __init__(self, x1, y1, text, font, color):
        self.top = y1
        self.left = x1
        if y1 is None:
            y1 = 0
        self.bottom = y1 + font.metrics("linespace")
        self.rect = Rect(x1, y1,
                         x1 + font.measure(text), y1 + font.metrics("linespace"))
        self.text = text
        self.font = font
        self.color = color

    def execute(self, scroll, canvas):
        canvas.create_text(
            self.rect.left, self.rect.top - scroll,
            text=self.text,
            font=self.font,
            anchor='nw',
            fill=self.color)

    def __repr__(self):
        return "DrawText(top={} left={} bottom={} text={} font={})" \
            .format(self.top, self.left, self.bottom, self.text, self.font)


class TagSelector:
    def __init__(self, tag):
        self.tag = tag
        self.priority = 1

    def matches(self, node):
        return isinstance(node, Element) and self.tag == node.tag

    def __repr__(self):
        return "TagSelector(tag={}, priority={})".format(
            self.tag, self.priority)


if __name__ == "__main__":
    import wbemocks
    _ = wbemocks.socket.patch().start()
    _ = wbemocks.ssl.patch().start()
    wbemocks.NORMALIZE_FONT = True
    url = 'http://test/chapter8-get-form2/submit?food=ribwich'
    wbemocks.socket.respond_200(url, "Mmm")
    url = wbemocks.socket.serve(
        "<button>An<i>italic<b>bold</b>button</i></button>")
    this_browser = Browser()
    this_browser.new_tab(URL(url))
    print_tree(this_browser.active_tab.document)

    # import sys
    # Browser().new_tab(URL(sys.argv[1]))
    # tkinter.mainloop()
