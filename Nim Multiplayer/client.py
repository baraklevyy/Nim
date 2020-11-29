# !/usr/bin/python3
import socket
import sys
import struct
import copy
from select import select
from collections import OrderedDict

SERVER_SEND_FORMAT = '>iiiiiii'
SERVER_SEND_LENGTH = 28
SERVER_RECEIVE_LENGTH = 16
SERVER_REC_FORMAT = '>iiii'
PAD = -3
START = -1
END = -2
max_bandwidth = 10000
EOF_LIKE = b''
buff_log = 5
BAD_INPUT = -100
ARBITRARY = 20
ACTIVE = -1
WAITING = -10
REJECTED = -20

################# GLOBAL VARIABLES #####################
queue = OrderedDict()
"""
keys - waiting sockets.
values - all metadata needed for client(Client class)
"""
active_sockets_dict = {}
"""{keys = active sockets , values = Client Class} """

#scapegoat_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # it seems we cannot pass empty socket list to select on Windows

########################################################

################# CLIENT_CLASS #########################
"""A data structure to store clients relevant data"""


class Client:
    def __init__(self, this_socket, this_heaps, address, TYPE=REJECTED):
        self.socket = this_socket
        self.TYPE = TYPE
        self.heaps = this_heaps
        self.accepted = 0
        self.win = 0
        self.stage = 0  # stage == 0 for greeting, == 1 for socket ready to receive from server regular game session, == 2 ready to send to server
        self.receive_end = 0
        self.amount_so_far = 0
        self.data = b""  # using this member instead of 'receive_all'
        self.unpacked_data = ()
        self.address = address

    # ********* FUNCTION MEMBERS ************

    # _______________________________________________________________
    def nonblocking_send(self, data):
        if len(data) == 0:
            return None
        self.amount_so_far += self.socket.send(data[self.amount_so_far:])
        ret = self.is_send_done()
        return ret

    # ________________________________________________________________
    def nonblocking_receive(self):
        self.data += socket.recv(SERVER_RECEIVE_LENGTH - len(self.data))
        return self.is_receive_done(self)

    # ________________________________________________________________
    def is_send_done(self):
        if self.amount_so_far == SERVER_SEND_LENGTH:
            self.amount_so_far = 0
            return True
        return False

    # _____________________________________________________________
    def is_receive_done(self):
        return True if len(self.data) == SERVER_RECEIVE_LENGTH else False

    # ________________________________________________________________
    def nullify_data(self):
        self.data = b""

    # ________________________________________________________________


########################################################
"""
def my_sendall(sock, data):
    if len(data) == 0:
        return None
    ret = sock.send(data)
    return my_sendall(sock, data[ret:])
def recv_data(dest_socket, length):
    data = b''
    remaining_length = length
    while remaining_length:
        current_data = dest_socket.recv(remaining_length)
        if not current_data:
            if data:
                raise Exception('Server returned corrupted data')
            else:
                return data
        data += current_data
        remaining_length -= len(current_data)
    return data
def send_heaps(socket, heaps, accepted, win):
    send_msg = [START, accepted, heaps[0], heaps[1], heaps[2], win, END]
    send_msg = [int(e) for e in send_msg]
    try:
        my_sendall(socket,
                   struct.pack(SERVER_SEND_FORMAT, send_msg[0], send_msg[1], send_msg[2], send_msg[3], send_msg[4],
                               send_msg[5], send_msg[6]))
    except socket.error as exc:
        print("An error occurred: %s\n" % exc)
        sys.exit()
def fill_buff(sock):  # also: return 1 if connection is terminated, and 0 otherwise.\
    buff = ()
    try:
        # raw_data = sock.recv(max_bandwidth)
        raw_data = recv_data(sock, 16)
    except socket.error as exc:
        print("An error occurred: %s\n" % exc)
        sys.exit()
    if raw_data == EOF_LIKE:
        sock.close()
        return 1, buff
    buff = struct.unpack(SERVER_REC_FORMAT, raw_data)
    while not (buff[0] == START and buff[-1] == END):
        try:
            raw_data = recv_data(sock, 16)
        except socket.error as exc:
            print("An error occurred: %s\n" % exc)
            sys.exit()
        if raw_data == EOF_LIKE:
            sock.close()
            return 1, buff
        # buff += struct.unpack(SERVER_REC_FORMAT, sock.recv(max_bandwidth))
        buff += struct.unpack(SERVER_REC_FORMAT, raw_data=recv_data(sock, 16))
    return 0, buff
"""


def fill_buff_MULTIPLAYER(
        client):  # also: return 1 if connection is terminated, 0 if buffer is ready , -1 if buffer not ready yet
    try:
        is_done = client.nonblocking_receive()
    except client.socket.error as exc:
        print("An error occurred: %s\n" % exc)
        """we need to eject this socket from the active_socket_dict"""
        active_sockets_dict.pop(client.socket, None)
    if client.data == EOF_LIKE:
        active_sockets_dict.pop(client.socket, None)
        client.socket.close()
        return 1
    if is_done:
        client.unpacked_data += struct.unpack(SERVER_REC_FORMAT, client.data)
        # client.nullify_data()  # erasing that data from the client
        client.stage = 2  # this socket were in stage 1 i.e recv data and now it should send the corresponding data after server move
        return 0
    return -1


def server_move(heaps):
    new_heaps = heaps
    if heaps[0] >= heaps[1]:
        if heaps[0] >= heaps[2]:
            new_heaps[0] -= 1
        else:
            new_heaps[2] -= 1
    else:
        if heaps[1] >= heaps[2]:
            new_heaps[1] -= 1
        else:
            new_heaps[2] -= 1
    return new_heaps


"""sockets that are in Readable list && in queue pressed 'Q' and exited from game"""


def removing_exited_sockets():
    scapegoat_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # it seems we cannot pass empty socket list to select on Windows
    ordered_sockets = list(queue.keys()) if len(queue) > 0 else [scapegoat_socket]
    read_ready, write_ready, exceptions = select(ordered_sockets, [], [], 0.3)
    for sock_to_remove in read_ready:
        queue.pop(sock_to_remove)


"""moving waiting players from queue to active dictionary"""


def wait_to_active(max_players):
    while (len(active_sockets_dict) < max_players) and (len(queue) > 0):
        current_sock, current_client = queue.popitem(last=False)
        current_client.TYPE = ACTIVE
        active_sockets_dict[current_sock] = current_client


def updating_client(client):
    read_ready_sock = client.socket
    termination, buff = fill_buff_MULTIPLAYER(active_sockets_dict[read_ready_sock])
    if termination:
        active_sockets_dict.pop(read_ready_sock)
    if int(client.buff[1]) == BAD_INPUT:
        client.heaps = server_move(client.heaps)
        if client.heaps == [0, 0, 0]:
            client.accepted = 0
            client.win = 0
        else:
            client.accepted = 0
            client.win = 2
    elif int(client.buff[2]) > int(client.heaps[int(client.buff[1])]):
        client.heaps = server_move(client.heaps)
        if client.heaps == [0, 0, 0]:
            client.accepted = 0
            client.win = 0
        else:
            client.accepted = 0
            client.win = 2
    else:
        client.heaps[int(client.buff[1])] -= int(client.buff[2])
        if client.heaps == [0, 0, 0]:
            client.accepted = 1
            client.win = 1
        else:
            client.heaps = server_move(client.heaps)
        if client.heaps == [0, 0, 0]:
            client.accepted = 1
            client.win = 0
        else:
            client.accepted = 1
            client.win = 0


def send_message(client):
    send_msg = [client.TYPE, client.accepted, client.heaps[0], client.heaps[1], client.heaps[2], client.win, END]
    send_msg = [int(e) for e in send_msg]
    packed_data = struct.pack(SERVER_SEND_FORMAT, send_msg[0], send_msg[1], send_msg[2], send_msg[3], send_msg[4],
                              send_msg[5], send_msg[6])
    try:
        to_next_stage = client.nonblocking_send(
            packed_data)  # figuring-out if in the next loop we have to comeback here cuz we dont have sendall anymore
        if to_next_stage:
            client.stage = 1  # indicating that in the next round we dont have to comeback to the greeting message and we should recv message from client
    except client.socket.error as exc:
        print("An error occurred while sending: %s\n" % exc)
        sys.exit()


def send_greeting(client, first_heaps=[PAD, PAD, PAD]):
    """START BIT is now: client.TYPE and can be 3 different types indicating 3 different cases:
    1. client.TYPE == ACTIVE == -1 : active game against client + sending corresponding greeting message
    2. client.TYPE == WAITING == -10 : socket in the 'waiting-list' + sending WAITING message
    3. client.TYPE == REJECT == -20 : socket should be rejected
    """
    send_msg = [client.TYPE, PAD, first_heaps[0], first_heaps[1], first_heaps[2], 2, END]
    send_msg = [int(e) for e in send_msg]
    packed_data = struct.pack(SERVER_SEND_FORMAT, send_msg[0], send_msg[1], send_msg[2], send_msg[3], send_msg[4],
                              send_msg[5], send_msg[6])
    """
    need to put this in client side
    greeting_type = {FIRST BYTE == ACTIVE: "Now you are playing against the server!\n+heaps",
                     FIRST BYTE == WAITING: "Waiting to play against the server.\n",
                     FIRST BYTE == REJECTED: "You are rejected by the server.\n"}
    """
    """making sure we can send to that client"""
    _, writeable, _ = select([], [client.socket], [], 0.5)
    if client.socket in writeable:
        try:
            to_next_stage = client.nonblocking_send(
                packed_data)  # figuring-out if in the next loop we have to comeback here cuz we dont have sendall anymore
            if to_next_stage:
                client.stage = 1  # indicating that in the next round we dont have to comeback to the greeting message and we should recv message from client
        except client.socket.error as exc:
            print("An error occurred while sending: %s\n" % exc)
            sys.exit()


def main(port, heaps, max_players, max_queue):
    listening_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listening_socket.bind(('', port))
    listening_socket.listen(ARBITRARY)
    #queue[listening_socket] = Client(listening_socket, heaps, 3333,WAITING)
    while True:
        if len(queue) > 0:
            removing_exited_sockets()  # removing sockets that quite from queue
        wait_to_active(max_players)  # moving players from queue to active game
        Readable, _, _ = select([listening_socket], [], [], 0.2)
        if listening_socket in Readable:  # means it is ready to accept another incoming connection
            new_client_socket, new_client_address = listening_socket.accept()  # accept won’t block
            print("Connection from %s has been established!", new_client_address)
            client = Client(new_client_socket, heaps, new_client_address)
            if len(active_sockets_dict) < max_players:  # dictionary to store the active players data
                client.TYPE = ACTIVE
                send_greeting(client, heaps)
                active_sockets_dict[new_client_socket] = client  # dictionary of active sockets
            elif len(active_sockets_dict) >= max_players and len(queue) < max_queue:  # waiting clients
                client.TYPE = WAITING
                send_greeting(client)
                queue[new_client_socket] = client  # ordered insertions
            else:  # reject this client
                send_greeting(client)  # TYPE == REJECT is default for class client

        if len(active_sockets_dict) > 0:
            read_ready, write_ready, _ = select(active_sockets_dict.keys(), active_sockets_dict.keys(), [], 0.5)
            for read_ready_sock in read_ready:  # read-ready sockets
                if 1 == active_sockets_dict[read_ready_sock].stage:  # read_ready_sock.recv() would not block here
                    updating_client(active_sockets_dict[read_ready_sock])

            for write_ready_sock in write_ready:
                if 0 == active_sockets_dict[write_ready_sock].stage:  # didnt finish greeting from previous iteration or move from waiting list to active dict
                    send_greeting(client, heaps)

                elif 2 == active_sockets_dict[write_ready_sock].stage:  # write_ready_sock.send() would not block here
                    send_message(active_sockets_dict[write_ready_sock])


if __name__ == '__main__':
    if len(sys.argv) < 6:
        print("[ERROR] Heaps size & number of concurrent players & max queue size should be supplied ")
        sys.exit()
    na, nb, nc, max_players_num, max_queue_size = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
    main_heaps = [int(na), int(nb), int(nc)]
    main_port = 6444 if (len(sys.argv) < 7) else sys.argv[6]
    main_port = int(main_port)
    main(main_port, main_heaps, int(max_players_num), int(max_queue_size))

