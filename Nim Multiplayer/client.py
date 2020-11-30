# !/usr/bin/python3
import socket
import sys
import struct
from select import select

CLIENT_SEND_FORMAT = '>iiii'
CLIENT_REC_FORMAT = '>iiiiiii'
PAD = -3
START = -1
END = -2
EOF_LIKE = b''
max_bandwidth = 10000
BAD_INPUT = -100
GREETING = -5
ACTIVE_GREETING = -5
ACTIVE = -1
WAITING = -10
REJECTED = -20
WIN = 1
LOSE = 0
SERVER_SEND_LENGTH = 28
SERVER_RECEIVE_LENGTH = 16
connected_socket_dict = {}
SEND_READY = 2
RECEIVE_READY = 1

class Client:
    def __init__(self, this_socket):
        self.socket = this_socket
        self.stage = RECEIVE_READY  # stage == 1 for socket ready to receive from server regular game session, == 2 ready to send to server
        self.amount_so_far = 0
        self.data = b''  # using this member instead of 'receive_all'
        self.unpacked_data = ()


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
        self.data += self.socket.recv(SERVER_SEND_LENGTH - len(self.data))
        ret = self.is_receive_done()
        return ret

    # ________________________________________________________________
    def is_send_done(self):
        if self.amount_so_far == SERVER_RECEIVE_LENGTH:
            self.amount_so_far = 0
            return True
        return False

    # _____________________________________________________________
    def is_receive_done(self):
        return True if len(self.data) == SERVER_SEND_LENGTH else False

    # ________________________________________________________________
    def nullify_data(self):
        self.data = b''

    # ________________________________________________________________



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


def show_heaps(rec_msg):  # also: returns 0 in case game is over or server rejection, 1 for continue game flow, -1 if WAITING mode

    if rec_msg[0] == WAITING:
        print('Waiting to play against the server.\n')
        return -1
    if rec_msg[0] == REJECTED:
        print('You are rejected by the server.\n')
        return 0

    if rec_msg[0] == ACTIVE_GREETING:
        print('Now you are playing against the server!\n')
    elif rec_msg[1] == 1:
        print('Move accepted:\n')
    elif rec_msg[1] == 0:
        print('illegal move:\n')
    else:
        print("")
    print("Heap A: %d\nHeap B: %d\nHeap C: %d\n" % (rec_msg[2], rec_msg[3], rec_msg[4]))

    if rec_msg[5] == WIN:
        print('You win!\n')
    elif rec_msg[5] == LOSE:
        print('Server win!\n')
    else:
        print("Your turn:\n")

    if rec_msg[5] in [LOSE, WIN]:
        return 0
    else:
        return 1


def fill_buff(client):  # # return 1 if connection is terminated, 0 if buffer is ready , -1 if buffer not ready yet
    try:
        is_done = client.nonblocking_receive()
        #client.data += recv_data(client.socket, SERVER_SEND_LENGTH)

    except client.socket.error as exc:
        print("An error occurred: %s\n" % exc)
        sys.exit()

    if client.data == EOF_LIKE: # server fall
        client.socket.close()
        return 1
    if is_done:
        client.stage = SEND_READY
        client.unpacked_data = ()
        client.unpacked_data = struct.unpack(CLIENT_REC_FORMAT, client.data)
        client.data = b''
        return 0
    return -1


def terminate(sock):
    sock.shutdown(socket.SHUT_RDWR)
    sock.close()
    sys.exit()


def send_command(client):
    is_legal = True
    user_input = list(input().split())
    abc = ['A', 'B', 'C']
    send_msg = [START, PAD, PAD, END]
    if len(user_input) == 1 and user_input[0] == 'Q':
        terminate(client.socket)
    if len(user_input) <= 1 or len(user_input) > 2:
        is_legal = False
    if is_legal:
        heap = user_input[0]
        amount = user_input[1]
        if heap not in abc or amount in abc or int(amount) < 0:
            is_legal = False
    send_msg[1] = abc.index(heap) if is_legal else BAD_INPUT
    send_msg[2] = amount if is_legal else BAD_INPUT
    data_to_send = struct.pack(CLIENT_SEND_FORMAT, int(send_msg[0]), int(send_msg[1]), int(send_msg[2]), int(send_msg[3]))
    try:
        is_done_sending = client.nonblocking_send(data_to_send)
        if is_done_sending:
            client.stage = RECEIVE_READY

    except client.socket.error as exc:
        print("An error occurred: %s\n" % exc)
        sys.exit()


def main(hostname, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client = Client(s)
    try:
        s.connect((hostname, port))
    except socket.error as exc:
        print("An error occurred: %s\n" % exc)
        sys.exit()
    while True:
        #read_ready, write_ready, _ = select([sys.stdin, s], [s], [], 0.5)
        read_ready, write_ready, _ = select([s], [s], [], 0.5)

        for obj in read_ready:
            if obj == sys.stdin:
                quit_game = s.read(1)
                if quit_game == 'Q':
                    terminate(s)

            if obj == s and client.stage == RECEIVE_READY:
                server_side_ter = fill_buff(client)
                if server_side_ter:
                    print("Disconnected from server\n")
                    sys.exit()
                if server_side_ter == 0: #succeed to receive all data from server
                    if not show_heaps(client.unpacked_data): # WIN\LOSE\REJECTED case
                        terminate(s)

        if s in write_ready and client.stage == SEND_READY:
            send_command(client)


if __name__ == '__main__':
    hostname, port = "", 0
    if len(sys.argv) < 2:
        hostname = socket.gethostname()
        port = 6444
    if len(sys.argv) == 2:
        hostname = sys.argv[1]
        port = 6444
    if len(sys.argv) > 2:
        hostname, port = socket.gethostbyname((sys.argv[1])), sys.argv[2]

    port = int(port)
    main(hostname, port)
