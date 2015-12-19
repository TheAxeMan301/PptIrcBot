import os
import serial
import sys
import time

# for use on raspberry pi, please disable your serial console
# a tool to do this automatically can be found at
#
#    https://github.com/lurch/rpi-serial-console
#
# to set up your pi to talk to the pic32 using this tool, run
#
#    raspi-serial-console disable
#
# then reboot your device.
#
# $Id: replay.py 51 2014-01-19 22:23:17Z true $

####

# if you have a game fix ID, enter it here
game_fix = 0
ubw_p1 = 0
ubw_p2 = 0

####

baud = 115200

####

ver_max = ['1', '1']

prebuffer = 30

####

framecount = [0, 0]
firstline = 0
totalframes = 0

latches = '1'
timeout = 0

p = {}
plog = []

####

if len(sys.argv) < 3:
	sys.stderr.write('Usage: ' + sys.argv[0] + ' <replayfile> <interface> [skip] [latches] [timeout]\n\n')
	sys.stderr.write('<replayfile> can be of these types: \n' +
		'    .fm2  (NES)\n' +
		'    .r08  (8-bit p1 + p2 std frame only MSB)\n' +
		'    .r16  (16bit p1 + p2 std frame only MSB)\n' +
		'    .r16m (16bit p1+p2+p3+p4 MSB)\n' +
		'    .r32  (32bit p1 + p2 std frame only MSB)\n\n')
	sys.stderr.write("<interface>  the serial interface, usually /dev/ttyAMA0 on Raspberry Pi\n")
	sys.stderr.write("[skip]       amount of initial lag frames to skip (fm2)\n")
	sys.stderr.write("             1 = skip initial latch, 0 = normal   (r08)\n")
	sys.stderr.write("[latches]    latches per frame (default 1, commonly 1 or 2)\n")
	sys.stderr.write("[timeout]    amount of lag frames until reset is detected\n\n")
	sys.exit(0)

if not os.path.exists(sys.argv[1]):
	sys.stderr.write('Error: "' + sys.argv[1] + '" not found\n')
	sys.exit(1)


# open the file and get the extension
fh = open(sys.argv[1], 'r')
fb = ''
fm = []
_, ftype = os.path.splitext(sys.argv[1])


# set this bitch up (additional things before we start)
if (len(sys.argv) >= 4):
	if (ftype == '.fm2'):
		skip = int(sys.argv[3], 10)
	else:
		if (int(sys.argv[3]) == 0):
			skip = 0
		else:
			skip = 1
else:
	skip = 0;

if (len(sys.argv) >= 5):
	latches = sys.argv[4]

if (len(sys.argv) >= 6):
	timeout = int(sys.argv[5], 10)

# if using ubw for gamepad display, configure it
if (ubw_p1):
	disp_p1 = serial.Serial(ubw_p1, 9600, timeout = 0)
	disp_p1.write('C,0,0,0,0' + chr(0x0d) + chr(0x0a))
	disp_p1.write('O,0,0,0' + chr(0x0d) + chr(0x0a))
	disp_p1.write('O,0,255,0' + chr(0x0d) + chr(0x0a))
	disp_p1.read(100)

if (ubw_p2):
	disp_p2 = serial.Serial(ubw_p2, 9600, timeout = 0)
	disp_p2.write('C,0,0,0,0' + chr(0x0d) + chr(0x0a))
	disp_p2.write('O,0,0,0' + chr(0x0d) + chr(0x0a))
	disp_p2.write('O,0,255,0' + chr(0x0d) + chr(0x0a))
	disp_p2.read(100)


# get the firmware version - if it fails then we aren't connected...
print("Looking for replay device...")
ser = serial.Serial(sys.argv[2], baud, timeout = 1)
ser.read()
while (ser.inWaiting()):
	ser.read() 					# clear out current receive buffer
ser.write("~v")					# poll for version
# ser.write("~W")					# reset ISCP flag
time.sleep(0.03) 				# usb fix


verr = 0
while (1):
	while (ser.inWaiting() == 0):
		pass

	ver = ser.read()

	if (ver == 'V'):
		ver = ser.read(3)
		print("Replay device version " + str(ord(ver[0])) + "." + str(ord(ver[1])) + ver[2] + " found.\n")
		if (ver[0] > ver_max[0] or ((ver[0] >= ver_max[0]) and (ver[1] > ver_max[1]))):
			sys.stderr.write("Error: Replay device is too new. Update this software. Exiting.\n")
			sys.exit(129)
		else:
			break
	else:
		verr += 1
		if (verr > 16):
			sys.stderr.write("Error: Replay device not found on " + sys.argv[2] + "... not plugged in? Maybe the console is on?\n")
			print("Running without finding a replay device. Expect issues.\n")
			# sys.exit(128)
			break


# final serial interface, on raspi use /dev/ttyAMA0 after disabling console
ser.close()
ser = serial.Serial(sys.argv[2], baud, timeout = 0)


# file specific initial setup
if (ftype == '.fm2'):
	fm = '88'

	# we need to determine which line is the first input line
	# check all lines; when first character is a pipe, we have it
	while (len(fb) == 0):
		t = fh.readline()
		firstline += 1
		if (len(t)):
			if (t[0] == '|'):
				fb = t

	print('File "' + sys.argv[1] + '" opened. FM2 input data stars at line ' + str(firstline) + '.')
	
	# get action count
	totalframes = 1
	for i, l in enumerate(fh):
		if (t[0] == '|'):
			totalframes += 1

	if (skip):
		print('Skipping ' + str(skip) + ' input actions.')

if (ftype[0:2] == '.r'):
	fm.append(ftype[3])
	fm.append(ftype[3])

	stat = os.stat(sys.argv[1])

	# get action count
	if (ftype[3:4] == '8'):
		totalframes = stat.st_size >> 1
	if (ftype[3:4] == '6'):
		if (ftype == '.r16m'):
			totalframes = stat.st_size >> 4
		else:
			totalframes = stat.st_size >> 2
	if (ftype[3:4] == '4'):
		totalframes = stat.st_size >> 3
	if (ftype[3:4] == '2'):
		totalframes = stat.st_size >> 4


if (latches):
	if (latches == 'V'):
		print('Latch detect mode is disabled; using a vsync-detect circuit instead.')
	elif (latches >= 'a' and latches <= 'z'):
		print('Latch detect mode is windowed, with a ~' + str(((ord(latches) - ord('a')) + 1) * 0.5) + 'ms window.')
	else:
		print('Latch detect mode is per-frame, with ' + latches + ' latches per frame.')

if (timeout):
	print('Replay device timeout set to ' + str(timeout) + ' frames.')

if (prebuffer):
	if (ftype[0:2] == '.r'):
		tskip = 0
	else:
		tskip = skip

	if (tskip):
		print('Frame stats below are ahead by ' + str(prebuffer + tskip + 1) + ' frames.')


# all done... print out info, wait X frames, then tell the device to stop
def cleanup():
	global prebuffer
	global framecount
	global p

	wait = prebuffer

	while (wait):
		while (ser.inWaiting() == 0):
			pass
		
		ser.read()
		wait -= 1
		
		# update with fake information
		p = plog.pop(0)
		
		framecount[0] += 1
		printinfo()
	
	# ser.write("~V")
	#time.sleep(0.001)
	time.sleep(2.001)
	# ser.write("~r")
	
	if (ubw_p1):
		disp_p1.write('O,0,255,0' + chr(0x0d) + chr(0x0a))
	if (ubw_p2):
		disp_p2.write('O,0,255,0' + chr(0x0d) + chr(0x0a))
	
	print("\r\nDone.")
	sys.exit(0)


def printinfo():
	global prebuffer
	global start
	global framecount
	global totalframes
	global tskip

	if (framecount == [tskip + prebuffer + 1, 0]):
		sys.stdout.write("Resetting...")
		start = time.time()
	else:
		ct = time.time()
		frameadj = framecount[0] - prebuffer
		if (ftype == '.fm2'):
			out = "%6u/%6u (%u lag + %u std), %5.2fms, %01u:%02u:%05.2fs " % (
					frameadj + framecount[1], totalframes, framecount[1], frameadj,
					(ct - t) * 1000,
					(ct - start) / 3600, ((ct - start) / 60) % 60, (ct - start) % 60)
		else:
			out = "%6u/%6u (+%u lag = %u), %5.2fms, %01u:%02u:%05.2fs " % (
					frameadj, totalframes, framecount[1], frameadj + framecount[1],
					(ct - t) * 1000,
					(ct - start) / 3600, ((ct - start) / 60) % 60, (ct - start) % 60)

		sys.stdout.write(out)
		
		if (fm[0] == '8'):
			sys.stdout.write("  " + display_nes())

		if (lagnow):
			sys.stdout.write(" **LAG**")
		
	sys.stdout.write("\033[K\r")
	sys.stdout.flush()



# seek to beginning of file, read out amount of bytes to skip
def fh_setup(skip):
	global fh
	global fbuf

	fh.seek(0)

	if (ftype == '.fm2'):
		a = 0
		while (a < firstline + skip):
			fbuf = fh.readline()
			a += 1
	if (ftype[0:2] == '.r'):
		# .rXX does not support skipping
		pass


# gets X bits for p1 then X bits for p2 sequentially
def raw_getbits(bytes):
	b = {}

	if (ftype == '.r16m'):
		for x in range(0, 8):
			b[x] = fh.read(bytes)
	elif (ftype == '.r08'):
		for x in range(0, 8):
			b[x] = chr(0)
		b[0] = fh.read(bytes)	# p1d0
		b[4] = fh.read(bytes)	# p2d0

	if (len(b[0]) == 0):
		# end of file...
		cleanup()
		return false

	if (bytes == 1):
		for x in range(0, 8):
			b[x] = ord(b[x][0]) << 24;
	if (bytes == 2):
		for x in range(0, 8):
			b[x] = ord(b[x][0]) << 24 | ord(b[x][1]) << 16;
	if (bytes == 4):
		pass

	return b


# gets the data from the fm2 dataline and returns as 2player bitfield
def fm2_getbits(fm2_str):
    p1 = 0
    p2 = 0
    
    if (len(fm2_str) == 0):
    	cleanup()
    	return 0, 0

    data = fm2_str.split('|')
    
    for x in range(0, 8):
        p1 = p1 | (0 if (data[2][x] == '.') else (1 << x))
        if (len(data[3])):
			p2 = p2 | (0 if (data[3][x] == '.') else (1 << x))
    
    return (p1 << 24), (p2 << 24)


# reads the next input and returns appropriately formatted data
def send_next_frame(is_reset):
	global p
	global plog
	global ftype

	b = {}
	cidx = 2

	if (ftype == '.fm2'):
		fbuf = fh.readline()
		b[0], b[4] = fm2_getbits(fbuf)
	if (ftype[0:2] == '.r'):
		b = raw_getbits(int(ftype[2:4], 10) / 8)

	if b:
		if (ftype == '.r08'):
			cidx = 4    # don't need to send multitap for nes, less comms = less problems 

		for x in range(0, 8, cidx):
			ser.write("~" + chr((x & 2) + (x >> 2) + ord('1'))
				+ chr(b[x    ] >> 24) + chr((b[x    ] >> 16) & 0xff) + chr((b[x    ] >> 8) & 0xff) + chr(b[x    ] & 0xff)
				+ chr(b[x + 1] >> 24) + chr((b[x + 1] >> 16) & 0xff) + chr((b[x + 1] >> 8) & 0xff) + chr(b[x + 1] & 0xff))
			# time.sleep(0.0005) # scope debug

		# add this command to the controller log
		plog.append(b)
		
		# and get the first entry
		if (not is_reset):
			p = plog.pop(0)

	return


# prints out nes input shit
def display_nes():
	global p

	p1 = p[0] >> 24
	p2 = p[4] >> 24

	# ubw
	if (ubw_p1):
		disp_p1.write('O,0,' + str(~p1 & 0xff) + ',0' + chr(0x0d) + chr(0x0a))
		disp_p1.read(100)

	ret = ["", ""]
	controls = "RLDUteBA"
	map = [range(3, -1, -1), range(5, 3, -1), range(6, 8)]

	# UDLR
	for x in map:
		for y in x:
			if (p1 & 1 << y):
				ret[0] += controls[y]
			else:
				ret[0] += " "

			if (p2 & 1 << y):
				ret[1] += controls[y]
			else:
				ret[1] += " "

	return 'p1:' + ret[0] + '  p2:' + ret[1]


t = time.time()
start = time.time()

reset = 0

fh_setup(skip) # prevents instant 'Done.' when starting with console already on

p[0] = 0 # fixes crash on non-windowed nes playback
p[4] = 0

print("")

while (1):
	while (ser.inWaiting() == 0):
		pass

	c = ser.read()
	lagnow = 0

	# print("\n" + c)
	
	if (c == 'F'):
		framecount[0] += 1
		send_next_frame(0)
        if (framecount[0] == 8700):
                ser.write("~l1")
	        reset = 0
        #if (framecount[0] == 16368):
        #        ser.write("~V")
	#        # reset = 0

	elif (c == 'L'):
		framecount[1] += 1
		lagnow = 1
		
		if (ftype == '.fm2'):
			fbuf = fh.readline()
		if (ftype[0:2] == '.r'):
			# nothing to set up
			pass

	elif (c == 'B'):
		reset = 0
		
	elif (c == 'R'):
		if (not reset):
			# +1 is because we are always buffering at least one frame ahead...
			framecount = [tskip + prebuffer + 1, 0] 

			# set bitlength to the appropriate size depending on file type,
			ser.write("~M1" + fm[0])
			ser.write("~M2" + fm[1])

			# set latches,
			if (latches.isdigit()):
				ser.write("~l" + str(int(latches, 10)))
			else:
				ser.write("~l" + latches[0])

			# set sequential lag frame count timeout,
			if (timeout):
				ser.write("~t" + chr((timeout >> 8) & 0xff) + chr(timeout & 0xff))

			# start data over,
			fh_setup(skip)

			# tell the device to reset buffers,
			ser.write("~r")

			# enable / disable lagframe buffer incrementing,
			if (ftype == '.fm2'):
				ser.write("~g1")
			else:
				ser.write("~g0")

			# force 60fps, disable frame period learning,
			ser.write("~c6")

			# skip the first ghost latch,
			if (ftype == '.r08'):
				ser.write("~s" + chr(skip + ord('0')))
				# if we are skipping this latch, feed initial empty player data.
				if (skip):
					p[0] = 0
					p[4] = 0

			# hack in the game fix ID,
			if (game_fix):
				ser.write("~h" + chr(game_fix))
			else:
				ser.write("~h" + chr(0xff))

			# and feed in first prebuffer bytes.
			for x in range(0, prebuffer):		
				send_next_frame(1)

			# also mark as reset so we don't do this again.
			reset = 1
		
	printinfo()

	t = time.time()
