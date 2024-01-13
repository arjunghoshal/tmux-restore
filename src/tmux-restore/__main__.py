from libtmux.server import Server
from libtmux.exc import LibTmuxException
from dataclasses import dataclass
from yaml import safe_dump, safe_load
from dacite import from_dict
from sys import argv
from os.path import expanduser


SESSIONS_FILE = expanduser('~/.tmux-restore')


@dataclass
class Pane:
    id: str
    path: str
    command: str

    def to_dict(self):
        return {'id': self.id, 'path': self.path, 'command': self.command}


@dataclass
class Window:
    id: str
    name: str
    layout: str
    panes: list[Pane]

    def to_dict(self):
        return {
                'id': self.id,
                'name': self.name,
                'layout': self.layout,
                'panes': [pane.to_dict() for pane in self.panes]
                }


@dataclass
class Session:
    id: str
    name: str
    windows: list[Window]

    def to_dict(self):
        return {
                'id': self.id,
                'name': self.name,
                'windows': [window.to_dict() for window in self.windows]
                }


@dataclass
class SessionList:
    sessions: list[Session]

    def to_dict(self):
        return {'sessions': [session.to_dict() for session in self.sessions]}


def save():
    server = Server()
    sessions = []
    for session in server.sessions:
        windows = []
        for window in session.windows:
            panes = []
            for pane in window.panes:
                panes.append(Pane(pane.pane_id, pane.pane_current_path, pane.pane_current_command))
            windows.append(Window(window.window_id, window.window_name, window.window_layout, panes))
        sessions.append(Session(session.session_id, session.session_name, windows))
    session_list = SessionList(sessions)
    with open(SESSIONS_FILE, "w") as sessions_file:
        sessions_file.write(safe_dump(session_list.to_dict()))


def restore():
    server = Server()
    sessions = None
    with open(SESSIONS_FILE) as sessions_file:
       sessions = safe_load(sessions_file)
    if not sessions:
        return
    session_list = from_dict(data=sessions, data_class=SessionList)
    for session in session_list.sessions:
        if server.has_session(session.name):
            continue
        tmux_session = server.new_session(session_name=session.name)
        for index, window in enumerate(session.windows):
            if index != 0:
                tmux_session.new_window(attach=True)
            tmux_session.windows[index].rename_window(window.name)
            for i in range(len(window.panes) - 1):
                try:
                    tmux_session.windows[index].split_window()
                except LibTmuxException:
                    tmux_session.windows[index].select_layout('tiled')
                    tmux_session.windows[index].split_window()
            tmux_session.windows[index].select_layout(window.layout)
            for i, pane in enumerate(window.panes):
                tmux_session.windows[index].panes[i].send_keys("cd " + pane.path, enter=True)
                tmux_session.windows[index].panes[i].send_keys('C-l', enter=False)


def main():
    if len(argv) == 1:
        return restore()
    if 'restore' in argv:
        return restore()
    if 'save' in argv:
        return save()


if __name__ == '__main__':
    main()
