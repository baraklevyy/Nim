# !/usr/bin/python3
import socket
import sys
import struct
import copy
from select import select
from collections import OrderedDict

##################################
#            DEFINES             #
##################################
SERVER_SEND_FORMAT = '>iiiiiii'
SERVER_SEND_LENGTH = 28
SERVER_REC_FORMAT = '>iiii'
SERVER_RECEIVE_LENGTH = 16
START = -1
END = -2
PAD = -3
EOF_LIKE = b''
BAD_INPUT = -100
ARBITRARY = 20
ACTIVE_GREETING = -5
ACTIVE = -1
WAITING = -10
REJECTED = -20
CLIENT_WIN = 1
CLIENT_LOSE = 0
##################################
#        GLOBAL VARIABLES        #
##################################
""" keys - waiting sockets.
    values - all metadata needed for client(Client class)"""
queue = OrderedDict()
""" {keys = ACTIVE sockets , values = Client Class} """
active_sockets_dict = {}
##################################
#           CLIENT               #
##################################
"""A data structure to store clients relevant data"""
class Client:
    def __init__(self, this_socket, this_heaps, TYPE=REJECTED):
        self.socket = this_socket
        self.TYPE = TYPE
        self.heaps = this_heaps
        self.accepted = 0
        self.win = 0
        self.stage = 0  # stage == 0 for greeting, == 1 for socket ready to receive from server regular game session, == 2 ready to send to server
        self.amount_so_far = 0
        self.data = b''  # using this member instead of 'receive_all'
        self.unpacked_data = ()

    # ********* FUNCTION MEMBERS ************

    def nonblocking_send(self, data):
        """
        socket nonblocking send - using this func after socket received from select as ready to recv.
        handling error in case of sudden shutdown of the client
        :param data:
        :return: None if no data to send
                 -1 if exception thrown and caught
        """
        try:
            if len(data) == 0:
                return None
            self.amount_so_far += self.socket.send(data[self.amount_so_far:])
        except Exception as exc:
            active_sockets_dict.pop(self.socket, None)
            self.socket.close()
            print("An error occurred: %s\n" % exc)
            return -1
        ret = self.is_send_done()
        return ret

    # ***********************************************
    def nonblocking_receive(self):
        try:
            self.data += self.socket.recv(SERVER_RECEIVE_LENGTH - len(self.data))
        except:
            print("An error occurred while receiving\n")
            self.socket.close()
            active_sockets_dict.pop(self.socket, None)
            return -1
        ret = self.is_receive_done()
        return ret

    # ***********************************************
    def is_send_done(self):
        if self.amount_so_far == SERVER_SEND_LENGTH:
            self.amount_so_far = 0
            return True
        return False

    # ***********************************************
    def is_receive_done(self):
        return True if len(self.data) == SERVER_RECEIVE_LENGTH else False

    # ***********************************************
    def nullify_data(self):
        self.data = b''

    # ***********************************************
def fill_buff_MULTIPLAYER(client):
    """
    receiving data from client and unpacked it
    :param client:
    :return: -1 if exception throw in recv func and we know that socket handling occured before
              1 if client socket send shutdown - in this case we have to eject socket from dict and close the socket
              0 life's good
              2 no error but doesnt receive all data in  that iteration.

    """
    is_done = client.nonblocking_receive()
    if is_done == -1: #exception already close and eject from common dictionary
        return -1
    if client.data == EOF_LIKE:
        return 1
    if is_done:
        client.unpacked_data = ()
        client.unpacked_data += struct.unpack(SERVER_REC_FORMAT, client.data)
        client.nullify_data()  # erasing that data from the client
        client.stage = 2  # this socket were in stage 1 i.e recv data and now it should send the corresponding data after server move
        return 0
    return 2


def server_move(heaps):
    """
    Distracting 1 unit from biggest heap
    :param heaps:
    :return: heaps after modifications
    """
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
    """
    Removing sockets that already exsited from the waiting queue
    :return: None
    """
    ordered_sockets = list(queue.keys())
    read_ready, write_ready, exceptions = select(ordered_sockets, [], [], 0.3)
    for sock_to_remove in read_ready:
        queue.pop(sock_to_remove)

def wait_to_active(max_players):
    """
    moving waiting sockets from waiting queue to the active clients dictionary if possible.
    moving ordered to FIFO rule
    :param max_players:
    :return: None
    """
    while (len(active_sockets_dict) < max_players) and (len(queue) > 0):
        current_sock, current_client = queue.popitem(last=False)
        current_client.TYPE = -5 # ACTIVE_GREETING
        active_sockets_dict[current_sock] = current_client


def updating_client(client):
    """
    Receiving data from client and updating the corresponding data into the specific client variable.
    Removing socket if neeeded
    :param client:
    :return: updated client member variables
    """
    termination = fill_buff_MULTIPLAYER(active_sockets_dict[client.socket])
    if termination == -1:
        return
    if termination == 2:
        return
        #not all data received in this iteration
    if termination == 1:
        active_sockets_dict.pop(client.socket)
        client.socket.close()
    elif int(client.unpacked_data[1]) == BAD_INPUT:
        client.heaps = server_move(client.heaps)
        if client.heaps == [0, 0, 0]:
            client.accepted = 0
            client.win = CLIENT_LOSE
        else:
            client.accepted = 0
            client.win = 2

    elif int(client.unpacked_data[2]) > int(client.heaps[int(client.unpacked_data[1])]): # input bigger than possible
        client.heaps = server_move(client.heaps)
        if client.heaps == [0, 0, 0]:
            client.accepted = 0
            client.win = CLIENT_LOSE
        else:
            client.accepted = 0
            client.win = 2
    else:
        client.heaps[int(client.unpacked_data[1])] -= int(client.unpacked_data[2])
        if client.heaps == [0, 0, 0]:
            client.accepted = 1
            client.win = CLIENT_WIN
        else:
            client.heaps = server_move(client.heaps)
            if client.heaps == [0, 0, 0]:
                client.accepted = 1
                client.win = CLIENT_LOSE
            else:
                client.accepted = 1
                client.win = 2


def send_message(client):
    """
    packing client raw_data to send(after the server calculations) and send it using the correspond socket
    :param client:
    :return:None
    """
    send_msg = [client.TYPE, client.accepted, client.heaps[0], client.heaps[1], client.heaps[2], client.win, END]
    send_msg = [int(e) for e in send_msg]
    packed_data = struct.pack(SERVER_SEND_FORMAT, send_msg[0], send_msg[1], send_msg[2], send_msg[3], send_msg[4],
                              send_msg[5], send_msg[6])

    to_next_stage = client.nonblocking_send(packed_data)  # figuring-out if in the next loop we have to comeback here cuz we dont have sendall anymore
    if to_next_stage:
        client.stage = 1  # indicating that in the next round we dont have to comeback to the greeting message and we should recv message from client


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
        to_next_stage = client.nonblocking_send(packed_data)  # figuring-out if in the next loop we have to comeback here cuz we dont have sendall anymore
        if to_next_stage == True:
            if client.TYPE == ACTIVE_GREETING:
                client.TYPE = ACTIVE
                client.stage = 1  # indicating that in the next round we dont have to comeback to the greeting message and we should recv message from client
        if to_next_stage == -1:
            return 0
        return 1


def main(port, heaps, max_players, max_queue):
    """
    main loop.
    listening_socket receiving accepts requests from clients .
    Server using select in order to deal with multiple clients
    :param port: default of designated port
    :param heaps: server initially choose heaps sizes
    :param max_players: max concurrent players
    :param max_queue: max clients can wait in queue
    :return: None
    """
    listening_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listening_socket.bind(('', port))
    listening_socket.listen(ARBITRARY)
    while True:
        if len(queue) > 0:
            removing_exited_sockets()  # removing sockets that quite from queue
        wait_to_active(max_players)  # moving players from queue to active game
        Readable, _, _ = select([listening_socket], [], [], 0.2)
        if listening_socket in Readable:  # means it is ready to accept another incoming connection
            new_client_socket, new_client_address = listening_socket.accept()  # accept won\92t block
            print("Connection from %s has been established!", new_client_address)
            deep_clone_heaps = [heaps[0], heaps[1], heaps[2]]
            client = Client(new_client_socket, deep_clone_heaps)
            if len(active_sockets_dict) < max_players:  # dictionary to store the active players data
                client.TYPE = ACTIVE_GREETING
                abruptly_quited = send_greeting(client, heaps)
                if abruptly_quited == 1:
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

        if len(active_sockets_dict) > 0:
            _, write_ready, _ = select([], active_sockets_dict.keys(), [], 0.5)
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
