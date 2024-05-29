"""
A barebones CHIP-8 emulator.
"""
import argparse
import time
import random
import pickle
import json
import pygame
import colorama

# region Config
config = {
    "clock_speed":     500,          # clock speed in Hz
    "rom":             "roms/6-keypad", # name of the ROM (without .ch8 - also used for config file name)
    "shift_mode":      "cosmac_vip", # can be "schip" or "cosmac_vip"
    "jmp_offset_mode": "cosmac_vip", # can be "schip" or "cosmac_vip"
    "random_mode":     "python",     # can be "python" or "zero"
    "add_index_mode":  "cosmac_vip", # can be "amiga" or "cosmac_vip",
    "store_load_mode": "cosmac_vip", # can be "schip" or "cosmac_vip",
    "font":            "default",    # can be "default" or the name of a font pkl file
    "log_chars":       True,         # log all characters fetched from the fontset to the console (makeshift tty mode)
    "debug":           False,        # enable debug mode
    "breakpoints":     [],           # list of pc values to break at
    "allow_unknown":   False,        # allow unknown opcodes to be ignored by default,
    "inject_ram":      {}            # inject values into specific RAM addresses at startup
}

# region Constants
running = True
ram = [0] * 4096
display = [[0] * 64 for _ in range(32)]
pc = 0x200
index = 0
stack = []
delay_timer = 0
sound_timer = 0
variables = [0] * 16
fontset = pickle.load(open("fontsets/default.pkl" if config["font"] == "default" else f"fontsets/{config['font']}", "rb"))
# https://tobiasvl.github.io/assets/images/cosmac-vip-keypad.png
key_actions = [False] * 16
keybinds = [
    pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4,
    pygame.K_q, pygame.K_w, pygame.K_e, pygame.K_r,
    pygame.K_a, pygame.K_s, pygame.K_d, pygame.K_f,
    pygame.K_z, pygame.K_x, pygame.K_c, pygame.K_v
]
most_recent_opcode = ""
char_log = ""

# region Utilities
def decrement_timers():
    global delay_timer, sound_timer
    if delay_timer > 0:
        delay_timer -= 1
    if sound_timer > 0:
        sound_timer -= 1
        # TODO: play noise

def get_shifted_bit(value, shift_amount):
    shifted_value = value >> shift_amount
    shifted_out_bit = (value >> (shift_amount - 1)) & 1
    return shifted_value, shifted_out_bit

def is_pressed(key_index) -> bool:
    global key_actions
    print("getting " + str(key_index) + " " + str(key_actions[key_index]))
    return key_actions[key_index]

def print_debug(config_override=None):
    print(f"PC: {pc}, I: {index}, Stack: {stack}, Delay: {delay_timer}, Sound: {sound_timer}, Vars: {variables}")
    if config["debug"]:
        print("RAM:")
        for i in range(0, 4096, 64):
            print("".join([f"{ram[i + j]:02X}" for j in range(64)]))
    if not config_override or config[config_override]:
        res = input("Continue anyway? [y/N] ")
        if res.lower() != "y":
            print("Halting...")
            exit(1)

# region Main loop
def main_loop():
    global ram, display, pc, index, stack, delay_timer, sound_timer, variables, fontset, key_layout, config, running, most_recent_opcode, char_log
    opcode = (ram[pc] << 8) | ram[pc + 1]
    pc += 2
    x = (opcode & 0x0F00) >> 8
    y = (opcode & 0x00F0) >> 4
    n = opcode & 0x000F
    nn = opcode & 0x00FF
    nnn = opcode & 0x0FFF
    # clear
    if opcode == 0x00E0:
        most_recent_opcode = "clear"
        display = [[0] * 64 for _ in range(32)]
    # jmp
    elif (opcode & 0xF000) == 0x1000:
        most_recent_opcode = "jump to " + hex(nnn)
        pc = nnn
    # call
    elif (opcode & 0xF000) == 0x2000:
        most_recent_opcode = "call " + hex(nnn)
        stack.append(pc)
        pc = nnn
    # return
    elif opcode == 0x00EE:
        most_recent_opcode = "return"
        try:
            pc = stack.pop()
        except IndexError:
            print(colorama.Fore.RED + "----- ERROR -----" + colorama.Style.RESET_ALL)
            print(colorama.Fore.RED + "Stack underflow" + colorama.Style.RESET_ALL)
            print_debug()
    # skip if equal to
    elif (opcode & 0xF000) == 0x3000:
        most_recent_opcode = f"skip if V{x} == {nn}"
        if variables[x] == nn:
            pc += 2
    # skip if not equal to
    elif (opcode & 0xF000) == 0x4000:
        most_recent_opcode = f"skip if V{x} != {nn}"
        if variables[x] != nn:
            pc += 2
    # skip if equal
    elif (opcode & 0xF00F) == 0x5000:
        most_recent_opcode = f"skip if V{x} == V{y}"
        if variables[x] == variables[y]:
            pc += 2
    # skip if not equal
    elif (opcode & 0xF00F) == 0x9000:
        most_recent_opcode = f"skip if V{x} != V{y}"
        if variables[x] != variables[y]:
            pc += 2
    # set
    elif (opcode & 0xF000) == 0x6000:
        most_recent_opcode = f"set V{x} to {nn}"
        variables[x] = nn
    # add
    elif (opcode & 0xF000) == 0x7000:
        most_recent_opcode = f"add {nn} to V{x}"
        variables[x] += nn
    # set
    elif (opcode & 0xF00F) == 0x8000:
        most_recent_opcode = f"set V{x} to V{y}"
        variables[x] = variables[y]
    # binary or
    elif (opcode & 0xF00F) == 0x8001:
        most_recent_opcode = f"V{x} |= V{y}"
        variables[x] |= variables[y]
    # binary and
    elif (opcode & 0xF00F) == 0x8002:
        most_recent_opcode = f"V{x} &= V{y}"
        variables[x] &= variables[y]
    # binary xor
    elif (opcode & 0xF00F) == 0x8003:
        most_recent_opcode = f"V{x} ^= V{y}"
        variables[x] ^= variables[y]
    # add
    elif (opcode & 0xF00F) == 0x8004:
        most_recent_opcode = f"V{x} += V{y}"
        sum = variables[x] + variables[y]
        variables[x] = sum & 0xFF
        # VF is set to 1 if there is a carry, 0 otherwise
        variables[0xF] = 1 if sum > 255 else 0
    # subtract
    elif (opcode & 0xF00F) == 0x8005:
        most_recent_opcode = f"V{x} -= V{y}"
        # VX = VX - VY
        # VF is set to 0 if there is a borrow, 1 otherwise
        variables[0xF] = 1 if variables[x] > variables[y] else 0
        variables[x] -= variables[y]
    elif (opcode & 0xF00F) == 0x8007:
        most_recent_opcode = f"V{x} = V{y} - V{x}"
        # VX = VY - VX
        # VF is set to 0 if there is a borrow, 1 otherwise
        variables[0xF] = 1 if variables[y] > variables[x] else 0
        variables[x] = variables[y] - variables[x]
    # shift
    elif (opcode & 0xF00F) == 0x8006:
        most_recent_opcode = f"V{x} >>= 1"
        if config["shift_mode"] == "cosmac_vip":
            variables[x] = variables[y]
        new_value, shifted_out = get_shifted_bit(variables[x], 1)
        variables[x] = new_value
        variables[0xF] = shifted_out
    elif (opcode & 0xF00F) == 0x800E:
        most_recent_opcode = f"V{x} <<= 1"
        if config["shift_mode"] == "cosmac_vip":
            variables[x] = variables[y]
        new_value, shifted_out = get_shifted_bit(variables[x], 7)
        variables[x] = new_value
    # set index
    elif (opcode & 0xF000) == 0xA000:
        most_recent_opcode = f"set I to {nnn}"
        index = nnn
    # jmp with offset
    elif (opcode & 0xF000) == 0xB000:
        most_recent_opcode = f"jump to {nnn} + V0"
        if config["jmp_offset_mode"] == "cosmac_vip":
            pc = nnn + variables[0]
        else:
            pc = nnn + variables[x]
    # random
    elif (opcode & 0xF000) == 0xC000:
        most_recent_opcode = f"V{x} = random & {nn}"
        if config["random_mode"] == "python":
            variables[x] = random.randint(0, 255) & nn
        else:
            variables[x] = 0
    # draw
    elif (opcode & 0xF000) == 0xD000:
        x_coord = variables[x] % 64
        y_coord = variables[y] % 32
        most_recent_opcode = f"draw at V{x} {x_coord}, V{y} {y_coord}, {n}"
        variables[0xF] = 0
        for j in range(n):
            byte = ram[index + j]
            for i in range(8):
                if byte & (0x80 >> i):
                    if display[y_coord + j][x_coord + i]:
                        variables[0xF] = 1
                    display[y_coord + j][x_coord + i] ^= 1
    # skip if key
    elif (opcode & 0xF0FF) == 0xE09E:
        most_recent_opcode = f"skip if key {variables[x]} is pressed"
        if is_pressed(variables[x]):
            most_recent_opcode = f"skip if key {variables[x]} is pressed (skipped)"
            pc += 2
    # skip if not key
    elif (opcode & 0xF0FF) == 0xE0A1:
        most_recent_opcode = f"skip if key {variables[x]} is not pressed"
        if not is_pressed(variables[x]):
            most_recent_opcode = f"skip if key {variables[x]} is not pressed (skipped)"
            pc += 2
    # get delay timer
    elif (opcode & 0xF0FF) == 0xF007:
        most_recent_opcode = f"set V{x} to delay timer {delay_timer}"
        variables[x] = delay_timer
    # set delay timer
    elif (opcode & 0xF0FF) == 0xF015:
        most_recent_opcode = f"set delay timer to V{x}"
        delay_timer = variables[x]
    # set sound timer
    elif (opcode & 0xF0FF) == 0xF018:
        most_recent_opcode = f"set sound timer to V{x}"
        sound_timer = variables[x]
    # add to index
    elif (opcode & 0xF0FF) == 0xF01E:
        most_recent_opcode = f"add V{x} to I {index}"
        index += variables[x]
        if index > 0xFFF:
            index -= 0xFFF
            if config["add_index_mode"] == "amiga":
                variables[0xF] = 1
    # get key
    elif (opcode & 0xF0FF) == 0xF00A:
        most_recent_opcode = f"wait for key press, store in V{x}"
        for i, key in enumerate(key_actions):
            if key:
                variables[x] = i
                break
            else:
                pc -= 2
    # set index to font
    elif (opcode & 0xF0FF) == 0xF029:
        most_recent_opcode = f"set I {index} to font for V{x}"
        index = variables[x] * 5
        if config["log_chars"]:
            char_log += f"{variables[x]:02X} "
    # binary coded decimal
    elif (opcode & 0xF0FF) == 0xF033:
        most_recent_opcode = f"store decimal of V{x} at I {index}"
        ram[index] = variables[x] // 100
        ram[index + 1] = (variables[x] // 10) % 10
        ram[index + 2] = variables[x] % 10
    # store registers
    elif (opcode & 0xF0FF) == 0xF055:
        most_recent_opcode = f"store V0 to V{x} at I {index}"
        for i in range(x + 1):
            ram[index + i] = variables[i]
        if config["store_load_mode"] != "schip":
            index += x + 1
    # load registers
    elif (opcode & 0xF0FF) == 0xF065:
        most_recent_opcode = f"load V0 to V{x} from I {index}"
        for i in range(x + 1):
            variables[i] = ram[index + i]
        if config["store_load_mode"] != "schip":
            index += x + 1
    else:
        print(colorama.Fore.RED + "----- ERROR -----" + colorama.Style.RESET_ALL)
        print(colorama.Fore.RED + f"Unknown opcode: {hex(opcode)}" + colorama.Style.RESET_ALL)
        print_debug(config_override="allow_unknown")
    # loop back variables if they go out of bounds
    for i in range(16):
        variables[i] &= 0xFF

# region Rendering
def render(screen):
    print("\033[H\033[J", end="")
    print(f"PC: {pc}\nI: {index}\nStack: {stack}\nDelay: {delay_timer}\nSound: {sound_timer}\nVars: {variables}")
    print(most_recent_opcode)
    if config["log_chars"]:
        print(char_log)
    print(key_actions)
    screen.fill((0, 0, 0))
    for y, row in enumerate(display):
        for x, val in enumerate(row):
            if val:
                pygame.draw.rect(screen, (255, 255, 255), (x * 10, y * 10, 10, 10))
    pygame.display.flip()
    if pc in config["breakpoints"]:
        res = input("Breakpoint hit. Would you like to step or continue? [S/c] ")
        if res.lower() != "c":
            print("Enabled stepping. Debugging mode enabled.")
            config["debug"] = True
    if config["debug"]:
        res = input("Press enter to step, or type 'c' to continue... ")
        if res.lower() == "c":
            config["debug"] = False

# region Key handling
def get_keys():
    global key_actions
    keys = pygame.key.get_pressed()
    for i, key in enumerate(keybinds):
        key_actions[i] = keys[key]

# region Entry
def main():
    global ram, display, pc, index, stack, delay_timer, sound_timer, variables, fontset, key_layout, config, running
    for i, val in enumerate(fontset):
        ram[i] = val
    with open(config["rom"]+".ch8", "rb") as f:
        rom = f.read()
    try:
        with open(config["rom"]+".json", "r") as f:
            rom_config = json.load(f)
        for key, val in rom_config.items():
            config[key] = val
    except:
        pass
    for i, val in enumerate(rom):
        ram[i + 0x200] = val
    for addr, val in config["inject_ram"].items():
        ram[int(addr)] = val
    pygame.init()
    screen = pygame.display.set_mode((640, 320))
    pygame.display.set_caption("Stupid CHIP-8 Emulator")
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        get_keys()
        main_loop()
        decrement_timers()
        render(screen)
        time.sleep(1 / config["clock_speed"])

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass