import random
from enum import Enum
import sys
sys.path.insert(1, '.')
from source import wsnlab_vis as wsn
import math
from source import config
from collections import Counter
import csv


import csv  # <— add this near your other imports

# Track where each node is placed
NODE_POS = {}  # {node_id: (x, y)}

# --- tracking containers ---
ALL_NODES = []              # node objects
CLUSTER_HEADS = []
ROLE_COUNTS = Counter()     # live tally per Roles enum
DATA_PACKET_TRACES = []     # traces for data packet routing
LOG_ENTRIES = []            # all log messages from nodes


def _addr_str(a): return "" if a is None else str(a)
def _role_name(r): return r.name if hasattr(r, "name") else str(r)

def log_data_packet_trace(event_type, node_id, node_addr, packet_id, source, dest, data_value, timestamp, next_hop=None, routing_option=None, previous_hop=None):
    """Log a data packet trace event.
    
    Args:
        event_type: 'SEND', 'ROUTE', 'RECEIVE', 'DROP'
        node_id: GUI of the node
        node_addr: Address of the node
        packet_id: Unique packet identifier
        source: Source address of the packet
        dest: Destination address of the packet
        data_value: Data payload value
        timestamp: Simulation time
        next_hop: Next hop address (for routing)
        routing_option: Routing method used
        previous_hop: Previous hop node ID
    """
    DATA_PACKET_TRACES.append({
        'event_type': event_type,
        'timestamp': timestamp,
        'node_id': node_id,
        'node_addr': _addr_str(node_addr),
        'packet_id': packet_id,
        'source': _addr_str(source),
        'dest': _addr_str(dest),
        'data_value': data_value,
        'next_hop': _addr_str(next_hop) if next_hop else '',
        'routing_option': routing_option or '',
        'previous_hop': previous_hop if previous_hop is not None else ''
    })


Roles = Enum('Roles', 'UNDISCOVERED UNREGISTERED ROOT REGISTERED CLUSTER_HEAD ROUTER')
"""Enumeration of roles"""

###########################################################
class SensorNode(wsn.Node):
    """SensorNode class is inherited from Node class in wsnlab.py.
    It will run data collection tree construction algorithms.

    Attributes:
        role (Roles): role of node
        is_root_eligible (bool): keeps eligibility to be root
        c_probe (int): probe message counter
        th_probe (int): probe message threshold
        neighbors_table (Dict): keeps the neighbor information with received heart beat messages
    """

    ###################
    def init(self):
        """Initialization of node. Setting all attributes of node.
        At the beginning node needs to be sleeping and its role should be UNDISCOVERED.

        Args:

        Returns:

        """
        self.scene.nodecolor(self.id, 1, 1, 1) # sets self color to white
        self.sleep()
        self.addr = None
        self.ch_addr = None
        self.parent_gui = None
        self.root_addr = None
        self.set_role(Roles.UNDISCOVERED)
        self.is_root_eligible = True if self.id == ROOT_ID else False
        self.c_probe = 0  # c means counter and probe is the name of counter
        self.c_heart_beat = 0  # c means counter and heart_beat is the name of counter
        self.th_probe = 10  # th means threshold and probe is the name of threshold
        self.c_join_request = 0  # c means counter and join_request is the name of counter
        self.hop_count = 99999
        self.neighbor_hop = 0
        self.neighbors_table = {}  # keeps neighbor information with received HB messages
        self.candidate_parents_table = []
        self.child_networks_table = {}
        self.members_table = []
        self.received_JR_guis = []  # keeps received Join Request global unique ids
        self.cluster_id = set(range(2,config.NODE_MAX_CHILD+2))
        self.child_id = set(range(1,config.NODE_MAX_CHILD+2))
        self.addr_to_net = {}
        self.net_to_addr = {}
        self.default_gateway = None  # Addr of default gateway (if any)
        self.default_gateway2 = None # Addr of doward gateway (for Router)
        self.join_time = 0
        self.parent_is_cluster_head = False
        self.tx_power_levels = config.NODE_TX_POWER_LEVELS[1]
        # Packet deduplication
        self.seen_packets = set()  # Track (source, packet_id) tuples to prevent duplicates
        self.packet_counter = 0  # Counter for generating unique packet IDs
        self.max_seen_packets = 1000  # Maximum size of seen_packets cache
    
    def log(self, message):
        """Override log method to capture all log messages to CSV."""
        # Call parent class log method
        super().log(message)
        # Capture log entry
        LOG_ENTRIES.append({
            'timestamp': self.now,
            'node_id': self.id,
            'node_addr': _addr_str(self.addr),
            'node_role': _role_name(self.role) if hasattr(self, 'role') else '',
            'message': str(message)
        })
    
    # Keep track of assigned Network IDs and Child IDs
    def add_network(self, pck):

        addr = pck['source']
        addr_key = (addr.net_addr, addr.node_addr)
        
        if addr_key in self.addr_to_net:
            new_net_id = self.addr_to_net[addr_key]
            return new_net_id
        if not self.cluster_id:
            return None
        
        new_net_id = min(self.cluster_id)
        self.cluster_id.remove(new_net_id)

        self.addr_to_net[addr_key] = new_net_id
        self.net_to_addr[new_net_id] = addr_key

        return new_net_id

    def remove_network(self, pck):
        net_id = pck['source']
        if net_id not in self.net_to_addr:
            return None
        addr_key = self.net_to_addr[net_id]
        self.cluster_id.add(net_id)
        del self.net_to_addr[net_id]
        del self.addr_to_net[addr_key]

    def add_child(self):

        if not self.child_id:
            return None
        new_child_id = min(self.child_id)
        self.child_id.remove(new_child_id)
        return new_child_id
    
    def remove_child(self, child_id):
        self.child_id.add(child_id)


    def export_to_csv(filename, data, header=None):
        with open(filename, mode="w", newline="", encoding="utf-8")as file:
            writer = csv.writer(file)

        if header:
            writer.writerow(header)
        writer.writerows(data)

        print(f"CSV file '{filename}' saved successfully")
    ###################
    def run(self):
        """Setting the arrival timer to wake up after firing.

        Args:

        Returns:

        """
        self.set_timer('TIMER_ARRIVAL', self.arrival)

    ###################

    def set_role(self, new_role, *, recolor=True):
        """Central place to switch roles, keep tallies, and (optionally) recolor."""
        old_role = getattr(self, "role", None)
        # If leaving cluster head role, kill TX power check timer
        if old_role == Roles.CLUSTER_HEAD and new_role != Roles.CLUSTER_HEAD:
            try:
                self.kill_timer('TIMER_TX_POWER_CHECK')
            except Exception:
                pass
        if old_role is not None:
            ROLE_COUNTS[old_role] -= 1
            if ROLE_COUNTS[old_role] <= 0:
                ROLE_COUNTS.pop(old_role, None)
        ROLE_COUNTS[new_role] += 1
        self.role = new_role

        if recolor:
            if new_role == Roles.UNDISCOVERED:
                self.scene.nodecolor(self.id, 1, 1, 1)
            elif new_role == Roles.UNREGISTERED:
                self.scene.nodecolor(self.id, 1, 1, 0)
            elif new_role == Roles.REGISTERED:
                self.scene.nodecolor(self.id, 0, 1, 0)
            elif new_role == Roles.CLUSTER_HEAD:
                self.scene.nodecolor(self.id, 0, 0, 1)
                self.draw_tx_range()
                # Schedule periodic TX power adaptation
                try:
                    self.set_timer('TIMER_TX_POWER_CHECK', config.CLUSTER_HEAD_TX_POWER_CHECK_INTERVAL)
                except Exception:
                    self.log('Failed to set TIMER_TX_POWER_CHECK')
            elif new_role == Roles.ROOT:
                self.scene.nodecolor(self.id, 0, 0, 0)
                self.set_timer('TIMER_EXPORT_CH_CSV', config.EXPORT_CH_CSV_INTERVAL)
                self.set_timer('TIMER_EXPORT_NEIGHBOR_CSV', config.EXPORT_NEIGHBOR_CSV_INTERVAL)
            elif new_role == Roles.ROUTER:
                self.scene.nodecolor(self.id, 0, 1, 1)
                self.remove_tx_range()
    ###################


    
    def become_unregistered(self):
        if self.role != Roles.UNDISCOVERED:
            self.kill_all_timers()
            self.log('I became UNREGISTERED')
        self.scene.nodecolor(self.id, 1, 1, 0)
        self.erase_parent()
        self.addr = None
        self.ch_addr = None
        self.parent_gui = None
        self.root_addr = None
        self.set_role(Roles.UNREGISTERED)
        self.c_probe = 0
        self.th_probe = 10
        self.hop_count = 99999
        self.neighbors_table = {}
        self.candidate_parents_table = []
        self.child_networks_table = {}
        self.members_table = []
        self.received_JR_guis = []  # keeps received Join Request global unique ids
        self.send_probe()
        self.set_timer('TIMER_JOIN_REQUEST', 20)


    ###################
    def update_neighbor(self, pck):
        pck['arrival_time'] = self.now
        # compute Euclidean distance between self and neighbor
        if pck['gui'] in NODE_POS and self.id in NODE_POS:
            x1, y1 = NODE_POS[self.id]
            x2, y2 = NODE_POS[pck['gui']]
            pck['distance'] = math.hypot(x1 - x2, y1 - y2)
        gui = pck['gui']

        # Ensure the neighbors_table entry exists and store requested fields
        entry = self.neighbors_table.get(gui, {})
        if pck['type'] == 'HEART_BEAT':
            # Store ch_addr and addr explicitly under the neighbor GUI key
            entry['ch_addr'] = pck.get('ch_addr')
            entry['addr'] = pck.get('addr')
            # Direct neighbor: hop is 1
            entry['neighbor_hop'] = 1
            entry['next_hop'] = pck.get('source')
            entry['role'] = pck.get('role')
            entry['distance'] = pck.get('distance')
            entry['arrival_time'] = pck.get('arrival_time')
            entry['source'] = pck.get('source')
            entry['gui'] = gui
            entry['hop_count'] = pck.get('hop_count')
            entry['from_pck'] = pck.get('type')
            entry['power_levels'] = pck.get('power_levels')
            self.neighbors_table[gui] = entry


        elif pck['type'] in ['NEIGHBOR_REQUEST', 'NEIGHBOR_REPLY']:
            # Merge neighbor tables from remote node, incrementing hop
            remote_table = pck.get('data', {}) or {}
            for remote_gui, remote_entry in remote_table.items():
                if remote_gui == self.id:
                    continue  # Do not add self to own neighbor table
                if not isinstance(remote_entry, dict):
                    continue
                remote_hop = remote_entry.get('neighbor_hop', remote_entry.get('hop_count', 0))
                new_hop = (remote_hop or 0) + 1
                # Only keep if within hop limit
                if new_hop > getattr(config, 'NEIGHBOR_TABLE_HOP', 2):
                    continue
                local = self.neighbors_table.get(remote_gui, {})
                local_hop = local.get('neighbor_hop', local.get('hop_count', 99999))
                if new_hop < local_hop or pck['arrival_time'] > local.get('arrival_time'):
                    merged = {
                        'ch_addr': remote_entry.get('ch_addr'),
                        'addr': remote_entry.get('addr'),
                        'next_hop': pck.get('source'),
                        'neighbor_hop': new_hop,
                        'role': remote_entry.get('role'),
                        'distance':  (pck.get('distance') + remote_entry.get('distance')),
                        'arrival_time': remote_entry.get('arrival_time'),
                        'source': remote_entry.get('source'),
                        'gui': remote_gui,
                        'power_levels': remote_entry.get('power_levels'),
                        'from_pck': pck.get('type')
                    }
                    self.neighbors_table[remote_gui] = merged

        # Always update candidate parents if new
        if pck.get('role') != Roles.ROUTER:
            if gui not in self.child_networks_table.keys() or gui not in self.members_table:
                if gui not in self.candidate_parents_table:
                    self.candidate_parents_table.append(gui)

    ###################
    def select_and_join(self):
        # Prefer candidates that are already cluster heads; if none, fall back to all candidates
        candidates = list(self.candidate_parents_table)
        ch_candidates = [g for g in candidates if self.neighbors_table.get(g, {}).get('role') == Roles.CLUSTER_HEAD]
        search_list = ch_candidates if ch_candidates else candidates

        min_hop = 99999
        min_hop_gui = 99999
        for gui in search_list:
            nb = self.neighbors_table.get(gui)
            if not nb:
                continue
            hop_count = nb.get('hop_count', 99999)
            if hop_count < min_hop or (hop_count == min_hop and gui < min_hop_gui):
                min_hop = hop_count
                min_hop_gui = gui
        # If no valid candidate was found, bail out
        if min_hop_gui == 99999:
            self.log(f"select_and_join: no valid candidate in {self.candidate_parents_table}")
            return

        # derive the effective source address: prefer ch_addr if present, else addr
        nb_entry = self.neighbors_table.get(min_hop_gui, {})
        selected_addr = nb_entry.get('ch_addr') if nb_entry.get('ch_addr') is not None else nb_entry.get('addr')
        if self.c_join_request < 3:
            self.send_join_request(selected_addr)
            self.c_join_request += 1
            self.set_timer('TIMER_JOIN_REQUEST', 5)
        else:
            if min_hop_gui in self.candidate_parents_table:
                self.candidate_parents_table.remove(min_hop_gui)
            else:
                self.log(f"Warning: tried to remove min_hop_gui {min_hop_gui} but it was not in candidate_parents_table: {self.candidate_parents_table}")
            self.c_join_request = 0
            self.set_timer('TIMER_JOIN_REQUEST', 5)

    ###################
    def send_probe(self):
        """Sending probe message to be discovered and registered.

        Args:

        Returns:

        """
        if self.role == Roles.UNDISCOVERED or self.role == Roles.UNREGISTERED:
            self.send({'dest': wsn.BROADCAST_ADDR, 'type': 'PROBE','source': self.ch_addr if self.ch_addr is not None else self.addr,
                       'gui': self.id,
                       'role': self.role,
                       'addr': self.addr,
                       'ch_addr': self.ch_addr,
                       'hop_count': self.hop_count,
                       'send_time': self.now})
        else:
            self.send({'dest': wsn.BROADCAST_ADDR, 'type': 'PROBE', 'source': self.ch_addr if self.ch_addr is not None else self.addr,
                       'gui': self.id,
                       'role': self.role,
                       'addr': self.addr,
                       'ch_addr': self.ch_addr,
                       'hop_count': self.hop_count,
                       'sent_time': self.now})
    ###################
    
    def send_update_parent(self, farthest_gui):

        self.send({'dest':wsn.BROADCAST_ADDR, 'type':'UPDATE_PARENT', 'source': self.ch_addr if self.ch_addr is not None else self.addr, 'data':farthest_gui,'gui':self.id,'sent_time': self.now})

        

    def send_cluster_head_info(self, dest):
        """Sending cluster head information to given destination address.

        Args:

        Returns:

        """
        self.send({'dest': dest,
                   'type': 'CLUSTER_HEAD_INFO',
                   'gui': self.id,
                   'ch_addr': self.ch_addr,
                   'child_networks_table': self.child_networks_table,
                   'members_table': self.members_table,
                   'parent_gui': self.parent_gui,
                   'child_id': self.child_id,
                   'cluster_id': self.cluster_id,
                   'net_to_addr': self.net_to_addr,
                   'addr_to_net': self.addr_to_net,
                   'send_time': self.now})

    def send_cluster_head_nomination(self, dest):
        """Sending cluster head nomination message to given destination address.

        Args:
            dest (Addr): Destination address

        Returns:

        """
        self.send({'dest': dest, 'ch_addr': self.ch_addr, 'type': 'CLUSTER_HEAD_NOMINATION', 'source': self.addr, 'sent_time': self.now})

    def send_data_packet(self, dest, sensor_value):
        """Sending data packet to a destination node.

        Args:
            dest (Addr): Destination address
            sensor_value (float): Sensor value to be sent

        Returns:

        """
        pck = {'dest': dest, 'type': 'DATA', 'source': self.ch_addr if self.ch_addr is not None else self.addr, 'data': sensor_value, 'previous_hop': self.id, 'sent_time': self.now}
        # Generate packet_id before routing
        if 'packet_id' not in pck:
            pck['packet_id'] = f"{self.id}_{self.packet_counter}"
            self.packet_counter += 1
        # Log SEND event
        log_data_packet_trace('SEND', self.id, self.addr, pck['packet_id'], pck['source'], dest, sensor_value, self.now)
        self.route_and_forward_package(pck)

    ###################
    def send_neighbor_request(self, dest):
        """Sending neighbor request message to be discovered and registered.

        Args:

        Returns:

        """
        self.send({'dest': dest, 'type': 'NEIGHBOR_REQUEST', 'source': self.ch_addr if self.ch_addr is not None else self.addr,
                'gui': self.id,
                'role': self.role,
                'addr': self.addr,
                'ch_addr': self.ch_addr,
                'data': self.neighbors_table,
                'sent_time': self.now})
    
    def send_neighbor_reply(self, dest):
        """Sending neighbor reply message to given destination address.

        Args:
            dest (Addr): Address of destination node
        Returns:

        """
        self.send({'dest': dest, 'type': 'NEIGHBOR_REPLY', 'source': self.ch_addr if self.ch_addr is not None else self.addr,
                   'gui': self.id,
                   'role': self.role,
                   'addr': self.addr,
                   'ch_addr': self.ch_addr,
                   'data': self.neighbors_table,
                   'sent_time': self.now})

    ###################
    def send_heart_beat(self):
        """Sending heart beat message

        Args:

        Returns:

        """
        self.send({'dest': wsn.BROADCAST_ADDR,
                   'type': 'HEART_BEAT',
                   'source': self.ch_addr if self.ch_addr is not None else self.addr,
                   'gui': self.id,
                   'role': self.role,
                   'addr': self.addr,
                   'ch_addr': self.ch_addr,
                   'hop_count': self.hop_count,
                   'power_levels': self.tx_power_levels,
                   'sent_time': self.now})

    ###################
    def send_join_request(self, dest):
        """Sending join request message to given destination address to join destination network

        Args:
            dest (Addr): Address of destination node
        Returns:

        """
        self.send({'dest': dest, 'type': 'JOIN_REQUEST', 'gui': self.id, 'sent_time': self.now})

    ###################
    def send_join_reply(self, gui, addr):
        """Sending join reply message to register the node requested to join.
        The message includes a gui to determine which node will take this reply, an addr to be assigned to the node
        and a root_addr.

        Args:
            gui (int): Global unique ID
            addr (Addr): Address that will be assigned to new registered node
        Returns:

        """
        self.send({'dest': wsn.BROADCAST_ADDR, 'type': 'JOIN_REPLY', 'source': self.ch_addr if self.ch_addr is not None else self.addr,
                   'gui': self.id, 'dest_gui': gui, 'addr': addr, 'root_addr': self.root_addr,
                   'hop_count': self.hop_count+1,'sent_time': self.now})

    def send_join_reject(self, gui, addr):
        """Sending join reject message to refuse the node requested to join.
        The message includes a gui to determine which node will take this reply, an addr to be assigned to the node
        and a root_addr.

        Args:
            gui (int): Global unique ID
            addr (Addr): Address that will be assigned to new registered node
        Returns:

        """
        self.send({'dest': wsn.BROADCAST_ADDR, 'type': 'JOIN_REJECT', 'source': self.ch_addr if self.ch_addr is not None else self.addr,
                     'gui': self.id, 'dest_gui': gui, 'addr': addr,
                     'hop_count': self.hop_count+1,'sent_time': self.now})
    
    ###################
    def send_join_ack(self, dest):
        """Sending join acknowledgement message to given destination address.

        Args:
            dest (Addr): Address of destination node
        Returns:

        """
        self.send({'dest': dest, 'type': 'JOIN_ACK', 'source': self.ch_addr if self.ch_addr is not None else self.addr,
                   'gui': self.id, 'sent_time': self.now})

    ###################
    def route_and_forward_package(self, pck):
        """Routing and forwarding given package
        
        Args:
            pck (Dict): package to route and forward it should contain dest, source and type.
        Returns:

        """
        # Add unique packet ID if not present (for deduplication)
        if 'packet_id' not in pck:
            pck['packet_id'] = f"{self.id}_{self.packet_counter}"
            self.packet_counter += 1
        
        # Validate destination exists
        dest = pck.get('dest')
        if dest is None:
            self.log(f"ERROR: Cannot route package with None destination: {pck}")
            return
                
        for gui_entries in self.neighbors_table.keys(): #check ch_addr and addr in neighbor table
            nb_entry = self.neighbors_table.get(gui_entries)
            if not isinstance(nb_entry, dict):
                continue
                
            # Check if destination matches neighbor's addr
            if nb_entry.get('addr') is not None and dest == nb_entry.get('addr'):
                next_hop = nb_entry.get('next_hop')
                if next_hop is None:
                    self.log(f"WARNING: next_hop is None for neighbor {gui_entries} with addr {nb_entry.get('addr')}")
                    continue
                pck['next_hop'] = next_hop
                pck['previous_hop'] = self.id
                pck['routing_option'] = 'Cluster Routing Cluster'
                self.log(f"Cluster Routing package {pck['type']} to next hop {pck['next_hop']} for destination {pck['dest']} from {pck['source']}")
                # Log ROUTE event for DATA packets
                if pck['type'] == 'DATA':
                    log_data_packet_trace('ROUTE', self.id, self.addr, pck.get('packet_id'), pck['source'], pck['dest'], pck.get('data'), self.now, next_hop=next_hop, routing_option='Cluster Routing Cluster', previous_hop=pck.get('previous_hop'))
                self.send(pck)
                return
                
            # Check if destination matches neighbor's ch_addr
            if nb_entry.get('ch_addr') is not None and dest == nb_entry.get('ch_addr'):
                if self.role == Roles.CLUSTER_HEAD:
                    if nb_entry.get('next_hop') == self.ch_addr:
                        if self.default_gateway is None:
                            self.log(f"WARNING: Cannot route via default_gateway (None) for dest {dest}")
                            continue
                        pck['next_hop'] = self.default_gateway
                        pck['routing_option'] = 'Cluster Routing Default Gateway'
                        pck['previous_hop'] = self.id
                        self.send(pck)
                        return
                    else:
                        next_hop = nb_entry.get('next_hop')
                        if next_hop is None:
                            self.log(f"WARNING: next_hop is None for neighbor {gui_entries} with ch_addr {nb_entry.get('ch_addr')}")
                            continue
                        pck['next_hop'] = next_hop
                        pck['previous_hop'] = self.id
                        pck['routing_option'] = 'Cluster Routing CH addr'
                        self.log(f"Cluster Routing package {pck['type']} to next hop {pck['next_hop']} for destination {pck['dest']} from {pck['source']}")
                        # Log ROUTE event for DATA packets
                        if pck['type'] == 'DATA':
                            log_data_packet_trace('ROUTE', self.id, self.addr, pck.get('packet_id'), pck['source'], pck['dest'], pck.get('data'), self.now, next_hop=next_hop, routing_option='Cluster Routing CH addr', previous_hop=pck.get('previous_hop'))
                        self.send(pck)
                        return

        # Root and cluster head route with child networks
        if self.role == Roles.CLUSTER_HEAD or self.role == Roles.ROOT:
            if hasattr(dest, 'net_addr') and dest.net_addr is not None:
                for child_gui, child_networks in self.child_networks_table.items():
                    if dest.net_addr in (child_networks or []):
                        nb = self.neighbors_table.get(child_gui, {})
                        next_hop = nb.get('addr')
                        if next_hop is None:
                            self.log(f"WARNING: Cannot route down tree - child {child_gui} has no addr in neighbors_table")
                            continue
                        pck['next_hop'] = next_hop
                        pck['previous_hop'] = self.id
                        pck['routing_option'] = 'Down Tree'
                        self.log(f"Down Tree Routing package {pck['type']} to next hop {pck['next_hop']} for destination {pck['dest']} from {pck['source']}")
                        # Log ROUTE event for DATA packets
                        if pck['type'] == 'DATA':
                            log_data_packet_trace('ROUTE', self.id, self.addr, pck.get('packet_id'), pck['source'], pck['dest'], pck.get('data'), self.now, next_hop=next_hop, routing_option='Down Tree', previous_hop=pck.get('previous_hop'))
                        self.send(pck)
                        return
        
        # Router routing with child networks
        if self.role == Roles.ROUTER:
            # Prevent routing loops: don't send back to the node we just received from
            prev_hop = pck.get('previous_hop')
            
            if pck.get('previous_hop') == self.parent_gui: # if pck is from default gateway then pass it downward
                if self.default_gateway2 is None:
                    self.log(f"ERROR: Router cannot forward downward - default_gateway2 is None")
                    return
                # Check if we're about to send it back to previous hop
                # Compare with the gui of the node at default_gateway2
                if prev_hop is not None:
                    # Find the gui that has default_gateway2 as their address
                    for gui, nb_entry in self.neighbors_table.items():
                        if isinstance(nb_entry, dict) and nb_entry.get('addr') == self.default_gateway2:
                            if gui == prev_hop:
                                self.log(f"ERROR: Router loop detected - would send packet back to previous_hop {prev_hop}")
                                return
                            break
                pck['next_hop'] = self.default_gateway2
                pck['routing_option'] = 'Cluster Routing Router Gateway 2'
            else: 
                if self.default_gateway is None:
                    self.log(f"ERROR: Router cannot forward upward - default_gateway is None")
                    return
                # Check if we're about to send it back to previous hop
                if prev_hop is not None:
                    # Find the gui that has default_gateway as their address
                    for gui, nb_entry in self.neighbors_table.items():
                        if isinstance(nb_entry, dict) and nb_entry.get('addr') == self.default_gateway:
                            if gui == prev_hop:
                                self.log(f"ERROR: Router loop detected - would send packet back to previous_hop {prev_hop}")
                                return
                            break
                pck['next_hop'] = self.default_gateway
                pck['routing_option'] = 'Cluster Routing Router Gateway'
            pck['previous_hop'] = self.id
            # Log ROUTE event for DATA packets
            if pck['type'] == 'DATA':
                log_data_packet_trace('ROUTE', self.id, self.addr, pck.get('packet_id'), pck['source'], pck['dest'], pck.get('data'), self.now, next_hop=pck.get('next_hop'), routing_option=pck.get('routing_option'), previous_hop=prev_hop)
            self.send(pck)
            return

        # Fallback: route up tree via default gateway
        if self.default_gateway is not None:
            pck['next_hop'] = self.default_gateway
            self.log(f"Up Tree Routing package (default gateway) {pck['type']} to next hop {pck['next_hop']} for destination {pck['dest']} from {pck['source']}")
            pck['previous_hop'] = self.id
            # Log ROUTE event for DATA packets
            if pck['type'] == 'DATA':
                log_data_packet_trace('ROUTE', self.id, self.addr, pck.get('packet_id'), pck['source'], pck['dest'], pck.get('data'), self.now, next_hop=self.default_gateway, routing_option='Up Tree', previous_hop=pck.get('previous_hop'))
            self.send(pck)
            return
        
        # No route found
        self.log(f"ERROR: No route found for package {pck['type']} to destination {dest} from {pck['source']}")

    ###################
    def send_network_request(self):
        """Sending network request message to root address to be cluster head

        Args:

        Returns:

        """
        self.route_and_forward_package({'dest': self.root_addr, 'type': 'NETWORK_REQUEST', 'source': self.addr, 'previous_hop': self.id, 'sent_time': self.now})

    ###################
    def send_network_reply(self, dest, addr):
        """Sending network reply message to dest address to be cluster head with a new adress

        Args:
            dest (Addr): destination address
            addr (Addr): cluster head address of new network

        Returns:

        """
        # NETWORK_REPLY must be routed to the source's current address, not the new address being assigned
        # The dest parameter is the source address from NETWORK_REQUEST - use it directly for routing
        self.route_and_forward_package({'dest': dest, 'type': 'NETWORK_REPLY', 'source': self.ch_addr if self.ch_addr is not None else self.addr, 'addr': addr, 'previous_hop': self.id, 'sent_time': self.now})

    ###################
    def send_network_update(self):
        """Sending network update message to parent

        Args:

        Returns:

        """
        if self.role == Roles.ROUTER:
            child_networks = [self.addr.net_addr]
        else:
            child_networks = [self.ch_addr.net_addr]

        for networks in self.child_networks_table.values():
            child_networks.extend(networks)
        if self.role == Roles.CLUSTER_HEAD or self.role == Roles.ROOT or self.role == Roles.ROUTER:
            if self.default_gateway is None:
                self.log(f"Warning: Attempted to send NETWORK_UPDATE but default_gateway is None. Skipping send.")
                return
            self.send({'dest': self.default_gateway, 'type': 'NETWORK_UPDATE', 'source': self.ch_addr if self.ch_addr is not None else self.addr,
                'gui': self.id, 'child_networks': child_networks})
            log_msg = f"Sent NETWORK_UPDATE to dest {self.neighbors_table[self.parent_gui]['ch_addr']} from {self.ch_addr} with child networks {child_networks}"
            return
        #elif self.role == Roles.Router: #update child networks table for router
            #self.send({'dest': self.neighbors_table[self.parent_gui]['addr'], 'type': 'NETWORK_UPDATE', 'source': self.addr,
            #    'gui': self.id, 'child_networks': child_networks})
            #log_msg = f"Sent NETWORK_UPDATE to dest {self.neighbors_table[self.parent_gui]['addr']} from {self.addr} with child networks {child_networks}"
            #return
        #elif self.role == Roles.ROUTER:
            #self.send({'dest': self.neighbors_table[self.parent_gui]['ch_addr'], 'type': 'NETWORK_UPDATE', 'source': self.ch_addr if self.ch_addr is not None else self.addr,
                #'gui': self.id, 'child_networks': child_networks})
            #log_msg = f"Sent NETWORK_UPDATE to dest {self.neighbors_table[self.parent_gui]['ch_addr']} from {self.addr} with child networks {child_networks}"

    ###################
    def on_receive(self, pck):
        #print(pck)
        #if random.random() < config.PACK_LOST_RATE:
            #self.log(f"Packet lost at {self.addr} from {pck.get('source')}: {pck} dest: {pck.get('dest')} package type: {pck.get('type')}")
            #return  # Simulate packet loss
        self.log(f"Packet received at {self.addr} from {pck.get('source')}: {pck} dest: {pck.get('dest')} package type: {pck.get('type')}")
        """Executes when a package received.

        Args:
            pck (Dict): received package
        Returns:

        """
        # Packet deduplication: Check if we've already processed this packet
        packet_id = pck.get('packet_id')
        source = pck.get('source')
        
        # Create a unique identifier for this packet
        if packet_id is not None and source is not None:
            packet_signature = (str(source), packet_id)
            
            # Check if we've seen this packet before
            if packet_signature in self.seen_packets:
                # Silently drop duplicate packet
                return
            
            # Mark this packet as seen
            self.seen_packets.add(packet_signature)
            
            # Prevent memory overflow: limit cache size
            if len(self.seen_packets) > self.max_seen_packets:
                # Remove oldest entries (convert to list, remove first half, convert back)
                seen_list = list(self.seen_packets)
                self.seen_packets = set(seen_list[len(seen_list)//2:])
        
        if self.role == Roles.ROOT or self.role == Roles.CLUSTER_HEAD:  # if the node is root or cluster head
            if 'next_hop' in pck.keys() and pck['dest'] != self.addr and pck['dest'] != self.ch_addr:  # forwards message if destination is not itself
                self.route_and_forward_package(pck)
                return
            
            if pck['type'] == 'HEART_BEAT':
                self.update_neighbor(pck)
            if pck['type'] == 'PROBE':  # it waits and sends heart beat message once received probe message
                # yield self.timeout(.5)
                self.send_heart_beat()
            if pck['type'] == 'JOIN_REQUEST':  # it waits and sends join reply message once received join request
                # yield self.timeout(.5) 
                for members_gui in self.members_table:
                    if pck['gui'] == members_gui:
                        return
                if len(self.members_table) >= config.NODE_MAX_CHILD:
                    self.send_join_reject(pck['gui'], self.addr if self.addr is not None else self.ch_addr)
                else:
                    child_addr = wsn.Addr(self.ch_addr.net_addr, self.add_child())
                    if self.addr == child_addr:
                        child_addr = wsn.Addr(self.ch_addr.net_addr, self.add_child())
                    self.send_join_reply(pck['gui'], child_addr)
            if pck['type'] == 'NETWORK_REQUEST':  # it sends a network reply to requested node
                # yield self.timeout(.5)
                if self.role == Roles.ROOT:
                    new_addr = wsn.Addr(self.add_network(pck),254)
                    self.send_network_reply(pck['source'],new_addr)
            if pck['type'] == 'JOIN_ACK':
                self.members_table.append(pck['gui'])
            if pck['type'] == 'NETWORK_UPDATE':
                self.child_networks_table[pck['gui']] = pck['child_networks']
                if self.role != Roles.ROOT:
                    self.send_network_update()
            if pck['type'] == 'DATA':
                self.log(f"DATA received from {pck['source']}: {pck['data']}")
                # Log RECEIVE event
                log_data_packet_trace('RECEIVE', self.id, self.addr, pck.get('packet_id'), pck['source'], pck['dest'], pck.get('data'), self.now, previous_hop=pck.get('previous_hop'))
            if pck['type'] == 'SENSOR':
                pass
                # self.log(str(pck['source'])+'--'+str(pck['sensor_value']))
            if pck['type'] == 'NEIGHBOR_REQUEST':
                self.update_neighbor(pck)
                # Only send a neighbor reply if the sender provided a valid source address
                if pck.get('source') is not None:
                    self.send_neighbor_reply(pck['source'])
            if pck['type'] == 'NEIGHBOR_REPLY':
                self.update_neighbor(pck)

        elif self.role == Roles.ROUTER:  # if the node is router
            if 'next_hop' in pck.keys() and pck['dest'] != self.addr:  # forwards message if destination is not itself
                self.route_and_forward_package(pck)
                return
            if pck['type'] == 'HEART_BEAT':
                self.update_neighbor(pck)

            if pck['type'] == 'PROBE':
                # yield self.timeout(.5)
                self.send_heart_beat()
            if pck['type'] == 'JOIN_REQUEST':  
                self.send_join_reject(pck['gui'], self.addr if self.addr is not None else self.ch_addr)
            if pck['type'] == 'NETWORK_UPDATE':
                self.child_networks_table[pck['gui']] = pck['child_networks']
                self.send_network_update()
            if pck['type'] == 'DATA':
                self.log(f"DATA received from {pck['source']}: {pck['data']}")
                # Log RECEIVE event
                log_data_packet_trace('RECEIVE', self.id, self.addr, pck.get('packet_id'), pck['source'], pck['dest'], pck.get('data'), self.now, previous_hop=pck.get('previous_hop'))
            if pck['type'] == 'NEIGHBOR_REQUEST':
                self.update_neighbor(pck)
                # Only send a neighbor reply if the sender provided a valid source address
                if pck.get('source') is not None:
                    self.send_neighbor_reply(pck['source'])
            if pck['type'] == 'NEIGHBOR_REPLY':
                self.update_neighbor(pck)

        elif self.role == Roles.REGISTERED:  # if the node is registered
            # REGISTERED nodes should not forward packets unless they're routers/cluster heads
            # Only process packets destined for this node
            if 'next_hop' in pck.keys() and pck['dest'] != self.addr:
                # This packet is not for us and we shouldn't forward it
                self.log(f"WARNING: REGISTERED node received packet not destined for self. Dropping. Dest={pck['dest']}, MyAddr={self.addr}")
                return
                
            if pck['type'] == 'HEART_BEAT':
                self.update_neighbor(pck)
            if pck['type'] == 'UPDATE_PARENT':
                farthest_gui = pck['data']
                if pck['gui'] == self.parent_gui:
                    if farthest_gui in self.neighbors_table.keys():
                        self.erase_parent()
                        self.parent_gui = farthest_gui
                        self.default_gateway = self.neighbors_table[farthest_gui]['ch_addr']
                        self.draw_parent()
                    else:
                        self.become_unregistered()
            if pck['type'] == 'PROBE':
                # yield self.timeout(.5)
                self.send_heart_beat()
            if pck['type'] == 'JOIN_REQUEST':  # it sends a network request to the root
                self.received_JR_guis.append(pck['gui'])
                # yield self.timeout(.5)
                self.send_network_request()
            if pck['type'] == 'CLUSTER_HEAD_NOMINATION':  # it becomes cluster head once received cluster head nomination 
                #self.addr = wsn.Addr(self.ch_addr.net_addr,1)
                self.add_child()
                self.ch_addr = pck['ch_addr']
                self.set_role(Roles.CLUSTER_HEAD)
                
                self.send_network_update()
                self.default_gateway = pck['source']
            if pck['type'] == 'CLUSTER_HEAD_INFO':  # it updates its tables with received cluster head information
                self.child_networks_table = pck['child_networks_table']
                self.members_table = pck['members_table']
                self.parent_gui = pck['parent_gui']
                self.cluster_id = pck['cluster_id']
                self.child_id = pck['child_id']
                self.child_id.remove(1)
                self.net_to_addr = pck['net_to_addr']
                self.addr_to_net = pck.get['addr_to_net']
                self.send_probe()
                self.draw_parent()
                #for gui in self.neighbors_table[gui]:
                #    if self.neighbors_table[guis]['next_hop'] == self.ch_addr:
                #        del self.neighbors_table[gui]

            if pck['type'] == 'NETWORK_REPLY':  # it becomes cluster head and send join reply to the candidates
                self.set_role(Roles.CLUSTER_HEAD)
                self.set_timer('CLUSTER_HEAD_NOMINATION', config.CLUSTER_HEAD_NOMINATION_INTERVAL)
                try:
                    write_clusterhead_distances_csv("clusterhead_distances.csv")
                except Exception as e:
                    self.log(f"CH CSV export error: {e}")
                self.scene.nodecolor(self.id, 0, 0, 1)
                self.ch_addr = pck['addr']
                
                self.send_network_update()
                # yield self.timeout(.5)
                self.send_heart_beat()
                for gui in self.received_JR_guis:
                    # yield self.timeout(random.uniform(.1,.5))
                    child_addr = wsn.Addr(self.ch_addr.net_addr, self.add_child())
                    if self.addr == child_addr:
                        child_addr = wsn.Addr(self.ch_addr.net_addr, self.add_child())
                    self.send_join_reply(gui, child_addr)
                    
            if pck['type'] == 'NETWORK_UPDATE':
                self.child_networks_table[pck['gui']] = pck['child_networks']
            if pck['type'] == 'DATA':
                self.log(f"DATA received from {pck['source']}: {pck['data']}")
                # Log RECEIVE event
                log_data_packet_trace('RECEIVE', self.id, self.addr, pck.get('packet_id'), pck['source'], pck['dest'], pck.get('data'), self.now, previous_hop=pck.get('previous_hop'))
            if pck['type'] == 'NEIGHBOR_REQUEST':
                self.update_neighbor(pck)
                # Only send a neighbor reply if the sender provided a valid source address
                if pck.get('source') is not None:
                    self.send_neighbor_reply(pck['source'])
            if pck['type'] == 'NEIGHBOR_REPLY':
                self.update_neighbor(pck)

        elif self.role == Roles.UNDISCOVERED:  # if the node is undiscovered
            if pck['type'] == 'HEART_BEAT':  # it kills probe timer, becomes unregistered and sets join request timer once received heart beat
                self.update_neighbor(pck)
                self.kill_timer('TIMER_PROBE')
                self.become_unregistered()

        if self.role == Roles.UNREGISTERED:  # if the node is unregistered
            if pck['type'] == 'HEART_BEAT':
                self.update_neighbor(pck)
            
            if pck['type'] == 'JOIN_REJECT': # remove source address from possible canidates once received join reject
                if pck['dest_gui'] == self.id:
                    gui_to_remove = pck['gui']
                    if gui_to_remove in self.candidate_parents_table:
                        self.candidate_parents_table.remove(gui_to_remove)
                    else:
                        self.log(f"Warning: JOIN_REJECT removal: gui {gui_to_remove} not in candidate_parents_table {self.candidate_parents_table}")
                    self.select_and_join()

            if pck['type'] == 'JOIN_REPLY':  # it becomes registered and sends join ack if the message is sent to itself once received join reply
                if pck['dest_gui'] == self.id:
                    self.addr = pck['addr']
                    self.parent_gui = pck['gui']
                    self.root_addr = pck['root_addr']
                    self.hop_count = pck['hop_count']
                    self.default_gateway = pck['source']
                    self.draw_parent()
                    self.kill_timer('TIMER_JOIN_REQUEST')
                    self.set_timer('TIMER_HEART_BEAT', config.HEARTH_BEAT_TIME_INTERVAL)
                    self.send_join_ack(pck['source'])
                    self.set_timer('RANDOM_PACKAGE', random.uniform(500, 1000))
                    if self.ch_addr is not None: # it could be a cluster head which lost its parent
                        self.set_role(Roles.CLUSTER_HEAD)
                        self.send_network_update()
                    else:
                        self.set_role(Roles.REGISTERED)
                        if config.ENABLE_MESH_ROUTING:
                            self.set_timer('TIMER_NEIGHBOR_REQUEST', config.NEIGHBOR_REQUEST_INTERVAL)
                    self.send_heart_beat()                           
                    # # sensor implementation
                    # timer_duration =  self.id % 20
                    # if timer_duration == 0: timer_duration = 1
                    # self.set_timer('TIMER_SENSOR', timer_duration)

    ###################
    def on_timer_fired(self, name, *args, **kwargs):
        """Executes when a timer fired.

        Args:
            name (string): Name of timer.
            *args (string): Additional args.
            **kwargs (string): Additional key word args.
        Returns:

        """
        if name == 'TIMER_ARRIVAL':  # it wakes up and set timer probe once time arrival timer fired
            self.scene.nodecolor(self.id, 1, 0, 0)  # sets self color to red
            self.wake_up()
            self.set_timer('TIMER_PROBE', 1)
        elif name == 'CLUSTER_HEAD_NOMINATION':  # if self and default gateways are clusterhead and self have childrends nominate farthest childrend to be cluster head and self become a router
            farthest_gui = None
            max_distance = -1
            for gui in self.members_table:
                if self.neighbors_table[gui]['distance'] > max_distance:
                    max_distance = self.neighbors_table[gui]['distance']
                    farthest_gui = gui
            if self.role == Roles.CLUSTER_HEAD:
                if farthest_gui is not None and self.neighbors_table[self.parent_gui]['role'] == Roles.CLUSTER_HEAD or self.neighbors_table[self.parent_gui]['role'] == Roles.ROOT:
                    self.send_cluster_head_nomination(self.neighbors_table[farthest_gui]['addr'])
                    self.send_cluster_head_info(self.neighbors_table[farthest_gui]['addr'])
                    self.default_gateway2 = self.neighbors_table[farthest_gui]['addr']
                    self.set_role(Roles.ROUTER)
                    self.send_neighbor_request(self.neighbors_table[gui]['addr'])
                    self.send_neighbor_request(self.default_gateway)
                    self.send_neighbor_request(self.default_gateway2)
                    self.scene.nodecolor(self.id, 0, 1, 1)  # sets self color to cyan
                    self.send_update_parent(farthest_gui)
                    self.ch_addr = None
                    #self.send_network_update()
                    #self.default_gateway = None


        elif name == 'RANDOM_PACKAGE':  # only registered nodes should send; pick registered destination
            if self.role != Roles.REGISTERED:
                self.set_timer('RANDOM_PACKAGE', random.uniform(250, 500))
            else:
                registered_ids = [n.id for n in sim.nodes if hasattr(n, 'role') and n.role == Roles.REGISTERED and n.id != self.id]
                if not registered_ids:
                    self.set_timer('RANDOM_PACKAGE', random.uniform(250, 500))
                else:
                    dest_gui = random.choice(registered_ids)
                    dest_addr = getattr(sim.nodes[dest_gui], 'addr', None)
                    if dest_addr is None:
                        self.set_timer('RANDOM_PACKAGE', random.uniform(250, 500))
                        return
                    self.send_data_packet(dest_addr, random.uniform(10,50))
                    self.set_timer('RANDOM_PACKAGE', random.uniform(250, 500))

        elif name == 'TIMER_PROBE':  # it sends probe if counter didn't reach the threshold once timer probe fired.
            if self.c_probe < self.th_probe:
                self.send_probe()
                self.c_probe += 1
                self.set_timer('TIMER_PROBE', 1)
            else:  # if the counter reached the threshold
                if self.is_root_eligible:  # if the node is root eligible, it becomes root
                    self.set_role(Roles.ROOT)
                    self.set_timer('RANDOM_PACKAGE', random.uniform(*config.RANDOM_PACKET_TIME_INTERVAL))
                    self.scene.nodecolor(self.id, 0, 0, 0)
                    self.addr = wsn.Addr(1, self.add_child())
                    self.ch_addr = wsn.Addr(1, 254)
                    self.root_addr = self.ch_addr
                    self.hop_count = 0
                    self.set_timer('TIMER_HEART_BEAT', config.HEARTH_BEAT_TIME_INTERVAL)
                else:  # otherwise it keeps trying to sending probe after a long time
                    self.c_probe = 0
                    self.set_timer('TIMER_PROBE', 100)

        elif name == 'TIMER_HEART_BEAT':  # it sends heart beat message once heart beat timer fired
            if self.role == Roles.UNREGISTERED and len(self.candidate_parents_table) == 0:
                self.become_undiscovered()
                return
            if self.role == Roles.UNREGISTERED and len(self.candidate_parents_table) > 0:
                self.select_and_join()
                return
            self.send_heart_beat()
            self.set_timer('TIMER_HEART_BEAT', config.HEARTH_BEAT_TIME_INTERVAL)
            #print(self.id)

        elif name == 'TIMER_NEIGHBOR_REQUEST': # it sends neighbor request message once neighbor request timer fired
            for gui in self.neighbors_table.keys():
                self.send_neighbor_request(self.neighbors_table[gui]['addr'])
            #self.set_timer('TIMER_NEIGHBOR_REQUEST', config.NEIGHBOR_REQUEST_INTERVAL)

        elif name == 'TIMER_JOIN_REQUEST':  # if it has not received heart beat messages before, it sets timer again and wait heart beat messages once join request timer fired.
            if len(self.candidate_parents_table) == 0:
                self.become_unregistered()
            else:  # otherwise it chose one of them and sends join request
                self.select_and_join()

        elif name == 'TIMER_SENSOR':
            self.route_and_forward_package({'dest': self.root_addr, 'type': 'SENSOR', 'source': self.ch_addr if self.ch_addr is not None else self.addr, 'sensor_value': random.uniform(10,50), 'previous_hop': self.id})
            timer_duration =  self.id % 20
            if timer_duration == 0: timer_duration = 1
            self.set_timer('TIMER_SENSOR', timer_duration)
        elif name == 'TIMER_EXPORT_CH_CSV':
            # Only root should drive exports (cheap guard)
            #self.export_to_csv("Cluster_Head", CLUSTER_HEADS)
            if self.role == Roles.ROOT:
                write_clusterhead_distances_csv("clusterhead_distances.csv")
                # reschedule
                self.set_timer('TIMER_EXPORT_CH_CSV', config.EXPORT_CH_CSV_INTERVAL)
        elif name == 'TIMER_EXPORT_NEIGHBOR_CSV':
            if self.role == Roles.ROOT:
                write_neighbor_distances_csv("neighbor_distances.csv")
                self.set_timer('TIMER_EXPORT_NEIGHBOR_CSV', config.EXPORT_NEIGHBOR_CSV_INTERVAL)

        elif name == 'TIMER_TX_POWER_CHECK':
            # Only cluster heads adapt TX power
            if self.role != Roles.CLUSTER_HEAD:
                return
            # Current position
            sx, sy = NODE_POS.get(self.id, (None, None))
            if sx is None:
                # Reschedule and abort if position unknown
                self.set_timer('TIMER_TX_POWER_CHECK', config.CLUSTER_HEAD_TX_POWER_CHECK_INTERVAL)
                return
            distances = []
            # Distances to members
            for gui in self.members_table:
                px, py = NODE_POS.get(gui, (None, None))
                if px is None:
                    continue
                distances.append(math.hypot(sx - px, sy - py))
            # Include distance to parent if present (to keep upstream connectivity)
            if self.parent_gui is not None:
                px, py = NODE_POS.get(self.parent_gui, (None, None))
                if px is not None:
                    distances.append(math.hypot(sx - px, sy - py))
            if not distances:
                self.set_timer('TIMER_TX_POWER_CHECK', config.CLUSTER_HEAD_TX_POWER_CHECK_INTERVAL)
                return
            max_dist = max(distances)
            required = max_dist * 1.05
            chosen_level = None
            for level in sorted(config.NODE_TX_POWER_LEVELS):
                if level >= required:
                    chosen_level = level
                    break
            if chosen_level is None:
                chosen_level = max(config.NODE_TX_POWER_LEVELS)
            chosen_scaled = chosen_level * config.SCALE
            if chosen_scaled != self.tx_range:
                old = self.tx_range
                # Update cluster head range and redraw its circle
                self.tx_range = chosen_scaled
                try:
                    self.remove_tx_range()
                except Exception:
                    pass
                self.draw_tx_range()
                # Propagate to member nodes (no circle drawing for them)
                for gui in self.members_table:
                    if 0 <= gui < len(sim.nodes):
                        try:
                            sim.nodes[gui].tx_range = chosen_scaled
                        except Exception:
                            continue
                self.log(f"TX_POWER_ADJUST CH={self.id} old={old:.2f} new={chosen_scaled:.2f} max_child_dist={max_dist:.2f} members={len(self.members_table)}")
            # Reschedule next check
            self.set_timer('TIMER_TX_POWER_CHECK', config.CLUSTER_HEAD_TX_POWER_CHECK_INTERVAL)



ROOT_ID = random.randrange(config.SIM_NODE_COUNT)  # 0..count-1



def write_node_distances_csv(path="node_distances.csv"):
    """Write pairwise node-to-node Euclidean distances as an edge list."""
    ids = sorted(NODE_POS.keys())
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source_id", "target_id", "distance"])
        for i, sid in enumerate(ids):
            x1, y1 = NODE_POS[sid]
            for tid in ids[i+1:]:  # i+1 to avoid duplicates and self-pairs
                x2, y2 = NODE_POS[tid]
                dist = math.hypot(x1 - x2, y1 - y2)
                w.writerow([sid, tid, f"{dist:.6f}"])


def write_node_distance_matrix_csv(path="node_distance_matrix.csv"):
    ids = sorted(NODE_POS.keys())
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["node_id"] + ids)
        for sid in ids:
            x1, y1 = NODE_POS[sid]
            row = [sid]
            for tid in ids:
                x2, y2 = NODE_POS[tid]
                dist = math.hypot(x1 - x2, y1 - y2)
                row.append(f"{dist:.6f}")
            w.writerow(row)


def write_clusterhead_distances_csv(path="clusterhead_distances.csv"):
    """Write pairwise distances between current cluster heads."""
    clusterheads = []
    for node in sim.nodes:
        # Only collect nodes that are cluster heads and have recorded positions
        if hasattr(node, "role") and node.role == Roles.CLUSTER_HEAD and node.id in NODE_POS:
            x, y = NODE_POS[node.id]
            clusterheads.append((node.id, x, y))

    if len(clusterheads) < 2:
        # Still write the header so the file exists/is refreshed
        with open(path, "w", newline="") as f:
            csv.writer(f).writerow(["clusterhead_1", "clusterhead_2", "distance"])
        return

    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["clusterhead_1", "clusterhead_2", "distance"])
        for i, (id1, x1, y1) in enumerate(clusterheads):
            for id2, x2, y2 in clusterheads[i+1:]:
                dist = math.hypot(x1 - x2, y1 - y2)
                w.writerow([id1, id2, f"{dist:.6f}"])



def write_data_packet_traces_csv(path="data_packet_traces.csv"):
    """Write all data packet trace events to CSV.
    
    Each row represents an event (SEND, ROUTE, RECEIVE) for a data packet.
    """
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["event_type", "timestamp", "node_id", "node_addr", "packet_id", 
                    "source", "dest", "data_value", "next_hop", "routing_option", "previous_hop"])
        
        for trace in DATA_PACKET_TRACES:
            w.writerow([
                trace['event_type'],
                f"{trace['timestamp']:.6f}",
                trace['node_id'],
                trace['node_addr'],
                trace['packet_id'],
                trace['source'],
                trace['dest'],
                f"{trace['data_value']:.6f}" if isinstance(trace['data_value'], (int, float)) else trace['data_value'],
                trace['next_hop'],
                trace['routing_option'],
                trace['previous_hop']
            ])


def write_logs_csv(path="simulation_logs.csv"):
    """Write all log entries to CSV.
    
    Each row represents a log message from a node during simulation.
    """
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "node_id", "node_addr", "node_role", "message"])
        
        for log_entry in LOG_ENTRIES:
            w.writerow([
                f"{log_entry['timestamp']:.6f}",
                log_entry['node_id'],
                log_entry['node_addr'],
                log_entry['node_role'],
                log_entry['message']
            ])


def write_neighbor_distances_csv(path="neighbor_distances.csv", dedupe_undirected=True):
    """
    Export neighbor distances per node.
    Each row is (node -> neighbor) with distance from NODE_POS.

    Args:
        path (str): output CSV path
        dedupe_undirected (bool): if True, writes each unordered pair once
                                  (min(node_id,neighbor_id), max(...)).
                                  If False, writes one row per direction.
    """
    # Safety: ensure we can compute distances
    if not globals().get("NODE_POS"):
        raise RuntimeError("NODE_POS is missing; record positions during create_network().")

    # Prepare a set to avoid duplicates if dedupe_undirected=True
    seen_pairs = set()

    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["node_id", "neighbor_id", "distance",
                    "neighbor_role", "neighbor_hop_count", "arrival_time"])

        for node in sim.nodes:
            # Skip nodes without any neighbor info yet
            if not hasattr(node, "neighbors_table"):
                continue

            x1, y1 = NODE_POS.get(node.id, (None, None))
            if x1 is None:
                continue  # no position → cannot compute distance

            # neighbors_table: key = neighbor GUI, value = heartbeat packet dict
            for n_gui, pck in getattr(node, "neighbors_table", {}).items():
                # Optional dedupe (unordered)
                if dedupe_undirected:
                    key = (min(node.id, n_gui), max(node.id, n_gui))
                    if key in seen_pairs:
                        continue
                    seen_pairs.add(key)

                # Position of neighbor
                x2, y2 = NODE_POS.get(n_gui, (None, None))
                if x2 is None:
                    continue

                # Distance (prefer pck['distance'] if you added it in update_neighbor)
                dist = pck.get("distance")
                if dist is None:
                    dist = math.hypot(x1 - x2, y1 - y2)

                # Extra fields (best-effort; may be missing)
                n_role = getattr(pck.get("role", None), "name", pck.get("role", None))
                hop = pck.get("hop_count", "")
                at  = pck.get("arrival_time", "")

                w.writerow([node.id, n_gui, f"{dist:.6f}", n_role, hop, at])

###########################################################
def create_network(node_class, number_of_nodes=100):
    """Creates given number of nodes at random positions with random arrival times.

    Args:
        node_class (Class): Node class to be created.
        number_of_nodes (int): Number of nodes.
    Returns:

    """
    edge = math.ceil(math.sqrt(number_of_nodes))
    for i in range(number_of_nodes):
        x = i / edge
        y = i % edge
        px = 300 + config.SCALE*x * config.SIM_NODE_PLACING_CELL_SIZE + random.uniform(-1 * config.SIM_NODE_PLACING_CELL_SIZE / 3, config.SIM_NODE_PLACING_CELL_SIZE / 3)
        py = 200 + config.SCALE* y * config.SIM_NODE_PLACING_CELL_SIZE + random.uniform(-1 * config.SIM_NODE_PLACING_CELL_SIZE / 3, config.SIM_NODE_PLACING_CELL_SIZE / 3)
        node = sim.add_node(node_class, (px, py))
        NODE_POS[node.id] = (px, py)   # <— add this line
        node.tx_range = config.NODE_TX_RANGE * config.SCALE
        node.logging = True
        node.arrival = random.uniform(0, config.NODE_ARRIVAL_MAX)
        if node.id == ROOT_ID:
            node.arrival = 0.1


sim = wsn.Simulator(
    duration=config.SIM_DURATION,
    timescale=config.SIM_TIME_SCALE,
    visual=config.SIM_VISUALIZATION,
    terrain_size=config.SIM_TERRAIN_SIZE,
    title=config.SIM_TITLE)

# creating random network
create_network(SensorNode, config.SIM_NODE_COUNT)

write_node_distances_csv("node_distances.csv")
write_node_distance_matrix_csv("node_distance_matrix.csv")

# start the simulation
sim.run()
print("Simulation Finished")

# Export data packet traces
write_data_packet_traces_csv("data_packet_traces.csv")
print(f"Data packet traces exported: {len(DATA_PACKET_TRACES)} events")

# Export all logs
write_logs_csv("simulation_logs.csv")
print(f"Simulation logs exported: {len(LOG_ENTRIES)} log entries")


# Created 100 nodes at random locations with random arrival times.
# When nodes are created they appear in white
# Activated nodes becomes red
# Discovered nodes will be yellow
# Registered nodes will be green.
# Root node will be black.
# Routers/Cluster Heads should be blue
