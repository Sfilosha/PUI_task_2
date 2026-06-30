import machine
import utime
import ssd1306
import json

# --- Ініціалізація обладнання ---
i2c = machine.I2C(0, scl=machine.Pin(5), sda=machine.Pin(4), freq=400000)
oled = ssd1306.SSD1306_I2C(128, 64, i2c)

led_r = machine.Pin(18, machine.Pin.OUT)
led_g = machine.Pin(19, machine.Pin.OUT)
led_b = machine.Pin(20, machine.Pin.OUT)

buzzer = machine.PWM(machine.Pin(22))
servo = machine.PWM(machine.Pin(21))
servo.freq(50)

btn_presence = machine.Pin(2, machine.Pin.IN, machine.Pin.PULL_DOWN)
btn_tamper = machine.Pin(3, machine.Pin.IN, machine.Pin.PULL_DOWN)
sw_key = machine.Pin(26, machine.Pin.IN, machine.Pin.PULL_DOWN)

rows = [machine.Pin(i, machine.Pin.OUT) for i in range(9, 13)]
cols = [machine.Pin(i, machine.Pin.IN, machine.Pin.PULL_DOWN) for i in range(13, 17)]
keys = [['1','2','3','A'], ['4','5','6','B'], ['7','8','9','C'], ['*','0','#','D']]

# --- Змінні стану ---
current_state = "LOCKED_IDLE"
pin_buffer = ""
fail_count = 0
last_state_log = ""

# --- Допоміжні функції ---
def get_timestamp():
    # Проста імітація таймстемпу для прототипу (у Pico без інтернету час починається з нуля)
    t = utime.localtime()
    return f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d}T{t[3]:02d}:{t[4]:02d}:{t[5]:02d}Z"

def log_json(event, state, user_id, ai_analysis, action, fallback=False):
    payload = {
        "event": event,
        "state": state,
        "user_id": user_id,
        "timestamp": get_timestamp(),
        "ai_analysis": ai_analysis,
        "action": action,
        "fallback": fallback,
        "schema_version": "v1.2"
    }
    print("\n=== AI_SYSTEM_LOG ===")
    print(json.dumps(payload))
    print("=====================\n")

def set_rgb(r, g, b):
    led_r.value(r)
    led_g.value(g)
    led_b.value(b)

def play_tone(freq, duration_ms):
    buzzer.freq(freq)
    buzzer.duty_u16(30000)
    utime.sleep_ms(duration_ms)
    buzzer.duty_u16(0)

def set_lock(open_lock):
    if open_lock:
        servo.duty_u16(8000) # Відчинено (~90 градусів)
    else:
        servo.duty_u16(2000) # Зачинено (0 градусів)

def show_screen(line1, line2="", line3="", line4=""):
    oled.fill(0)
    oled.text(line1, 0, 0)
    oled.text(line2, 0, 20)
    oled.text(line3, 0, 40)
    oled.text(line4, 0, 50)
    oled.show()

def read_keypad():
    for i, row in enumerate(rows):
        row.value(1)
        for j, col in enumerate(cols):
            if col.value() == 1:
                row.value(0)
                utime.sleep_ms(200) # Debounce
                return keys[i][j]
        row.value(0)
    return None

def mock_ai_check(pin):
    if pin == "1234":
        return "GRANTED"
    elif pin == "9999": 
        return "LOW_CONFIDENCE"
    else:
        return "DENIED"

# --- Стартові налаштування ---
set_lock(False)
set_rgb(0, 0, 0)
print("SYSTEM STARTED. Waiting for interaction...")

# --- Головний цикл (State Machine) ---
while True:
    
    # Логування зміни стану в консоль
    if current_state != last_state_log:
        print(f"[STATE CHANGE] -> {current_state}")
        last_state_log = current_state

    # 1. Глобальні переривання
    if sw_key.value() == 1:
        current_state = "DOOR_OPEN"
        show_screen("MECH KEY USED", "System Override")
        set_lock(True)
        set_rgb(0, 1, 1) # Cyan
        
        log_json("MANUAL_KEY_USED", "OVERRIDE", "admin", None, "ACCESS_GRANTED", True)
        
        while sw_key.value() == 1:
            utime.sleep_ms(100)
        current_state = "AUTO_RELOCK"

    elif btn_tamper.value() == 1:
        current_state = "SAFE_MODE"
        show_screen("! SAFE MODE !", "TAMPER DETECTED", "LOCKED")
        set_lock(False)
        
        log_json("TAMPER_DETECTED", "SAFE_MODE", "system", {"confidence": 0.99, "anomaly_reason": "physical_force", "ai_result": "critical_threat"}, "TRIGGER_ALARM")
        
        while btn_tamper.value() == 1:
            set_rgb(1, 0, 0)
            play_tone(1000, 100)
            set_rgb(0, 0, 0)
            play_tone(1500, 100)
        current_state = "LOCKED_IDLE" 

    # 2. Логіка станів
    if current_state == "LOCKED_IDLE":
        show_screen("LOCKED_IDLE", "Waiting...")
        set_rgb(0, 0, 0)
        pin_buffer = ""
        
        if btn_presence.value() == 1:
            current_state = "PRESENCE_DETECTED"
            play_tone(500, 100)

    elif current_state == "PRESENCE_DETECTED":
        show_screen("Enter PIN:")
        set_rgb(1, 1, 1)
        
        key = read_keypad()
        if key:
            current_state = "AUTH_INPUT"
            pin_buffer += key
            play_tone(800, 50)

    elif current_state == "AUTH_INPUT":
        show_screen("Enter PIN:", "*" * len(pin_buffer))
        
        key = read_keypad()
        if key:
            play_tone(800, 50)
            set_rgb(0, 0, 0)
            utime.sleep_ms(50)
            set_rgb(1, 1, 1)
            
            if key == '#': # Enter
                current_state = "AI_CHECK"
            elif key == '*': # Clear
                pin_buffer = ""
            elif len(pin_buffer) < 8:
                pin_buffer += key

    elif current_state == "AI_CHECK":
        show_screen("AI CHECKING...", "Context Analyze")
        set_rgb(0, 0, 1)
        
        utime.sleep(1.5) # Імітація обробки
        
        result = mock_ai_check(pin_buffer)
        if result == "GRANTED":
            log_json("PIN_ENTERED", "AUTH_INPUT", "cowork_res_402", {"confidence": 0.92, "anomaly_reason": "none", "ai_result": "normal_attempt"}, "ACCESS_GRANTED")
            current_state = "ACCESS_GRANTED"
            fail_count = 0
            
        elif result == "LOW_CONFIDENCE":
            log_json("PIN_ENTERED", "AUTH_INPUT", "cowork_res_402", {"confidence": 0.35, "anomaly_reason": "unusual_time_for_user", "ai_result": "suspicious_attempt"}, "ACCESS_DENIED")
            current_state = "ACCESS_DENIED"
            show_screen("AI: DENIED", "Anomalous Time")
            utime.sleep(2)
            
        else:
            fail_count += 1
            if fail_count >= 3:
                log_json("PIN_ENTERED", "AUTH_INPUT", "unknown_user", {"confidence": 0.05, "anomaly_reason": "brute_force_detected", "ai_result": "malicious_attempt"}, "LOCKOUT")
                current_state = "LOCKOUT"
            else:
                log_json("PIN_ENTERED", "AUTH_INPUT", "unknown_user", {"confidence": 0.15, "anomaly_reason": "invalid_credentials", "ai_result": "rejected"}, "ACCESS_DENIED")
                current_state = "ACCESS_DENIED"
                show_screen("DENIED", f"Fails: {fail_count}/3")
                utime.sleep(2)

    elif current_state == "ACCESS_GRANTED":
        show_screen("ACCESS GRANTED", "Welcome!")
        set_rgb(0, 1, 0)
        play_tone(1000, 150)
        play_tone(1500, 200)
        current_state = "DOOR_OPEN"

    elif current_state == "DOOR_OPEN":
        set_lock(True)
        show_screen("DOOR OPEN", "Please enter")
        set_rgb(0, 1, 0)
        utime.sleep(3) 
        current_state = "AUTO_RELOCK"

    elif current_state == "AUTO_RELOCK":
        show_screen("LOCKING...")
        set_lock(False)
        play_tone(600, 200)
        set_rgb(1, 1, 0)
        utime.sleep(1)
        current_state = "LOCKED_IDLE"

    elif current_state == "ACCESS_DENIED":
        set_rgb(1, 0, 0)
        play_tone(400, 300)
        current_state = "PRESENCE_DETECTED"
        pin_buffer = ""

    elif current_state == "LOCKOUT":
        show_screen("SYSTEM LOCKOUT", "Wait 10 sec...")
        set_rgb(1, 0.5, 0)
        play_tone(200, 500)
        utime.sleep(10)
        fail_count = 0
        current_state = "LOCKED_IDLE"
        
    utime.sleep_ms(50)