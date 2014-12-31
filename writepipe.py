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

    #sendMessage('TheAxeMan:Hello ;)Kappa __Kappa\n')
    #for i in xrange(4):
    #    sendMessage('Hello %d\n' % (i,))
    #time.sleep(5)
    sendMessage('TheAxeMan:Speak up red!o_O This fox is a tricky fox.xx\n')
    sendMessage('<red>:My lines! ResidentSleeper\n')


if __name__ == '__main__':
    main()