import sys
import os
import time
import re
from threading import Thread
from Queue import Queue

"""
Bitstream format:

0xxxxxyyyyyzzzzz - Three characters * 5 bits each for chat
1xxxxxxx0yyyyyyy - Two chars * 7 bits each in normal ascii encoding
                   The second char is for Red.
1xxxxxxx1yyyyyyy - One char and a command. The command might cause some
                   following input to be treated differently.

The 5 bit character mapping:
(This is TheAxeMan's suggestion, see below for my reasoning)

0  (no char)    16 p
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
15 o            31 (newline)

The all zeros no char allows 0x0000 to be a full no-op. Also allows for
using 1 or 2 of the 3 allowed.
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
First guess is to say opcode 0000001 means the next input is an emote.
The next 16 bits are an emote according to some mapping we make.
Then go back to text as normal.
"""

NopBits = 0x0000
HighBitSet = 2 ** 15

def makeFiveBitMap():
    """Set the mapping for the 5 bit chars"""
    mapping = {}
    #a-z are 1-26 (0 is null)
    for i in xrange(ord('a'), ord('z')+1):
        mapping[chr(i)] = 1 + i - ord('a')
    mapping.update({
        ' ': 27,
        '?': 28,
        '!': 29,
        ':': 30,
        '\n': 31,
    })
    return mapping

FiveBitMapping = makeFiveBitMap()


def charIsSupported(c):
    """Is the character supported? Filter non-printing or maybe other chars"""
    #For now no filtering
    return True

def encodeThreeChars(c1=None, c2=None, c3=None):
    """Get the 16-bit encoding for up to three characters"""
    n1 = FiveBitMapping.get(c1, 0)
    n2 = FiveBitMapping.get(c2, 0)
    n3 = FiveBitMapping.get(c3, 0)
    return n1 << 10 + n2 << 5 + n3

def encodeRedChar(redChar):
    """Encode a char for red's text"""
    if ord(redChar) < 128:
        return HighBitSet + ord(redChar)
    return HighBitSet

def encodeChatChar(chatChar):
    """Encode a single chat char in ascii"""
    if ord(chatChar) < 128:
        return HighBitSet + ord(chatChar) << 7
    return HighBitSet

def encodeTwoChars(chatChar=None, redChar=None):
    """Encode two characters, one for chat and one for Red.
       Both are optional.
    """
    bits = HighBitSet  #this is 2**15 so set bit 16
    #Sanity check: ensure char code is 7 bits
    if chatChar is not None and ord(chatChar) < 128:
        bits += ord(chatChar) << 7
    if redChar is not None and ord(redChar) < 128:
        bits += ord(redChar)
    return bits



def main():
    """For testing, display control output"""

if __name__ == "__main__":
    main()
