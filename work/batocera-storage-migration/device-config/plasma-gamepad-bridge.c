#include <SDL2/SDL.h>
#include <fcntl.h>
#include <linux/input-event-codes.h>
#include <linux/uinput.h>
#include <math.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

static volatile sig_atomic_t running = 1;
static int uinput_fd = -1;
static SDL_GameController *controllers[16];
static double right_x[16];
static double right_y[16];
static bool left_click;
static bool right_click;
static bool left_trigger[16];
static bool right_trigger[16];
static bool touchpad_click[16];
static bool guide_held[16];
static bool key_state[16][KEY_MAX + 1];
static bool key_emitted[KEY_MAX + 1];
static bool touch_active[16][2];
static float touch_x[16][2];
static float touch_y[16][2];

static void stop_running(int signo)
{
    (void)signo;
    running = 0;
}

static int emit_event(uint16_t type, uint16_t code, int32_t value)
{
    struct input_event event = {
        .type = type,
        .code = code,
        .value = value,
    };
    return write(uinput_fd, &event, sizeof(event)) == sizeof(event) ? 0 : -1;
}

static int enable_key(unsigned long code)
{
    return ioctl(uinput_fd, UI_SET_KEYBIT, code);
}

static int create_uinput_device(void)
{
    static const unsigned long keys[] = {
        BTN_LEFT, BTN_RIGHT, KEY_ENTER, KEY_ESC, KEY_SPACE, KEY_TAB,
        KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_PAGEUP, KEY_PAGEDOWN,
        KEY_LEFTMETA,
    };
    struct uinput_setup setup = {
        .id = {
            .bustype = BUS_USB,
            .vendor = 0x28de,
            .product = 0x1205,
            .version = 1,
        },
    };

    snprintf(setup.name, sizeof(setup.name), "Batocera Plasma Gamepad Mouse");
    uinput_fd = open("/dev/uinput", O_WRONLY | O_NONBLOCK);
    if (uinput_fd < 0) {
        perror("Could not open /dev/uinput");
        return -1;
    }
    if (ioctl(uinput_fd, UI_SET_EVBIT, EV_KEY) < 0 ||
        ioctl(uinput_fd, UI_SET_EVBIT, EV_REL) < 0 ||
        ioctl(uinput_fd, UI_SET_RELBIT, REL_X) < 0 ||
        ioctl(uinput_fd, UI_SET_RELBIT, REL_Y) < 0 ||
        ioctl(uinput_fd, UI_SET_RELBIT, REL_WHEEL) < 0) {
        perror("Could not configure uinput event types");
        goto fail;
    }
    for (size_t i = 0; i < sizeof(keys) / sizeof(keys[0]); i++) {
        if (enable_key(keys[i]) < 0) {
            perror("Could not configure uinput key");
            goto fail;
        }
    }
    if (ioctl(uinput_fd, UI_DEV_SETUP, &setup) < 0 ||
        ioctl(uinput_fd, UI_DEV_CREATE) < 0) {
        perror("Could not create uinput device");
        goto fail;
    }
    usleep(200000);
    fprintf(stderr, "Connected to parent compositor through uinput\n");
    return 0;

fail:
    close(uinput_fd);
    uinput_fd = -1;
    return -1;
}

static void pointer_motion(double x, double y)
{
    if (uinput_fd < 0 || (x == 0 && y == 0))
        return;
    emit_event(EV_REL, REL_X, (int32_t)lround(x));
    emit_event(EV_REL, REL_Y, (int32_t)lround(y));
    emit_event(EV_SYN, SYN_REPORT, 0);
}

static void pointer_button(uint32_t button, bool pressed)
{
    if (uinput_fd < 0)
        return;
    emit_event(EV_KEY, button, pressed);
    emit_event(EV_SYN, SYN_REPORT, 0);
}

static void keyboard_key(uint32_t key, bool pressed)
{
    if (uinput_fd < 0)
        return;
    emit_event(EV_KEY, key, pressed);
    emit_event(EV_SYN, SYN_REPORT, 0);
}

static void pointer_scroll(double delta)
{
    if (uinput_fd < 0 || fabs(delta) < 1.0)
        return;
    emit_event(EV_REL, REL_WHEEL, delta > 0 ? -1 : 1);
    emit_event(EV_SYN, SYN_REPORT, 0);
}

static void open_controller(int device_index)
{
    if (!SDL_IsGameController(device_index))
        return;
    const SDL_JoystickID pending_instance = SDL_JoystickGetDeviceInstanceID(device_index);
    for (size_t i = 0; i < sizeof(controllers) / sizeof(controllers[0]); i++) {
        if (controllers[i] &&
            SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(controllers[i])) == pending_instance)
            return;
    }
    SDL_GameController *controller = SDL_GameControllerOpen(device_index);
    if (!controller)
        return;
    const int instance = SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(controller));
    for (size_t i = 0; i < sizeof(controllers) / sizeof(controllers[0]); i++) {
        if (!controllers[i]) {
            controllers[i] = controller;
            fprintf(stderr, "Controller connected: %s (instance %d)\n",
                SDL_GameControllerName(controller), instance);
            return;
        }
    }
    SDL_GameControllerClose(controller);
}

static int controller_slot(SDL_JoystickID instance)
{
    for (size_t i = 0; i < sizeof(controllers) / sizeof(controllers[0]); i++) {
        if (controllers[i] &&
            SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(controllers[i])) == instance)
            return (int)i;
    }
    return -1;
}

static void update_pointer_button(uint32_t button)
{
    bool pressed = false;
    for (size_t i = 0; i < sizeof(controllers) / sizeof(controllers[0]); i++) {
        if (button == BTN_LEFT)
            pressed = pressed || left_trigger[i] || touchpad_click[i];
        else
            pressed = pressed || right_trigger[i];
    }

    bool *emitted = button == BTN_LEFT ? &left_click : &right_click;
    if (pressed != *emitted) {
        *emitted = pressed;
        pointer_button(button, pressed);
    }
}

static void update_keyboard_key(uint32_t key)
{
    bool pressed = false;
    for (size_t i = 0; i < sizeof(controllers) / sizeof(controllers[0]); i++)
        pressed = pressed || key_state[i][key];
    if (pressed != key_emitted[key]) {
        key_emitted[key] = pressed;
        keyboard_key(key, pressed);
    }
}

static void release_controller_state(int slot)
{
    right_x[slot] = 0;
    right_y[slot] = 0;
    left_trigger[slot] = false;
    right_trigger[slot] = false;
    touchpad_click[slot] = false;
    guide_held[slot] = false;
    update_pointer_button(BTN_LEFT);
    update_pointer_button(BTN_RIGHT);
    for (size_t key = 0; key <= KEY_MAX; key++) {
        if (key_state[slot][key]) {
            key_state[slot][key] = false;
            update_keyboard_key((uint32_t)key);
        }
    }
}

static void close_controller(SDL_JoystickID instance)
{
    const int slot = controller_slot(instance);
    if (slot < 0)
        return;
    fprintf(stderr, "Controller disconnected: %s\n", SDL_GameControllerName(controllers[slot]));
    release_controller_state(slot);
    SDL_GameControllerClose(controllers[slot]);
    controllers[slot] = NULL;
    memset(touch_active[slot], 0, sizeof(touch_active[slot]));
}

static double normalized_axis(Sint16 value)
{
    double axis = value >= 0 ? value / 32767.0 : value / 32768.0;
    const double deadzone = 0.18;
    if (fabs(axis) < deadzone)
        return 0;
    return copysign((fabs(axis) - deadzone) / (1.0 - deadzone), axis);
}

static void handle_axis(const SDL_ControllerAxisEvent *event)
{
    const int slot = controller_slot(event->which);
    if (slot < 0)
        return;
    if (event->axis == SDL_CONTROLLER_AXIS_RIGHTX)
        right_x[slot] = normalized_axis(event->value);
    else if (event->axis == SDL_CONTROLLER_AXIS_RIGHTY)
        right_y[slot] = normalized_axis(event->value);
    else if (event->axis == SDL_CONTROLLER_AXIS_TRIGGERLEFT) {
        const bool pressed = event->value > 24000;
        if (pressed != right_trigger[slot]) {
            right_trigger[slot] = pressed;
            update_pointer_button(BTN_RIGHT);
        }
    } else if (event->axis == SDL_CONTROLLER_AXIS_TRIGGERRIGHT) {
        const bool pressed = event->value > 24000;
        if (pressed != left_trigger[slot]) {
            left_trigger[slot] = pressed;
            update_pointer_button(BTN_LEFT);
        }
    }
}

static void toggle_osk(void)
{
    FILE *command = fopen("/mnt/batocera/desktop-tools/plasma-command", "w");
    if (!command)
        return;
    fputs("osk-toggle\n", command);
    fclose(command);
}

static void handle_button(const SDL_ControllerButtonEvent *event)
{
    const int slot = controller_slot(event->which);
    if (slot < 0)
        return;
    const bool pressed = event->state == SDL_PRESSED;
    uint32_t key = 0;

    switch (event->button) {
    case SDL_CONTROLLER_BUTTON_GUIDE:
        guide_held[slot] = pressed;
        return;
    case SDL_CONTROLLER_BUTTON_A: key = KEY_ENTER; break;
    case SDL_CONTROLLER_BUTTON_B: key = KEY_ESC; break;
    case SDL_CONTROLLER_BUTTON_X:
        if (pressed && guide_held[slot]) {
            toggle_osk();
            return;
        }
        key = KEY_SPACE;
        break;
    case SDL_CONTROLLER_BUTTON_Y: key = KEY_TAB; break;
    case SDL_CONTROLLER_BUTTON_DPAD_UP: key = KEY_UP; break;
    case SDL_CONTROLLER_BUTTON_DPAD_DOWN: key = KEY_DOWN; break;
    case SDL_CONTROLLER_BUTTON_DPAD_LEFT: key = KEY_LEFT; break;
    case SDL_CONTROLLER_BUTTON_DPAD_RIGHT: key = KEY_RIGHT; break;
    case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: key = KEY_PAGEUP; break;
    case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: key = KEY_PAGEDOWN; break;
    case SDL_CONTROLLER_BUTTON_START: key = KEY_LEFTMETA; break;
    case SDL_CONTROLLER_BUTTON_TOUCHPAD:
        touchpad_click[slot] = pressed;
        update_pointer_button(BTN_LEFT);
        return;
    default:
        return;
    }
    key_state[slot][key] = pressed;
    update_keyboard_key(key);
}

static void handle_touch(const SDL_ControllerTouchpadEvent *event)
{
    const int slot = controller_slot(event->which);
    if (slot < 0 || event->finger < 0 || event->finger >= 2)
        return;

    const bool pointer_pad = SDL_GameControllerGetNumTouchpads(controllers[slot]) == 1 || event->touchpad == 1;
    if (event->type == SDL_CONTROLLERTOUCHPADDOWN) {
        touch_active[slot][event->finger] = true;
    } else if (event->type == SDL_CONTROLLERTOUCHPADUP) {
        touch_active[slot][event->finger] = false;
    } else if (event->type == SDL_CONTROLLERTOUCHPADMOTION && touch_active[slot][event->finger]) {
        const double dx = (event->x - touch_x[slot][event->finger]) * 1100.0;
        const double dy = (event->y - touch_y[slot][event->finger]) * 700.0;
        if (pointer_pad)
            pointer_motion(dx, dy);
        else
            pointer_scroll(dy);
    }
    touch_x[slot][event->finger] = event->x;
    touch_y[slot][event->finger] = event->y;
}

static void handle_sdl_events(void)
{
    SDL_Event event;
    while (SDL_PollEvent(&event)) {
        switch (event.type) {
        case SDL_CONTROLLERDEVICEADDED: open_controller(event.cdevice.which); break;
        case SDL_CONTROLLERDEVICEREMOVED: close_controller(event.cdevice.which); break;
        case SDL_CONTROLLERAXISMOTION: handle_axis(&event.caxis); break;
        case SDL_CONTROLLERBUTTONDOWN:
        case SDL_CONTROLLERBUTTONUP: handle_button(&event.cbutton); break;
        case SDL_CONTROLLERTOUCHPADDOWN:
        case SDL_CONTROLLERTOUCHPADMOTION:
        case SDL_CONTROLLERTOUCHPADUP: handle_touch(&event.ctouchpad); break;
        default: break;
        }
    }
}

int main(void)
{
    signal(SIGINT, stop_running);
    signal(SIGTERM, stop_running);

    if (create_uinput_device() < 0)
        return 1;

    if (SDL_Init(SDL_INIT_GAMECONTROLLER | SDL_INIT_EVENTS) < 0) {
        fprintf(stderr, "SDL initialization failed: %s\n", SDL_GetError());
        return 1;
    }
    SDL_SetHint(SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS, "1");
    for (int i = 0; i < SDL_NumJoysticks(); i++)
        open_controller(i);

    while (running) {
        handle_sdl_events();

        double pointer_x = 0;
        double pointer_y = 0;
        double magnitude = 0;
        for (size_t i = 0; i < sizeof(controllers) / sizeof(controllers[0]); i++) {
            const double candidate = hypot(right_x[i], right_y[i]);
            if (candidate > magnitude) {
                magnitude = candidate;
                pointer_x = right_x[i];
                pointer_y = right_y[i];
            }
        }
        if (magnitude > 0) {
            const double speed = 0.6 + 5.0 * magnitude * magnitude;
            pointer_motion(pointer_x * speed, pointer_y * speed);
        }
        SDL_Delay(5);
    }

    for (size_t i = 0; i < sizeof(controllers) / sizeof(controllers[0]); i++) {
        if (controllers[i]) {
            release_controller_state((int)i);
            SDL_GameControllerClose(controllers[i]);
        }
    }
    SDL_Quit();
    if (uinput_fd >= 0) {
        ioctl(uinput_fd, UI_DEV_DESTROY);
        close(uinput_fd);
    }
    return 0;
}
