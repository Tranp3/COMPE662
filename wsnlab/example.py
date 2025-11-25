import random
from enum import Enum
import sys
# insert at 1, 0 is the script path (or '' in REPL)
sys.path.insert(1, '.')
from source import wsnlab_vis as wsn
import math
from source import config

Roles = Enum('Roles', 'UNDISCOVERED UNREGISTERED ROOT REGISTERED CLUSTER_HEAD')
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
        received_HB_addresses (List of Addr): keeps the addresses of received heart beat messages
    """

    ###################
    def init(self):
        """Initialization of node. Setting all attributes of node.
        At the beginning node needs to be sleeping and its role should be UNDISCOVERED.

        Args:

        Returns:

        """
        self.sleep()
        self.addr = None
        self.ch_addr = None
        self.is_root_eligible = True
        self.example_counter = 0

    ###################
    def run(self):
        """Setting the arrival timer to wake up after firing.

        Args:

        Returns:

        """
        self.set_timer('TIMER_ARRIVAL', self.arrival)

    ###################
    def on_receive(self, pck):
        self.log(pck['example_variable'] * self.id)


    ###################
    def on_timer_fired(self, name, *args, **kwargs):
        if name == 'TIMER_ARRIVAL':
            self.wake_up()
            self.log('HELLO')
            package = {'dest': wsn.BROADCAST_ADDR, 'example_variable': 5}
            self.send(package)







ROOT_ID = random.randint(0, config.SIM_NODE_COUNT)


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
        px = 50 + x * config.SIM_NODE_PLACING_CELL_SIZE + random.uniform(-1 * config.SIM_NODE_PLACING_CELL_SIZE / 3, config.SIM_NODE_PLACING_CELL_SIZE / 3)
        py = 50 + y * config.SIM_NODE_PLACING_CELL_SIZE + random.uniform(-1 * config.SIM_NODE_PLACING_CELL_SIZE / 3, config.SIM_NODE_PLACING_CELL_SIZE / 3)
        node = sim.add_node(node_class, (px, py))
        node.tx_range = config.NODE_TX_RANGE
        node.logging = True
        node.arrival = random.uniform(0, config.NODE_ARRIVAL_MAX)


sim = wsn.Simulator(
    duration=config.SIM_DURATION,
    timescale=config.SIM_TIME_SCALE,
    visual=config.SIM_VISUALIZATION,
    terrain_size=config.SIM_TERRAIN_SIZE,
    title=config.SIM_TITLE)

# creating random network
create_network(SensorNode, config.SIM_NODE_COUNT)

# start the simulation
sim.run()

# Created 100 nodes at random locations with random arrival times.
# When nodes are created they appear in white
# Activated nodes becomes red
# Discovered nodes will be yellow
# Registered nodes will be green.
# Root node will be black.
# Routers/Cluster Heads should be blue
