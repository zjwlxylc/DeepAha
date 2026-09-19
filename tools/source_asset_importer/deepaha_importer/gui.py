"""Small native Chinese desktop window. All Tk calls stay on the UI thread."""
from __future__ import annotations
import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from . import __version__
from .client import ClientConfig, RemoteClient
from .config import default_data_dir, load_config, save_config
from .controller import ImportSession
from .demo import demo_client
from .errors import ImporterError

LABELS = {'ADD':'新增', 'UPDATE':'更新研究版本', 'NO_CHANGE':'无变化', 'DUPLICATE':'重复，保留引用', 'CONFLICT':'冲突'}
KINDS = {'source':'来源', 'brief':'采集建议', 'evidence':'研究证据', 'demand':'需求', 'graph':'关系',
         'blind_spot':'盲区', 'queue':'队列', 'lifecycle':'维护提案', 'pattern':'模式',
         'demand_delta':'需求变化', 'manual_review':'人工审核项'}


class ImportWindow:
    def __init__(self, root, data_dir=None):
        self.root = root
        self.data_dir = Path(data_dir or default_data_dir())
        self.session = ImportSession(self.data_dir / 'receipts')
        self.work_queue = queue.Queue(); self.busy = False; self.closed = False
        self.item_details = {}
        try: cfg = load_config(self.data_dir / 'settings.json')
        except ImporterError: cfg = ClientConfig('')
        self.demo = tk.BooleanVar(value=True)
        self.server = tk.StringVar(value=cfg.base_url)
        self.environment = tk.StringVar(value=cfg.expected_environment)
        self.target_id = tk.StringVar(value=cfg.expected_target_id or '')
        self.token = tk.StringVar(value='')
        self.loopback = tk.BooleanVar(value=cfg.allow_http_loopback)
        self.status = tk.StringVar(value='可从资料库获取资产包，或选择已有本地文件。默认仍是本地演练，不会自动入库。')
        self.file_name = tk.StringVar(value='尚未选择文件')
        self.ca_file, self.timeout = cfg.ca_file, cfg.timeout_seconds
        self.controls = []; self.remote_controls = []
        self._build()
        for v in (self.demo, self.server, self.environment, self.target_id, self.token, self.loopback):
            v.trace_add('write', self._invalidate)
        self.root.protocol('WM_DELETE_WINDOW', self._close)
        self._after_id = self.root.after(100, self._poll)
        self.root.bind('<Destroy>', self._destroyed, add='+')

    def _build(self):
        self.root.title(f'DeepAha 来源资产导入工具 {__version__} · 待正式系统联调')
        self.root.geometry('1100x790'); self.root.minsize(850, 620)
        outer = ttk.Frame(self.root, padding=18); outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='DeepAha  来源资产导入', font=('', 19, 'bold')).pack(anchor='w')
        ttk.Label(outer, text='从资料库获取 / 选择本地文件 → 查看预览 → 明确确认 → 保存回执', font=('', 11)).pack(anchor='w', pady=(4, 10))
        self.banner = tk.Label(outer, text='本地演练：只写本机演练库，不是正式入库，也不会启动 WMA。',
                               bg='#FFF1DF', fg='#7C3500', anchor='w', padx=12, pady=8)
        self.banner.pack(fill='x', pady=(0, 10))
        conn = ttk.LabelFrame(outer, text='1. 选择使用环境', padding=10); conn.pack(fill='x')
        toggle = ttk.Checkbutton(conn, text='本地演练（不需要服务器或授权）', variable=self.demo)
        toggle.grid(row=0, column=0, columnspan=3, sticky='w'); self.controls.append(toggle)
        ttk.Label(conn, text='服务器地址').grid(row=1, column=0, sticky='w', pady=5)
        entry = ttk.Entry(conn, textvariable=self.server, width=50); entry.grid(row=1, column=1, sticky='ew', padx=8); self.controls.append(entry); self.remote_controls.append(entry)
        combo = ttk.Combobox(conn, textvariable=self.environment, values=['STAGING','PRODUCTION','TEST','DEMO'], state='readonly', width=14)
        combo.grid(row=1, column=2, sticky='ew'); self.controls.append(combo); self.remote_controls.append(combo)
        ttk.Label(conn, text='本机导入授权').grid(row=2, column=0, sticky='w')
        token = ttk.Entry(conn, textvariable=self.token, show='●'); token.grid(row=2, column=1, sticky='ew', padx=8); self.controls.append(token); self.remote_controls.append(token)
        ttk.Label(conn, text='仅本次会话使用，不保存').grid(row=2, column=2, sticky='w')
        ttk.Label(conn, text='固定目标 ID（可选）').grid(row=3, column=0, sticky='w', pady=5)
        target = ttk.Entry(conn, textvariable=self.target_id); target.grid(row=3, column=1, sticky='ew', padx=8); self.controls.append(target); self.remote_controls.append(target)
        save = ttk.Button(conn, text='保存连接设置（不含授权）', command=self._save_settings)
        save.grid(row=3, column=2, sticky='ew'); self.controls.append(save); self.remote_controls.append(save)
        loop = ttk.Checkbutton(conn, text='允许本机 HTTP 测试（绝不允许外部明文地址）', variable=self.loopback)
        loop.grid(row=4, column=1, columnspan=2, sticky='w', padx=8); self.controls.append(loop); self.remote_controls.append(loop)
        conn.columnconfigure(1, weight=1)
        choose = ttk.Frame(outer); choose.pack(fill='x', pady=10)
        library = ttk.Button(choose, text='从资料库获取', command=self._library); library.pack(side='left', padx=(0, 6)); self.controls.append(library)
        select = ttk.Button(choose, text='选择本地文件', command=self._choose); select.pack(side='left'); self.controls.append(select)
        sample = ttk.Button(choose, text='载入演练样本', command=self._sample); sample.pack(side='left', padx=6); self.controls.append(sample)
        ttk.Label(choose, textvariable=self.file_name, wraplength=450).pack(side='left', padx=8)
        # Reserve the footer BEFORE the expanding panes so action buttons never disappear.
        footer = ttk.Frame(outer); footer.pack(side='bottom', fill='x')
        split = ttk.Panedwindow(outer, orient='vertical'); split.pack(fill='both', expand=True)
        treebox = ttk.Frame(split); split.add(treebox, weight=3)
        self.tree = ttk.Treeview(treebox, columns=('kind','name','action','version'), show='headings', height=9)
        for key, label, width in [('kind','资产类型',100),('name','名称 / 外部键',410),('action','预计操作',180),('version','系统情报版本',100)]:
            self.tree.heading(key, text=label); self.tree.column(key, width=width, minwidth=70)
        yscroll = ttk.Scrollbar(treebox, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side='left', fill='both', expand=True); yscroll.pack(side='right', fill='y')
        self.tree.bind('<<TreeviewSelect>>', self._details)
        self.detail = ScrolledText(split, height=7, wrap='word', font=('', 10)); split.add(self.detail, weight=2)
        approval = ttk.Frame(footer); approval.pack(fill='x', pady=4)
        ttk.Label(approval, text='来源批准独立于入库：本窗口只保存候选。正式启用请在 DeepAha 审核入口完成。').pack(anchor='w')
        bar = ttk.Frame(footer); bar.pack(fill='x', pady=8)
        self.preview_button = ttk.Button(bar, text='3. 预览（不入库）', command=self._preview)
        self.preview_button.pack(side='left'); self.controls.append(self.preview_button)
        self.commit_button = ttk.Button(bar, text='4. 确认并导入', command=self._commit, state='disabled')
        self.commit_button.pack(side='left', padx=7)
        recover = ttk.Button(bar, text='查询 / 恢复回执', command=self._recover); recover.pack(side='left'); self.controls.append(recover)
        results = ttk.Button(bar, text='打开结果目录', command=self._open_results); results.pack(side='right'); self.controls.append(results)
        self.progress = ttk.Progressbar(footer, mode='indeterminate'); self.progress.pack(fill='x')
        ttk.Label(footer, textvariable=self.status, wraplength=1000).pack(anchor='w', pady=(6,0))
        self._text('点击“从资料库获取”，程序会在后台调用本机 Codex 读取指定目录、取回选中的原件。\n'
                   '需要本机 Codex 已有资料库读取/导出工具与授权；不会自动导入或上传回执。\n'
                   '真实服务器接口、账号权限及正式来源审核需要由 Codex 接入现有 DeepAha。\n'
                   '当前可以先用演练样本体验检查、确认、去重与回执流程。')
        self._restore_controls()

    def _config(self):
        return ClientConfig(self.server.get().strip(), self.environment.get(), self.target_id.get().strip() or None,
                            self.loopback.get(), self.timeout, self.ca_file)

    def _invalidate(self, *_):
        if self.busy: return
        self.session.invalidate(); self.commit_button.configure(state='disabled')
        self._restore_controls()
        message = ('本地演练：只写本机演练库，不是正式入库，也不会启动 WMA。' if self.demo.get()
                   else f'远程 {self.environment.get()}：请先核对服务器地址、权限和目标；预览不会入库。')
        self.banner.configure(text=message)
        self.status.set('环境或设置已变化，请重新预览。')

    def _save_settings(self):
        try:
            save_config(self._config(), self.data_dir / 'settings.json')
            self.status.set('连接设置已保存；导入授权没有保存。')
        except ImporterError as e: messagebox.showerror('配置未保存', e.message)

    def _client_factory(self):
        # Read every Tk variable BEFORE entering a worker thread.
        use_demo, cfg = self.demo.get(), self._config()
        token = self.token.get().strip() or os.environ.get('DEEPAHA_IMPORT_TOKEN', '')
        return lambda: demo_client(self.data_dir / 'demo') if use_demo else RemoteClient(cfg, token)

    def _library(self):
        if self.busy:
            return
        self.session.invalidate()
        self.commit_button.configure(state='disabled')
        from .library_window import LibraryWindow
        LibraryWindow(self.root, self.data_dir, self._load)

    def _choose(self):
        path = filedialog.askopenfilename(title='选择本轮 Handoff.json', filetypes=[('JSON资产包','*.json')])
        if path: self._load(path)

    def _sample(self):
        self.demo.set(True)
        path = Path(__file__).resolve().parent / 'data' / 'demo_Handoff.json'
        self._load(path)

    def _load(self, path):
        self.commit_button.configure(state='disabled')
        def work(): return self.session.load(path)
        def done(package):
            self.file_name.set(Path(path).name)
            self.tree.delete(*self.tree.get_children()); self.item_details.clear()
            self.status.set(f'已读取批次 {package.run_key}，共 {len(package.assets())} 项研究资产。请点击预览。')
            self._text('文件结构和附件已检查；尚未与数据库比对，也未提交。\n包哈希：' + package.package_hash)
        self._work(work, done)

    def _preview(self):
        try: factory = self._client_factory()
        except ImporterError as e: messagebox.showerror('无法预览', e.message); return
        self._work(lambda: self.session.preview(factory()), self._show_preview)

    def _show_preview(self, preview):
        self.tree.delete(*self.tree.get_children()); self.item_details.clear()
        for number, item in enumerate(preview['items']):
            iid = str(number); self.item_details[iid] = item
            self.tree.insert('', 'end', iid=iid, values=(KINDS.get(item['kind'], item['kind']), item['name'],
                             LABELS.get(item['action'],item['action']), item['system_revision']))
        summary = (f"目标环境：{preview['environment']}\n目标 ID：{preview['target_id']}\n批次：{preview['run_key']}\n"
                   f"汇总：{json.dumps(preview.get('counts',{}),ensure_ascii=False)}\n")
        summary += '\n'.join(str(x) for x in preview.get('warnings', []))
        if preview.get('conflicts'):
            summary += '\n\n冲突（未提交）：\n' + json.dumps(preview['conflicts'], ensure_ascii=False, indent=2)
        self._text(summary)
        self.status.set('预览完成，尚未入库。请核对后确认。' if preview['can_commit'] else '存在冲突或无提交权限，不能导入。')
        self.commit_button.configure(state='normal' if preview['can_commit'] else 'disabled')

    def _commit(self):
        pre = self.session.preview_result
        if not pre: return
        message = f"批次：{pre['run_key']}\n目标环境：{pre['environment']}\n存储目标：{pre['target_id']}\n\n"
        if pre['environment'] != 'PRODUCTION': message += '注意：这是非生产环境，不是正式入库。\n\n'
        message += '仅保存本批研究资产，不自动批准来源或启动 WMA。\n是否确认提交？'
        if not messagebox.askyesno('确认本次导入', message, default='no'): return
        self._work(lambda: self.session.commit(True), self._show_receipt)

    def _recover(self):
        try: factory = self._client_factory()
        except ImporterError as e: messagebox.showerror('无法查询', e.message); return
        self._work(lambda: self.session.recover(factory()), self._show_receipt)

    def _show_receipt(self, result):
        r = result['receipt']
        self.status.set(f"回读确认：{r['status']}；回执已保存。")
        self.commit_button.configure(state='disabled')
        self._text(f"结果：{r['status']}\n批次：{r['run_key']}\n回执：{result['json_path']}\n阅读版：{result['markdown_path']}\n\n"
                   '回传资料库是可选反馈，不影响本次导入完成。\n'
                   '演练/测试回执不是正式导入结果，不要当作正式反馈上传。')

    def _details(self, _=None):
        selected = self.tree.selection()
        if selected and selected[0] in self.item_details:
            item = self.item_details[selected[0]]
            detail = {'plan': item}
            if self.session.package:
                for asset in self.session.package.assets():
                    if asset.key == item['key'] and asset.kind == item['kind']:
                        detail['research_record'] = asset.payload; break
            self._text(json.dumps(detail, ensure_ascii=False, indent=2))

    def _text(self, value):
        self.detail.configure(state='normal'); self.detail.delete('1.0','end'); self.detail.insert('1.0', value)
        self.detail.configure(state='disabled')

    def _work(self, work, done):
        if self.busy: return
        self.busy = True; self.commit_button.configure(state='disabled')
        for c in self.controls: c.configure(state='disabled')
        self.progress.start(12); self.status.set('正在处理，请稍候。不会自动点击确认。')
        def worker():
            try: self.work_queue.put((True, work(), done))
            except Exception as e: self.work_queue.put((False, e, done))
        threading.Thread(target=worker, daemon=True).start()

    def _restore_controls(self):
        for c in self.controls:
            state = 'disabled' if self.demo.get() and c in self.remote_controls else 'readonly' if isinstance(c, ttk.Combobox) else 'normal'
            c.configure(state=state)

    def _poll(self):
        if self.closed: return
        try: ok, result, done = self.work_queue.get_nowait()
        except queue.Empty: pass
        else:
            self.busy = False; self.progress.stop()
            self._restore_controls()
            if ok: done(result)
            else:
                self.session.invalidate(); self.commit_button.configure(state='disabled')
                message = f'[{result.code}] {result.message}' if isinstance(result, ImporterError) else '处理失败：' + type(result).__name__ + '。请检查文件、配置或本机权限。'
                self.status.set(message); self._text(message)
                messagebox.showerror('未确认完成', message)
        self._after_id = self.root.after(100, self._poll)

    def _destroyed(self, event):
        if event.widget is self.root:
            self.closed = True
            try: self.root.after_cancel(self._after_id)
            except tk.TclError: pass

    def _open_results(self):
        path = self.session.results_dir.resolve(); path.mkdir(parents=True, exist_ok=True)
        if os.name == 'nt': os.startfile(str(path))
        elif sys.platform == 'darwin': subprocess.Popen(['open', str(path)])
        else: subprocess.Popen(['xdg-open', str(path)])

    def _close(self):
        if self.busy:
            messagebox.showinfo('请等待当前操作完成', '提交过程中不关闭窗口；若网络异常，可稍后查询回执。')
            return
        self.closed = True; self.token.set(''); self.root.destroy()


def main(data_dir=None):
    root = tk.Tk(); ImportWindow(root, data_dir); root.mainloop()

if __name__ == '__main__': main()
