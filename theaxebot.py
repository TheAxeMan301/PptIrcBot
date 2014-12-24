#IRC and yaml reading bot

import irc.client
import sys
import logging
import re
import yaml
import os
import time
from threading import Thread
from Queue import Queue

#Setting the global logger to debug gets all sorts of irc debugging
#logging.getLogger().setLevel(logging.DEBUG)

#Local debugging that can be easily turned off
#from logging import debug
def debug(msg):
    print msg

IrcServer = 'irc.freenode.net'
IrcNick = 'TheAxeBot'
IrcChannel = '#lsnes'

ReplayPipeName = 'replay_pipe'
TasbotPipeName = 'tasbot_pipe'
ScreenPlayFileName = 'screenplay.txt'

def writeToPipe(writePipe, msg):
    """Utility function to write a message to a pipe.
       First add a newline if it doesn't have one.
       Then write the message and flush the pipe.
    """
    if not msg.endswith('\n'):
        msg += '\n'
    writePipe.write(msg)
    writePipe.flush()


class ReplayTextThread(Thread):
    """This thread grabs strings off the queue and writes them to the
       pipe that the replay script should be reading from.
       This ensures thread safety between the multiple threads that need
       to write to that pipe.
       It will never stop so do not wait for it!
    """
    def __init__(self, replayQueue):
        super(ReplayTextThread, self).__init__()

        self.replayQueue = replayQueue

    def run(self):
        if not os.path.exists(ReplayPipeName):
            os.mkfifo(ReplayPipeName)
        writePipe = open(ReplayPipeName, 'w')
        while True:
            msg = self.replayQueue.get()
            writeToPipe(writePipe, msg)

class ScreenPlayThread(Thread):
    def __init__(self, ircBot):
        super(ScreenPlayThread, self).__init__()

        self.ircBot = ircBot
        self.script = []
            
    def readScreenPlay(self, filename):
        screenPlayFile = open(filename)
        rawScript = screenPlayFile.readlines()
        screenPlayFile.close()
        
        for line in rawScript:
            #Commented lines with #
            if re.match("\s*#", line):
                continue
            words = line.split()
            if len(words) < 3:
                continue
            delay = float(words[0])
            speaker = words[1].lower()
            m = re.match(words[0] + '\s+' + words[1] + '\s+(.+)', line)
            if not m:
                continue
            text = m.groups()[0]
            if text == '':
                continue
            self.script.append((delay, speaker, text))

    def run(self):
        if not os.path.exists(TasbotPipeName):
            os.mkfifo(TasbotPipeName)
        tasBotPipe = open(TasbotPipeName, 'w')

        for delay, speaker, text in self.script:
            time.sleep(delay)
            if speaker == 'red':
                self.ircBot.replayQueue.put("<red>:" + text)
                self.ircBot.connection.privmsg(IrcChannel, text)
            if speaker == 'tasbot':
                writeToPipe(tasBotPipe, text)


class PptIrcBot(irc.client.SimpleIRCClient):
    def __init__(self):
        irc.client.SimpleIRCClient.__init__(self)
        self.badWords = self.getBadWords('bad-words.txt')
        #Precompiled tokenizing regex
        self.splitter = re.compile(r'[^\w]+')
        self.urlregex = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
        self.otherbadregex = re.compile(r'\.((com)|(org)|(net))')
        self.replayQueue = Queue()

    def on_welcome(self, connection, event):
        connection.join(IrcChannel)

    def on_join(self, connection, event):
        """Fires on joining the channel.
           This is when the action starts.
        """
        self.replayThread = ReplayTextThread(self.replayQueue)
        self.replayThread.start()

        self.screenPlayThread = ScreenPlayThread(self)
        self.screenPlayThread.start()

    def on_disconnect(self, connection, event):
        sys.exit(0)

    #def _dispatcher(self, connection, event):
        #debug(event.type)
        #irc.client.SimpleIRCClient._dispatcher(self, connection, event)

    def on_pubmsg(self, connection, event):
        debug("pubmsg from %s: %s" % (event.source, event.arguments[0]))
        text = event.arguments[0]
        words = self.splitter.split(text)
        sender = event.source.split('!')[0]

        #Check for non-ascii characters
        try:
            text.decode('ascii')
        except (UnicodeDecodeError, UnicodeEncodeError):
            self.connection.privmsg(IrcChannel, "Naughty " + sender + " (not ascii)")
            return

        if self.urlregex.search(text):
            self.connection.privmsg(IrcChannel, "Naughty " + sender + " (url)")
            return

        if self.otherbadregex.search(text):
            self.connection.privmsg(IrcChannel, "Naughty " + sender + " (url-like)")
            return

        #We probably also want to filter some typically non-printing ascii chars:
        #[18:12] <@Ilari> Also, one might want to drop character codes 0-31 and 127. And then map the icons to some of those.

        if any(word in self.badWords for word in words):
            self.connection.privmsg(IrcChannel, "Naughty " + sender + " (bad word)")
            return
        self.replayQueue.put(sender + ':' + text)

    def getBadWords(self, filename):
        badWords = open(filename)
        badWordList = set([word.strip() for word in badWords.readlines()])
        if '' in badWordList:
            badWordList.remove('')
        badWords.close()
        return badWordList


def main():
    if ':' in IrcServer:
        try:
            server, port = IrcServer.split(":")
            port = int(port)
        except Exception:
            print("Error: Bad server:port specified")
            sys.exit(1)
    else:
        server = IrcServer
        port = 6667

    c = PptIrcBot()

    try:
        c.connect(server, port, IrcNick)
    except irc.client.ServerConnectionError as x:
        print(x)
        sys.exit(1)
    c.start()

if __name__ == "__main__":
    main()