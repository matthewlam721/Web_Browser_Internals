from ast import List
from pathlib import Path
import re
import time
import ssl
import socket
import tkinter
from tkinter import Tk, font

WIDTH, HEIGHT = 800, 600
HSTEP, VSTEP = 13, 18
SCROLL_STEP = 100
Emoji_Dictionary = {}

class ContinueOuterLoop(Exception):
    pass
class URL:

    cache = {}

    def __init__(self, url):
        self.url = url
        # (http)://(example.org)(/index.html)
        self.scheme, url = url.split("://", 1)
        assert self.scheme in ["http", "https", "file"]
        if self.scheme == "http":
            self.port = 80
        elif self.scheme == "https":
            self.port = 443
        elif self.scheme == "file":
            self.port = None
            self.path = url
            return

        if "/" not in url:
            url = url + "/"
        self.host, url = url.split("/", 1)
        self.path = "/" + url
        # http://example.org:8080/index.html
        if ":" in self.host:
            self.host, port = self.host.split(":", 1)
            self.port = int(port)

    def __repr__(self):
        return "URL(scheme={}, host={}, port={}, path={!r})".format(
            self.scheme, self.host, self.port, self.path)

    def request(self, headers=None):

        cache = self.cache.get(self.url)
        if cache and time.time() < cache['time'] + cache['maxAge']:
            return cache['response']

        if self.scheme == "file":
            with open(self.path, 'r') as file:
                return file.read()

        import ssl

        s = socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )

        if self.scheme == "https":
            # ctx = ssl.create_default_context()
            ctx = ssl._create_unverified_context()
            s = ctx.wrap_socket(s, server_hostname=self.host)

        s.connect((self.host, self.port))

        request = ("GET {} HTTP/1.1\r\n"
                   "Host: {}\r\n"
                   "Connection: close\r\n".format(self.path, self.host))
        if headers:
            headers = {header.casefold(): value for header,
                       value in headers.items()}
            if 'user-agent' not in headers:
                headers['user-agent'] = 'penguin'
            for header, value in headers.items():
                request += "{}: {}\r\n".format(header, value)
        else:
            request += "User-Agent: penguin\r\n"

        request += "\r\n"
        s.send(request.encode("utf8"))

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

        if 300 <= int(status) <= 399:
            redirectLoaction = response_headers.get('location')

            if '://' not in redirectLoaction:
                redirectLoaction = "{}://{}{}".format(
                    self.scheme, self.host, redirectLoaction)

            return URL(redirectLoaction).request(headers)

        body = response.read()

        cacheControl = response_headers.get('cache-control')
        if int(status) == 200:
            if cacheControl is not None:
                if 'max-age' in cacheControl:
                    maxAge = int(cacheControl.split('=')[1])
                    self.cache[self.url] = {
                        'time': time.time(), 'maxAge': maxAge, 'response': body}
        s.close()
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

FONTS = {}

def get_font(size, weight, slant, family):
    key = (size, weight, slant, family)
    if key not in FONTS:
        font = tkinter.font.Font(size=size, weight=weight,
                                 slant=slant, family=family)
        label = tkinter.Label(font=font)
        FONTS[key] = (font, label)
    return FONTS[key][0]

class Text:
    def __init__(self, text, parent):
        self.text = text
        self.children = []
        self.parent = parent

    def __repr__(self):
        return repr(self.text)

class Element:
    def __init__(self, tag, attributes, parent):
        self.tag = tag
        self.children = []
        self.parent = parent
        self.attributes = attributes
        self.style = self.parse_style_attributes()

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

def print_tree(node, indent=0):
    """
    Here we’re printing each node in the tree, and using indentation to show the tree structure.
    """
    print(" " * indent, node)
    for child in node.children:
        print_tree(child, indent + 2)

def cascade_priority(rule):
    selector, body = rule
    return selector.priority

class HTMLParser:

    def __init__(self, body):
        self.body = body
        self.unfinished = []

    def parse(self):
        text = ""
        in_tag = False
        in_script = False
        isCommect = False
        startIndex = 0
        startbrackets = []

        for i, c in enumerate(self.body):
            if in_script:
                if c == "<":
                    if self.body[i+1:i+9] == "/script>":
                        in_tag = True
                        in_script = False
                        if text:
                            self.add_text(text)
                        text = ""
                    else:
                        text += c
                elif c == ">":
                    text += c
                else:
                    text += c
            else:
                if c == "<":
                    # quoted attributes:
                    startbrackets.append("<")

                    if self.body[i+1:i+4] == "!--":
                        isCommect = True
                        startIndex = i + 4
                        counter = 5
                    elif len(startbrackets) > 1:
                        text += c
                        continue
                    if text:
                        self.add_text(text)

                    in_tag = True
                    text = ""
                elif c == ">":
                    # if is script
                    if text == "script":
                        in_script = True
                    elif text == "/script":
                        in_script = False

                    # if is comment
                    if self.body[i-2:i] == "--":
                        if i - startIndex >= 2:
                            text = ""
                            isCommect = False
                            in_tag = False
                    else:
                        if isCommect:
                            pass
                        # quoted attributes:
                        elif len(startbrackets) != 0:
                            startbrackets.pop()
                            text += c
                            if len(startbrackets) == 0:
                                text = text[:-1]
                                in_tag = False
                                self.add_tag(text)
                                text = ""
                            continue
                        else:
                            in_tag = False
                            self.add_tag(text)
                            text = ""
                else:
                    if not isCommect:
                        text += c
        if not in_tag and text:
            self.add_text(text)
        return self.finish()

    def get_attributes(self, text):
        inQuote = False
        # split by space which make alt='Les Horribles Cernettes becomes alt="'Les" horribles="" cernettes'="
        parts = text.split()
        quotesfirst = []
        newPart = []
        try:
            for i, part in enumerate(parts):
                if inQuote:
                    if "'" in part:
                        inQuote = not inQuote
                        newPart[len(newPart) - 1] += " " + \
                            part.replace("'", "")
                        continue
                    elif "\"" in part:
                        inQuote = not inQuote
                        newPart[len(newPart) - 1] += " " + \
                            part.replace("\"", "")
                        continue
                    newPart[len(newPart) - 1] += " " + part  # combine quotes
                    continue
                if "'" in part:
                    for c in range(len(part)):
                        if part[c] == "'":
                            quotesfirst.append([c, "'"])
                if "\"" in part:
                    count = 0
                    for c in range(len(part)):
                        if part[c] == "\"":
                            quotesfirst.append([c, "\""])
                            count += 1
                            if count == 2:
                                quotesfirst.pop()
                                quotesfirst.pop()
                                splitparts = part.split("\"")
                                for i, splitpart in enumerate(splitparts):
                                    if i == 1:
                                        newPart[len(newPart) - 1] += splitpart
                                        continue
                                    newPart.append(splitpart)
                                raise ContinueOuterLoop

                    # word = part.replace("\"", "")
                    # newPart.append(word)
                    # continue
                if quotesfirst:
                    inQuote = not inQuote
                    smallest = [100, "a"]
                    for e in quotesfirst:
                        if smallest[0] >= e[0]:
                            smallest = e
                    word = part.replace(smallest[1], "")
                    newPart.append(word)
                    continue
                newPart.append(part)
        except ContinueOuterLoop:
            pass
        parts = newPart

        tag = parts[0].casefold()
        attributes = {}
        for attrpair in parts[1:]:
            if attrpair and attrpair[0] == "=" and attrpair.count("=") == 1:
                attributes["default_attribute"] = ""
            elif attrpair.count("=") == 2 and attrpair[0] == "=":
                first_eq_index = attrpair.find("=")
                second_eq_index = attrpair.find("=", first_eq_index + 1)
                key = "default_attribute"
                value = attrpair[second_eq_index + 1:]
                attributes[key.casefold()] = value
                if len(value) > 2 and value[0] in ["'", "\""]:
                    value = value[1:-1]
            elif "=" in attrpair:
                key, value = attrpair.split("=", 1)
                attributes[key.casefold()] = value
                if len(value) > 2 and value[0] in ["'", "\""]:
                    value = value[1:-1]

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
        self.implicit_tags(tag)
        if tag.startswith("!"):
            return  # ignore comments in HTML i.e. <!-- comment text -->
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
            # paragraph test
            parent = self.unfinished[-1] if self.unfinished else None
            bob = []
            if tag == "p":
                for i, unfinishedTag in enumerate(self.unfinished):
                    if unfinishedTag.tag == "p":
                        if i == len(self.unfinished) - 1:
                            parent = self.unfinished[i-1]
                            parent.children.append(unfinishedTag)
                            del self.unfinished[i]
                        else:
                            for j in range(len(self.unfinished) - 1, i, -1):
                                parent = self.unfinished[j-1]
                                parent.children.append(self.unfinished[j])
                                bob.append(Element(
                                    self.unfinished[j].tag, self.unfinished[j].attributes, self.unfinished[j].parent))
                                del self.unfinished[j]

                            parent = self.unfinished[i-1]
                            parent.children.append(unfinishedTag)
                            del self.unfinished[i]

            node = Element(tag, attributes, parent)
            self.unfinished.append(node)

            while bob:
                self.unfinished.append(bob.pop())

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

BLOCK_ELEMENTS = [
    "html", "body", "article", "section", "nav", "aside",
    "h1", "h2", "h3", "h4", "h5", "h6", "hgroup", "header",
    "footer", "address", "p", "hr", "pre", "blockquote",
    "ol", "ul", "menu", "li", "dl", "dt", "dd", "figure",
    "figcaption", "main", "div", "table", "form", "fieldset",
    "legend", "details", "summary"]

class DrawRect:
    def __init__(self, x1, y1, x2, y2, color):
        self.top = y1
        self.left = x1
        self.bottom = y2
        self.right = x2
        self.color = color

    def __repr__(self):
        return "DrawRect(top={} left={} bottom={} right={} color={})".format(
            self.top, self.left, self.bottom, self.right, self.color)

    def execute(self, scroll, canvas):
        canvas.create_rectangle(
            self.left, self.top - scroll,
            self.right, self.bottom - scroll,
            width=0,
            fill=self.color)

class DrawText:
    def __init__(self, x1, y1, text, font, color):
        self.top = y1
        self.left = x1
        self.text = text
        self.font = font
        self.bottom = y1 + font.metrics("linespace")
        self.color = color

    def __repr__(self):
        return "DrawText(top={} left={} bottom={} text={} font={})" \
            .format(self.top, self.left, self.bottom, self.text, self.font)

    def execute(self, scroll, canvas):
        canvas.create_text(
            self.left, self.top - scroll,
            text=self.text,
            font=self.font,
            anchor='nw',
            fill=self.color)  # use color in the text drawing

def paint_tree(layout_object, display_list):
    display_list.extend(layout_object.paint())

    for child in layout_object.children:
        paint_tree(child, display_list)

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
        # self.style = "roman"
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

    def word(self, node, word):
        weight = node.style["font-weight"]
        style = node.style["font-style"]
        family = node.style["font-family"]
        if style == "normal":
            style = "roman"
        size = int(float(node.style["font-size"][:-2]) * 0.75)
        font = get_font(size, weight, style, family)
        color = node.style["color"]
        if (self.abbr):
            buffer = ""
            setCapital = False
            for c in word:
                if (c.islower() and setCapital) or (not c.islower() and not setCapital):
                    if (setCapital):
                        c = c.upper()
                    buffer += c
                    continue
                if c.islower():
                    if (buffer):
                        buffer_length = font.measure(buffer)
                        self.line.append(
                            (self.cursor_x, buffer, font, self.superscript))
                        self.cursor_x += buffer_length
                        buffer = ""
                    buffer += c.upper()
                    font = get_font(size//2, "bold", style, family)
                    setCapital = True
                else:
                    if (buffer):
                        buffer_length = font.measure(buffer)
                        self.line.append(
                            (self.cursor_x, buffer, font, self.superscript))
                        self.cursor_x += buffer_length
                        buffer = ""
                    buffer += c
                    font = get_font(size, weight, style, family)
                    setCapital = False
            word = buffer

        w = font.measure(word)
        if (self.cursor_x + w > self.width):
            if "\N{soft hyphen}" in word:
                split_word = word.split("\N{soft hyphen}")
                buffer = ''
                current_word = ''
                for current_word in split_word:
                    if (self.cursor_x + font.measure(word_buffer + current_word + "-") <= WIDTH-HSTEP):
                        word_buffer += current_word
                    else:
                        self.word(word_buffer + "-")
                        word_buffer = current_word
                        self.flush()
                self.word(word_buffer)
                return
            # self.cursor_y += font.metrics("linespace") * 1.25
            self.cursor_x = HSTEP
            self.flush()
        self.line.append((self.cursor_x, word, font, color))
        self.cursor_x += w + get_font(size, weight, style, family).measure(" ")

    def flush(self):
        if not self.line:
            return
        metrics = [font.metrics() for x, word, font, color in self.line]

        if (self.center):
            line_length = self.line[-1][0] - self.line[0][0] + \
                self.line[-1][2].measure(self.line[-1][1])
            line_start = WIDTH/2 - line_length/2
            offset = line_start - self.line[0][0]

        max_ascent = max(font.metrics("ascent")
                         for x, word, font, color in self.line)

        baseline = self.cursor_y + 1.25*max_ascent

        for rel_x, word, font, color in self.line:
            x = rel_x + self.x
            y = baseline - font.metrics("ascent")
            self.display_list.append((x, y, word, font, color))

        max_descent = max(font.metrics("descent")
                          for x, word, font, color in self.line)

        self.cursor_y += font.metrics("linespace") * 1.25

        self.height_of_first_line = (1.25 * max_descent) + (1.25 * max_ascent)

        self.cursor_x = 0
        self.line = []

    def recurse(self, node):
        if isinstance(node, Text):
            for word in node.text.split():
                self.word(node, word)
        else:
            if node.tag == "br":
                self.flush()
            for child in node.children:
                self.recurse(child)

    def layout(self):
        self.display_list = []
        if self.previous:
            self.y = self.previous.y + self.previous.height
        else:
            self.y = self.parent.y

        if isinstance(self.nodes[0], Element) and self.nodes[0].tag == "li":
            self.x = self.parent.x + (2 * HSTEP)
            self.width = self.parent.width - (2 * HSTEP)
        else:
            width = self.nodes[0].style.get("width", "auto")

            self.x = self.parent.x
            if width == "auto":
                self.width = self.parent.width
            else:
                widthAsFloat = float(width[:-2])
                if widthAsFloat < 0:
                    self.width = self.parent.width
                else:
                    self.width = widthAsFloat

        mode = self.layout_mode()
        if mode == "block":
            previous = None
            for child in self.node.children:
                next = BlockLayout(child, self, previous)
                self.children.append(next)
                previous = next
         
        else:
            self.cursor_x = 0
            self.cursor_y = 0
            self.weight = "normal"
            # self.style = "roman"
            self.size = 16

            self.line = []
            self.center = False
            self.superscript = False
            self.abbr = False
            for node in self.nodes:
                self.recurse(node)
            self.flush()

        for child in self.children:
            child.layout()

        if mode == "block":
            self.height = sum([child.height for child in self.children])
        else:
            height = self.nodes[0].style.get("height", "auto")

            if height == "auto":
                self.height = self.cursor_y
            else:
                self.height = float(height[:-2])

    def layout_mode(self):

        if not isinstance(self.nodes, Text):
            if len(self.nodes) > 1:
                return "inline"
            elif isinstance(self.nodes[0], Text):
                return "inline"
            elif any([isinstance(child, Element) and child.tag in BLOCK_ELEMENTS for child in self.nodes[0].children]):
                return "block"
            elif self.nodes[0].children:
                return "inline"

        if isinstance(self.node, Text):
            return "inline"
        elif any([isinstance(child, Element) and
                  child.tag in BLOCK_ELEMENTS
                  for child in self.node.children]):
            return "block"
        elif self.node.children:
            return "inline"
        else:
            return "block"

    def layout_intermediate(self):
        previous = None
        for child in self.node.children:
            # hidden-head
            if isinstance(child, Element) and child.tag == "head":
                continue
            next = BlockLayout(child, self, previous)
            self.children.append(next)
            previous = next

    def paint(self):
        cmds = []
        bgcolor = self.node.style.get("background-color",
                                      "transparent")
        if bgcolor != "transparent":
            x2, y2 = self.x + self.width, self.y + self.height
            rect = DrawRect(self.x, self.y, x2, y2, bgcolor)
            cmds.append(rect)

        for x, y, word, font, color in self.display_list:
            cmds.append(DrawText(x, self.y + y,
                                 word, font, color))
        return cmds
       
    def __repr__(self):
        return "BlockLayout(x={}, y={}, width={}, height={})".format(
            self.x, self.y, self.width, self.height)

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
        self.scroll = 0
        self.window.bind("<Down>", self.scrolldown)
        # self.window.bind("<Configure>", self.resize)
        self.canvas.pack(fill=tkinter.BOTH, expand=1)
        self.display_list = []
        bi_times = tkinter.font.Font(
            family="Times",
            size=16,
            weight="bold",
            slant="italic",
        )

    def load(self, url):
        body = url.request()
        self.nodes = HTMLParser(body).parse()
        rules = DEFAULT_STYLE_SHEET.copy()

        links = [
            node.attributes["href"]
            for node in tree_to_list(self.nodes, [])
            if isinstance(node, Element)
            and node.tag == "link"
            and node.attributes.get("rel") == "stylesheet"
            and "href" in node.attributes
        ]

        for link in links:
            try:
                body = url.resolve(link).request()
            except:
                continue
            rules.extend(CSSParser(body).parse())

        sorted(rules, key=cascade_priority)
        style(self.nodes, sorted(rules, key=cascade_priority))
        self.document = DocumentLayout(self.nodes)
        self.document.layout()
        self.display_list = []
        paint_tree(self.document, self.display_list)
        self.draw()

    def draw(self):
        self.canvas.delete("all")
        for cmd in self.display_list:
            if cmd.top > (self.scroll + HEIGHT):
                continue
            if cmd.bottom < self.scroll:
                continue
            cmd.execute(self.scroll, self.canvas)

    def scrolldown(self, e):

        max_y = max(self.document.height + 2*VSTEP - HEIGHT, 0)
        self.scroll = min(self.scroll + SCROLL_STEP, max_y)
        self.draw()

def tree_to_list(tree, list):
    list.append(tree)
    for child in tree.children:
        tree_to_list(child, list)
    return list

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
        if (prop.casefold() == "font"):
            i= self.i
            self.ignore_until([";","}"])
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
                if(prop=="font"):
                    split_value = val.split()
                    if len(split_value)== 1:
                        pairs["font-family"] = split_value[0]
                    elif len(split_value) == 2:
                        pairs["font-size"] = split_value[0]
                        pairs["font-family"] = split_value[1]
                    elif len(split_value) == 3:
                        if split_value[0] == "italic":
                            pairs["font-style"] = split_value[0]
                        else:
                            pairs["font-weight"] = split_value[0]

                        pairs["font-size"] = split_value[1]
                        pairs["font-family"] = split_value[2]                    
                    elif len(split_value) == 4:
                        pairs["font-style"] = split_value[0]
                        pairs["font-weight"] = split_value[1]
                        pairs["font-size"] = split_value[2]
                        pairs["font-family"] = split_value[3] 
                    elif len(split_value) > 4:
                        pairs["font-style"] = split_value[0]
                        pairs["font-weight"] = split_value[1]
                        pairs["font-size"] = split_value[2]
                        font_family= """ """.join(split_value[3:])
                        pairs["font-family"] = font_family
                else:              
                    pairs[prop.casefold()] = val
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


class ClassSelector:
    def __init__(self, className):
        self.classname = className
        self.priority = 10

    def __repr__(self):
        return "ClassSelector(classname={}, priority={})".format(
            self.classname, self.priority)

    def matches(self, node):
        node_classes = node.attributes.get("class", "").split()
        return isinstance(node, Element) and self.classname in node_classes


class TagSelector:
    def __init__(self, tag):
        self.tag = tag
        self.priority = 1

    def matches(self, node):
        return isinstance(node, Element) and self.tag == node.tag

    def __repr__(self):
        return "TagSelector(tag={}, priority={})".format(
            self.tag, self.priority)


class DescendantSelector:
    def __init__(self, ancestor, descendant):
        self.ancestor = ancestor
        self.descendant = descendant
        self.priority = ancestor.priority + descendant.priority

    def __repr__(self):
        return ("DescendantSelector(ancestor={}, descendant={}, priority={})") \
            .format(self.ancestor, self.descendant, self.priority)

    def matches(self, node):
        if not self.descendant.matches(node):
            return False
        while node.parent:
            if self.ancestor.matches(node.parent):
                return True
            node = node.parent
        return False


INHERITED_PROPERTIES = {
    "font-size": "16px",
    "font-style": "normal",
    "font-weight": "normal",
    "color": "black",
    "font-family": "Times"
}


def style(node, rules):

    node.style = {}
    for property, default_value in INHERITED_PROPERTIES.items():
        if node.parent:
            node.style[property] = node.parent.style[property]
        else:
            node.style[property] = default_value
    for selector, body in rules:
        if not selector.matches(node):
            continue
        for property, value in body.items():
            node.style[property] = value
    if isinstance(node, Element) and "style" in node.attributes:
        pairs = CSSParser(node.attributes["style"]).body()
        for property, value in pairs.items():
            node.style[property] = value
    if node.style["font-size"].endswith("%"):
        if node.parent:
            parent_font_size = node.parent.style["font-size"]
        else:
            parent_font_size = INHERITED_PROPERTIES["font-size"]
        node_pct = float(node.style["font-size"][:-1]) / 100
        parent_px = float(parent_font_size[:-2])
        node.style["font-size"] = str(node_pct * parent_px) + "px"
    for child in node.children:
        style(child, rules)


def cascade_priority(rule):
    selector, body = rule
    return selector.priority


DEFAULT_STYLE_SHEET = CSSParser(open("browser.css").read()).parse()

if __name__ == "__main__":
    import sys
    import wbemocks
    _ = wbemocks.socket.patch().start()
    _ = wbemocks.ssl.patch().start()

    
    body = '<div style="height:100px">Set height</div>'
    url = URL(wbemocks.socket.serve(body))
    this_browser = Browser()
    this_browser.load(url)
    # print_style(html.style)

    
