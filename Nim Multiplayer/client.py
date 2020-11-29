#!/usr/bin/python3
import socket
import sys
import struct

CLIENT_SEND_FORMAT = '>iiii'
CLIENT_REC_FORMAT = '>iiiiiii'
PAD = -3
START = -1
END = -2
EOF_LIKE = b''
max_bandwidth = 10000
BAD_INPUT = -100


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


def show_heaps(rec_msg):  # also: returns 0 in case game is over, 1 otherwise.

    if rec_msg[1] == 1:
        print('Move accepted:\n')
    elif rec_msg[1] == 0:
        print('illegal move:\n')
    else:
        print("")
    print("Heap A: %d\nHeap B: %d\nHeap C: %d\n" % (rec_msg[2], rec_msg[3], rec_msg[4]))

    if rec_msg[5] == 1:
        print('You win!\n')
    elif rec_msg[5] == 0:
        print('Server win!\n')
    else:
        print("Your turn:\n")

    if rec_msg[5] in [0, 1]:
        return 0
    else:
        return 1


def fill_buff(sock):  # also: return 1 if connection is terminated, and 0 otherwise.\
    buff = ()
    try:
        # raw_data = sock.recv(max_bandwidth)
        raw_data = recv_data(sock, 28)

    except socket.error as exc:
        print("An error occurred: %s\n" % exc)
        sys.exit()

    if raw_data == EOF_LIKE:
        # sock.shutdown(socket.SHUT_RDWR)
        sock.close()
        return 1, buff
    buff = struct.unpack(CLIENT_REC_FORMAT, raw_data)
    while not (buff[0] == START and buff[-1] == END):
        try:
            raw_data = recv_data(sock, 28)
            # raw_data = sock.recv(max_bandwidth)
        except socket.error as exc:
            print("An error occurred: %s\n" % exc)
            sys.exit()
        if raw_data == EOF_LIKE:
            # sock.shutdown(socket.SHUT_RDWR)
            sock.close()
            return 1, buff
        # buff += struct.unpack(CLIENT_REC_FORMAT, sock.recv(max_bandwidth))
        buff += struct.unpack(CLIENT_REC_FORMAT, raw_data=recv_data(sock, 28))
    return 0, buff


def terminate(sock):
    sock.shutdown(socket.SHUT_RDWR)
    sock.close()
    sys.exit()


def send_command(socket):
    is_legal = True
    user_input = list(input().split())
    abc = ['A', 'B', 'C']
    send_msg = [START, PAD, PAD, END]
    if len(user_input) == 1 and user_input[0] == 'Q':
        terminate(socket)
    if len(user_input) <= 1 or len(user_input) > 2:
        is_legal = False
    if is_legal:
        heap = user_input[0]
        amount = user_input[1]
        if heap not in abc or amount in abc or int(amount) < 0:
            is_legal = False
    send_msg[1] = abc.index(heap) if is_legal else BAD_INPUT
    send_msg[2] = amount if is_legal else BAD_INPUT
    try:
        my_sendall(socket,
                   struct.pack(CLIENT_SEND_FORMAT, int(send_msg[0]), int(send_msg[1]), int(send_msg[2]),
                               int(send_msg[3])))

    except socket.error as exc:
        print("An error occurred: %s\n" % exc)
        sys.exit()


def main(hostname, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((hostname, port))
    except socket.error as exc:
        print("An error occurred: %s\n" % exc)
        sys.exit()
    while True:
        server_side_ter, buff = fill_buff(s)
        if server_side_ter:
            print("Disconnected from server\n")
            s.close()
            sys.exit()
        if not show_heaps(buff):
            terminate(s)
        send_command(s)


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