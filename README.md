# screenreco

A modern screen recording tool for Wayland compositors with visual feedback, automatic uploads, and intuitive controls.

## Features

- 🎬 **Area selection recording** - Select any area of your screen to record
- 🎤 **Optional audio recording** - Include system/microphone audio
- 🔴 **Visual recording indicator** - Animated glowing border shows recording area
- 🎮 **Interactive controls** - Cancel/Save buttons positioned above recording area
- ☁️ **Automatic upload** - Uploads to 0x0.st and copies link to clipboard
- ⌨️ **Hotkey support** - Quick toggle recording with keyboard shortcuts

## Requirements

- Wayland compositor with layer-shell support (Hyprland, Sway, etc.)
- `wf-recorder` - Wayland screen recorder
- `slurp` - Area selection tool
- `wl-clipboard` - Clipboard utilities
- `curl` - For uploading
- Development packages:
  - `wayland-devel`
  - `wayland-protocols-devel`
  - `wlr-protocols`
  - `gtk3-devel`
  - `gcc`, `make`, `pkg-config`

### Arch Linux

```bash
sudo pacman -S wf-recorder slurp wl-clipboard curl wayland wayland-protocols gtk3 gcc make pkg-config
yay -S wlr-protocols
```

### Fedora

```bash
sudo dnf install wf-recorder slurp wl-clipboard curl wayland-devel wayland-protocols-devel gtk3-devel gcc make pkg-config
```

### Ubuntu/Debian

```bash
sudo apt install wf-recorder slurp wl-clipboard curl libwayland-dev wayland-protocols libgtk-3-dev gcc make pkg-config
# Note: wlr-protocols may need manual installation
```

## Installation

1. Clone or download this repository:

```bash
git clone https://github.com/yourusername/screenreco.git
cd screenreco
```

2. Build the components:

```bash
make
```

3. Install system-wide:

```bash
sudo make install
```

Or install to custom prefix:

```bash
make install PREFIX=$HOME/.local
```

## Usage

### Basic Recording

Start a screen recording (without audio):
```bash
screenreco
```

Start recording with audio:
```bash
screenreco --with-audio
```

### Workflow

1. **Start recording**: Run `screenreco` or use your configured hotkey
2. **Select area**: Click and drag to select the recording area
3. **Recording active**: 
   - A glowing red border shows the recording area
   - Cancel/Save buttons appear above the frame
4. **Stop recording**:
   - Click **Save** button - Uploads recording and copies link to clipboard
   - Click **Cancel** button - Discards the recording
   - Run the command/hotkey again - Saves and uploads (default action)

### Hyprland Configuration

Add these keybindings to your `~/.config/hypr/hyprland.conf`:

```bash
# Screen recording without audio
bind = SUPER SHIFT, R, exec, screenreco

# Screen recording with audio  
bind = SUPER CTRL, R, exec, screenreco --with-audio
```

Add these window rules for proper button positioning:

```bash
# Screen recorder button controls
windowrulev2 = float, title:screen-recorder-controls.*
windowrulev2 = size 200 50, title:screen-recorder-controls.*
windowrulev2 = noborder, title:screen-recorder-controls.*
windowrulev2 = noshadow, title:screen-recorder-controls.*
windowrulev2 = noanim, title:screen-recorder-controls.*
```

### Sway Configuration

Add to your `~/.config/sway/config`:

```bash
# Screen recording keybindings
bindsym $mod+Shift+r exec screenreco
bindsym $mod+Ctrl+r exec screenreco --with-audio

# Window rules for recording controls
for_window [title="screen-recorder-controls.*"] floating enable
for_window [title="screen-recorder-controls.*"] border none
```

## File Locations

- **Recordings**: Saved to `~/Videos/screen-recording-YYYY-MM-DD-HHMM.mp4`
- **Upload history**: Logged to `~/Videos/upload-links.log`
- **Temporary files**: Uses `/tmp` for state management

## Customization

### Using Local Binaries (Development)

Set environment variables to use custom binary locations:

```bash
export SCREENRECO_BORDER=/path/to/border-overlay
export SCREENRECO_BUTTONS=/path/to/button-window
screenreco
```

### Border Appearance

The border overlay features a smooth pulsating glow effect. To customize, edit `src/border-overlay.c` and adjust:
- Animation speed: `sin(t * 1.5)` - change the multiplier
- Color range: Modify the RGB calculations in the `draw_border` function
- Border width: Change `BORDER_WIDTH` define

## Troubleshooting

### Buttons not appearing in correct position

Ensure your compositor supports the layer-shell protocol and that the window rules are properly configured.

### Recording doesn't start

Check that `wf-recorder` is installed and working:
```bash
wf-recorder -g "0,0 100x100" -f test.mp4
```

### Upload fails

Verify internet connection and that 0x0.st is accessible:
```bash
echo "test" | curl -F "file=@-" https://0x0.st
```

### No audio in recordings

- Ensure PulseAudio or PipeWire is running
- Check default audio source: `pactl info | grep "Default Source"`
- Test audio recording: `wf-recorder -a -f test-audio.mp4`

## Uninstallation

```bash
sudo make uninstall
```

Or if installed with custom prefix:
```bash
make uninstall PREFIX=$HOME/.local
```