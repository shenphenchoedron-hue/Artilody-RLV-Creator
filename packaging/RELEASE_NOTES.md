## Artilody RLV Creator

Make Real Life Videos (MP4 + GPX + XML) from GoPro recordings.

### New in 1.1.2: the name you choose is used everywhere
- When you export under a new name, the route title now changes too. Before, the title kept the name of the GoPro file, so the training app still showed the old name.
- The export dialog has a *Title* field. It follows the name unless you type your own title.
- The title is written to the XML, the GPX track and the MP4 video's title tag.

### New in 1.1.1: H.264 video
- Videos are now exported in **H.264 / AVC** by default, like the reference RLV files. Some training apps could not open the HEVC videos and reported the video file as missing.
- H.265 / HEVC can still be chosen under *Format* in the export dialog.
- The video is written as limited-range BT.709 (GoPro records full range), which all players expect.

### New in 1.1.0: a fresh look
- New dark theme with blue accents and a matching set of icons.
- Welcome screen with a big *Open GoPro video(s)…* button and a three-step guide (Open → Cut → Export). Files can be dropped onto it.
- New toolbar with a highlighted **Export** button. Distance, speed and elevation are shown as badges at the top right.
- Playback bar with a round play button, a large time display and a red **Cut out** button.
- Dark map with a glowing route, green start and amber end markers; darker timeline with a shaded elevation profile.
- The window fits smaller screens (minimum 1157×804).

- Reads GPS from GoPro videos (GPS5 / GPS9). Chapter files of one ride are joined automatically.
- Cut out parts of the film: the same seconds are removed from the video and the GPS data, and the film closes the gap at once.
- Unlimited undo / redo. Removed parts can also be restored one by one.
- Exports MP4 in H.264 (or H.265/HEVC), 1920×1080 (16:9), 30 fps, plus GPX and XML files in the RLV reference format.
- Map, elevation profile, information texts (de/en), and optional heart rate / cadence import.

### Downloads
| System | File |
|---|---|
| Windows 10/11 | `…-Windows-Setup.exe` (installer) or `…-Windows-Portable.zip` |
| macOS Apple Silicon | `…-macOS-AppleSilicon.dmg` |
| macOS Intel | `…-macOS-Intel.dmg` |
| Debian 12+/Ubuntu 22.04+ | `artilody-rlv-creator_…_amd64.deb` (`sudo apt install ./artilody-rlv-creator_*_amd64.deb`) |
| Other Linux | `…-Linux-x86_64.tar.gz` |

The apps are not code-signed. On macOS, right-click the app and choose *Open* the first time. On Windows, click *More info* and then *Run anyway*.
See the [README](https://github.com/shenphenchoedron-hue/Artilody-RLV-Creator#readme) for instructions.
