#!/usr/bin/python3
import sys
import struct
import wrapper
import threading
import time
from wrapper import recv_from_any_link, send_to_link, get_switch_mac, get_interface_name

def parse_ethernet_header(data):
    # Unpack the header fields from the byte array
    #dest_mac, src_mac, ethertype = struct.unpack('!6s6sH', data[:14])
    dest_mac = data[0:6]
    src_mac = data[6:12]
    
    # Extract ethertype. Under 802.1Q, this may be the bytes from the VLAN TAG
    ether_type = (data[12] << 8) + data[13]

    vlan_id = -1
    # Check for VLAN tag (0x8100 in network byte order is b'\x81\x00')
    if ether_type == 0x8200:
        vlan_tci = int.from_bytes(data[14:16], byteorder='big')
        vlan_id = vlan_tci & 0x0FFF  # extract the 12-bit VLAN ID
        ether_type = (data[16] << 8) + data[17]

    return dest_mac, src_mac, ether_type, vlan_id

def create_vlan_tag(vlan_id):
    # 0x8100 for the Ethertype for 802.1Q
    # vlan_id & 0x0FFF ensures that only the last 12 bits are used
    return struct.pack('!H', 0x8200) + struct.pack('!H', vlan_id & 0x0FFF)

def send_bpdu_every_sec():

    global mac_table
    global vlan_table
    global switch_priority
    global interface_status
    global is_root_bridge
    global interfaces
    global own_bridge_id
    global root_path_cost
    global root_bridge_id

    while True:
        # Send BDPU every second if necessary

        if is_root_bridge:

            bpdu, bpdu_length = create_bpdu(get_switch_mac(), own_bridge_id, root_path_cost, root_bridge_id)
            for i in interfaces:
                i_name = get_interface_name(i)
                i_type = get_interface_type(i_name, vlan_table)

                if i_type == "trunk":
                    send_to_link(i, bpdu, bpdu_length)

        time.sleep(1)

def is_unicast(mac):
    return int(mac.split(":")[0], 16) % 2 == 0


def read_switch_config(switch_id):
    fin = open("./configs/switch{}.cfg".format(switch_id))
    
    # Read each line individually.
    lines = fin.readlines()

    # First line is the switch priority.
    switch_priority = int(lines[0])

    # Initialize VLAN table.
    vlan_table = {}

    # Remove first line (the priority)
    lines.pop(0)

    for line in lines:
        split_line = line.split()

        vlan_id = split_line[1]

        if vlan_id != 'T':
            vlan_id = int(vlan_id)

        vlan_table[split_line[0]] = vlan_id

    return switch_priority, vlan_table

def is_tagged(data):
    # Extract ethertype. Under 802.1Q, this may be the bytes from the VLAN TAG
    ether_type = (data[12] << 8) + data[13]

    vlan_id = -1
    # Check for VLAN tag (0x8100 in network byte order is b'\x81\x00')
    if ether_type == 0x8200:
        vlan_tci = int.from_bytes(data[14:16], byteorder='big')
        vlan_id = vlan_tci & 0x0FFF  # extract the 12-bit VLAN ID

    if vlan_id == -1:
        return False
    return True

def add_vlan_tag(data, length, vlan_id):
    return data[0:12] + create_vlan_tag(vlan_id) + data[12:], length + 4

def remove_vlan_tag(data, length):
    return data[0:12] + data[16:], length - 4

def get_interface_type(interface, vlan_table):
    if vlan_table[interface] == 'T':
        return "trunk"
    return "access"

def forward_frame(data, length, interface, vlan_id):

    i_name = get_interface_name(interface)
    i_type = get_interface_type(i_name, vlan_table)

    # Send only on interfaces that have the same VLAN ID
    # or on trunk interfaces.
    in_vlan = (vlan_table[i_name] == vlan_id) or (vlan_table[i_name] == 'T')

    if not in_vlan or interface_status[i_name] == "blocking":
        return 

    # If sending on a trunk interface, add the vlan tag.
    if i_type == "trunk":
        data, length = add_vlan_tag(data, length, vlan_id)

    send_to_link(interface, data, length)

def create_bpdu(src_mac, bpdu_own_bridge_id, bpdu_root_path_cost, bpdu_root_bridge_id):

    # Size         6          6             4              4                4
    # Format    dest_mac | src_mac | own_bridge_id | root_path_cost | root_bridge_id
    format = "!6s6sIII"

    dest_mac = b"\x01\x80\xC2\x00\x00\x00"
    bpdu = struct.pack(format, dest_mac, src_mac, bpdu_own_bridge_id, bpdu_root_path_cost, bpdu_root_bridge_id)

    return bpdu, len(bpdu) 


def is_bpdu(dest_mac):
    if dest_mac == "01:80:c2:00:00:00":
        return True
    return False

def process_received_bpdu(data, length, interface):
    
    global mac_table
    global vlan_table
    global switch_priority
    global interface_status
    global is_root_bridge
    global interfaces
    global own_bridge_id
    global root_path_cost
    global root_bridge_id
    global root_port

    # Size         6          6             4               4               4
    # Format    dest_mac | src_mac | own_bridge_id | root_path_cost | root_bridge_id
    format = "!6s6sIII"
    
    dest_mac, src_mac, bpdu_own_bridge_id, bpdu_root_path_cost, bpdu_root_bridge_id = struct.unpack(format, data)

    if bpdu_root_bridge_id < root_bridge_id:
        
        root_bridge_id = bpdu_root_bridge_id
        root_path_cost = bpdu_root_path_cost + 10
        root_port = interface

        if is_root_bridge:
            
            for i in interfaces:
                i_name = get_interface_name(i)
                i_type = get_interface_type(i_name, vlan_table)

                if i_type != "access" and i != root_port:
                    interface_status[i_name] = "blocking"

            is_root_bridge = False
            root_port_name = get_interface_name(root_port)

        if interface_status[root_port_name] == "blocking":
            interface_status[root_port_name] = "listening"

        # Update and forward this BPDU to all other trunk ports.
        bpdu, bpdu_length = create_bpdu(get_switch_mac(), own_bridge_id, root_path_cost, bpdu_root_bridge_id)
        for i in interfaces:
            i_name = get_interface_name(i)
            i_type = get_interface_type(i_name, vlan_table)

            if i_type == "trunk":
                send_to_link(i, bpdu, bpdu_length)

            

    elif bpdu_root_bridge_id == root_bridge_id:

        if interface == root_port and bpdu_root_path_cost + 10 < root_path_cost:
            root_path_cost = bpdu_root_path_cost + 10

        elif interface != root_port:

            if bpdu_root_path_cost > root_path_cost:
                if interface_status[get_interface_name(interface)] != "listening":
                    interface_status[get_interface_name(interface)] == "listening"

    elif bpdu_own_bridge_id == own_bridge_id:
            
        interface_status[get_interface_name(interface)] = "blocking"
        
        
    if own_bridge_id == root_bridge_id:
        for i in interfaces:
            interface_status[get_interface_name(i)] = "listening"





mac_table = {}
vlan_table = {}
switch_priority = None
interface_status = {}

interfaces = {}

is_root_bridge = True

own_bridge_id = None
root_path_cost = None
root_bridge_id = None
root_port = None

def main():

    global mac_table
    global vlan_table
    global switch_priority
    global interface_status
    global is_root_bridge
    global interfaces
    global own_bridge_id
    global root_path_cost
    global root_bridge_id
    global root_port


    # init returns the max interface number. Our interfaces
    # are 0, 1, 2, ..., init_ret value + 1
    switch_id = sys.argv[1]

    
    num_interfaces = wrapper.init(sys.argv[2:])
    interfaces = range(0, num_interfaces)
    
     # Get switch VLAN config.
    switch_priority, vlan_table = read_switch_config(switch_id)


    own_bridge_id = switch_priority
    root_path_cost = 0
    root_bridge_id = switch_priority

    #print("# Starting switch with id {}".format(switch_id), flush=True)
    #print("[INFO] Switch MAC", ':'.join(f'{b:02x}' for b in get_switch_mac()))

    # Create and start a new thread that deals with sending BDPU
    t = threading.Thread(target=send_bpdu_every_sec)
    t.start()

    # Start all trunk ports in blocking mode and rest in listening mode.
    for i in interfaces:
        
        i_name = get_interface_name(i)
        i_type = get_interface_type(i_name, vlan_table)

        if i_type == "trunk":
            interface_status[i_name] = "blocking"
        else:
            interface_status[i_name] = "listening"

    # Send Hello BPDU.
    hello_bpdu, hello_bpdu_length = create_bpdu(get_switch_mac(), switch_priority, 0, switch_priority)
    
    for i in interfaces:
        send_to_link(i, hello_bpdu, hello_bpdu_length)

    while True:

        interface, data, length = recv_from_any_link()
        dest_mac, src_mac, ethertype, vlan_id = parse_ethernet_header(data)

        # Print the MAC src and MAC dst in human readable format
        dest_mac = ':'.join(f'{b:02x}' for b in dest_mac)
        src_mac = ':'.join(f'{b:02x}' for b in src_mac)

        #print(f'Destination MAC: {dest_mac}')
        #print(f'Source MAC: {src_mac}')
        #print(f'EtherType: {ethertype}')
        #print("Received frame of size {} on interface {}".format(length, interface), flush=True)

        interface_name = get_interface_name(interface)
        interface_type = get_interface_type(interface_name, vlan_table)
     
        
        if vlan_id == -1 and interface_type == "access":

            # Packet came from a host to the switch, assign a VLAN ID to it.
            vlan_id = vlan_table[interface_name]
        
        elif interface_type == "trunk" and not is_bpdu(dest_mac):

            # Packet came from a trunk interface, remove its VLAN tag.
            data, length = remove_vlan_tag(data, length)

        # Associate the packet's source mac with the interface it
        # was received on. 
        mac_table[src_mac] = interface
        

        if is_unicast(dest_mac):
            if dest_mac in mac_table:
                forward_frame(data, length, mac_table[dest_mac], vlan_id)

            else:
                for i in interfaces:
                    if i != interface:
                        forward_frame(data, length, i, vlan_id)
        else:

            if is_bpdu(dest_mac):
                process_received_bpdu(data, length, interface)
                continue

            for i in interfaces:
                if i != interface:
                    forward_frame(data, length, i, vlan_id)
                    


if __name__ == "__main__":
    main()
