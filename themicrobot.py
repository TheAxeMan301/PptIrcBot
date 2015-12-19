#!/usr/bin/env python2.7

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
from subprocess import call

#Setting the global logger to debug gets all sorts of irc debugging
#logging.getLogger().setLevel(logging.DEBUG)

#Local debugging that can be easily turned off
#from logging import debug


def debug(msg):
    try:
        print msg
    except UnicodeEncodeError:
        pass

#debug = logging.critical

settingsFile = open("settings.yaml")
settings = yaml.load(settingsFile)
settingsFile.close()

IrcServer = settings.get('IrcServer', 'irc.freenode.net')
IrcNick = settings.get('IrcNick', 'TheAxeBot')
IrcPassword = settings.get('IrcPassword', None)
IrcChannel = settings.get('IrcChannel', '#lsnes')

ReplayPipeName = settings.get('ReplayPipeName', 'replay_pipe')
TasbotPipeName = settings.get('TasbotPipeName', 'tasbot_pipe')
ScreenPlayFileName = settings.get('ScreenPlayFileName', 'screenplay.txt')

TasbotPipeEnable = settings.get('TasbotPipeEnable', False)
TasbotEspeakEnable = settings.get('ScreenPlayFileName', True)


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
        self.readScreenPlay(ScreenPlayFileName)

    def readScreenPlay(self, filename):
        with open(filename) as rawScript:
            for line in rawScript:
                #Commented lines with #
                if re.match("\s*#", line):
                    continue
                m = re.match(r'(?P<delay>\S+)\s+(?P<speaker>\S+?):?\s+(?P<text>.+)', line)
                if not m:
                    continue
                delay = float(m.group('delay'))
                speaker = m.group('speaker').lower()
                text = m.group('text')
                self.script.append((delay, speaker, text))

    def run(self):
        if TasbotPipeEnable:
            if not os.path.exists(TasbotPipeName):
                os.mkfifo(TasbotPipeName)
            tasBotPipe = open(TasbotPipeName, 'w')

        for delay, speaker, text in self.script:
            time.sleep(delay)
            #debug("%s says %s" % (speaker, text))
            if speaker == 'red':
                self.ircBot.replayQueue.put("<red>:" + text)
                # self.ircBot.connection.privmsg(IrcChannel, text)
            if speaker == 'tasbot':
                if TasbotPipeEnable:
                    writeToPipe(tasBotPipe, text)
                if TasbotEspeakEnable:
                    call(['espeak', text])


class PptIrcBot(irc.client.SimpleIRCClient):
    def __init__(self):
        irc.client.SimpleIRCClient.__init__(self)
        self.badWords = self.getBadWords('bad-words.txt')
        #Precompiled tokenizing regex
        self.splitter = re.compile(r'[^\w]+')
        self.urlregex = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
        self.otherbadregex = re.compile(r'\.((com)|(org)|(net))')
        self.replayQueue = Queue()
        self.nonPrintingChars = set([chr(i) for i in xrange(32)])
        self.nonPrintingChars.add(127)

    def on_welcome(self, connection, event):
        print 'joining', IrcChannel
        connection.join(IrcChannel)

    def on_join(self, connection, event):
        """Fires on joining the channel.
           This is when the action starts.
        """
        if (event.source.find(IrcNick) != -1):
            print "I joined!"
            self.screenPlayThread = ScreenPlayThread(self)
            self.replayThread = ReplayTextThread(self.replayQueue)
            print 'starting replay thread'
            self.replayThread.start()
            print 'starting screenplay thread'
            self.screenPlayThread.start()

        # self.screenPlayThread = ScreenPlayThread(self)
        # self.replayThread = ReplayTextThread(self.replayQueue)
        # print 'starting replay thread'
        # self.replayThread.start()
        # print 'starting screenplay thread'
        # self.screenPlayThread.start()

    def on_disconnect(self, connection, event):
        sys.exit(0)

    def naughtyMessage(self, sender, reason):
        #Be sure to get rid of the naughty message before the event!
        #An easy way is to just make this function a pass
        #pass
        # self.connection.privmsg(IrcChannel, "Naughty %s (%s)" % (sender, reason))
        print("Naughty %s (%s)" % (sender, reason))

    def on_pubmsg(self, connection, event):
        debug("pubmsg from %s: %s" % (event.source, event.arguments[0]))
        text = event.arguments[0]
        sender = event.source.split('!')[0]

        #Check for non-ascii characters
        try:
            text.decode('ascii')
        except (UnicodeDecodeError, UnicodeEncodeError):
            self.naughtyMessage(sender, "not ascii")
            return
        except Exception:
            #I am not sure what else can happen but just to be safe, reject on other errors
            return

        if self.urlregex.search(text):
            self.naughtyMessage(sender, "url")
            return

        if self.otherbadregex.search(text):
            self.naughtyMessage(sender, "url-like")
            return

        #We probably also want to filter some typically non-printing ascii chars:
        #[18:12] <@Ilari> Also, one might want to drop character codes 0-31 and 127. And then map the icons to some of those.
        if any(c in self.nonPrintingChars for c in text):
            self.naughtyMessage(sender, "non-printing chars")
            return

        text_lower = text.lower()
        for badword_regex in self.badWords:
          if badword_regex.search(text_lower):
            self.naughtyMessage(sender, "bad word: " + badword_regex.pattern)
            return
        
        words = self.splitter.split(text_lower)
        words = map(lambda x:x.lower(),words)
        print words

        # if any(word.lower() in self.badWords for word in words):
            # self.naughtyMessage(sender, "bad word:" + word)
            # return
        self.replayQueue.put(sender + ':' + text)

    def getBadWords(self, filename):
        #Make sure all the entries are lower case
        #We lower-case the incoming text to make the check case-insensitive
        badWords = open(filename)
        badWordList_strings = set([word.strip().lower() for word in badWords.readlines()])
        badWords.close()
        
        if '' in badWordList_strings:
            badWordList_strings.remove('')
        
        badWordList_regex_strings = []

        for word in badWordList_strings:
            word = re.sub(r'[sz]', '[s5z2$]', word);
            word = re.sub(r'a', '[a4]', word);
            word = re.sub(r'e', '[e3]', word);
            word = re.sub(r'i', '[i1]', word);
            word = re.sub(r'l', '[l1]', word);
            word = re.sub(r'o', '[o0]', word);
            word = re.sub(r't', '[t7]', word);
            word = re.sub(r'g', '[g6]', word);
            word = re.sub(r'b', '[b8]', word);
            word = re.sub(r'f', '(f|ph)', word);
            word = re.sub(r'(c|k)', '[ck]', word);
            badWordList_regex_strings.append(word)
        
        badWordList = []
        
        for word in badWordList_regex_strings:
            badWordList.append(re.compile(word))
        
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
        c.connect(server, port, IrcNick, password=IrcPassword)
    except irc.client.ServerConnectionError as x:
        print(x)
        sys.exit(1)
    c.start()

if __name__ == "__main__":
    main()
