"""English GUI for reviewing and importing Career saves."""
from contextlib import closing
from datetime import datetime
from pathlib import Path
import sqlite3
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import career_import
import datos
import lanzador
import launch
import layout
from transporte import Screen


def game_date(value):
    return f'{value:08d}' if not 10000101 <= value <= 99991231 else (
        f'{value//10000:04d}-{value//100%100:02d}-{value%100:02d}')


class CareerImportDialog:
    def __init__(self, parent, executor, game, profile):
        self.parent, self.executor = parent, executor
        self.game, self.profile = game, profile
        self.window = tk.Toplevel(parent)
        self.window.title('Import Existing Career')
        self.window.transient(parent)
        self.window.minsize(820, 405)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.window.grab_set()
        self.busy = False
        self.manually_ordered = False
        self.values = {}
        self.items = {}
        self.linked = []
        self.status = tk.StringVar(value='Looking for Career saves…')
        self.location = tk.StringVar()

        frame = ttk.Frame(self.window, padding=12)
        frame.pack(expand=True, fill='both')
        ttk.Label(frame, text='Select saves from one Career, oldest first. Use Ctrl or Shift to select several.',
                  wraplength=770).pack(anchor='w')
        tools = ttk.Frame(frame)
        tools.pack(fill='x', pady=(8, 4))
        self.folder_button = ttk.Button(tools, text='Browse Folder…', command=self.choose_folder)
        self.files_button = ttk.Button(tools, text='Add Save Files…', command=self.choose_files)
        self.linked_button = ttk.Button(tools, text='View Linked Saves', command=self.view_linked)
        self.up_button = ttk.Button(tools, text='Move Up', command=lambda: self.move(-1))
        self.down_button = ttk.Button(tools, text='Move Down', command=lambda: self.move(1))
        for button in (self.folder_button, self.files_button, self.linked_button, self.up_button, self.down_button):
            button.pack(side='left', padx=(0, 6))

        list_area = ttk.Frame(frame)
        list_area.pack(expand=True, fill='both')
        columns = ('save', 'club', 'season', 'date', 'modified', 'status')
        self.tree = ttk.Treeview(list_area, columns=columns, show='headings', selectmode='extended', height=9)
        headings = ('Save', 'Team ID', 'Season', 'Career date', 'File modified', 'Status')
        widths = (200, 65, 55, 100, 135, 200)
        for name, heading, width in zip(columns, headings, widths, strict=True):
            self.tree.heading(name, text=heading)
            self.tree.column(name, width=width, minwidth=45, stretch=name in ('save', 'status'))
        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar = ttk.Scrollbar(list_area, orient='vertical', command=self.tree.yview)
        scrollbar.pack(side='right', fill='y')
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind('<<TreeviewSelect>>', self.selection_changed)
        self.tree.bind('<Control-a>', self.select_all)
        ttk.Label(frame, textvariable=self.location, wraplength=790).pack(anchor='w', pady=(3, 5))

        ttk.Label(frame, text='Link to an existing checkpoint, or use the selected save history').pack(anchor='w')
        self.anchor = ttk.Combobox(frame, state='readonly')
        self.anchor.pack(fill='x', pady=(2, 7))
        ttk.Label(frame, textvariable=self.status, wraplength=790).pack(anchor='w', pady=(2, 6))
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x')
        self.preview_button = ttk.Button(buttons, text='Preview Import…', command=self.preview)
        self.preview_button.pack(side='right')
        self.close_button = ttk.Button(buttons, text='Close', command=self.close)
        self.close_button.pack(side='right', padx=6)
        self.controls = (self.folder_button, self.files_button, self.linked_button, self.up_button,
                         self.down_button, self.preview_button, self.close_button)
        self.start('Looking for Career saves…', self.load_initial, self.populate_initial)

    def start(self, message, work, finished):
        self.busy = True
        self.status.set(message)
        for button in self.controls:
            button.configure(state='disabled')
        self.anchor.configure(state='disabled')
        future = self.executor.submit(self.in_session, work)

        def poll():
            if not future.done():
                self.window.after(80, poll)
                return
            self.busy = False
            for button in self.controls:
                button.configure(state='normal')
            self.anchor.configure(state='readonly')
            self.selection_changed()
            try:
                result = future.result()
            except (OSError, ValueError, RuntimeError, sqlite3.Error, subprocess.SubprocessError) as exc:
                self.status.set('The operation could not finish.')
                messagebox.showerror('Career Import', str(exc), parent=self.window)
                return
            finished(result)
        self.window.after(80, poll)

    def in_session(self, work):
        with lanzador.single_launcher():
            launch.closed()
            if layout.JOURNAL.exists():
                raise RuntimeError('Recover the previous session before importing a Career.')
            launch.configure_runtime(self.game, self.profile)
            return work()

    def load_initial(self):
        paths = (self.profile/'0/FIFA16').glob('*/DATA')
        candidates = career_import.read_candidates(paths, discover=True)
        with closing(career_import.open_preview()) as db:
            linked = career_import.registered_saves(db)
        return candidates, linked

    def populate_initial(self, result):
        candidates, self.linked = result
        choices = ['New Career / use registered saves in the selection']
        for row in self.linked:
            choices.append(f"{row['label']} · S{row['season']} · {game_date(row['date'])} · "
                           f"{row['save_label'] or 'Career save'} · {row['sha'][:12]}")
        self.anchor.configure(values=choices)
        self.anchor.current(0)
        self.add_results(candidates)

    def add_results(self, results):
        registered = {row['sha'] for row in self.linked}
        results.sort(key=lambda row: (row[1] is None, row[1]['season'] if row[1] else 0,
                                     row[1]['date'] if row[1] else 0, str(row[0])))
        for path, value, error in results:
            if path in self.items:
                self.tree.delete(self.items[path])
                self.values.pop(self.items[path])
            if value:
                modified = datetime.fromtimestamp(value['modified_ns']/1e9).strftime('%Y-%m-%d %H:%M')
                cells = (value['save_label'] or path.parent.name, value['club'], value['season'],
                         game_date(value['date']), modified,
                         'Registered' if value['sha'] in registered else 'Ready')
            else:
                cells = (path.name, '', '', '', '', 'Unavailable')
            item = self.tree.insert('', 'end', values=cells)
            self.items[path] = item
            self.values[item] = (path, value, error)
        self.status.set(f'{len(self.values)} saves listed. Move one row at a time to correct the order, '
                        'then select the saves to import.')
        if not self.manually_ordered:
            def chronological(item):
                path, value, _ = self.values[item]
                return (value is None, value['season'] if value else 0,
                        value['date'] if value else 0, str(path))
            for i, item in enumerate(sorted(self.tree.get_children(), key=chronological)):
                self.tree.move(item, '', i)
        self.selection_changed()

    def selection_changed(self, _event=None):
        selected = self.tree.selection()
        if len(selected) == 1:
            path, _, error = self.values[selected[0]]
            self.location.set(f'{path}\n{error}' if error else str(path))
        else:
            self.location.set('')
        if not self.busy:
            self.preview_button.configure(state='normal' if selected and
                                          all(self.values[i][1] for i in selected) else 'disabled')
            for button in (self.up_button, self.down_button):
                button.configure(state='normal' if len(selected) == 1 else 'disabled')

    def select_all(self, _event):
        if not self.busy:
            self.tree.selection_set([item for item in self.tree.get_children() if self.values[item][1]])
        return 'break'

    def choose_folder(self):
        folder = filedialog.askdirectory(parent=self.window, mustexist=True, title='Find Career Saves')
        if folder:
            self.start('Checking this folder…',
                       lambda: career_import.read_candidates(
                           career_import.folder_saves(layout.directory(folder)), discover=True),
                       self.add_results)

    def choose_files(self):
        files = filedialog.askopenfilenames(parent=self.window, title='Select FIFA 16 Career Save Files')
        if files:
            self.start('Checking the selected saves…', lambda: career_import.read_candidates(files),
                       self.add_results)

    def move(self, direction):
        (item,) = self.tree.selection()
        index = self.tree.index(item) + direction
        if 0 <= index < len(self.values):
            self.manually_ordered = True
            self.tree.move(item, '', index)

    def view_linked(self):
        child = tk.Toplevel(self.window)
        child.title('Linked Career Saves')
        child.transient(self.window)
        text = ScrolledText(child, width=95, height=19, padx=8, pady=8)
        text.pack(expand=True, fill='both')
        text.insert('end', '\n\n'.join(
            f"{row['label']} | Season {row['season']} | {game_date(row['date'])} | Team {row['club']}\n"
            f"{row['save_label']} · {row['sha'][:12]} · Parent: "
            f"{row['parent'][:12] if row['parent'] else 'First checkpoint'}\n{row['source']}"
            for row in self.linked) or 'No saves are registered yet.')
        text.configure(state='disabled')

    def preview(self):
        selected = set(self.tree.selection())
        values = [self.values[item][1] for item in self.tree.get_children() if item in selected]
        choice = self.anchor.current()
        parent = self.linked[choice-1]['sha'] if choice > 0 else None
        self.start('Reconstructing a preview…', lambda: career_import.preview_import(values, parent),
                   self.confirm)

    def confirm(self, preview):
        seasons = '\n'.join(
            f'Season {s} · {rows} publishable rows · {apps}/{goals}/{assists}/{clean}'
            for s, rows, apps, goals, assists, clean in preview.seasons)
        warnings = '\n\n' + '\n'.join(preview.warnings) if preview.warnings else ''
        text = (f'{preview.added} new checkpoints, {preview.reused} already known or duplicate selections.\n\n'
                f'Rows with appearances / goals / assists / clean sheets\n{seasons}{warnings}\n\n'
                'Confirm only if these saves and any selected parent belong to the same Career.')
        self.status.set('Review the preview before importing.')
        review = tk.Toplevel(self.window)
        review.title('Confirm Career Import')
        review.transient(self.window)
        review.grab_set()
        details = ScrolledText(review, width=76, height=12, wrap='word', padx=10, pady=10)
        details.pack(expand=True, fill='both')
        details.insert('end', text)
        details.configure(state='disabled')
        buttons = ttk.Frame(review, padding=8)
        buttons.pack(fill='x')

        def dismiss():
            review.destroy()
            self.window.grab_set()

        def accept():
            dismiss()
            self.start('Validating and registering the selected saves…',
                       lambda: self.commit(preview), self.completed)

        ttk.Button(buttons, text='Import Selected Saves', command=accept).pack(side='right')
        cancel = ttk.Button(buttons, text='Cancel', command=dismiss)
        cancel.pack(side='right', padx=8)
        cancel.focus_set()
        review.bind('<Escape>', lambda _: dismiss())
        review.protocol('WM_DELETE_WINDOW', dismiss)

    def commit(self, preview):
        launch.check_game(self.game)
        launch.check_components()
        launch.ensure_screens(self.game)
        launch.check_payload()
        screens = [Screen((layout.PAYLOAD/f'{stem}.apt').read_bytes(), player=i == 0)
                   for i, stem in enumerate(layout.RESOURCES)]
        source = datos.Source()

        def validate(sha, db):
            buckets, club, _ = source.snapshot(sha, db)
            for screen in screens:
                screen.payload(buckets, club, 1)

        return career_import.commit_import(preview, validate)

    def completed(self, result):
        messagebox.showinfo('Career Import',
                            f'{result.added} new checkpoints registered. '
                            f'{result.reused} existing or duplicate selections reused.\n\n'
                            'Launch FIFA 16 and load a registered save to continue tracking.',
                            parent=self.window)
        self.close()

    def close(self):
        if not self.busy:
            self.window.destroy()
