#!/usr/bin/env python
# encoding: utf-8

import collections
import socket
import threading
import time
import json

import urwid
from line import LineClient
from curve.ttypes import ContentType, TalkException

palette = [
    ('line', 'light green', 'black'),
    ('r_line', 'black', 'light green'),
    ('error', 'light red', 'black'),
    ('warn', 'yellow', 'black'),
    ('info', 'light blue', 'black'),
    ('label', 'white', 'black'),
    ('submit', 'light cyan', 'black'),
    ('r_submit', 'black', 'light cyan'),
    ('cancel', 'light red', 'black'),
    ('r_cancel', 'black', 'light red'),
    ('self', 'light blue', 'black'),
    ('r_self', 'black', 'light blue'),
    ('others', 'light magenta', 'black'),
    ('r_others', 'black', 'light magenta')
]


class ScrollListBox(urwid.ListBox):

    def mouse_event(self, size, event, button, col, row, focus):
        if button == 4:
            self._keypress_page_up(size)
        elif button == 5:
            self._keypress_page_down(size)

        return super(
            ScrollListBox,
            self).mouse_event(
            size,
            event,
            button,
            col,
            row,
            focus)


class Context:

    def __init__(self, loop=None, client=None):
        self.loop = loop
        self.client = client
        self.lock = threading.Lock()
        self.history = collections.deque(maxlen=100)


class Page(object):

    def __init__(self, parent, context):
        self.parent = parent
        self.context = context
        self.page = self.gen_page()

    @staticmethod
    def gen_button_attrmap(button, attr):
        return urwid.AttrMap(button, attr, 'r_'+attr)

    @staticmethod
    def gen_padding(widget):
        return urwid.Padding(widget, left=2, right=2)

    @staticmethod
    def gen_top(widget):
        return urwid.Overlay(widget, urwid.SolidFill(u'\N{MEDIUM SHADE}'),
                             align=urwid.CENTER, width=(urwid.RELATIVE, 80),
                             valign=urwid.MIDDLE, height=(urwid.RELATIVE, 80),
                             min_width=20, min_height=9)

    @staticmethod
    def on_exit_clicked(button):
        raise urwid.ExitMainLoop()

    def gen_paeg(self):
        pass

    def go_back_page(self):
        if self.parent:
            self.parent.child = None
            self.context.loop.widget = self.parent.page
        else:
            urwid.ExitMainLoop()

    def go_to_page(self, PageType):
        self.child = PageType(self, self.context)
        self.context.loop.widget = self.child.page
        self.context.loop.draw_screen()


class ChatPulling(threading.Thread):

    def __init__(self, chat_page, context):
        super(ChatPulling, self).__init__()
        self.chat_page = chat_page
        self.context = context
        self.is_stop = False

    def run(self):
        while not self.is_stop:
            try:
                body = self.chat_page.gen_body()
                if body:
                    self.chat_page.frame.contents['body'] = (body, None)
            except TalkException as e:
                self.is_stop = True
                context = Context(self.context.loop)
                login_page = LoginPage(None, context)
                login_page.status.set_text(('error', e.reason))
                context.loop.widget = login_page.page
                context.loop.draw_screen()
            except Exception as e:
                self.is_stop = True
                context = Context(self.context.loop)
                login_page = LoginPage(None, context)
                login_page.status.set_text(('error', e.message))
                context.loop.widget = login_page.page
                context.loop.draw_screen()
            else:
                self.context.loop.draw_screen()
                time.sleep(1)


class TalkBox(urwid.Edit):

    def __init__(self, parent, context):
        super(TalkBox, self).__init__()
        self.parent = parent
        self.context = context

    def keypress(self, size, key):
        if key == 'enter':
            self.parent.sendMessage()
            self.set_edit_text('')
            self.parent.footer.focus_position = 0
        if key == 'ctrl u':
            self.set_edit_text('')
        else:
            return super(TalkBox, self).keypress(size, key)


class ChatPage(Page):

    def __init__(self, parent, context):
        super(ChatPage, self).__init__(parent, context)

    def pull(self):
        self.pulling = ChatPulling(self, context)
        self.pulling.daemon = True
        self.pulling.start()

    def sendMessage(self):
        text = self.edit.get_edit_text()
        if not text:
            return
        try:
            self.context.history.append(text)
            with self.context.lock:
                self.context.item.sendMessage(
                    text.encode(
                        encoding='UTF-8',
                        errors='strict')
                )
            self.context.loop.draw_screen()
        except TalkException as e:
            context = Context(self.context.loop)
            login_page = LoginPage(None, context)
            login_page.status.set_text(('error', e.reason))
            context.loop.widget = login_page.page
            context.loop.draw_screen()
        except Exception as e:
            context = Context(self.context.loop)
            login_page = LoginPage(None, context)
            login_page.status.set_text(('error', e.message))
            context.loop.widget = login_page.page
            context.loop.draw_screen()

    @staticmethod
    def on_send_clicked(self, button):
        self.sendMessage()
        self.edit.set_edit_text('')
        self.footer.focus_position = 0

    @staticmethod
    def on_back_clicked(self, button):
        self.go_back_page()
        self.context.item = None
        self.pulling.is_stop = True

    def gen_body(self):
        messages = collections.deque(maxlen=50)
        with self.context.lock:
            recent = self.context.item.getRecentMessages(count=50)

        for m in recent:
            align = urwid.RIGHT
            color = 'self'
            name = ""
            if m.sender:
                align = urwid.LEFT
                color = 'others'
                name = m.sender.name + ": "

            text = m.text
            if m.contentType:
                try:
                    text = ContentType._VALUES_TO_NAMES[m.contentType]
                except:
                    text = "OTHER"
                color = 'r_' + color

            text = name + text
            messages.append(urwid.Text((color, text), align))
        messages.reverse()
        body = urwid.ListBox(
            urwid.SimpleFocusListWalker(
                messages
            )
        )
        body.body.set_focus(len(messages) - 1)
        body._selectable = False
        return body

    def gen_page(self):
        self.header = urwid.AttrMap(
            urwid.Text(self.context.item.name, urwid.CENTER),
            'r_line'
        )

        self.body = self.gen_body()

        send = urwid.Button('Send')
        urwid.connect_signal(send, 'click',
                             self.on_send_clicked, user_args=[self])

        back = urwid.Button('Back')
        urwid.connect_signal(back, 'click',
                             self.on_back_clicked, user_args=[self])

        self.edit = TalkBox(self, self.context)
        self.footer = urwid.Columns([
            self.edit,
            urwid.Columns([
                self.gen_button_attrmap(send, 'submit'),
                self.gen_button_attrmap(back, 'cancel')
            ])
        ])
        self.frame = urwid.Frame(self.body, self.header, self.footer, 'footer')
        return self.gen_top(
            self.gen_padding(
                self.frame
            )
        )


class FriendsPage(Page):

    def __init__(self, parent, context):
        super(FriendsPage, self).__init__(parent, context)

    @staticmethod
    def on_item_clicked(self, item, button):
        self.context.item = item
        self.go_to_page(ChatPage)
        self.child.pull()

    @staticmethod
    def on_back_clicked(self, button):
        self.go_back_page()

    def gen_item_button(self, body, item):
        button = urwid.Button(item.name)
        body.append(self.gen_button_attrmap(button, 'submit'))
        urwid.connect_signal(
            button,
            'click',
            self.on_item_clicked,
            user_args=[
                self,
                item])

    def gen_page(self):
        body = []
        back = urwid.Button('Back')
        urwid.connect_signal(
            back,
            'click',
            self.on_back_clicked,
            user_args=[self])
        body.append(self.gen_button_attrmap(back, 'submit'))
        groups = self.context.client.groups
        body.append(
            urwid.Text(('info', 'Groups(' + str(len(groups)) + ')'))
        )
        for g in groups:
            self.gen_item_button(body, g)

        friends = self.context.client.contacts
        body.append(
            urwid.Text(('info', 'Friends(' + str(len(friends)) + ')'))
        )
        for f in friends:
            self.gen_item_button(body, f)

        return self.gen_top(
            self.gen_padding(
                ScrollListBox(
                    urwid.SimpleFocusListWalker(body)
                )
            )
        )


class MainPage(Page):

    def __init__(self, parent, context):
        super(MainPage, self).__init__(parent, context)

    @staticmethod
    def on_friends_clicked(self, button):
        self.go_to_page(FriendsPage)

    @staticmethod
    def on_logout_clicked(self, button):
        context = Context(self.context.loop)
        login_page = LoginPage(None, context)
        login_page.status.set_text(('warn', 'Logout'))
        context.loop.widget = login_page.page
        context.loop.draw_screen()

    def gen_page(self):
        friends = urwid.Button('Friends')
        urwid.connect_signal(friends, 'click',
                             self.on_friends_clicked, user_args=[self])
        chats = urwid.Button('Chats')
        logout = urwid.Button('Logout')
        urwid.connect_signal(logout, 'click',
                             self.on_logout_clicked, user_args=[self])
        exit = urwid.Button('Exit')
        urwid.connect_signal(exit, 'click', self.on_exit_clicked)

        listbox = urwid.ListBox(
            urwid.SimpleFocusListWalker([
                self.gen_button_attrmap(friends, 'submit'),
                self.gen_button_attrmap(chats, 'submit'),
                self.gen_button_attrmap(logout, 'cancel'),
                self.gen_button_attrmap(exit, 'cancel')
            ])
        )
        return self.gen_top(self.gen_padding(listbox))


class Verification(threading.Thread):

    def __init__(self, pin_page, context):
        super(Verification, self).__init__()
        self.pin_page = pin_page
        self.context = context
        self.is_cancel = False

    def save_data(self):
        data = {}
        data['uid'] = self.pin_page.parent.uid.get_edit_text()
        data['password'] = self.pin_page.parent.password.get_edit_text()
        data['authToken'] = self.context.client.authToken
        with open('.pyline', 'w') as outfile:
            json.dump(data, outfile)

    def run(self):
        try:
            with self.context.lock:
                self.context.client.continueLogin()
        except TalkException as e:
            if not self.is_cancel:
                self.pin_page.parent.status.set_text(
                    ('error', e.reason))
                self.pin_page.go_back_page()
        except Exception as e:
            if not self.is_cancel:
                self.pin_page.parent.status.set_text(
                    ('error', e.message))
                self.pin_page.go_back_page()
        else:
            if not self.is_cancel:
                self.save_data()
                self.pin_page.go_to_page(MainPage)


class PinPage(Page):

    def __init__(self, parent, context):
        super(PinPage, self).__init__(parent, context)

    @staticmethod
    def on_cancel_clicked(self, button):
        self.verification.is_cancel = True
        self.parent.status.set_text(('warn', "Cancel login"))
        self.go_back_page()

    def verify(self):
        self.verification = Verification(self, self.context)
        self.verification.daemon = True
        self.verification.start()

    def gen_page(self):
        cancel = urwid.Button(('cancel', 'Cancel'))
        urwid.connect_signal(cancel, 'click',
                             self.on_cancel_clicked, user_args=[self])

        listbox = urwid.ListBox(
            urwid.SimpleFocusListWalker([
                urwid.Text(('line', 'Enter PinCode ' +
                            str(self.context.client._pinCode) +
                            ' to your mobile phone in 2 minutes.')),
                cancel
            ])
        )

        return self.gen_top(self.gen_padding(listbox))


class LoginPage(Page):

    def __init__(self, parent, context):
        super(LoginPage, self).__init__(parent, context)

    @staticmethod
    def on_login_clicked(self, button):
        self.status.set_text(('info', "Login..."))
        self.context.loop.draw_screen()
        authToken = get_authToken()
        try:
            with self.context.lock:
                client = LineClient(authToken=authToken)
            context = Context(client=client)
            context.loop = urwid.MainLoop(
                MainPage(
                    None,
                    context).page,
                palette)
            context.loop.run()
        except:
            try:
                with self.context.lock:
                    self.context.client = LineClient(
                        self.uid.get_edit_text(),
                        self.password.get_edit_text(),
                        com_name=socket.gethostname(),
                        delay=True)
            except TalkException as e:
                self.status.set_text(('error', e.reason))
                self.context.loop.draw_screen()
            except Exception as e:
                self.status.set_text(('error', e.message))
                self.context.loop.draw_screen()
            else:
                self.go_to_page(PinPage)
                self.child.verify()

    @staticmethod
    def get_uid():
        uid = None
        try:
            json_data = open('.pyline')
            data = json.load(json_data)
            uid = data['uid']
            json_data.close()
        except:
            pass
        return uid

    @staticmethod
    def get_password():
        password = None
        try:
            json_data = open('.pyline')
            data = json.load(json_data)
            password = data['password']
            json_data.close()
        except:
            pass
        return password

    def gen_page(self):
        title = urwid.Text(('line', 'Line'))

        self.uid = urwid.Edit(('label', 'ID\n'))
        uid = self.get_uid()
        if uid:
            self.uid.set_edit_text(uid)

        self.password = urwid.Edit(('label', 'Password\n'))
        password = self.get_password()
        if password:
            self.password.set_edit_text(password)

        self.status = urwid.Text('')

        login = urwid.Button('Login')
        urwid.connect_signal(login, 'click',
                             self.on_login_clicked, user_args=[self])

        exit = urwid.Button('Exit')
        urwid.connect_signal(exit, 'click', self.on_exit_clicked)

        listbox = urwid.ListBox(
            urwid.SimpleFocusListWalker([
                title,
                urwid.Divider(),
                self.uid,
                self.password,
                self.status,
                self.gen_button_attrmap(login, 'submit'),
                self.gen_button_attrmap(exit, 'cancel')
            ])
        )

        return self.gen_top(self.gen_padding(listbox))


def get_authToken():
    authToken = None
    try:
        json_data = open('.pyline')
        data = json.load(json_data)
        authToken = data['authToken']
        json_data.close()
    except:
        pass
    return authToken


if __name__ == '__main__':
    authToken = get_authToken()
    try:
        client = LineClient(authToken=authToken)
        context = Context(client=client)
        context.loop = urwid.MainLoop(MainPage(None, context).page, palette)
        context.loop.run()
    except:
        context = Context()
        context.loop = urwid.MainLoop(LoginPage(None, context).page, palette)
        context.loop.run()
