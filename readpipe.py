#Read from a pipe and write to stdout
#Created for testing the pipes for the IRC bot

import sys
import os
import time


def readNextLine(readPipe):
    """Read the next line, halting everything until something comes"""
    while True:
        line = readPipe.readline()
        #If we read from flushed pipe then wait a moment before moving on
        if line == '':
            time.sleep(0.1)
            continue
        return line.rstrip('\n')

def main():
    if len(sys.argv) == 1:
        pipeName = 'pipe_test'
    else:
        pipeName = sys.argv[1]

    if not os.path.exists(pipeName):
        os.mkfifo(pipeName)

    readPipe = open(pipeName, 'r')

    readCount = 0
    while True:
        readCount += 1
        line = readNextLine(readPipe)
        print "%d: %s" % (readCount, line)

    readPipe.close()

if __name__ == '__main__':
    main()