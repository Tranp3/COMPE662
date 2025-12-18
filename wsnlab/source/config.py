## network properties
BROADCAST_NET_ADDR = 255
BROADCAST_NODE_ADDR = 255
NEIGHBOR_TABLE_HOP = 2
NEIGHBOR_REQUEST_INTERVAL = 200  # simulation time units;
ENABLE_MESH_ROUTING = True
CLUSTER_HEAD_NOMINATION_INTERVAL = 15  # simulation time units;
CLUSTER_HEAD_TX_POWER_CHECK_INTERVAL = 500  # simulation time units;
PACK_LOST_RATE = 0.1  # packet lost rate [0..1]
NUM_NODE_KILL = 0 # number of nodes to be killed during simulation
TIME_TO_KILL_NODE = 1000  # simulation time units; when to kill nodes
CHECK_NEIGHBOR_TIMEOUT_INTERVAL = 30  # simulation time units; interval to check neighbor timeout
NEIGHBOR_TIMEOUT = 100  # simulation time units; timeout duration for neighbors
PARENT_NEIGHBOR_TIMEOUT = 100  # simulation time units; faster timeout for parent/gateway nodes (critical path)
DEREGISTER_COOLDOWN = 5  # simulation time units; suppress duplicate deregisters while in-flight
ROUTING_FAILURE_THRESHOLD = 3  # max consecutive routing failures before marking route as dead
NODE_POWER_MODEL = True
CHECK_OVERLAP_INTERVAL = 100

## power model properties (only used if NODE_POWER_MODEL = True)
NODE_BATTERY_CAPACITY = 6000  # 21600 for 2000mA battery energy battery capacity for non-root nodes
NODE_RX_CURRENT = .2400384  # energy consumption when receiving a packet
# TX current consumption by power level (mA per packet)
NODE_TX_CURRENT = {
    30: .108528,
    60: .1264032,
    90: .140448,
    120: .178752,
    150: .2221632
}

## node properties
NODE_TX_RANGE = 150  # transmission range of nodes
NODE_ARRIVAL_MAX = 200  # max time to wake up
NODE_MAX_CHILD = 40  # max child nodes
NODE_TX_POWER_LEVELS = [40,80,120,160,200]  # transmission power levels

## simulation properties
SIM_NODE_COUNT = 75  # node count in simulation
SIM_NODE_PLACING_CELL_SIZE = 75  # cell size to place one node
SIM_DURATION = 10000  # simulation Duration in seconds
SIM_TIME_SCALE = 0.0001  #  The real time dureation of 1 second simualtion time
SIM_TERRAIN_SIZE = (1400, 1400)  #terrain size
SIM_TITLE = 'Data Collection Tree'  # title of visualization window
SIM_VISUALIZATION = True  # visualization active
SCALE = 1  # scale factor for visualization


## application properties
HEARTH_BEAT_TIME_INTERVAL = 30
REPAIRING_METHOD = 'FIND_ANOTHER_PARENT' # 'ALL_ORPHAN', 'FIND_ANOTHER_PARENT'
EXPORT_CH_CSV_INTERVAL = 10  # simulation time units;
EXPORT_NEIGHBOR_CSV_INTERVAL = 10  # simulation time units;
RANDOM_PACKET_TIME_INTERVAL = (50, 150)  # min, max time interval to send random data packet