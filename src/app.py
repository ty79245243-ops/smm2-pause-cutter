from __future__ import annotations
import argparse, json, queue, threading
from dataclasses import replace
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import cv2
from media_io import VideoCapture
from diagnostics import logger,configure
from engine import analyze, export, keep_ranges, Cancelled, VERSION
from pause_table import PauseTable,ROW_HEIGHT,HEADER_HEIGHT


class App:
    def __init__(self, root):
        self.root = root
        root.title(f'Mario Pause Cutter {VERSION} — マリオメーカー2')
        root.geometry('1040x350'); root.minsize(920,330)
        self.q = queue.Queue(); self.cancel = threading.Event()
        self.busy = False; self.analysis = None; self.original_cuts = []
        self.photos = []; self.editor = None;self.resize_preview_job=None
        self.preview_request=0;self.preview_pending=None;self.preview_thread=None;self.preview_lock=threading.Lock()
        self.details_visible = False;self.results_visible=False
        self.view_mode=tk.StringVar(value="all");self.applied_filter="all"
        self.file = tk.StringVar(); self.audio = tk.StringVar(value='mute')
        self.status = tk.StringVar(value='まず「元動画を選択…」から動画を読み込んでください。')

        style = ttk.Style(); style.theme_use('clam')
        style.configure('.', font=('Yu Gothic UI',10))
        style.configure('Title.TLabel',font=('Yu Gothic UI',20,'bold'))
        style.configure('Step.TLabel',font=('Yu Gothic UI',11,'bold'))
        style.configure('Hint.TLabel',foreground='#5e6672')

        main = ttk.Frame(root,padding=20); main.pack(fill='both',expand=True)
        ttk.Label(main,text=f'Mario Pause Cutter {VERSION}',style='Title.TLabel').pack(anchor='w')
        ttk.Label(main,text='ポーズを確認しながらカットして、動画を保存します。',style='Hint.TLabel').pack(anchor='w',pady=(0,10))
        ttk.Label(main,text='1. 元動画を選択',style='Step.TLabel').pack(anchor='w')
        row = ttk.Frame(main); row.pack(fill='x',pady=(4,10))
        self.entry = ttk.Entry(row,textvariable=self.file,state='readonly')
        self.entry.pack(side='left',fill='x',expand=True)
        self.choose_btn = ttk.Button(row,text='元動画を選択…',command=self.choose)
        self.choose_btn.pack(side='left',padx=(8,0))

        ttk.Label(main,text='2. 音声を設定',style='Step.TLabel').pack(anchor='w')
        audio = ttk.Frame(main); audio.pack(fill='x',pady=3)
        self.radios = []
        for text,value in [('消音（初期設定）','mute'),('音声を残す','keep')]:
            r = ttk.Radiobutton(audio,text=text,value=value,variable=self.audio)
            r.pack(side='left',padx=(0,16)); self.radios.append(r)
        ttk.Label(main,text='音声を残す場合、カットの継ぎ目でBGMや効果音が途切れます。',style='Hint.TLabel').pack(anchor='w')

        actions = ttk.Frame(main); actions.pack(fill='x',pady=(10,6))
        self.analyze_btn = ttk.Button(actions,text='3. ポーズを解析',command=self.scan)
        self.analyze_btn.pack(side='left')
        self.cancel_btn = ttk.Button(actions,text='中止',command=self.cancel.set)
        self.cancel_btn.pack(side='left',padx=8)
        self.bar = ttk.Progressbar(main,maximum=100); self.bar.pack(fill='x')
        ttk.Label(main,textvariable=self.status,wraplength=960).pack(anchor='w',pady=(5,0))

        # Results are always compact first; review is an optional expansion.
        self.results=ttk.Frame(main)
        review_bar=ttk.Frame(self.results);review_bar.pack(fill='x',pady=(12,0))
        self.review_btn=ttk.Button(review_bar,text='区間一覧を開く ▾',command=self.toggle_details)
        self.review_btn.pack(side='left')
        self.review_count=tk.StringVar()
        ttk.Label(review_bar,textvariable=self.review_count,style='Hint.TLabel').pack(side='left',padx=12)
        self.details = ttk.Frame(self.results)
        self.details.columnconfigure(0,weight=1)
        self.details.rowconfigure(2,weight=1,minsize=ROW_HEIGHT+HEADER_HEIGHT+2)
        filters=ttk.Frame(self.details);filters.grid(row=0,column=0,sticky='ew',pady=(8,2))
        ttk.Label(filters,text='表示：').pack(side='left')
        self.filter_radios=[]
        for text,value in [('すべて','all'),('通常のみ','normal'),('要確認のみ','review')]:
            radio=ttk.Radiobutton(filters,text=text,value=value,variable=self.view_mode,command=self.apply_filter)
            radio.pack(side='left',padx=(0,14));self.filter_radios.append(radio)
        self.filter_count=tk.StringVar()
        ttk.Label(filters,textvariable=self.filter_count,style='Hint.TLabel').pack(side='left')
        ttk.Label(self.details,text='チェックボックスでカット予定を切り替えます。白い数値欄はEnterまたは外側のクリックで確定、Escで取消。',style='Hint.TLabel').grid(row=1,column=0,sticky='w')
        self.table = PauseTable(self.details,on_select=lambda i:self.preview(),
            on_toggle=self.toggle_row,on_reset=self.reset_row,on_edit_focus=self.edit_focus,
            before_action=self.finish_edit,on_commit=self.finish_edit_event,on_escape=self.cancel_edit_event,reset_needed=self.reset_needed)
        self.table.grid(row=2,column=0,sticky='nsew',pady=6)

        previews = ttk.Frame(self.details); previews.grid(row=3,column=0,sticky='ew',pady=(6,0))
        self.preview_labels = []; self.caption_labels = []
        for text in ['カット直前（残る）','検出したメニュー','カット直後（残る）']:
            box = ttk.Frame(previews); box.pack(side='left',expand=True,fill='x')
            caption = ttk.Label(box,text=text); caption.pack(); self.caption_labels.append(caption)
            label = ttk.Label(box,text='区間を選択',anchor='center'); label.pack()
            self.preview_labels.append(label)
        self.export_area = ttk.Frame(self.results); self.export_area.pack(side='bottom',fill='x',pady=(14,0))
        self.export_btn = ttk.Button(self.export_area,text='4. MP4を書き出す…',command=self.save)
        self.export_btn.pack(side='left')
        self.refresh_controls()
        self.poll_job=root.after(100,self.poll)
        root.bind('<Destroy>',self.on_destroy,add='+')
        root.bind('<Configure>',self.on_resize,add='+')
        root.bind('<Button-1>',self.outside_click,add='+')
        root.protocol('WM_DELETE_WINDOW',self.close)

    def refresh_controls(self):
        ready = bool(self.file.get()) and not self.busy
        self.choose_btn.configure(state='disabled' if self.busy else 'normal')
        self.analyze_btn.configure(state='normal' if ready else 'disabled')
        for r in self.radios: r.configure(state='normal' if ready else 'disabled')
        self.export_btn.configure(state='normal' if self.analysis and not self.busy else 'disabled')
        self.cancel_btn.configure(state='normal' if self.busy else 'disabled')
        self.table.set_busy(self.busy)
        self.review_btn.configure(state='normal' if self.analysis and not self.busy else 'disabled')
        for radio in self.filter_radios:radio.configure(state='normal' if self.analysis and not self.busy else 'disabled')

    def compact_size(self):
        self.root.minsize(920,440 if self.results_visible else 330)
        self.root.geometry(f'{max(920,self.root.winfo_width())}x{470 if self.results_visible else 350}')

    def hide_details(self):
        self.cancel_edit();self.details.pack_forget();self.results.pack_forget()
        self.details_visible=False;self.results_visible=False
        self.review_btn.configure(text='区間一覧を開く ▾')
        self.table.stop_animation();self.compact_size()

    def show_results(self):
        self.results.pack(fill='both',expand=True);self.results_visible=True
        self.details.pack_forget();self.details_visible=False
        self.review_btn.configure(text='区間一覧を開く ▾');self.compact_size()

    def show_details(self):
        if self.busy or not self.analysis:return
        if not self.details_visible:
            self.details.pack(fill='both',expand=True)
            self.details_visible=True;self.review_btn.configure(text='区間一覧を閉じる ▴')
            self.root.minsize(920,780)
            height=max(780,min(920,self.root.winfo_screenheight()-100))
            self.root.geometry(f'{max(920,self.root.winfo_width())}x{height}')
            self.root.after_idle(self.select_first_visible)

    def toggle_details(self):
        if self.busy or not self.analysis:return
        if not self.finish_edit():return
        if self.details_visible:
            self.details.pack_forget();self.details_visible=False
            self.review_btn.configure(text='区間一覧を開く ▾')
            self.table.stop_animation();self.clear_previews();self.compact_size()
        else:self.show_details()

    def needs_review(self,i):
        # Manual unchecking is not a detection failure. Keep detector concerns
        # visible even after the user enables or edits those intervals.
        return not self.original_cuts[i].enabled or self.original_cuts[i].note.startswith('要確認') or self.analysis.cuts[i].note.startswith('要確認')

    def filtered_indices(self):
        if not self.analysis:return []
        mode=self.view_mode.get()
        return [i for i in range(len(self.analysis.cuts))
                if mode=='all' or (self.needs_review(i) if mode=='review' else not self.needs_review(i))]

    def select_first_visible(self):
        if not self.details_visible:return
        if self.table.indices:
            if self.table.selected_index not in self.table.indices:self.table.select(self.table.indices[0])
            else:self.preview()
        else:self.clear_previews()

    def apply_filter(self):
        if not self.analysis:return
        if not self.finish_edit():self.view_mode.set(self.applied_filter);return
        selected=self.selected();indices=self.filtered_indices()
        self.table.set_filter(indices);self.applied_filter=self.view_mode.get()
        self.filter_count.set(f'{len(indices)} / {len(self.analysis.cuts)}区間')
        self.clear_previews()
        if self.details_visible:
            if selected in indices:self.table.select(selected)
            elif indices:self.table.select(indices[0])

    def choose(self):
        if self.busy: return
        path = filedialog.askopenfilename(title='元動画を選択',filetypes=[('動画','*.mp4 *.mkv *.mov *.avi *.m4v'),('すべて','*.*')])
        if path: self.load_file(path)

    def load_file(self,path):
        self.hide_details(); self.file.set(path); self.analysis = None; self.original_cuts = []
        self.clear_rows(); self.clear_previews(); self.bar['value'] = 0
        self.status.set('音声を設定し、「3. ポーズを解析」を押してください。')
        self.refresh_controls()

    def clear_rows(self):
        self.table.set_rows([])

    def clear_previews(self):
        with self.preview_lock:
            self.preview_request+=1;self.preview_pending=None
        for label in self.preview_labels: label.configure(image='',text='区間を選択')
        self.photos = []

    def locked(self,b):
        self.busy = b; self.refresh_controls()

    def work(self,fn,kind):
        self.cancel.clear(); self.locked(True); self.bar['value'] = 0
        def worker():
            try: self.q.put((kind,fn(lambda p,s:self.q.put(('progress',(p,s))))))
            except Cancelled: self.q.put(('cancelled',None))
            except Exception as e:
                logger.exception('Background operation %s failed',kind)
                self.q.put(('error',str(e)))
        threading.Thread(target=worker,daemon=True).start()

    def scan(self):
        if self.busy or not self.file.get(): return
        self.hide_details(); self.analysis = None; self.original_cuts = []
        self.clear_rows(); self.clear_previews()
        self.status.set('動画を解析しています…')
        path = self.file.get(); self.work(lambda cb:analyze(path,cb,self.cancel),'analyzed')

    def accept_analysis(self,analysis):
        self.hide_details();self.clear_previews()
        self.analysis = analysis
        # Independent snapshots: editing rows must never change reset defaults.
        self.original_cuts = [replace(c) for c in analysis.cuts]
        self.view_mode.set("all");self.applied_filter="all"
        self.locked(False); self.fill(); self.show_results()

    def fill(self):
        self.cancel_edit(); self.clear_rows()
        self.table.set_rows(self.analysis.cuts,self.analysis.fps)
        self.apply_filter();self.summary()

    def update_row(self,i):
        self.table.refresh_row(i)
        self.summary()
        if self.table.indices!=self.filtered_indices():self.apply_filter()
        elif self.selected()==i: self.preview()

    def summary(self):
        review=sum(self.needs_review(i) for i in range(len(self.analysis.cuts)))
        self.review_count.set(f'通常 {len(self.analysis.cuts)-review}区間／要確認 {review}区間')
        a = self.analysis; removed = sum(c.end-c.start for c in a.cuts if c.enabled)
        self.status.set(f'{len(a.cuts)}区間検出／カット予定 {sum(c.enabled for c in a.cuts)}区間／削除 {removed:,}フレーム ({removed/a.fps:.2f}秒)／出力 {(a.frames-removed)/a.fps:.2f}秒')

    def selected(self):
        return self.table.selected_index if self.analysis else None

    def toggle_row(self,i):
        if self.busy or not self.analysis: return
        c = self.analysis.cuts[i]; c.enabled = not c.enabled
        try: keep_ranges(self.analysis)
        except ValueError as e:
            c.enabled = not c.enabled; self.table.refresh_row(i); messagebox.showerror('区間を確認',str(e)); return
        self.update_row(i)

    def begin_edit(self,i,key):
        if self.busy or not self.analysis: return
        self.table.focus_entry(i,key)

    def edit_focus(self,i,key,entry):
        if self.busy:return
        if self.editor and self.editor[0] is entry:return
        self.finish_edit()
        self.table.select(i)
        self.editor=(entry,i,key);entry.selection_range(0,'end')

    def edit_boundary(self,i,key,text):
        c = self.analysis.cuts[i]; old = replace(c)
        try:
            value = int(text.strip())
            if key=='start': c.start = value-1
            elif key=='end': c.end = value
            else: raise ValueError('編集できない列です。')
            if not 0<=c.start<c.end<=self.analysis.frames:
                raise ValueError('元動画の範囲内で、削除開始≦削除終了にしてください。')
            keep_ranges(self.analysis)
        except ValueError as e:
            self.analysis.cuts[i] = old
            messagebox.showerror('入力を確認',str(e)); return False
        if (c.start,c.end)==(old.start,old.end):return True
        c.note = '手動で境界を変更'
        self.update_row(i); return True

    def finish_edit(self):
        if not self.editor: return True
        entry,i,key = self.editor
        if not entry.winfo_exists():self.editor=None;return True
        value = entry.get()
        self.editor = None
        ok=self.edit_boundary(i,key,value)
        self.table.refresh_row(i)
        return ok

    def finish_edit_event(self):
        self.finish_edit(); self.table.body.focus_set(); return 'break'

    def cancel_edit(self):
        if self.editor:
            entry,i,key = self.editor; self.editor = None
            if entry.winfo_exists():
                value=self.analysis.cuts[i].start+1 if key=='start' else self.analysis.cuts[i].end
                entry.delete(0,'end');entry.insert(0,str(value))
            self.table.refresh_row(i)

    def cancel_edit_event(self):
        self.cancel_edit(); self.table.body.focus_set(); return 'break'

    def outside_click(self,event):
        fields=[e for row in self.table.visible.values() for e in row.fields.values()]
        if event.widget in fields:return
        # A reset must also rescue an unfinished invalid value.
        if any(event.widget is row.reset for row in self.table.visible.values()):
            self.cancel_edit()
        else:self.finish_edit()
        if self.root.focus_get() in fields:self.table.body.focus_set()

    def reset_needed(self,i):
        if not self.analysis or i>=len(self.original_cuts):return False
        if self.analysis.cuts[i]!=self.original_cuts[i]:return True
        if self.editor and self.editor[1]==i:
            entry,_,key=self.editor
            c=self.analysis.cuts[i]
            value=str(c.start+1 if key=='start' else c.end)
            return entry.winfo_exists() and entry.get().strip()!=value
        return False

    def reset_row(self,i):
        if self.busy or not self.analysis: return
        self.cancel_edit()
        self.analysis.cuts[i] = replace(self.original_cuts[i])
        try: keep_ranges(self.analysis)
        except ValueError:
            # Always recover the original boundaries even if another edited row
            # now overlaps. Keep this row until the conflict has been corrected.
            self.analysis.cuts[i].enabled = False
            self.analysis.cuts[i].note = '要確認：解析時の境界にリセット（他区間と重なるためカットしない）'
        self.table.select(i,notify=False); self.update_row(i)

    def preview(self,event=None):
        if self.busy or not self.details_visible: return
        i = self.selected()
        if i is None: return
        c=self.analysis.cuts[i]
        indices=[max(0,c.start-1),(c.menu_start+c.menu_end)//2,min(self.analysis.frames-1,c.end)]
        max_height=max(100,min(169,self.root.winfo_height()-650))
        width=max(160,min(300,(self.table.winfo_width()-10)//3,round(max_height*16/9)))
        # A single decoder worker takes the newest pending request. Video seeks
        # never block wheel animation, and stale previews cannot replace a new row.
        with self.preview_lock:
            self.preview_request+=1
            self.preview_pending=(self.preview_request,self.analysis.source,indices,width)
            if self.preview_thread is None:
                self.preview_thread=threading.Thread(target=self.preview_worker,daemon=True)
                self.preview_thread.start()

    def preview_worker(self):
        while True:
            with self.preview_lock:
                task=self.preview_pending;self.preview_pending=None
                if task is None:self.preview_thread=None;return
            request,source,indices,width=task;frames=[];cap=VideoCapture(source)
            try:
                for index in indices:
                    with self.preview_lock:
                        if request!=self.preview_request:break
                    cap.set(cv2.CAP_PROP_POS_FRAMES,index);ok,f=cap.read()
                    if ok:
                        f=cv2.resize(f,(width,round(width*9/16)),interpolation=cv2.INTER_AREA)
                        ok,png=cv2.imencode('.png',f)
                        frames.append((png.tobytes() if ok else None,index))
                    else:frames.append((None,index))
                if len(frames)==3:self.q.put(('preview',(request,frames)))
            except Exception:
                logger.exception('Preview decoding failed')
                self.q.put(('preview',(request,[(None,index) for index in indices])))
            finally:cap.release()

    def display_preview(self,request,frames):
        if request!=self.preview_request or not self.analysis or not self.details_visible:return
        photos=[]
        for j,(png,index) in enumerate(frames):
            if png:
                photo=tk.PhotoImage(data=png);photos.append(photo)
                self.preview_labels[j].configure(image=photo,text='')
                self.caption_labels[j].configure(text=f'{["直前（残る）","メニュー","直後（残る）"][j]}：{index+1}フレーム')
            else:self.preview_labels[j].configure(image='',text='プレビューを読み込めません')
        self.photos=photos

    def save(self):
        if self.busy or not self.analysis or not self.finish_edit(): return
        try: keep_ranges(self.analysis)
        except ValueError as e: messagebox.showerror('区間を確認',str(e)); return
        src = Path(self.analysis.source)
        path = filedialog.asksaveasfilename(title='カット後の動画を保存',initialdir=str(src.parent),
            initialfile=src.stem+'_pausecut.mp4',defaultextension='.mp4',filetypes=[('MP4','*.mp4')])
        if not path: return
        if Path(path).exists():
            messagebox.showerror('名前を変更','上書きせず、別のファイル名で保存してください。'); return
        mute = self.audio.get()=='mute'; self.status.set('書き出しを開始します…')
        self.work(lambda cb:export(self.analysis,path,mute,cb,self.cancel),'exported')

    def poll(self):
        try:
            while True:
                kind,data = self.q.get_nowait()
                if kind=='preview':self.display_preview(*data)
                elif kind=='progress': self.bar['value'] = data[0]*100; self.status.set(data[1])
                elif kind=='analyzed':
                    self.accept_analysis(data)
                    if not data.cuts: self.status.set('ポーズメニューは見つかりませんでした。動画はそのまま書き出せます。')
                elif kind=='exported':
                    self.locked(False)
                    messagebox.showinfo('保存完了',f'保存しました。\n{data["output"]}\n\nカット記録（.cuts.json）も同じ場所に保存しました。')
                elif kind=='cancelled': self.locked(False); self.status.set('中止しました。')
                elif kind=='error':
                    self.locked(False); self.status.set('処理に失敗しました。'); messagebox.showerror('エラー',data)
        except queue.Empty: pass
        self.poll_job=self.root.after(100,self.poll)

    def on_destroy(self,event):
        if event.widget is self.root and self.poll_job is not None:
            with self.preview_lock:self.preview_request+=1;self.preview_pending=None
            self.root.after_cancel(self.poll_job);self.poll_job=None
            if self.resize_preview_job is not None:self.root.after_cancel(self.resize_preview_job);self.resize_preview_job=None

    def on_resize(self,event):
        if event.widget is not self.root or not self.details_visible:return
        if self.resize_preview_job is not None:self.root.after_cancel(self.resize_preview_job)
        self.resize_preview_job=self.root.after(120,self.resize_preview)

    def resize_preview(self):
        self.resize_preview_job=None
        self.preview()

    def close(self):
        if self.busy:
            self.cancel.set(); self.status.set('中止しています。処理が止まってから閉じてください。')
        else: self.cancel_edit(); self.root.destroy()


def main():
    configure(VERSION)
    p = argparse.ArgumentParser()
    p.add_argument('--analyze'); p.add_argument('--output'); p.add_argument('--keep-audio',action='store_true')
    p.add_argument('--report'); p.add_argument('--smoke-ui',action='store_true'); args = p.parse_args()
    if args.analyze:
        a = analyze(args.analyze,lambda p,s:print(s,flush=True))
        data = {'frames':a.frames,'fps':a.fps,'cuts':[vars(c) for c in a.cuts]}
        if args.output: data = export(a,args.output,not args.keep_audio,lambda p,s:print(s,flush=True))
        if args.report: Path(args.report).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        else: print(json.dumps(data,ensure_ascii=False,indent=2))
    else:
        root = tk.Tk()
        help_menu = tk.Menu(root, tearoff=False)
        help_menu.add_command(label='ライセンス', command=lambda: messagebox.showinfo(
            'ライセンス', 'SMM2 Pause Cutter：MIT\n'
            '動画読み込み用FFmpeg：LGPL 2.1以降（DLL）\n'
            '書き出し用FFmpeg・x264：GPL 2以降（別プロセス）\n'
            'PyAV・OpenCV・NumPy・Python等：各コンポーネントのライセンス\n\n'
            'ライセンス全文はlicenses、対応ソースとビルド手順はsourceフォルダに同梱しています。\n'
            'ソースの改変やライブラリの交換を禁止する追加条件はありません。'))
        menu = tk.Menu(root)
        menu.add_cascade(label='ヘルプ', menu=help_menu)
        root.configure(menu=menu)
        def callback_error(kind,value,trace):
            logger.error('UI callback failed',exc_info=(kind,value,trace))
            messagebox.showerror('エラー','処理中にエラーが発生しました。ローカルのログを確認してください。')
        root.report_callback_exception=callback_error
        App(root)
        if args.smoke_ui: root.after(1000,root.destroy)
        root.mainloop()


if __name__=='__main__': main()
