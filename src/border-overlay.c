#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <math.h>
#include <time.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <wayland-client.h>
#include "wlr-layer-shell-unstable-v1-client-protocol.h"

#define BORDER_WIDTH 3

struct app_state {
    struct wl_display *display;
    struct wl_registry *registry;
    struct wl_compositor *compositor;
    struct wl_shm *shm;
    struct wl_surface *surface;
    struct zwlr_layer_surface_v1 *layer_surface;
    struct zwlr_layer_shell_v1 *layer_shell;
    struct wl_buffer *buffer;
    void *shm_data;
    size_t shm_size;
    int shm_fd;
    int32_t x, y, width, height;
    int configured;
    int running;
};

static void layer_surface_configure(void *data, struct zwlr_layer_surface_v1 *surface,
                                   uint32_t serial, uint32_t width, uint32_t height) {
    struct app_state *state = data;
    zwlr_layer_surface_v1_ack_configure(surface, serial);
    state->configured = 1;
}

static void layer_surface_closed(void *data, struct zwlr_layer_surface_v1 *surface) {
    struct app_state *state = data;
    state->running = 0;
}

static const struct zwlr_layer_surface_v1_listener layer_surface_listener = {
    .configure = layer_surface_configure,
    .closed = layer_surface_closed,
};

static void registry_global(void *data, struct wl_registry *registry,
                           uint32_t id, const char *interface, uint32_t version) {
    struct app_state *state = data;
    
    if (strcmp(interface, "wl_compositor") == 0) {
        state->compositor = wl_registry_bind(registry, id, &wl_compositor_interface, 1);
    } else if (strcmp(interface, "wl_shm") == 0) {
        state->shm = wl_registry_bind(registry, id, &wl_shm_interface, 1);
    } else if (strcmp(interface, "zwlr_layer_shell_v1") == 0) {
        state->layer_shell = wl_registry_bind(registry, id, &zwlr_layer_shell_v1_interface, 1);
    }
}

static void registry_global_remove(void *data, struct wl_registry *registry, uint32_t id) {}

static const struct wl_registry_listener registry_listener = {
    .global = registry_global,
    .global_remove = registry_global_remove,
};

static struct wl_buffer* create_shm_buffer(struct app_state *state) {
    int width = state->width + 2 * BORDER_WIDTH;
    int height = state->height + 2 * BORDER_WIDTH;
    int stride = width * 4;
    state->shm_size = stride * height;
    
    state->shm_fd = memfd_create("border-overlay", MFD_CLOEXEC);
    if (state->shm_fd < 0) return NULL;
    
    if (ftruncate(state->shm_fd, state->shm_size) < 0) {
        close(state->shm_fd);
        return NULL;
    }
    
    state->shm_data = mmap(NULL, state->shm_size, PROT_READ | PROT_WRITE,
                          MAP_SHARED, state->shm_fd, 0);
    if (state->shm_data == MAP_FAILED) {
        close(state->shm_fd);
        return NULL;
    }
    
    struct wl_shm_pool *pool = wl_shm_create_pool(state->shm, state->shm_fd, state->shm_size);
    struct wl_buffer *buffer = wl_shm_pool_create_buffer(pool, 0, width, height,
                                                         stride, WL_SHM_FORMAT_ARGB8888);
    wl_shm_pool_destroy(pool);
    return buffer;
}

static void draw_border(struct app_state *state) {
    uint32_t *pixels = state->shm_data;
    int width = state->width + 2 * BORDER_WIDTH;
    int height = state->height + 2 * BORDER_WIDTH;
    
    // Get smooth animation time
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    double t = ts.tv_sec + ts.tv_nsec / 1000000000.0;
    
    // Smooth pulsating glow effect
    double pulse = (sin(t * 1.5) + 1.0) / 2.0;  // 0 to 1 smooth wave
    
    // Animate between deep red and bright red-orange for glow effect
    uint8_t r = (uint8_t)(180 + pulse * 75);   // 180-255
    uint8_t g = (uint8_t)(pulse * 40);         // 0-40 (adds orange tint at peak)
    uint8_t b = 0;
    uint8_t alpha = (uint8_t)(200 + pulse * 55);  // 200-255 alpha (always visible)
    
    // ARGB format for Wayland
    uint32_t color = (alpha << 24) | (r << 16) | (g << 8) | b;
    
    // Clear buffer
    memset(pixels, 0, state->shm_size);
    
    // Draw border with gradient effect for extra glow
    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x++) {
            int border_dist = 0;
            
            // Calculate distance from edge for gradient
            if (y < BORDER_WIDTH) border_dist = y;
            else if (y >= height - BORDER_WIDTH) border_dist = height - 1 - y;
            else if (x < BORDER_WIDTH) border_dist = x;
            else if (x >= width - BORDER_WIDTH) border_dist = width - 1 - x;
            else continue;  // Not in border
            
            // Apply subtle gradient to inner edge
            float gradient = 1.0;
            if (border_dist < BORDER_WIDTH) {
                gradient = 0.8 + 0.2 * (border_dist / (float)BORDER_WIDTH);
            }
            
            uint8_t final_alpha = (uint8_t)(alpha * gradient);
            pixels[y * width + x] = (final_alpha << 24) | (color & 0x00FFFFFF);
        }
    }
    
    wl_surface_attach(state->surface, state->buffer, 0, 0);
    wl_surface_damage(state->surface, 0, 0, width, height);
    wl_surface_commit(state->surface);
}

int main(int argc, char *argv[]) {
    if (argc != 2) {
        fprintf(stderr, "Usage: %s \"x,y widthxheight\"\n", argv[0]);
        return 1;
    }
    
    struct app_state state = {0};
    state.running = 1;
    sscanf(argv[1], "%d,%d %dx%d", &state.x, &state.y, &state.width, &state.height);
    
    state.display = wl_display_connect(NULL);
    if (!state.display) return 1;
    
    state.registry = wl_display_get_registry(state.display);
    wl_registry_add_listener(state.registry, &registry_listener, &state);
    wl_display_roundtrip(state.display);
    
    state.surface = wl_compositor_create_surface(state.compositor);
    state.layer_surface = zwlr_layer_shell_v1_get_layer_surface(
        state.layer_shell, state.surface, NULL,
        ZWLR_LAYER_SHELL_V1_LAYER_OVERLAY, "screen-recorder-border");
    
    zwlr_layer_surface_v1_add_listener(state.layer_surface, &layer_surface_listener, &state);
    zwlr_layer_surface_v1_set_anchor(state.layer_surface,
        ZWLR_LAYER_SURFACE_V1_ANCHOR_TOP | ZWLR_LAYER_SURFACE_V1_ANCHOR_LEFT);
    zwlr_layer_surface_v1_set_exclusive_zone(state.layer_surface, -1);
    zwlr_layer_surface_v1_set_margin(state.layer_surface,
        state.y - BORDER_WIDTH, 0, 0, state.x - BORDER_WIDTH);
    zwlr_layer_surface_v1_set_size(state.layer_surface,
        state.width + 2 * BORDER_WIDTH, state.height + 2 * BORDER_WIDTH);
    wl_surface_commit(state.surface);
    
    while (!state.configured && state.running) {
        wl_display_dispatch(state.display);
    }
    
    // Make surface passthrough
    struct wl_region *empty = wl_compositor_create_region(state.compositor);
    wl_surface_set_input_region(state.surface, empty);
    wl_region_destroy(empty);
    wl_surface_commit(state.surface);
    
    state.buffer = create_shm_buffer(&state);
    if (!state.buffer) return 1;
    
    while (state.running) {
        if (access("/tmp/stop-screen-recorder-overlay", F_OK) == 0) break;
        draw_border(&state);
        wl_display_dispatch_pending(state.display);
        wl_display_flush(state.display);
        usleep(16666);
    }
    
    // Cleanup
    if (state.buffer) wl_buffer_destroy(state.buffer);
    if (state.shm_data) munmap(state.shm_data, state.shm_size);
    if (state.shm_fd >= 0) close(state.shm_fd);
    if (state.layer_surface) zwlr_layer_surface_v1_destroy(state.layer_surface);
    if (state.surface) wl_surface_destroy(state.surface);
    if (state.layer_shell) zwlr_layer_shell_v1_destroy(state.layer_shell);
    if (state.shm) wl_shm_destroy(state.shm);
    if (state.compositor) wl_compositor_destroy(state.compositor);
    if (state.registry) wl_registry_destroy(state.registry);
    if (state.display) wl_display_disconnect(state.display);
    
    return 0;
}