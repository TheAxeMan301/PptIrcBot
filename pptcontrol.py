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

1xxxxxxx11101110 - Command to shift palette forward one.

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

LINE_LENGTH = 32  # Number of symbols per line.


RED_COOLDOWN = 4  # Delay between RED's characters.

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
        'SomeFace',  # FIXME Placeholder
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
    # 0-96 in the order of this string, matching the font
    legalChars = list(
        '\nabcdefghijklmno'
        'pqrstuvwxyz ?!:.'
        '"#$%&\\\'()*+,-./0'
        '123456789;,=@ABC'
        'DEFGHIJKLMNOPQRS'
        'TUVWXYZ[\]^_`{|}'
        '~'
    )
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


# Here we compile a massive regex that captures all multi-character symbols.
SYMBOLS = [r'\bShiftPalette\b']
SYMBOLS += sorted((re.escape(e) for e in RobotEmoteMap), reverse=True)
SYMBOLS += [r'\b{}\b'.format(re.escape(e)) for e in sorted(FaceEmoteMap, reverse=True)]
SYMBOL_REGEX = re.compile('(' + '|'.join(SYMBOLS) + ')')


def textToSymbols(line):
    """
    Parse a line into list of symbols in our font, filtering out those which
    cannot be displayed.

    >>> textToSymbols('Kappa Kappa foo')
    ['Kappa', ' ', 'Kappa', ' ', 'f', 'o', 'o']
    >>> textToSymbols('a b  c   ')
    ['a', ' ', 'b', ' ', ' ', 'c', ' ', ' ', ' ']
    >>> textToSymbols('A ShiftPalette Z')
    ['A', ' ', 'ShiftPalette', ' ', 'Z']
    >>> textToSymbols('Kappa:D')
    ['Kappa', ':D']
    >>> textToSymbols('KappaKappa:D')
    ['K', 'a', 'p', 'p', 'a', 'K', 'a', 'p', 'p', 'a', ':D']
    >>> textToSymbols('a B c D e')
    ['a', ' ', 'B', ' ', 'c', ' ', 'D', ' ', 'e']
    >>> textToSymbols('Kappa foo bar')
    ['Kappa', ' ', 'f', 'o', 'o', ' ', 'b', 'a', 'r']
    >>> textToSymbols('>>>Hello :)Kappa__ UnSane')
    ['H', 'e', 'l', 'l', 'o', ' ', ':)', 'K', 'a', 'p', 'p', 'a', '_', '_', ' ', 'UnSane']
    """
    symbols = []
    for chunk in SYMBOL_REGEX.split(line):
        if chunk in RobotEmoteMap or chunk in FaceEmoteMap or chunk == 'ShiftPalette':
            symbols.append(chunk)
        else:
            for char in chunk:
                if char in SevenBitMapping:
                    symbols.append(char)
    return symbols


def formatRoomMessage(message):
    r"""
    Format an IRC message from the chat room by converting it to the font's
    symbol set and applying line wrapping.  The result is a list of symbols.

    >>> formatRoomMessage('blue:hello, world!')
    ['b', 'l', 'u', 'e', ':', ' ', 'h', 'e', 'l', 'l', 'o', ',', ' ', 'w', 'o', 'r', 'l', 'd', '!', '\n']
    >>> formatRoomMessage('<yellow>:go:far\n')
    ['y', 'e', 'l', 'l', 'o', 'w', ':', ' ', 'g', 'o', ':', 'f', 'a', 'r', '\n']

    >>> message = 'purple:this is a long message, one so long it will wrap\n'
    >>> lines = list(
    ...     'purple: this is a long message, \n'
    ...     'one so long it will wrap\n'
    ... )
    >>> formatRoomMessage(message) == lines
    True
    """
    # Full line should have nick:text. Need to split that up because nick does
    # not get emotes.
    nick, text = message.split(':', 1)
    symbols = ([c for c in nick if c in SevenBitMapping] + [':'] +
               textToSymbols(text.rstrip('\n')))
    return symbols + ['\n']
    #This puts newlines for each line. Instead the snes side will handle this.
    #lines = []
    #for i in range(0, len(symbols), LINE_LENGTH):
        #lines.extend(symbols[i:i + LINE_LENGTH])
        #lines.append('\n')
    #return lines


def padForRed(symbols):
    """
    Pad the message with spaces so that its length is a multiple of 32.

    :param list symbols:

    >>> padForRed(['a']) == ['a'] + [' '] * 31
    True
    >>> padForRed(['a'] * 32) == ['a'] * 32
    True
    """
    if len(symbols) % 32 == 0:
        return symbols
    return symbols + [' '] * (32 - (len(symbols) % 32))


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
    # return (SevenBitMapping.get(chatChar, NullCharCode) << 8) + SevenBitMapping.get(redChar, NullCharCode)

# A no-op is two null chars
#NopBits = encodeTwoChars()
NopBits = 0xFFFF


ShiftPaletteBits = 0b1111111111101110


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
                self.redQueue.put(line[len('<red>:'):])
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

    def readRedQueue(self):
        """Grab a line of red's text"""
        if self.redQueue.empty():
            return
        #Red's lines just have the text
        text = self.redQueue.get().rstrip('\n')
        self.redChars = padForRed(textToSymbols(text)) + ['\n']
        debug("Parsed red line: " + str(self.redChars))

    def readChatQueue(self):
        """Grab a line of chat text"""
        if self.chatQueue.empty():
            return
        line = self.chatQueue.get()
        self.chatChars = formatRoomMessage(line)
        debug("Parsed chat line: " + str(self.chatChars))

    def getBitsToSend(self):
        """Check our char queues and get the bits to send"""

        #First see if we have chars for red
        if len(self.redChars) > 0:
            if self.redChars[0] == 'ShiftPalette':
                self.redChars.pop(0)
                return ShiftPaletteBits
            if self.redCooldown == 0:
                # Set cooldown - This is what slows down red's typing.
                self.redCooldown = RED_COOLDOWN
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
            debug("One 7-bit char: %r" % (self.chatChars[0]))
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

    bs = BitStreamer('pipe_test')
    thread = BitStreamerTestThread(bs)
    thread.daemon = True
    thread.start()


if __name__ == "__main__":
    main()
