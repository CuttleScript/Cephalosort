# Cephalosort

A Python tool that organizes messy media downloads into clean, consistently named folders. Point it at a directory full of files named like `The_Dark_Knight_2008_1080p_H265.mkv` and it creates `The Dark Knight (2008) [1080p H265]` folders, moves everything in, and handles subtitles automatically.

```
The_Dark_Knight_2008_1080p_H265.mkv        →   The Dark Knight (2008) [1080p H265]/
The_Dark_Knight_2008_1080p_H265.en.srt     →   The Dark Knight (2008) [1080p H265]/Subtitles/
```

## Features

- Parses `Title_Year_Quality_Codec` filenames and creates matching `Title (Year) [Quality Codec]` folders
- Recursively traverses subdirectories, preserving relative structure in the output
- Automatically detects and moves associated subtitle files
- Three subtitle modes: `same` folder, `subfolder`, or `none`
- Three collision modes when a target folder already exists: `skip`, `merge`, or `rename` with a numbered suffix
- Dry run mode — preview every change before anything is touched
- Windows-safe folder names: invalid characters replaced, reserved names handled, length capped
- Warns if output directory is inside source directory and recursive mode is on

## Requirements

- Python 3.6+
- No external dependencies

## Setup

Edit the config block near the top of the script to set your defaults:

```python
SOURCE_DIR = "."                  # Directory to process — "." means current directory
OUTPUT_DIR = None                 # None means organize in-place; set a path to move elsewhere
RECURSIVE = False                 # Traverse subdirectories
DRY_RUN = False                   # Set True to preview without making changes
EXISTING_FOLDER_ACTION = "merge"  # "skip" | "merge" | "rename"
SUBTITLE_MODE = "subfolder"       # "same" | "subfolder" | "none"
```

All values can be overridden at runtime with CLI arguments.

## Usage

```
python cephalosort.py [options]
```

| Argument | Description |
|---|---|
| `-d`, `--directory` | Source directory to process (default: `.`) |
| `-o`, `--output` | Output directory for organized folders (default: same as source) |
| `-r`, `--recursive` | Process subdirectories recursively |
| `--dry-run` | Preview changes without moving anything |
| `--existing` | `skip` / `merge` / `rename` (default: `merge`) |
| `--subtitles` | `same` / `subfolder` / `none` (default: `subfolder`) |
| `--subtitle-folder` | Subtitle subfolder name (default: `Subtitles`) |
| `--max-length` | Max folder name length (default: `200`) |
| `--version` | Show version and exit |

## Examples

```bash
# Preview what would happen in the current directory
python cephalosort.py --dry-run

# Organize a folder in-place
python cephalosort.py -d /path/to/downloads

# Move organized folders to a separate output location
python cephalosort.py -d /path/to/downloads -o /path/to/media

# Recursive, output to a different drive
python cephalosort.py -r -d D:/Downloads -o E:/Media

# Skip files if a matching folder already exists
python cephalosort.py --existing skip

# Don't touch subtitle files
python cephalosort.py --subtitles none
```

## Filename Format

Files must follow the pattern `Title_Year_Quality_Codec.ext`. Year must be `19xx` or `20xx`. Files that don't match are skipped and reported in the summary.

```
Alien_Romulus_2024_2160p_H265.mkv   →   Alien Romulus (2024) [2160p H265]/
A_Quiet_Place_2018_1080p_H264.mp4   →   A Quiet Place (2018) [1080p H264]/
```

## Subtitle Detection

Cephalosort matches subtitles to their video by filename stem and moves them automatically.

| File | Matched as |
|---|---|
| `Movie_2024_1080p.srt` | Exact match |
| `Movie_2024_1080p.en.srt` | Language code |
| `Movie_2024_1080p.forced.srt` | Flag |
| `Movie_2024_1080p.en.forced.srt` | Language + flag |

**Supported formats:** `.srt` `.sub` `.sbv` `.ass` `.ssa` `.vtt` `.idx` `.sup`

## Collision Handling

| Mode | Behaviour |
|---|---|
| `merge` | Move file into the existing folder *(default)* |
| `skip` | Leave the file where it is |
| `rename` | Create a new numbered folder — `Title (2024) [1080p] (2)` |

## Windows Compatibility

Folder names are automatically sanitized for Windows:

- Invalid characters (`< > : " / \ | ? *`) are replaced with safe alternatives
- Reserved names (`CON`, `NUL`, `COM1`–`COM9`, etc.) are prefixed with `_`
- Trailing dots and spaces are stripped
- Folder name length is capped (default: 200 characters, configurable)
