## network properties
BROADCAST_NET_ADDR = 255
BROADCAST_NODE_ADDR = 255
NEIGHBOR_TABLE_HOP = 2
NEIGHBOR_REQUEST_INTERVAL = 200  # simulation time units;
ENABLE_MESH_ROUTING = True
CLUSTER_HEAD_NOMINATION_INTERVAL = 10  # simulation time units;
CLUSTER_HEAD_TX_POWER_CHECK_INTERVAL = 200  # simulation time units;
PACK_LOST_RATE = 0.1  # packet lost rate [0..1]

## node properties
NODE_TX_RANGE = 120  # transmission range of nodes
NODE_ARRIVAL_MAX = 200  # max time to wake up
NODE_MAX_CHILD = 40  # max child nodes
NODE_TX_POWER_LEVELS = [40,45,50,55,60,65,70,75,80,86,90,95,100,105,110,115,120,125,130,135,140]  # transmission power levels

## simulation properties
SIM_NODE_COUNT = 100  # node count in simulation
SIM_NODE_PLACING_CELL_SIZE = 75  # cell size to place one node
SIM_DURATION = 5000  # simulation Duration in seconds
SIM_TIME_SCALE = 0.00001  #  The real time dureation of 1 second simualtion time
SIM_TERRAIN_SIZE = (1400, 1400)  #terrain size
SIM_TITLE = 'Data Collection Tree'  # title of visualization window
SIM_VISUALIZATION = True  # visualization active
SCALE = 1  # scale factor for visualization


## application properties
HEARTH_BEAT_TIME_INTERVAL = 100
REPAIRING_METHOD = 'FIND_ANOTHER_PARENT' # 'ALL_ORPHAN', 'FIND_ANOTHER_PARENT'
EXPORT_CH_CSV_INTERVAL = 10  # simulation time units;
EXPORT_NEIGHBOR_CSV_INTERVAL = 10  # simulation time units;
RANDOM_PACKET_TIME_INTERVAL = (50, 150)  # min, max time interval to send random data packet