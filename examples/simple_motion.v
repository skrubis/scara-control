;===============================================================================
; SIMPLE_MOTION.V - Basic motion program template
;===============================================================================
; Description: Simple pick and place motion routine
; 
; Setup before running:
; 1. Jog robot to positions using Cobra Jogger
; 2. At each position, type: HERE location_name
; 3. Upload this program
; 4. Execute: DO simple_motion
;
; Safety: Test in free space first!
;===============================================================================

.PROGRAM simple_motion

  ; Initialization
  AUTO
  TYPE "Simple Motion Program Starting..."
  
  ; Set motion parameters
  SPEED 50 ALWAYS        ; 50% speed
  ACCEL 50, 50          ; 50% acceleration/deceleration
  
  ; Teach positions (do this manually first!)
  ; At V+ prompt, jog to each position and type:
  ;   HERE home
  ;   HERE pickup
  ;   HERE place
  ;
  ; Or define them here if you know coordinates:
  ; SET home = TRANS(0, 300, 50, 0)
  ; SET pickup = TRANS(200, 200, 50, 0)
  ; SET place = TRANS(-200, 200, 50, 0)
  
  TYPE "Moving to home position..."
  MOVE home
  DELAY 1.0
  
  ; Pick and place cycle
  cycle_count = 0
  WHILE cycle_count < 3 DO
    cycle_count = cycle_count + 1
    TYPE "Starting cycle ", cycle_count
    
    ; Move to pickup
    TYPE "  Moving to pickup..."
    APPRO pickup, 50      ; Approach 50mm above
    MOVE pickup           ; Move to pickup
    DELAY 0.5             ; Dwell
    ; CLOSE 1             ; Close gripper (if equipped)
    DELAY 0.5
    DEPART 50             ; Depart 50mm up
    
    ; Move to place
    TYPE "  Moving to place..."
    APPRO place, 50       ; Approach 50mm above
    MOVE place            ; Move to place
    DELAY 0.5             ; Dwell
    ; OPEN 1              ; Open gripper (if equipped)
    DELAY 0.5
    DEPART 50             ; Depart 50mm up
    
    TYPE "  Cycle complete"
  END
  
  ; Return home
  TYPE "Returning home..."
  MOVE home
  
  TYPE "Program complete - ", cycle_count, " cycles"

.END
