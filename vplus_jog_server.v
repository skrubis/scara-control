;===============================================================================
; V+ JOG SERVER FOR ADEPT COBRA 600
;===============================================================================
; Description: Receives velocity commands from PC and executes smooth jogging
; Protocol: Text-based velocity packets with CRC16 checksum
; Serial Port: SERIAL(2) - must be configured before running
; Update Rate: 50 Hz (20ms cycle time)
;
; Setup Instructions:
; 1. Transfer this file to V+ controller
; 2. Configure serial port: SERIAL 2, 115200, 8, 1, 0
; 3. Execute: DO jogserver
; 4. On PC side, switch to "V+ Jog Server" mode
;
; Protocol Format: V <vx> <vy> <vz> <vtheta> *<CRC16>\r\n
; Example: V 100.50 -50.25 0.00 5.50 *A3F2\r\n
;
; Safety: Includes timeout watchdog - stops motion if no packet for 200ms
;===============================================================================

.PROGRAM jogserver

;----- Configuration Parameters -----
GLOBAL cycle_time = 0.02        ; 50 Hz update rate (20ms)
GLOBAL timeout_limit = 0.2      ; Watchdog timeout (200ms)
GLOBAL max_velocity = 500.0     ; Max velocity limit (mm/s or deg/s)

;----- State Variables -----
GLOBAL vx, vy, vz, vtheta      ; Current velocities
GLOBAL last_packet_time        ; Timestamp of last valid packet
GLOBAL packet_count            ; Total packets received
GLOBAL error_count             ; Checksum errors

;----- Initialization -----
AUTO
TYPE "==================================="
TYPE "   Cobra 600 Jog Server v1.0"
TYPE "==================================="
TYPE "Protocol: V vx vy vz vtheta *CRC16"
TYPE "Cycle time: ", cycle_time, " seconds"
TYPE "Timeout: ", timeout_limit, " seconds"
TYPE ""

; Initialize velocities to zero
vx = 0.0
vy = 0.0
vz = 0.0
vtheta = 0.0

packet_count = 0
error_count = 0
last_packet_time = TIMER

; Set motion parameters
SPEED 100 ALWAYS
ACCEL 100, 100

TYPE "Jog Server Ready - Waiting for commands..."
TYPE ""

;----- Main Loop -----
WHILE TRUE DO
    ; Check for incoming packet on SERIAL(2)
    $packet = ""
    
    ; Non-blocking read with timeout
    READ SERIAL(2) $packet TIMEOUT 0.01
    
    ; Process packet if received
    IF LEN($packet) > 0 THEN
        ; Validate and parse packet
        CALL parse_packet($packet)
    END
    
    ; Watchdog: stop motion if no packet received within timeout
    IF (TIMER - last_packet_time) > timeout_limit THEN
        IF vx <> 0.0 OR vy <> 0.0 OR vz <> 0.0 OR vtheta <> 0.0 THEN
            ; Timeout - stop motion
            vx = 0.0
            vy = 0.0
            vz = 0.0
            vtheta = 0.0
            TYPE "WATCHDOG: Motion stopped (timeout)"
        END
    END
    
    ; Calculate incremental moves
    dx = vx * cycle_time
    dy = vy * cycle_time
    dz = vz * cycle_time
    dtheta = vtheta * cycle_time
    
    ; Clamp to safe maximums (±5mm or ±5deg per step)
    dx = MAX(-5.0, MIN(5.0, dx))
    dy = MAX(-5.0, MIN(5.0, dy))
    dz = MAX(-5.0, MIN(5.0, dz))
    dtheta = MAX(-5.0, MIN(5.0, dtheta))
    
    ; Execute motion if non-zero
    IF dx <> 0.0 OR dy <> 0.0 OR dz <> 0.0 OR dtheta <> 0.0 THEN
        DMOVE(dx, dy, dz, dtheta) NOWAIT
    END
    
    ; Maintain cycle time
    DELAY cycle_time
END

TYPE "Jog Server Stopped"
.END


;===============================================================================
; PARSE_PACKET - Validate checksum and extract velocities
;===============================================================================
; Input: $packet - received string (e.g., "V 100.0 50.0 0.0 5.0 *A3F2\r\n")
; Updates global variables: vx, vy, vz, vtheta, packet_count, error_count
;===============================================================================
.PROGRAM parse_packet($packet)

LOCAL $cmd, $vx_str, $vy_str, $vz_str, $vtheta_str, $crc_str
LOCAL calc_crc, recv_crc
LOCAL valid

valid = FALSE

; Basic format check: must start with "V " and contain "*"
IF LEFT($packet, 2) <> "V " THEN
    GOTO parse_error
END

IF INSTR($packet, "*") <= 0 THEN
    GOTO parse_error
END

; Split packet into components
; Format: V vx vy vz vtheta *CRC
; Note: V+ string parsing is limited, this is simplified

; Extract CRC (last 4 chars before \r\n)
$crc_str = ""
LOCAL crc_pos
crc_pos = INSTR($packet, "*")
IF crc_pos > 0 THEN
    $crc_str = MID($packet, crc_pos + 1, 4)  ; Get 4 hex digits after *
END

; Calculate expected CRC on everything before the *
$data_part = LEFT($packet, crc_pos - 1)
calc_crc = CALL calc_crc16($data_part)

; Convert received CRC from hex string to integer
; Note: V+ may not have native hex conversion, this is pseudo-code
recv_crc = CALL hex_to_int($crc_str)

; Validate CRC
IF calc_crc <> recv_crc THEN
    error_count = error_count + 1
    IF error_count MOD 10 = 1 THEN  ; Print every 10th error
        TYPE "CRC ERROR: Expected ", calc_crc, " Got ", recv_crc
    END
    GOTO parse_error
END

; CRC valid - parse velocities
; Extract numeric values (simplified parsing)
; In real implementation, use proper string tokenization
$values = MID($packet, 3, crc_pos - 4)  ; Extract "vx vy vz vtheta" part

; Parse individual values (pseudo-code, adapt to V+ string functions)
; V+ typically uses VAL() for string-to-number conversion
LOCAL temp_vx, temp_vy, temp_vz, temp_vtheta

; This is simplified - in real code, need proper tokenization
; Assuming space-delimited values
temp_vx = VAL(WORD($values, 1))
temp_vy = VAL(WORD($values, 2))
temp_vz = VAL(WORD($values, 3))
temp_vtheta = VAL(WORD($values, 4))

; Validate velocity limits
IF ABS(temp_vx) > max_velocity THEN GOTO parse_error
IF ABS(temp_vy) > max_velocity THEN GOTO parse_error
IF ABS(temp_vz) > max_velocity THEN GOTO parse_error
IF ABS(temp_vtheta) > max_velocity THEN GOTO parse_error

; Update global velocities
vx = temp_vx
vy = temp_vy
vz = temp_vz
vtheta = temp_vtheta

; Update state
packet_count = packet_count + 1
last_packet_time = TIMER
valid = TRUE

; Status output (throttled to every 100 packets)
IF packet_count MOD 100 = 0 THEN
    TYPE "Packets: ", packet_count, " Errors: ", error_count
END

parse_error:
IF NOT valid THEN
    ; Invalid packet - keep previous velocities for one cycle
    ; Watchdog will stop motion if errors persist
END

.END


;===============================================================================
; CALC_CRC16 - Calculate CRC-16-CCITT checksum
;===============================================================================
; Input: $data - string to calculate CRC for
; Returns: 16-bit CRC value (integer)
;
; CRC-16-CCITT: polynomial 0x1021, initial value 0xFFFF
;===============================================================================
.PROGRAM calc_crc16($data)

LOCAL crc, i, j, byte_val, data_len

crc = 65535  ; 0xFFFF initial value
data_len = LEN($data)

; Process each character
FOR i = 1 TO data_len
    byte_val = ASC(MID($data, i, 1))  ; Get ASCII value of character
    
    ; XOR byte with high byte of CRC
    crc = XOR(crc, SHL(byte_val, 8))
    
    ; Process 8 bits
    FOR j = 1 TO 8
        IF AND(crc, 32768) <> 0 THEN  ; Check if MSB is set (0x8000)
            crc = XOR(SHL(crc, 1), 4129)  ; 0x1021 polynomial
        ELSE
            crc = SHL(crc, 1)
        END
        
        ; Keep within 16 bits
        crc = AND(crc, 65535)
    END
END

RETURN crc
.END


;===============================================================================
; HEX_TO_INT - Convert 4-character hex string to integer
;===============================================================================
; Input: $hex - 4-character hex string (e.g., "A3F2")
; Returns: integer value
;===============================================================================
.PROGRAM hex_to_int($hex)

LOCAL value, i, digit, char_val

value = 0

FOR i = 1 TO 4
    digit = 0
    char_val = ASC(MID($hex, i, 1))
    
    ; Convert hex digit to value
    IF char_val >= 48 AND char_val <= 57 THEN      ; '0'-'9'
        digit = char_val - 48
    ELSE IF char_val >= 65 AND char_val <= 70 THEN ; 'A'-'F'
        digit = char_val - 55
    ELSE IF char_val >= 97 AND char_val <= 102 THEN ; 'a'-'f'
        digit = char_val - 87
    END
    
    value = value * 16 + digit
END

RETURN value
.END


;===============================================================================
; WORD - Extract Nth space-delimited word from string (helper function)
;===============================================================================
; Input: $str - input string, n - word number (1-indexed)
; Returns: the nth word
;===============================================================================
.PROGRAM WORD($str, n)

LOCAL $result, word_count, i, in_word, start_pos, end_pos
LOCAL ch

$result = ""
word_count = 0
in_word = FALSE
start_pos = 0

FOR i = 1 TO LEN($str)
    ch = MID($str, i, 1)
    
    IF ch <> " " AND NOT in_word THEN
        ; Start of new word
        word_count = word_count + 1
        in_word = TRUE
        start_pos = i
        
        IF word_count = n THEN
            end_pos = i
        END
    ELSE IF ch = " " AND in_word THEN
        ; End of word
        in_word = FALSE
        
        IF word_count = n THEN
            end_pos = i - 1
            $result = MID($str, start_pos, end_pos - start_pos + 1)
            RETURN $result
        END
    ELSE IF in_word AND word_count = n THEN
        end_pos = i
    END
END

; Handle last word (no trailing space)
IF word_count = n AND in_word THEN
    $result = MID($str, start_pos, end_pos - start_pos + 1)
END

RETURN $result
.END


;===============================================================================
; NOTES AND LIMITATIONS
;===============================================================================
;
; 1. This V+ code is written for V+ language circa 1998 (Adept controller)
;    Some functions may need adjustment based on your specific V+ version
;
; 2. String parsing in V+ is limited - you may need to adapt WORD() function
;    or use built-in functions if available (FIELD, SPLIT, etc.)
;
; 3. Bitwise operations (XOR, AND, SHL) may have different syntax on your
;    controller. Check your V+ Language Reference manual.
;
; 4. The READ SERIAL with TIMEOUT may not be supported on all V+ versions.
;    Alternative: Use STATUS SERIAL(2) to check for available data
;
; 5. For production use, consider adding:
;    - Position limits checking
;    - Collision zones
;    - E-stop integration
;    - Status LED feedback
;
; 6. Test thoroughly in free space before production use!
;
;===============================================================================
