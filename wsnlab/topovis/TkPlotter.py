from .common import *
try:
    from Tkinter import *
except ImportError:  # could be Python3
    from tkinter import *
from . import GenericPlotter

arrowMap = { 'head' : LAST, 'tail' : FIRST, 'both' : BOTH, 'none' : NONE }

def colorStr(color):
    if color == None:
        return ''
    else:
        return '#%02x%02x%02x' % tuple(int(x*255) for x in color)

###############################################
class Plotter(GenericPlotter):
    def __init__(self, windowTitle='TopoVis', terrain_size=None, params=None):
        GenericPlotter.__init__(self, params)
        self.nodes = {}
        self.links = {}
        self.nodeLinks = {}
        self.lineStyles = {}
        self.shapes = {}
        self.windowTitle = windowTitle
        self.prepareCanvas(terrain_size)
        self.lastShownTime = 0

    ###################
    def prepareCanvas(self,terrain_size=None):
        if terrain_size is not None:
            tx,ty = terrain_size
        else:
            tx,ty = 700,700
        self.tk = Tk()
        self.tk.title(self.windowTitle)
        
        # use a PanedWindow so the user can resize the inspector
        try:
            self.mainframe = PanedWindow(self.tk, orient=HORIZONTAL)
            self.mainframe.pack(fill=BOTH, expand=YES)

            # canvas on the left
            self.canvas = Canvas(self.mainframe, width=tx, height=ty)
            self.timeText = self.canvas.create_text(0,0,text="time=0.0",anchor=NW)
            self.mainframe.add(self.canvas, minsize=200)

            # side info panel on the right - persistent inspector
            self.info_panel = Frame(self.mainframe, width=360)
            # prevent the frame from shrinking below its requested width
            try:
                self.info_panel.pack_propagate(False)
            except Exception:
                pass
            self.mainframe.add(self.info_panel, minsize=200)
            # ensure the sash is placed so the inspector is visible by default
            try:
                # force geometry update then set sash at ~70% of canvas width
                self.mainframe.update_idletasks()
                sash_x = int(tx * 0.70)
                # sash_place expects (index, x, y)
                self.mainframe.sash_place(0, sash_x, 0)
            except Exception:
                pass
        except Exception:
            # fallback to simple pack if PanedWindow is unavailable
            self.mainframe = Frame(self.tk)
            self.mainframe.pack(fill=BOTH, expand=YES)
            self.canvas = Canvas(self.mainframe, width=tx, height=ty)
            self.canvas.pack(side=LEFT, fill=BOTH, expand=YES)
            self.timeText = self.canvas.create_text(0,0,text="time=0.0",anchor=NW)
            self.info_panel = Frame(self.mainframe, width=360)
            self.info_panel.pack(side=RIGHT, fill=Y)

        # (Top inspector removed) -- Details list and Detail pane are used instead.
        # details listbox with scrollbar (shows attributes/details)
        self.neigh_label = Label(self.info_panel, text="Info:")
        self.neigh_label.pack(anchor='nw', padx=6)
        self.neigh_frame = Frame(self.info_panel)
        self.neigh_frame.pack(fill=BOTH, expand=YES, padx=6, pady=(0,6))
        self.neigh_scroll = Scrollbar(self.neigh_frame, orient=VERTICAL)
        self.neigh_list = Listbox(self.neigh_frame, yscrollcommand=self.neigh_scroll.set, height=8)
        self.neigh_scroll.config(command=self.neigh_list.yview)
        self.neigh_scroll.pack(side=RIGHT, fill=Y)
        self.neigh_list.pack(side=LEFT, fill=BOTH, expand=YES)
        
        try:
            self.neigh_list.config(bg='white', fg='black', selectbackground="#04ad09")
        except Exception:
            pass

        # double-click list entry to show details quickly
        try:
            self.neigh_list.bind('<Double-1>', lambda ev: self.show_selected_neighbor_details())
            # also on single selection change show details
            self.neigh_list.bind('<<ListboxSelect>>', lambda ev: self.show_selected_neighbor_details())
        except Exception:
            pass
        
        # button to show messages sent/received by the currently inspected node
        self.msgs_btn = Button(self.info_panel, text="Show node messages", command=lambda: self.show_node_messages())
        self.msgs_btn.pack(padx=6, pady=(0,6))

        # persistent detail area (shows full value of selected attribute)
        self.neigh_detail_label = Label(self.info_panel, text="Detail:")
        self.neigh_detail_label.pack(anchor='nw', padx=6)
        self.neigh_detail_text = Text(self.info_panel, wrap=WORD, width=40, height=16)
        self.neigh_detail_text.pack(fill=X, padx=6, pady=(0,6))
        try:
            self.neigh_detail_text.config(state=DISABLED, bg='white', fg='black')
        except Exception:
            self.neigh_detail_text.config(state=DISABLED)

    ###################
    def setTime(self, time):
        if (time - self.lastShownTime > 0.05):
            self.canvas.itemconfigure(self.timeText, text='Time: %.2fS' % time)
            self.lastShownTime = time

    ###################
    def updateNodePosAndSize(self,id):
        p = self.params
        c = self.canvas
        if id not in self.nodes.keys():
            node_tag = c.create_oval(0,0,0,0)
            label_tag = c.create_text(0,0,text=str(id))
            self.nodes[id] = (node_tag,label_tag)
            # bind left-click on both the node shape and the label to show node info
            try:
                # lambda captures id as nid default argument
                self.canvas.tag_bind(node_tag, '<Button-1>', lambda ev, nid=id: self.show_node_info(nid))
                self.canvas.tag_bind(label_tag, '<Button-1>', lambda ev, nid=id: self.show_node_info(nid))
            except Exception:
                # fail silently if binding isn't possible
                pass
        else:
            (node_tag,label_tag) = self.nodes[id]

        node = self.scene.nodes[id]
        nodesize = node.scale*p.nodesize
        x1 = node.pos[0] - nodesize
        y1 = node.pos[1] - nodesize
        (x2,y2) = (x1 + nodesize*2, y1 + nodesize*2)
        c.coords(node_tag, x1, y1, x2, y2)
        c.coords(label_tag, node.pos)

        for l in self.nodeLinks[id]:
            self.updateLink(*l)

    ###################
    def configLine(self,tagOrId,style):
        config = {}
        config['fill']  = colorStr(style.color)
        config['width'] = style.width
        config['arrow'] = arrowMap[style.arrow]
        config['dash']  = style.dash
        self.canvas.itemconfigure(tagOrId,**config)

    ###################
    def configPolygon(self,tagOrId,lineStyle,fillStyle):
        config = {}
        config['outline'] = colorStr(lineStyle.color)
        config['width']    = lineStyle.width
        config['dash']     = lineStyle.dash
        config['fill']     = colorStr(fillStyle.color)
        self.canvas.itemconfigure(tagOrId,**config)

    ###################
    def createLink(self,src,dst,style):
        if src is dst:
            raise('Source and destination are the same node')
        p = self.params
        c = self.canvas
        (x1,y1,x2,y2) = computeLinkEndPoints(
                self.scene.nodes[src],
                self.scene.nodes[dst], 
                p.nodesize)
        link_obj = c.create_line(x1, y1, x2, y2, tags='link')
        self.configLine(link_obj, self.scene.lineStyles[style])
        return link_obj

    ###################
    def updateLink(self,src,dst,style):
        p = self.params
        c = self.canvas
        link_obj = self.links[(src,dst,style)]
        (x1,y1,x2,y2) = computeLinkEndPoints(
                self.scene.nodes[src],
                self.scene.nodes[dst], 
                p.nodesize)
        c.coords(link_obj, x1, y1, x2, y2)


    ###################
    def node(self,id,x,y):
        self.nodeLinks[id] = []
        self.updateNodePosAndSize(id)
        self.tk.update()

    ###################
    def nodemove(self,id,x,y):
        self.updateNodePosAndSize(id)
        self.tk.update()

    ###################
    def nodecolor(self,id,r,g,b):
        (node_tag,label_tag) = self.nodes[id]
        self.canvas.itemconfig(node_tag, outline=colorStr((r,g,b)))
        self.canvas.itemconfigure(label_tag, fill=colorStr((r,g,b)))
        self.tk.update()

    ###################
    def show_node_info(self, node_id):
        """
        Populate the persistent inspector with attributes for node_id.
        """
        # record current inspected node for selection handlers
        self.current_inspected_node = node_id

        sim = getattr(self, 'sim', None)
        if sim is None or not hasattr(sim, 'nodes'):
            try:
                self.neigh_list.delete(0, END)
                self.neigh_detail_text.config(state=NORMAL)
                self.neigh_detail_text.delete('1.0', END)
                self.neigh_detail_text.insert(END, "(Plotter has no reference to the Simulator instance)")
                self.neigh_detail_text.config(state=DISABLED)
            except Exception:
                pass
            return

        try:
            node = sim.nodes[node_id]
            keys = ['id', 'pos', 'addr', 'ch_addr', 'parent_gui', 'root_addr', 'role', 'hop_count', 'arrival', 'tx_range', 'default_gateway']

            # populate the details listbox with node attribute summaries
            self.neigh_list.delete(0, END)
            # common attributes
            for k in keys:
                if hasattr(node, k):
                    val = getattr(node, k)
                    preview = repr(val)
                    if len(preview) > 80:
                        preview = preview[:77] + '...'
                    self.neigh_list.insert(END, f"{k}: {preview}")

            # other tables summarized as additional entries
            if hasattr(node, 'neighbors_table'):
                try:
                    self.neigh_list.insert(END, f"neighbors_table: {len(node.neighbors_table)} entries")
                except Exception:
                    self.neigh_list.insert(END, f"neighbors_table: {type(node.neighbors_table)}")
            if hasattr(node, 'candidate_parents_table'):
                self.neigh_list.insert(END, f"candidate_parents_table: {len(node.candidate_parents_table)} entries")
            if hasattr(node, 'child_networks_table'):
                try:
                    self.neigh_list.insert(END, f"child_networks_table: {len(node.child_networks_table)} entries")
                except Exception:
                    self.neigh_list.insert(END, f"child_networks_table: {type(node.child_networks_table)}")
            if hasattr(node, 'members_table'):
                self.neigh_list.insert(END, f"members_table: {len(node.members_table)} entries")
            if hasattr(node, 'cluster_id'):
                try:
                    self.neigh_list.insert(END, f"cluster_id (available ids): {sorted(list(node.cluster_id))}")
                except Exception:
                    self.neigh_list.insert(END, f"cluster_id: {node.cluster_id}")
        except Exception as e:
            try:
                self.neigh_list.delete(0, END)
                self.neigh_detail_text.config(state=NORMAL)
                self.neigh_detail_text.delete('1.0', END)
                self.neigh_detail_text.insert(END, f"Error reading sim.nodes[{node_id}]: {e}")
                self.neigh_detail_text.config(state=DISABLED)
            except Exception:
                pass

    def show_selected_neighbor_details(self):
        """Show the selected neighbor's stored heartbeat packet (if available) in the inspector or a popup."""
        sel = self.neigh_list.curselection()
        if not sel:
            return
        # the list entries are 'key: preview' or summary entries like 'neighbors_table: N entries'
        entry = self.neigh_list.get(sel[0])
        try:
            key = entry.split(':', 1)[0]
            key = key.strip()
        except Exception:
            return
        # use stored current inspected node id
        cur_id = getattr(self, 'current_inspected_node', None)

        sim = getattr(self, 'sim', None)
        if sim is None or cur_id is None:
            return

        try:
            node = sim.nodes[cur_id]
            # populate the persistent detail pane based on selected attribute key
            detail_lines = []
            detail_lines.append(f"Attribute '{key}' (from node {cur_id}):")
            try:
                if hasattr(node, key):
                    val = getattr(node, key)
                    # pretty print containers
                    if isinstance(val, dict):
                        if not val:
                            detail_lines.append("(empty dict)")
                        else:
                            for kk, vv in val.items():
                                detail_lines.append(f"{kk}: {vv}")
                    elif isinstance(val, (list, tuple, set)):
                        if not val:
                            detail_lines.append(f"(empty {type(val).__name__})")
                        else:
                            for i, vv in enumerate(val):
                                detail_lines.append(f"[{i}] {vv}")
                    else:
                        detail_lines.append(repr(val))
                else:
                    # fallback: maybe this was a computed summary (e.g., 'neighbors_table: N entries')
                    entry_val = entry.split(':',1)[1].strip() if ':' in entry else ''
                    detail_lines.append(entry_val)
            except Exception as e:
                detail_lines.append(f"Error reading attribute: {e}")

            # write into the neigh_detail_text widget
            try:
                self.neigh_detail_text.config(state=NORMAL)
                self.neigh_detail_text.delete('1.0', END)
                self.neigh_detail_text.insert(END, '\n'.join(str(l) for l in detail_lines))
                self.neigh_detail_text.config(state=DISABLED)
            except Exception:
                # fallback: print to console
                print('\n'.join(detail_lines))
        except Exception as e:
            print(f"Error showing neighbor details: {e}")

    ###################
    def show_node_messages(self):
        """Display sent and received messages for the currently inspected node in the neighbor-detail pane."""
        # use stored current inspected node id
        cur_id = getattr(self, 'current_inspected_node', None)

        sim = getattr(self, 'sim', None)
        if sim is None or cur_id is None:
            return

        try:
            node = sim.nodes[cur_id]
            sent = getattr(node, '_sent_messages', []) or []
            recv = getattr(node, '_received_messages', []) or []

            # merge lists and sort by timestamp
            merged = []
            for t, p in sent:
                merged.append((t, 'sent', p))
            for t, p in recv:
                merged.append((t, 'recv', p))

            merged.sort(key=lambda x: x[0])

            lines = []
            lines.append(f"Chronological message history for node {cur_id}:")
            if not merged:
                lines.append("(no messages)")
            else:
                for t, direction, p in merged:
                    if direction == 'sent':
                        lines.append(f"[{t:.6f}] -> {p}")
                    else:
                        lines.append(f"[{t:.6f}] <- {p}")

            try:
                self.neigh_detail_text.config(state=NORMAL)
                self.neigh_detail_text.delete('1.0', END)
                self.neigh_detail_text.insert(END, '\n'.join(str(l) for l in lines))
                self.neigh_detail_text.config(state=DISABLED)
            except Exception:
                # fallback: print to console
                print('\n'.join(lines))
        except Exception as e:
            print(f"Error showing node messages: {e}")

    ###################
    def nodewidth(self,id,width):
        (node_tag,label_tag) = self.nodes[id]
        self.canvas.itemconfig(node_tag, width=width)
        self.tk.update()

    ###################
    def nodescale(self,id,scale):
        # scale attribute has been set by TopoVis
        # just update the node
        self.updateNodePosAndSize(id)
        self.tk.update()

    ###################
    def nodelabel(self,id,label):
        (node_tag,label_tag) = self.nodes[id]
        self.canvas.itemconfigure(label_tag, text=self.scene.nodes[id].label)
        self.tk.update()

    ###################
    def addlink(self,src,dst,style):
        self.nodeLinks[src].append((src,dst,style))
        self.nodeLinks[dst].append((src,dst,style))
        self.links[(src,dst,style)] = self.createLink(src, dst, style)
        self.tk.update()

    ###################
    def dellink(self,src,dst,style):
        self.nodeLinks[src].remove((src,dst,style))
        self.nodeLinks[dst].remove((src,dst,style))
        self.canvas.delete(self.links[(src,dst,style)])
        del self.links[(src,dst,style)]
        self.tk.update()

    ###################
    def clearlinks(self):
        self.canvas.delete('link')
        self.links.clear()
        for n in self.nodes.keys():
            self.nodeLinks[n] = []
        self.tk.update()

    ###################
    def circle(self,x,y,r,id,linestyle,fillstyle):
        if id in self.shapes.keys():
            self.canvas.delete(self.shapes[id])
            del self.shapes[id]
        self.shapes[id] = self.canvas.create_oval(x-r,y-r,x+r,y+r)
        self.configPolygon(self.shapes[id], linestyle, fillstyle)
        self.tk.update()

    ###################
    def line(self,x1,y1,x2,y2,id,linestyle):
        if id in self.shapes.keys():
            self.canvas.delete(self.shapes[id])
            del self.shapes[id]
        self.shapes[id] = self.canvas.create_line(x1,y1,x2,y2)
        self.configLine(self.shapes[id], linestyle)
        self.tk.update()

    ###################
    def rect(self,x1,y1,x2,y2,id,linestyle,fillstyle):
        if id in self.shapes.keys():
            self.canvas.delete(self.shapes[id])
            del self.shapes[id]
        self.shapes[id] = self.canvas.create_rectangle(x1,y1,x2,y2)
        self.configPolygon(self.shapes[id], linestyle, fillstyle)
        self.tk.update()

    ###################
    def delshape(self,id):
        if id in self.shapes.keys():
            self.canvas.delete(self.shapes[id])
            self.tk.update()

    ###################
    def on_node_click(self, node_id):
        """
        Show a small popup window with selected node's key attributes.
        Attempts to read the simulation node object from self.sim.nodes.
        """
        # gather info lines
        info_lines = []
        info_lines.append(f"Node id: {node_id}")
        sim = getattr(self, 'sim', None)
        if sim is not None and hasattr(sim, 'nodes'):
            try:
                node = sim.nodes[node_id]
                # list of common attributes to display (best-effort)
                keys = ['id', 'pos', 'addr', 'ch_addr', 'parent_gui', 'root_addr', 'role', 'hop_count', 'arrival', 'tx_range', 'default_gateway']
                for k in keys:
                    if hasattr(node, k):
                        info_lines.append(f"{k}: {getattr(node, k)}")

                # neighbors and some tables - summarize lengths to avoid huge dumps
                if hasattr(node, 'neighbors_table'):
                    try:
                        info_lines.append(f"neighbors_table: {len(node.neighbors_table)} entries")
                    except Exception:
                        info_lines.append(f"neighbors_table: {type(node.neighbors_table)}")
                if hasattr(node, 'candidate_parents_table'):
                    info_lines.append(f"candidate_parents_table: {len(node.candidate_parents_table)} entries")
                if hasattr(node, 'child_networks_table'):
                    try:
                        info_lines.append(f"child_networks_table: {len(node.child_networks_table)} entries")
                    except Exception:
                        info_lines.append(f"child_networks_table: {type(node.child_networks_table)}")
                if hasattr(node, 'members_table'):
                    info_lines.append(f"members_table: {len(node.members_table)} entries")
                if hasattr(node, 'cluster_id'):
                    try:
                        info_lines.append(f"cluster_id (available ids): {sorted(list(node.cluster_id))}")
                    except Exception:
                        info_lines.append(f"cluster_id: {node.cluster_id}")
            except Exception as e:
                info_lines.append(f"Error reading sim.nodes[{node_id}]: {e}")
        else:
            info_lines.append("(Plotter has no reference to the Simulator instance)")

        # create popup window
        try:
            popup = Toplevel(self.tk)
            popup.title(f"Node {node_id} info")
            text = Text(popup, wrap=WORD, width=60, height=20)
            text.pack(fill=BOTH, expand=YES)
            text.insert(END, '\n'.join(str(l) for l in info_lines))
            text.config(state=DISABLED)
        except Exception:
            # fallback: print to console
            print('\n'.join(info_lines))
