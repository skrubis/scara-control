import time
import serial
import cv2 as cv
import matplotlib.pyplot as plt
import numpy as np
from _thread import start_new_thread, allocate_lock
import random




robotenable=True
xpixel=256
ypixel=256
drawx=200#mm
drawy=200#mm

#New Koordinatesystem
rob0 =np.array([337, -111,0])#origin
roby =np.array([337, -12,0])#x
robx =np.array([491 , -111 ,0])#y



def move(S,x,y,z,R):
    S.write(b"POINT a\n\r")
    send=str(x)+","+str(y)+","+str(z)+","+"0.00"+","+"180"+","+str(R)+"\n\r"
    S.write(send.encode())
    print(send)
    S.write(b"\n\r")
    S.write(b"DO MOVE a\n\r")
    #x -350_500
    #y-560_560
    #z170-370
def normalize(v):
    norm = np.linalg.norm(v)
    if norm == 0:
       return v
    return v / norm

lock = allocate_lock()
Frame_count = 0
Processed_Frames=0
Frame=np.zeros((100, 100), np.uint8)
org=np.zeros((100, 100), np.uint8)
dithered=0
newFrame=False

def thread_capture(cap):
    global org,Frame,Frame_count,newFrame
    while True:
        ret, frame = cap.read()
        lock.acquire()
        frame = cv.imread('Unbenannt.png', cv.IMREAD_GRAYSCALE)
        Frame = frame#cv.cvtColor(frame, cv.COLOR_BGR2GRAY)
        org=frame
        Frame_count=Frame_count+1
        newFrame=True
        lock.release()
        # img = cv.imread('rocket3.png', 0)
        # img = cv.imread('Hand.jpg', 0)
        # img = cv.imread('gray.png', 0)
        # img = cv.imread('Lenna.png', 0)
        # img = cv.imread('Portal_companion_Cube.jpg', 0)
        # img=gray

    return

def thread_dither():
    global dither_out,Processed_Frames,newFrame
    while True:
        while newFrame==False:
            time.sleep(0.05)
        lock.acquire()
        img=Frame
        newFrame=False
        lock.release()
        dimensions = img.shape
        img = img[:, int((dimensions[1] - dimensions[0]) / 4):dimensions[1] - int((dimensions[1] - dimensions[0]) / 4)]
        #dimensions = img.shape
        data = cv.resize(img, (int(xpixel), int(ypixel)))
        #clahe = cv.createCLAHE(clipLimit=5, tileGridSize=(3,3))
        #img = clahe.apply(img)
        dimensions = data.shape
        dithered = np.zeros((dimensions[0], dimensions[1]), np.uint8)

        for y in range(0, dimensions[0], 1):
            for x in range(0, dimensions[1], 1):
                pixel = data[y, x]

                if pixel > 128:
                    dithered[y, x] = 1
                    newvalue = 255
                else:
                    newvalue = 0

                # Burkes
                error = -(newvalue * 1 - pixel * 1) / 32

                if (x < dimensions[1] - 2):
                    data[y, x + 2] = data[y, x + 2] + 4 * error
                    data[y, x + 1] = data[y, x + 1] + 8 * error
                elif (x < dimensions[1] - 1):
                    data[y, x + 1] = data[y, x + 1] + 8 * error

                if (x < dimensions[1] - 1 and y < dimensions[0] - 1):
                    data[y + 1, x + 1] = data[y + 1, x + 1] + 4 * error

                if (x < dimensions[1] - 2 and y < dimensions[0] - 1):
                    data[y + 1, x + 2] = data[y + 1, x + 2] + 2 * error

                if (1 < x and y < dimensions[0] - 1):
                    data[y + 1, x - 2] = data[y + 1, x - 2] + 2 * error

                if (0 < x and y < dimensions[0] - 1):
                    data[y + 1, x - 1] = data[y + 1, x - 1] + 4 * error

                if (y < dimensions[0] - 1):
                    data[y + 1, x] = data[y + 1, x] + 8 * error

        lock.acquire()
        dither_out = dithered
        Processed_Frames=Processed_Frames+1
        lock.release()

    return


cap = cv.VideoCapture(0)
start_new_thread(thread_capture,(cap,))
start_new_thread(thread_dither,())

count_int = 0
while True:
    if Processed_Frames>0 and count_int<Processed_Frames:
        lock.acquire()
        bild = dither_out
        lock.release()
        disp = cv.resize(bild, (400, 400), fx=2, fy=2, interpolation=cv.INTER_NEAREST)
        disporg=cv.resize(org, (400, 400), fx=2, fy=2, interpolation=cv.INTER_NEAREST)
        #cv.imshow('Frame'+str(Frame_count)+'Processed'+str(Processed_Frames), bild*255)
        cv.imshow('image', disp*255)
        cv.imshow('org', disporg)
        cv.waitKey(1)
        print(str(Frame_count)+" processed "+ str(Processed_Frames))
        count_int=Processed_Frames
        if count_int>20:
            cv.imwrite('out.png',bild*255)
            time.sleep(5)
            print("out")
            break



####Dithering


xdir=normalize(robx-rob0)
ypoint=normalize(roby-rob0)
zdir=normalize(np.cross(xdir,ypoint))
ydir=np.cross(zdir,xdir)


xvec=xdir*drawx/xpixel
yvec=ydir*drawy/ypixel
zvec=zdir

img0 = np.array([0, 0,0])
imgx = np.array([1, 0,0])
imgy = np.array([0, 1,0])
imgz = np.array([0, 0,1])



M = np.array([[1, 0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]])
G00=np.dot(xvec,imgx)
G10=np.dot(xvec,imgy)
G20=np.dot(xvec,imgz)
G30=0
G01=np.dot(yvec,imgx)
G11=np.dot(yvec,imgy)
G21=np.dot(yvec,imgz)
G31=0
G02=np.dot(zvec,imgx)
G12=np.dot(zvec,imgy)
G22=np.dot(zvec,imgz)
G32=0
G03=rob0[0]
G13=rob0[1]
G23=rob0[2]
G33=1

G = np.array([[G00, G01,G02,G03],[G10,G11,G12,G13],[G20,G21,G22,G23],[G30,G31,G32,G33]])

#G=np.linalg.inv(G)
#G = np.array([int(np.dot(xvec,imgx)),int(np.dot(yvec,imgx)),int(np.dot(zvec,imgx)),rob0[0]],   [int(np.dot(xvec,imgy)),int(np.dot(yvec,imgy)),int(np.dot(zvec,imgy)),rob0[1]],[int(np.dot(xvec,imgz)),int(np.cross(yvec,imgz)),int(np.dot(zvec,imgz)),rob0[2]],[0,0,0,1])

test0=G.dot(np.array([0, 0,0,1]))
test1=G.dot(np.array([xpixel, 0,0,1]))
test2=G.dot(np.array([0,ypixel,0,1]))

lock.acquire()
Print = dither_out
lock.release()
printsize = Print.shape
#mean=np.mean(Print)
#if mean <= 0.5:
#    Print=abs(1-Print)

if robotenable:
    ser = serial.Serial()
    print("robot enable")
    ser.port = 'COM3'
    ser.baudrate = 9600
    ser.xonxoff = True
    ser.rtscts = False
    ser.dsrdtr = True
    ser.open()
    ser.is_open
    ser.write(b"SPEED 30\n\r")

for count in range(0,xpixel*ypixel-1,1):
    x=random.randint(0, 49)
    y=random.randint(0, 49)
    test2 = G.dot(np.array([y, x, Print[y, x], 1]))
    if test2[2] == 0.0 and robotenable:
        move(ser,test2[0],test2[1],  240,180)
        time.sleep(0.5)
        move(ser, test2[0], test2[1], 224 , 180)
        time.sleep(0.5)
        move(ser, test2[0], test2[1], 240, 180)
        time.sleep(0.5)
        Print[y, x]=1


#for y in range(0, printsize[0], 1):
#    for x in range(0, printsize[1], 1):
#        test2 = G.dot(np.array([y, x, Print[y,x], 1]))

#        if test2[2] ==0.0 and robotenable:
#            move(ser,test2[0],test2[1],  240,180)
#            time.sleep(0.5)
#            move(ser, test2[0], test2[1], 224 , 180)
#            time.sleep(0.5)
#            move(ser, test2[0], test2[1], 240, 180)
#            time.sleep(0.5)

#        if test2[2] ==0.0:
#            if x == 0:
#                move(ser,test2[0],test2[1],  240,180)
#
#            move(ser, test2[0], test2[1], 232 , 180)
#            if x == 49:
#                move(ser, test2[0], test2[1], 240, 180)
#                continue
#            if x!=49:
#                next = G.dot(np.array([y, x, Print[y,x+1], 1]))
#                if next[2] != 0.0:
#                    move(ser, test2[0], test2[1], 240, 180)
        #if test2[]
    #time.sleep(1)
#move(ser,300,300,  350,180)
