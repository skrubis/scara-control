import serial
import time
#ser = serial.Serial('COM3')  # open serial port
robotenable = True
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
   
if robotenable:
    ser = serial.Serial()
    ser.close()
    print("robot enable")
    ser.port = 'COM3'
    #ser.baudrate = 19200
    ser.baudrate = 9600
    #ser.baudrate = 38400
    ser.xonxoff = False
    ser.rtscts = False
    ser.dsrdtr = False
    ser.open()
    print(ser.name) # check which port was really used
    ser.is_open
    
    #ser.write(bytes(b"CALIBRATE \n\r"))
    #ser.write(bytes(b"Y \n\r"))
    #time.sleep(240)    
    ser.write(bytes(b"SPEED 50 \n\r"))
    time.sleep(0.5)
    print("initialized")

while True:
    ser.is_open
    ser.write(b"\n\r")
    move(ser,300,-440,180,240)
    time.sleep(.5)
    move(ser,300,-400,240,210)
    time.sleep(.5)
    #time.sleep(1)
    #move(ser,300,-400,200,210)
    #time.sleep(1)
    #move(ser,-300,200,350,180)
    #time.sleep(1)
    #move(ser,300,-450,250,180)
    #time.sleep(2)


    
#ser.close()

    

