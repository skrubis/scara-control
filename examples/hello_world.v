;===============================================================================
; HELLO_WORLD.V - Simple test program to verify upload works
;===============================================================================
; Description: Prints messages to verify program execution
; Usage: DO hello_world
;===============================================================================

.PROGRAM hello_world

  ; Program initialization
  AUTO
  
  ; Print greeting
  TYPE "========================================="
  TYPE "   Hello from uploaded V+ program!"
  TYPE "========================================="
  TYPE ""
  TYPE "Program: HELLO_WORLD"
  TYPE "Status: Running"
  TYPE ""
  
  ; Countdown demonstration
  TYPE "Starting countdown..."
  TYPE "3..."
  DELAY 1.0
  TYPE "2..."
  DELAY 1.0
  TYPE "1..."
  DELAY 1.0
  TYPE "GO!"
  TYPE ""
  
  ; Variable demonstration
  counter = 0
  WHILE counter < 5 DO
    counter = counter + 1
    TYPE "Loop iteration: ", counter
    DELAY 0.5
  END
  
  TYPE ""
  TYPE "Program complete!"
  TYPE "========================================="

.END
