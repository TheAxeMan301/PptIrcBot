import sys
import os
import time
import re
from threading import Thread
from Queue import Queue


def debug(msg):
    print msg


"""
Bitstream format:

0xxxxxyyyyyzzzzz - Three characters * 5 bits each for chat
1xxxxxxx0yyyyyyy - Two chars * 7 bits for a more extended char set.
                   The second char is for Red.
1xxxxxxx1yyyyyyy - One char and a command. The command might cause some
                   following input to be treated differently.

The 5 bit character mapping:

0  (newline)    16 p
1  a            17 q
2  b            18 r
3  c            19 s
4  d            20 t
5  e            21 u
6  f            22 v
7  g            23 w
8  h            24 x
9  i            25 y
10 j            26 z
11 k            27   (space)
12 l            28 ? (question mark)
13 m            29 ! (exclamation mark)
14 n            30 : (colon)
15 o            31 .

Alphabet and space should be obvious. We can convert text to lowercase.
colon is there because it comes after every nick
newline is there to end each line
After that I looked at last year's chat and ? and ! are the most common
punctuation. Think about it, if we pull this off it is going to be a
!!!??? situation, not something you end with a period.

We can convert text to lowercase. Emotes are sent separately so no worries
about them here.

I'll try to organize the code to make it easy to change if necessary.

About the two char command, ascii 0 will be a non-printing null. So when
Red speaks we can send one char of normal chat and one char for Red.

What about the commands? At the very least we need a command for emotes.
Let's call the 7 bits the opcode.
"""

#This is 10000000 0000000, 16 bits with just the high bit set
HighBitSet = 2 ** 15

#The 7-bit encoding for null character
NullCharCode = 127


#************************
#*  Character mappings  *
#************************


def makeFiveBitMap():
    """Set the mapping for the 5 bit chars"""
    mapping = {}
    #a-z are 1-26
    for i in xrange(ord('a'), ord('z') + 1):
        mapping[chr(i)] = 1 + i - ord('a')
    mapping.update({
        '\n': 0,
        ' ': 27,
        '?': 28,
        '!': 29,
        ':': 30,
        '.': 31,
    })
    return mapping


FiveBitMapping = makeFiveBitMap()


def makeEmoteMaps():
    #These are simpler emotes. Tracked separately because the parsing is slightly different.
    RobotEmoteList = [
        ':)',
        ':(',
        ':o',
        ':z',
        'B)',
        ':/',
        ';)',
        ';p',
        ':p',
        'R)',
        'o_O',
        ':D',
        '>(',
        '<3',
    ]
    #Mapping will be 0-13 in the order of this list
    RobotEmoteMap = dict([(RobotEmoteList[i], i) for i in xrange(len(RobotEmoteList))])

    #Face emotes that we have actually converted.
    #Other face emotes will be parsed but mapped to some other face.
    FaceEmoteList = [
        'Kappa',
        'FrankerZ',
        'ResidentSleeper',
        'FailFish',
        'KreyGasm',
        'PogChamp',
        'SwiftRage',
        'PJSalt',
        'BibleThump',
        'WinWaker',
    ]
    #Mapping will be 14-24 in the order of this list
    FaceEmoteMap = dict([(FaceEmoteList[i], i + len(RobotEmoteList)) for i in xrange(len(FaceEmoteList))])

    #Read all the emotes from a text file
    with open('twitchemotes.txt') as twitchEmoteFile:
        allFaceEmotes = [emote.strip() for emote in twitchEmoteFile.readlines()]
    for emote in allFaceEmotes:
        if len(emote) > 0 and emote not in FaceEmoteMap:
            #This sets the default
            FaceEmoteMap[emote] = FaceEmoteMap['Kappa']

    return RobotEmoteMap, FaceEmoteMap


RobotEmoteMap, FaceEmoteMap = makeEmoteMaps()


def makeSevenBitMapping():
    """Mapping for 7 bit chars, including emotes"""
    #0-96 in the order of this string
    legalChars = list('\nabcdefghijklmnopqrstuvwxyz ?!:."#$%&\\\'()*+,-./0123456789;,=@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\]^_`{|}~')
    mapping = dict([(legalChars[i], i) for i in xrange(len(legalChars))])

    #Now add in emotes
    #Robot emotes have an index from 0-13. That gets mapped to 97-110 in this map.
    for emote in RobotEmoteMap:
        mapping[emote] = 97 + RobotEmoteMap[emote]
    #Face emotes have an index from 14-24. That gets mapped to 111-121 in this map.
    for emote in FaceEmoteMap:
        mapping[emote] = 97 + FaceEmoteMap[emote]
    #127 is a non-printing null (no-op)

    return mapping

SevenBitMapping = makeSevenBitMapping()

#************************
#*  Encoding functions  *
#************************


def encodeThreeChars(c1=None, c2=None, c3=None):
    """
    Get the 16-bit encoding for up to three characters.

    >>> decodeBits(encodeThreeChars('a', 'b', 'c'))
    '0000010001000011'
    """
    n1 = FiveBitMapping.get(c1, 0)
    n2 = FiveBitMapping.get(c2, 0)
    n3 = FiveBitMapping.get(c3, 0)
    return (n1 << 10) + (n2 << 5) + n3


def encodeRedChar(redChar):
    """
    Encode a char for red's text as a 16-bit value.
    """
    return HighBitSet + SevenBitMapping.get(redChar, NullCharCode)


def encodeChatChar(chatChar):
    """Encode a single chat char in ascii"""
    return HighBitSet + (SevenBitMapping.get(chatChar, NullCharCode) << 8)


def encodeTwoChars(chatChar=None, redChar=None):
    """Encode two characters, one for chat and one for Red.
       Both are optional.
    """
    return HighBitSet + (SevenBitMapping.get(chatChar, NullCharCode) << 8) + SevenBitMapping.get(redChar, NullCharCode)


# A no-op is two null chars
NopBits = encodeTwoChars()


class TextPipeHandler(Thread):
    """Reads the input from the replay pipe and adds to the line queues.
       Decides when to drop chat if it gets too backed up.
    """
    def __init__(self, chatQueue, redQueue, pipeName):
        super(TextPipeHandler, self).__init__()

        self.chatQueue = chatQueue
        self.redQueue = redQueue

        if not os.path.exists(pipeName):
            os.mkfifo(pipeName)
        self.readPipe = open(pipeName, 'r')

    def readNextLine(self):
        """Read the next line, halting everything until something comes"""
        while True:
            line = self.readPipe.readline()
            #If we read from flushed pipe then wait a moment before moving on
            if line == '':
                time.sleep(0.1)
                continue
            return line.rstrip('\n')

    def run(self):
        """Listen on the pipe. On reading something add it to the appropriate queue"""
        while True:
            line = self.readNextLine()
            if line.startswith('<red>'):
                debug('line for Red: ' + line)
                self.redQueue.put(line)
            #Check the number of chat lines queued up. Drop this one if there are too many.
            elif self.chatQueue.qsize() < 20:
                debug('chat line: ' + line)
                self.chatQueue.put(line)


class BitStreamer(object):
    """Manages the stream of commands to send"""
    def __init__(self, pipeName=None):
        self.chatQueue = Queue()
        self.redQueue = Queue()

        #If we got a pipe name then start the pipe handler thread
        #It will add to the queues as it reads text from chat
        if pipeName is not None:
            pipeThread = TextPipeHandler(self.chatQueue, self.redQueue, pipeName)
            pipeThread.start()

        #Translate next line into a list of chars or emotes to send
        self.chatChars = []
        self.redChars = []

        #Number of inputs until another char from red
        self.redCooldown = 0

        # Here we compile a massive regex that finds all robot emotes.  Note
        # that they must be in reverse-sorted order so that the longest prefix
        # is matched in the case of overlap.
        robotEmotes = map(re.escape, sorted(RobotEmoteMap.keys(), reverse=True))
        self.robotEmoteRegex = re.compile('(?:' + '|'.join(robotEmotes) + ')')

        self.tokenizeRegex = re.compile("[^A-Za-z0-9_@]+")

    def readRedQueue(self):
        """Grab a line of red's text"""
        if self.redQueue.empty():
            return
        #Red's lines just have the text
        text = self.redQueue.get().rstrip('\n')
        self.redChars = self.parseLine(text) + ['\n']
        debug("Parsed red line: " + str(self.redChars))

    def readChatQueue(self):
        """Grab a line of chat text"""
        if self.chatQueue.empty():
            return
        #Full line should have nick:text. Need to split that up because
        #nick does not get emotes
        line = self.chatQueue.get()
        nick = line.split(':')[0]
        #Ensure exactly one newline at end. Strip any off the right and add one back.
        text = line[len(nick) + 1:].rstrip('\n')
        self.chatChars = [c for c in nick if c in SevenBitMapping] + [':', ' '] + self.parseLine(text) + ['\n']
        debug("Parsed chat line: " + str(self.chatChars))

    def parseLine(self, line):
        """Parse a line into list of chars and emotes"""
        #First parse out any robot emotes
        robotEmotes = self.robotEmoteRegex.findall(line)

        #With no robot emotes skip to parsing for face emotes
        if len(robotEmotes) == 0:
            return self.parseLineFace(line)

        #Otherwise we have n robot emotes separating n+1 sections of text
        sections = self.robotEmoteRegex.split(line)

        #Sanity check...want to be defensive here
        if len(sections) != len(robotEmotes) + 1:
            return self.parseLineFace(line)

        parsedLine = []
        for i in xrange(len(sections)):
            parsedLine += self.parseLineFace(sections[i])
            if i < len(robotEmotes):
                parsedLine.append(robotEmotes[i])
        return parsedLine

    def parseLineFace(self, line):
        """Parse a line for face emotes. Also remove any unsupported chars.
           Does not sort out 5-bit encodable chars yet.
        """
        spaces = self.tokenizeRegex.findall(line)
        words = self.tokenizeRegex.split(line)

        #sanity...
        if len(spaces) + 1 != len(words):
            return [c.lower() for c in line if c in SevenBitMapping]

        parsedLine = []
        for i in xrange(len(words)):
            word = words[i]
            if word in FaceEmoteMap:
                #Emote is treated like a single character
                parsedLine.append(word)
            else:
                #Other text gets split into chars. Invalid chars screened out.
                #Convert to lowercase too.
                parsedLine += [c.lower() for c in word if c in SevenBitMapping]
            if i < len(spaces):
                parsedLine += [c.lower() for c in spaces[i] if c in SevenBitMapping]
        return parsedLine

    def getBitsToSend(self):
        """Check our char queues and get the bits to send"""

        #First see if we have chars for red
        if len(self.redChars) > 0:
            if self.redCooldown == 0:
                #Set cooldown - This is what slows down red's typing.
                self.redCooldown = 4
                if len(self.chatChars) == 0:
                    #no chat char
                    debug("One char for Red: %r" % (self.redChars[0],))
                    return encodeRedChar(self.redChars.pop(0))
                else:
                    #include a chat char
                    debug("Chat: %r Red: %r" % (self.chatChars[0], self.redChars[0],))
                    return encodeTwoChars(
                        self.chatChars.pop(0),
                        self.redChars.pop(0))
            else:
                self.redCooldown -= 1

        # Chat chars only. Figure out how many of next chars are 5-bit
        # encodable.  If all three of them then we use the compact
        # format.
        if (len(self.chatChars) >= 3 and
                self.chatChars[0] in FiveBitMapping and
                self.chatChars[1] in FiveBitMapping and
                self.chatChars[2] in FiveBitMapping):
            c1 = self.chatChars.pop(0)
            c2 = self.chatChars.pop(0)
            c3 = self.chatChars.pop(0)

            debug("Three 5-bit chars: %r %r %r" % (c1, c2, c3))
            return encodeThreeChars(c1, c2, c3)

        #Send a chat char if one is available
        if len(self.chatChars) > 0:
            debug("One 7-bit char: '%s'" % (self.chatChars[0]))
            return encodeChatChar(self.chatChars.pop(0))

        #Default to no-op
        return NopBits

    def getNextBits(self):
        """Send the next set of bits based on incoming text.
           Red's chat gets priority. We can send a chat char with his.
        """
        #If we have no text from chat or red see if there is more
        #available in the Queue
        if len(self.chatChars) == 0:
            self.readChatQueue()
        if len(self.redChars) == 0:
            self.readRedQueue()

        #This is the stream that goes to replay
        return self.getBitsToSend()


def decodeBits(bits):
    """Debugging decode of 16 bits. Convert to binary string e.g. 00111011011010101010"""
    return format(bits, '#018b')[2:]


class BitStreamerTestThread(Thread):
    """Tests the BitStreamer by printing out its output"""
    def __init__(self, bs):
        super(BitStreamerTestThread, self).__init__()
        self.bs = bs

    def run(self):
        #For testing we grab an stream input every 1/10 of a second
        for i in xrange(1000):
            time.sleep(0.1)
            print decodeBits(self.bs.getNextBits())


def main():
    """For testing, display control output"""

    if '--test' in sys.argv:
        import doctest
        res = doctest.testmod()
        print res
        sys.exit(1 if res.failed else 0)

    #Test with input from writepipe
    if True:
        bs = BitStreamer('pipe_test')
        BitStreamerTestThread(bs).start()

    #Test some other code
    if False:
        bs = BitStreamer()
        print bs.parseLine('>>>Hello :)Kappa__ UnSane')
        print decodeBits(bs.getNextBits())


if __name__ == "__main__":
    main()
