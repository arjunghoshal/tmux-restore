from libtmux.exc import LibTmuxException
from yaml import safe_dump, safe_load
from libtmux.server import Server
from psutil import Process, process_iter
from dataclasses import dataclass
from os.path import expanduser
from dacite import from_dict
from sys import argv


SESSIONS_FILE = expanduser('~/.tmux-restore')


@dataclass
class Command:
    cmdline: str
    enter: bool = True

    def to_dict(self):
        return {'cmdline': self.cmdline, 'enter': self.enter}


@dataclass
class RunningProcess:
    commands: list[Command]

    def to_dict(self):
        return {'commands': [c.to_dict() for c in self.commands]}


@dataclass
class Pane:
    id: str
    path: str
    running_processes: list[RunningProcess]

    def to_dict(self):
        return {'id': self.id, 'path': self.path, 'running_processes': [rp.to_dict() for rp in self.running_processes]}


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


def save_nvim_process(process: dict) -> RunningProcess:
    return RunningProcess([
        Command(cmdline=' '.join(process['cmdline'])),
        Command(cmdline='C-o', enter=False),
        Command(cmdline='C-o', enter=False),
        ])


def save_general_process(process: dict):
    return RunningProcess([
        Command(cmdline=' '.join(process['cmdline']))
        ])


def save_pane_processes(pane) -> list[RunningProcess]:
    processes = []
    pane_process = Process(int(pane.pane_pid))
    attributes = ['pid', 'name', 'terminal', 'cmdline']
    running_processes = [p.info for p in process_iter(attributes) if p.info['terminal'] == pane_process.terminal()]
    GENERAL_COMMANDS = [
            'emacs',
            'vi',
            'ssh',
            'psql',
            'mysql',
            'sqlite3',
            'man',
            'less',
            'more',
            'tail',
            'top',
            'htop',
            'irssi',
            'weechat',
            'mutt',
            ]
    for process in running_processes:
        match process['cmdline'][0]:
            case '-bash':
                continue
            case 'vim' | 'nvim':
                processes.append(save_nvim_process(process))
            case command if command in GENERAL_COMMANDS:
                processes.append(save_general_process(process))
    return processes


def save_panes(window_panes) -> list[Pane]:
    panes = []
    for pane in window_panes:
        processes = save_pane_processes(pane)
        panes.append(Pane(pane.pane_id, pane.pane_current_path, processes))
    return panes


def save_windows(session_windows) -> list[Window]:
    windows = []
    for window in session_windows:
        panes = save_panes(window.panes)
        windows.append(Window(window.window_id, window.window_name, window.window_layout, panes))
    return windows


def save_sessions(server_sessions):
    sessions = []
    for session in server_sessions:
        windows = save_windows(session.windows)
        sessions.append(Session(session.session_id, session.session_name, windows))
    return sessions


def save():
    server = Server()
    sessions = save_sessions(server.sessions)
    session_list = SessionList(sessions)
    with open(SESSIONS_FILE, "w") as sessions_file:
        sessions_file.write(safe_dump(session_list.to_dict()))


def restore_pane(tmux_pane, pane: Pane):
    tmux_pane.send_keys("cd " + pane.path)
    tmux_pane.send_keys('C-l', enter=False)
    for running_process in pane.running_processes:
        for command in running_process.commands:
            tmux_pane.send_keys(command.cmdline, enter=command.enter)


def restore_window(tmux_window, window: Window):
    tmux_window.rename_window(window.name)
    for _ in range(len(window.panes) - 1):
        try:
            tmux_window.split_window()
        except LibTmuxException:
            tmux_window.select_layout('tiled')
            tmux_window.split_window()
    tmux_window.select_layout(window.layout)
    for index, pane in enumerate(window.panes):
        restore_pane(tmux_window.panes[index], pane)


def restore_session(tmux_session, session: Session):
    for index, window in enumerate(session.windows):
        if index != 0:
            tmux_session.new_window(attach=True)
        restore_window(tmux_session.windows[index], window)


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
        restore_session(tmux_session, session)

def main():
    if len(argv) == 1:
        return restore()
    if 'restore' in argv:
        return restore()
    if 'save' in argv:
        return save()


if __name__ == '__main__':
    main()
