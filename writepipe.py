#Write to a pipe at timed intervals

import sys
import os
import time

pipeName = 'pipe_test'

def sendMessage(msg):
    writePipe = open(pipeName, 'w')
    writePipe.write(msg)
    writePipe.flush()
    writePipe.close()


def main():
    if not os.path.exists(pipeName):
        os.mkfifo(pipeName)

    sendMessage('Hello there\n')
    for i in xrange(100):
        sendMessage('Hello %d\n' % (i,))
    time.sleep(1)
    sendMessage('Goodbye\n')


if __name__ == '__main__':
    main()