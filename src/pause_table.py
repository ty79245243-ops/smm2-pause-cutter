"""A virtualized, pixel-scrolling Tk table with real controls in its cells."""
import math
import time
import tkinter as tk
from tkinter import ttk

ROW_HEIGHT = 56
HEADER_HEIGHT = 42
HEADER_BG = '#d6e3f3'
HEADER_LINE = '#8096b1'
GRID_LINE = '#c2cede'
ROW_COLORS = ('#eef3f9','#e5edf6')
SELECTED_BG = '#9dc5f2'
TEXT = '#24364d'


class Row:
    def __init__(self,table,index):
        self.table=table; self.index=index; self.width=0; self.selected=None
        self.canvas=tk.Canvas(table.body,height=ROW_HEIGHT,highlightthickness=0,bd=0)
        self.window=table.body.create_window(0,0,window=self.canvas,anchor='nw')
        self.plan_value=tk.BooleanVar(value=False)
        self.plan=tk.Checkbutton(self.canvas,variable=self.plan_value,font=('Yu Gothic UI',10,'bold'),
            cursor='hand2',selectcolor='white',bd=0,highlightthickness=0,
            command=lambda:table.act('toggle',index),takefocus=True)
        self.fields={};self.field_values={}
        for key in ('start','end'):
            value=tk.StringVar();self.field_values[key]=value
            e=tk.Entry(self.canvas,textvariable=value,justify='center',font=('Yu Gothic UI',11),
                bg='white',fg=TEXT,disabledbackground='white',disabledforeground='#8491a2',
                relief='flat',bd=0,highlightthickness=1,highlightbackground='#a1b3c9',highlightcolor='#3679c8')
            e.bind('<FocusIn>',lambda event,key=key,e=e:table.on_edit_focus(index,key,e))
            e.bind('<FocusOut>',lambda event:table.before_action())
            e.bind('<Return>',lambda event:table.commit_event())
            e.bind('<Escape>',lambda event:table.escape_event())
            self.fields[key]=e
        self.seconds=tk.Label(self.canvas,font=('Yu Gothic UI',10),fg='#55667d')
        self.note=tk.Label(self.canvas,font=('Yu Gothic UI',10),fg=TEXT,anchor='w',justify='left')
        self.reset=tk.Button(self.canvas,text='リセット',font=('Yu Gothic UI',9),cursor='hand2',
            bg='#f6f8fc',fg='#405b7c',activebackground='#d8e5f5',activeforeground=TEXT,
            relief='raised',bd=1,command=lambda:table.act('reset',index),takefocus=True)
        for value in self.field_values.values():
            value.trace_add('write',lambda *args:self.update_reset())
        for widget in (self.canvas,self.seconds,self.note):
            widget.bind('<Button-1>',lambda event:table.select(index))
        # No bind_all: wheel routing is limited to this table and its controls.
        for widget in (self.canvas,self.plan,self.seconds,self.note,self.reset,*self.fields.values()):
            widget.bind('<MouseWheel>',table.wheel)
            widget.bind('<Button-4>',lambda e:table.scroll_pixels(-90))
            widget.bind('<Button-5>',lambda e:table.scroll_pixels(90))
        self.sync()

    def sync(self):
        c=self.table.rows[self.index]; busy=self.table.busy
        self.plan_value.set(c.enabled)
        self.plan.configure(text='カット予定' if c.enabled else 'カットしない',
            fg=TEXT,activeforeground=TEXT,state='disabled' if busy else 'normal')
        for key,e in self.fields.items():
            value=str(c.start+1 if key=='start' else c.end)
            e.configure(state='normal')
            if e.get()!=value: e.delete(0,'end');e.insert(0,value)
            e.configure(state='disabled' if busy else 'normal')
        self.seconds.configure(text=f'{(c.end-c.start)/self.table.fps:.3f}')
        self.note.configure(text=c.note)
        self.update_reset()
        self.layout(self.table.body.winfo_width(),force=True)

    def update_reset(self):
        enabled=not self.table.busy and self.table.reset_needed(self.index)
        self.reset.configure(state='normal' if enabled else 'disabled',
            bg='#326bad' if enabled else '#f6f8fc',fg='white' if enabled else '#405b7c',
            activebackground='#25588f',activeforeground='white',
            disabledforeground='#98a3b2',cursor='hand2' if enabled else 'arrow')

    def layout(self,width,force=False):
        selected=self.table.selected_index==self.index
        if not force and width==self.width and selected==self.selected:return
        self.width=width;self.selected=selected
        bg=SELECTED_BG if selected else ROW_COLORS[self.table.positions[self.index]%2]
        self.canvas.configure(width=width,bg=bg)
        self.seconds.configure(bg=bg);self.note.configure(bg=bg)
        self.plan.configure(bg=bg,activebackground=bg)
        self.canvas.delete('grid')
        bounds=self.table.column_bounds(width)
        for x in bounds:self.canvas.create_line(x,0,x,ROW_HEIGHT,fill=GRID_LINE,width=1,tags='grid')
        self.canvas.create_line(0,ROW_HEIGHT-1,width,ROW_HEIGHT-1,fill=GRID_LINE,width=1,tags='grid')
        if selected:self.canvas.create_line(2,0,2,ROW_HEIGHT,fill='#326bad',width=3,tags='grid')
        for j,key in enumerate(self.table.keys):
            x,X=bounds[j:j+2];w=X-x
            if key=='plan':self.plan.place(x=x+10,y=11,width=w-20,height=33)
            elif key in ('start','end'):
                field_width=min(76,w-24)
                self.fields[key].place(x=x+(w-field_width)//2,y=13,width=field_width,height=30)
            elif key=='seconds':self.seconds.place(x=x+4,y=10,width=w-8,height=36)
            elif key=='note':
                self.note.configure(wraplength=max(60,w-20))
                self.note.place(x=x+10,y=5,width=w-20,height=46)
            elif key=='reset':self.reset.place(x=x+10,y=12,width=w-20,height=31)

    def destroy(self):
        self.table.body.delete(self.window);self.canvas.destroy()


class PauseTable(tk.Frame):
    keys=('plan','start','end','seconds','note','reset')
    titles=('カット予定','削除開始','削除終了','削除秒数','判定','操作')
    def __init__(self,parent,*,on_select,on_toggle,on_reset,on_edit_focus,
                 before_action,on_commit,on_escape,reset_needed=lambda i:True):
        super().__init__(parent,bg=HEADER_LINE,highlightthickness=1,highlightbackground=HEADER_LINE)
        self.rows=[];self.indices=[];self.positions={};self.fps=60;self.busy=False;self.selected_index=None
        self.on_select=on_select;self.on_toggle=on_toggle;self.on_reset=on_reset
        self.on_edit_focus=on_edit_focus;self.before_action=before_action
        self.on_commit=on_commit;self.on_escape=on_escape;self.reset_needed=reset_needed
        self.offset=0.0;self.target_offset=0.0;self.animation=None;self.last_tick=0
        self.visible={}
        self.columnconfigure(0,weight=1);self.rowconfigure(1,weight=1)
        self.header=tk.Canvas(self,height=HEADER_HEIGHT,bg=HEADER_BG,highlightthickness=0,bd=0)
        self.header.grid(row=0,column=0,sticky='ew')
        tk.Frame(self,bg=HEADER_BG,width=17).grid(row=0,column=1,sticky='nsew')
        self.body=tk.Canvas(self,height=ROW_HEIGHT*6,bg=ROW_COLORS[0],highlightthickness=0,bd=0,takefocus=True)
        self.body.grid(row=1,column=0,sticky='nsew')
        self.scrollbar=ttk.Scrollbar(self,orient='vertical',command=self.scroll_command)
        self.scrollbar.grid(row=1,column=1,sticky='ns')
        self.body.bind('<Configure>',self.resize)
        self.body.bind('<MouseWheel>',self.wheel)
        self.header.bind('<MouseWheel>',self.wheel)
        self.body.bind('<Button-4>',lambda e:self.scroll_pixels(-90))
        self.body.bind('<Button-5>',lambda e:self.scroll_pixels(90))
        self.body.bind('<Down>',lambda e:self.scroll_pixels(ROW_HEIGHT))
        self.body.bind('<Up>',lambda e:self.scroll_pixels(-ROW_HEIGHT))
        self.body.bind('<Next>',lambda e:self.scroll_pixels(self.body.winfo_height()*.85))
        self.body.bind('<Prior>',lambda e:self.scroll_pixels(-self.body.winfo_height()*.85))
        self.bind('<Destroy>',self.destroy_event)

    @staticmethod
    def column_bounds(width):
        widths=[136,98,98,92,max(140,width-520),96]
        bounds=[0]
        for w in widths:bounds.append(bounds[-1]+w)
        return bounds

    @property
    def max_offset(self):return max(0,len(self.indices)*ROW_HEIGHT-self.body.winfo_height())

    def resize(self,event=None):
        self.offset=min(self.offset,self.max_offset);self.target_offset=min(self.target_offset,self.max_offset)
        self.draw_header();self.render()

    def draw_header(self):
        width=self.body.winfo_width();bounds=self.column_bounds(width)
        self.header.delete('all')
        self.header.create_rectangle(0,0,width,HEADER_HEIGHT,fill=HEADER_BG,outline=HEADER_LINE,width=3)
        for x in bounds[1:-1]:self.header.create_line(x,0,x,HEADER_HEIGHT,fill=HEADER_LINE,width=3)
        self.header.create_line(0,HEADER_HEIGHT-2,width,HEADER_HEIGHT-2,fill=HEADER_LINE,width=3)
        for j,title in enumerate(self.titles):
            x,X=bounds[j:j+2]
            self.header.create_text((x+X)/2,HEADER_HEIGHT/2,text=title,fill=TEXT,font=('Yu Gothic UI',10,'bold'))

    def set_rows(self,rows,fps=60):
        self.stop_animation()
        for row in self.visible.values():row.destroy()
        self.visible.clear();self.rows=rows;self.indices=list(range(len(rows)));self.positions={i:i for i in self.indices};self.fps=fps;self.selected_index=None
        self.offset=self.target_offset=0.0;self.render()

    def set_filter(self,indices):
        self.stop_animation()
        for row in self.visible.values():row.destroy()
        self.visible.clear();self.indices=list(indices)
        self.positions={i:position for position,i in enumerate(self.indices)}
        self.selected_index=None;self.offset=self.target_offset=0.0;self.render()

    def set_busy(self,busy):
        self.busy=busy
        for row in self.visible.values():row.sync()

    def refresh_row(self,index):
        if index in self.visible:self.visible[index].sync()

    def select(self,index,notify=True):
        if self.busy or index not in self.positions:return
        if not self.before_action():return
        old=self.selected_index;self.selected_index=index
        for i in (old,index):
            if i in self.visible:self.visible[i].layout(self.body.winfo_width(),force=True)
        if notify and old!=index:self.on_select(index)

    def act(self,action,index):
        if self.busy:return
        if action=='reset':self.on_escape()
        if not self.before_action():return
        self.select(index,notify=False)
        (self.on_toggle if action=='toggle' else self.on_reset)(index)

    def focus_entry(self,index,key):
        if index not in self.visible:
            self.jump_to(self.positions[index]*ROW_HEIGHT)
        e=self.visible[index].fields[key]
        e.focus_set();e.selection_range(0,'end')
        self.on_edit_focus(index,key,e)

    def commit_event(self):
        self.on_commit();self.body.focus_set();return 'break'

    def escape_event(self):
        self.on_escape();self.body.focus_set();return 'break'

    def wheel(self,event):
        # Fractional deltas from high-resolution wheels/trackpads are retained.
        return self.scroll_pixels(-float(event.delta)/120.0*90.0)

    def scroll_pixels(self,pixels):
        if not self.before_action():return 'break'
        self.body.focus_set()
        self.target_offset=max(0.0,min(self.max_offset,self.target_offset+pixels))
        if self.animation is None:
            self.last_tick=time.perf_counter();self.animation=self.after(16,self.tick)
        return 'break'

    def tick(self):
        self.animation=None;now=time.perf_counter();dt=min(.1,max(.001,now-self.last_tick));self.last_tick=now
        remaining=self.target_offset-self.offset
        if abs(remaining)<.3:
            self.offset=self.target_offset;self.render();return
        self.offset+=remaining*(1-math.exp(-24*dt))
        self.render();self.animation=self.after(16,self.tick)

    def jump_to(self,pixels):
        self.stop_animation();self.offset=self.target_offset=max(0.0,min(self.max_offset,pixels));self.render()

    def scroll_command(self,*args):
        if not self.before_action():return
        self.body.focus_set()
        if args[0]=='moveto':self.jump_to(float(args[1])*len(self.indices)*ROW_HEIGHT)
        else:
            step=ROW_HEIGHT if args[2]=='units' else self.body.winfo_height()*.85
            self.scroll_pixels(int(args[1])*step)

    def render(self):
        height=self.body.winfo_height();width=self.body.winfo_width()
        first=max(0,int(self.offset//ROW_HEIGHT)-1)
        last=min(len(self.indices),math.ceil((self.offset+height)/ROW_HEIGHT)+1)
        wanted=set(self.indices[first:last])
        self.body.delete("empty")
        if not self.indices:
            self.body.create_text(width/2,max(30,height/2),text="該当する区間はありません",fill=TEXT,font=("Yu Gothic UI",11),tags="empty")
        for i in list(self.visible):
            if i not in wanted:self.visible.pop(i).destroy()
        for i in sorted(wanted):
            if i not in self.visible:self.visible[i]=Row(self,i)
            row=self.visible[i]
            self.body.coords(row.window,0,self.positions[i]*ROW_HEIGHT-self.offset)
            self.body.itemconfigure(row.window,width=width,height=ROW_HEIGHT)
            row.layout(width)
        total=max(1,len(self.indices)*ROW_HEIGHT)
        self.scrollbar.set(self.offset/total,min(1,(self.offset+height)/total))

    def stop_animation(self):
        if self.animation is not None:
            self.after_cancel(self.animation);self.animation=None

    def destroy_event(self,event):
        if event.widget is self:self.stop_animation()
