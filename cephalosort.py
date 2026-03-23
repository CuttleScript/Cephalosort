#!/usr/bin/env python3
# cephalosort.py
# Name: Cephalosort
# Author: Cuttlescript (https://github.com/cuttlescript)
# Version: 1.4
# Date: 2026-03-24
# Requires Python 3.6+

"""
Media file organizer that creates formatted folders and moves files into them.
Converts filenames like "Title_Year_Quality_Codec" into "Title (Year) [Quality Codec]" folders.
Handles Windows filename restrictions and existing folder scenarios.
Automatically detects and moves subtitle files with videos.
Supports optional output directory for organized files.
"""

import os
import re
import sys
import argparse
import shutil
from pathlib import Path
from typing import Optional, Tuple, List

# -----config-----
# Default configuration - can be overridden by CLI arguments

# Enable recursive directory traversal
RECURSIVE = False

# Enable dry run mode (show what would happen without making changes)
DRY_RUN = False

# Source directory to process (default to current directory)
# Use raw strings (r"") or forward slashes for Windows paths to avoid escape issues
# Examples: r"D:\Video\Downloads" or "D:/Video/Downloads" or "."
SOURCE_DIR = "."

# Output directory for organized folders (default: None, which means same as source)
# If set, all organized folders will be created in this directory instead
# Use raw strings (r"") or forward slashes for Windows paths
# Examples: r"D:\Media\Organized" or "D:/Media/Organized" or None
OUTPUT_DIR = None

# How to handle when target folder already exists:
# 'skip' - Skip the file and don't move it
# 'merge' - Move file into existing folder
# 'rename' - Create a new folder with a numbered suffix (e.g., "Title (2024) [1080p] (2)")
EXISTING_FOLDER_ACTION = "merge"

# Maximum folder name length (Windows MAX_PATH considerations)
# 255 is the Windows limit for a single path component
MAX_FOLDER_NAME_LENGTH = 200

# Subtitle handling options:
# 'subfolder' - Move subtitles to a 'Subtitles' subfolder within the media folder
# 'same' - Move subtitles to the same folder as the video file
# 'none' - Don't move subtitle files
SUBTITLE_MODE = "subfolder"

# Subtitle subfolder name (used when SUBTITLE_MODE is 'subfolder')
SUBTITLE_FOLDER_NAME = "Subtitles"

# Video file extensions to process
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.m4v', '.wmv', '.flv', '.webm', '.mpg', '.mpeg'}

# Subtitle file extensions to detect and move with video files
SUBTITLE_EXTENSIONS = {'.srt', '.sub', '.sbv', '.ass', '.ssa', '.vtt', '.idx', '.sup'}

# -----config-----


class MediaOrganizer:
    """Organizes media files into formatted folders."""
    
    # Windows reserved filenames
    WINDOWS_RESERVED_NAMES = {
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    }
    
    def __init__(self, source_dir: str, output_dir: Optional[str] = None, 
                 recursive: bool = False, dry_run: bool = False, 
                 existing_action: str = "merge", max_folder_length: int = 200,
                 subtitle_mode: str = "subfolder", subtitle_folder_name: str = "Subtitles"):
        self.source_dir = Path(source_dir).resolve()
        self.output_dir = Path(output_dir).resolve() if output_dir else None
        self.recursive = recursive
        self.dry_run = dry_run
        self.existing_action = existing_action.lower()
        self.max_folder_length = max_folder_length
        self.subtitle_mode = subtitle_mode.lower()
        self.subtitle_folder_name = subtitle_folder_name
        self.files_processed = 0
        self.files_moved = 0
        self.files_skipped = 0
        self.folders_created = 0
        self.subtitles_moved = 0
        self.errors = 0
        
        # Validate existing_action
        if self.existing_action not in ['skip', 'merge', 'rename']:
            print(f"[WARNING] Invalid existing_action '{existing_action}', using 'merge'")
            self.existing_action = 'merge'
        
        # Validate subtitle_mode
        if self.subtitle_mode not in ['subfolder', 'same', 'none']:
            print(f"[WARNING] Invalid subtitle_mode '{subtitle_mode}', using 'same'")
            self.subtitle_mode = 'same'
    
    def get_target_base_dir(self, source_file_dir: Path) -> Path:
        """
        Get the base directory where organized folders should be created.
        
        If output_dir is set, use that. Otherwise, use the same directory as the source file.
        For recursive processing, maintains relative directory structure in output.
        
        Args:
            source_file_dir: The directory containing the source file
        
        Returns: The directory where the organized folder should be created
        """
        if self.output_dir is None:
            # No output dir specified, use same location as source file
            return source_file_dir
        
        # If output dir is specified and we're doing recursive processing,
        # maintain the relative directory structure
        if self.recursive:
            try:
                # Get the relative path from source_dir to source_file_dir
                rel_path = source_file_dir.relative_to(self.source_dir)
                # Create the same structure in output_dir
                return self.output_dir / rel_path
            except ValueError:
                # source_file_dir is not relative to source_dir (shouldn't happen)
                return self.output_dir
        else:
            # Not recursive, just use output_dir directly
            return self.output_dir
    
    def sanitize_windows_filename(self, name: str) -> str:
        """
        Sanitize a filename/folder name for Windows compatibility.
        
        Removes or replaces characters that are invalid on Windows:
        < > : " / \\ | ? *
        Also handles reserved names and trailing dots/spaces.
        """
        # Replace invalid characters with safe alternatives or remove them
        # < > : " / \ | ? *
        char_replacements = {
            '<': '(',
            '>': ')',
            ':': ' -',
            '"': "'",
            '/': '-',
            '\\': '-',
            '|': '-',
            '?': '',
            '*': '',
            '\x00': '',  # Null character
        }
        
        for old_char, new_char in char_replacements.items():
            name = name.replace(old_char, new_char)
        
        # Remove any other control characters (0x00-0x1F)
        name = re.sub(r'[\x00-\x1f]', '', name)
        
        # Remove trailing dots and spaces (Windows doesn't allow these)
        name = name.rstrip('. ')
        
        # Collapse multiple spaces
        name = re.sub(r'\s+', ' ', name)
        
        # Check if the name (without extension) is a Windows reserved name
        name_upper = name.split('.')[0].upper()
        if name_upper in self.WINDOWS_RESERVED_NAMES:
            name = f"_{name}"
        
        # Ensure the name isn't empty
        if not name:
            name = "unnamed"
        
        # Truncate if too long while preserving the format
        if len(name) > self.max_folder_length:
            # Try to preserve the year and quality info at the end
            match = re.search(r'(\(\d{4}\)\s*\[.+?\])$', name)
            if match:
                suffix = match.group(1)
                max_title_length = self.max_folder_length - len(suffix) - 3  # 3 for "..."
                if max_title_length > 10:
                    name = name[:max_title_length] + "..." + suffix
                else:
                    name = name[:self.max_folder_length]
            else:
                name = name[:self.max_folder_length]
        
        return name
    
    def clean_title(self, title: str) -> str:
        """Clean up the title by removing special characters and normalizing."""
        # Remove leading special characters like ¡¿
        title = re.sub(r'^[¡¿\s]+', '', title)
        # Replace underscores with spaces
        title = title.replace('_', ' ')
        # Clean up multiple spaces
        title = re.sub(r'\s+', ' ', title)
        title = title.strip()
        # Fall back to 'Untitled' if nothing remains after cleaning
        return title if title else 'Untitled'
    
    def parse_filename(self, filename: str) -> Optional[Tuple[str, str, str]]:
        """
        Parse filename to extract title, year, and quality/codec info.
        
        Expected format: Title_Year_Quality_Codec
        Returns: (title, year, quality_codec) or None if pattern doesn't match
        """
        # Remove file extension
        name_without_ext = os.path.splitext(filename)[0]
        
        # Pattern to match: Title_Year_Quality_Codec
        # Year must be 4 digits starting with 19 or 20
        pattern = r'^(.+?)_((?:19|20)\d{2})_(.+)$'
        match = re.match(pattern, name_without_ext)
        
        if match:
            title = self.clean_title(match.group(1))
            year = match.group(2)
            quality_codec = match.group(3).replace('_', ' ')
            return (title, year, quality_codec)
        
        return None
    
    def format_folder_name(self, title: str, year: str, quality_codec: str) -> str:
        """
        Format the folder name according to the target pattern.
        
        Format: Title (Year) [Quality Codec]
        """
        folder_name = f"{title} ({year}) [{quality_codec}]"
        # Sanitize for Windows compatibility
        return self.sanitize_windows_filename(folder_name)
    
    def get_unique_folder_path(self, base_folder: Path) -> Path:
        """
        Get a unique folder path by appending a number if necessary.
        
        Example: "Title (2024) [1080p]" -> "Title (2024) [1080p] (2)"
        """
        if not base_folder.exists():
            return base_folder
        
        counter = 2
        while True:
            new_folder = base_folder.parent / f"{base_folder.name} ({counter})"
            if not new_folder.exists():
                return new_folder
            counter += 1
            
            # Safety check to prevent infinite loop
            if counter > 1000:
                raise ValueError(f"Too many duplicate folders for {base_folder.name}")
    
    def get_unique_file_path(self, file_path: Path) -> Path:
        """
        Get a unique file path by appending a number if the file already exists.
        
        Example: "video.mp4" -> "video (2).mp4"
        """
        if not file_path.exists():
            return file_path
        
        stem = file_path.stem
        suffix = file_path.suffix
        parent = file_path.parent
        
        counter = 2
        while True:
            new_path = parent / f"{stem} ({counter}){suffix}"
            if not new_path.exists():
                return new_path
            counter += 1
            
            # Safety check
            if counter > 1000:
                raise ValueError(f"Too many duplicate files for {file_path.name}")
    
    def find_subtitle_files(self, video_path: Path) -> List[Path]:
        """
        Find subtitle files associated with a video file.
        
        Looks for subtitle files with the same name as the video (different extension)
        or with common subtitle suffixes like .en, .eng, .forced, etc.
        
        Example matches for "Movie_2024_1080p_H265.mp4":
        - Movie_2024_1080p_H265.srt
        - Movie_2024_1080p_H265.en.srt
        - Movie_2024_1080p_H265.eng.srt
        - Movie_2024_1080p_H265.forced.srt
        """
        subtitle_files = []
        video_stem = video_path.stem
        video_dir = video_path.parent
        
        # Get all files in the same directory
        try:
            for file in video_dir.iterdir():
                if not file.is_file():
                    continue
                
                # Check if it's a subtitle file
                if file.suffix.lower() not in SUBTITLE_EXTENSIONS:
                    continue
                
                file_stem = file.stem
                
                # Exact match (same name, different extension)
                if file_stem == video_stem:
                    subtitle_files.append(file)
                    continue
                
                # Match with language/subtitle codes
                # Examples: video.en.srt, video.eng.srt, video.forced.srt, video.en.forced.srt
                # Pattern: video_name + optional subtitle codes + extension
                if file_stem.startswith(video_stem + '.'):
                    subtitle_files.append(file)
                    continue
        
        except Exception as e:
            print(f"[WARNING] Error searching for subtitles: {e}")
        
        return subtitle_files
    
    def move_subtitle_file(self, subtitle_path: Path, target_base_folder: Path) -> bool:
        """
        Move a subtitle file to the appropriate location.
        
        Args:
            subtitle_path: Path to the subtitle file
            target_base_folder: The main video folder (not the subtitle subfolder)
        
        Returns: True if successful, False otherwise
        """
        try:
            # Determine target directory based on subtitle mode
            if self.subtitle_mode == 'subfolder':
                target_dir = target_base_folder / self.subtitle_folder_name
            else:  # 'same'
                target_dir = target_base_folder
            
            target_file_path = target_dir / subtitle_path.name
            
            # Check if file already exists and get unique name if needed
            if target_file_path.exists():
                target_file_path = self.get_unique_file_path(target_file_path)
            
            if self.dry_run:
                if self.subtitle_mode == 'subfolder':
                    print(f"[DRY RUN] Would move subtitle: {subtitle_path.name} -> {target_base_folder.name}/{self.subtitle_folder_name}/")
                else:
                    print(f"[DRY RUN] Would move subtitle: {subtitle_path.name} -> {target_base_folder.name}/")
            else:
                # Create subtitle folder if needed
                if self.subtitle_mode == 'subfolder' and not target_dir.exists():
                    target_dir.mkdir(parents=True, exist_ok=True)
                    print(f"[CREATE] Subtitle folder: {target_base_folder.name}/{self.subtitle_folder_name}/")
                
                # Move the subtitle file
                shutil.move(str(subtitle_path), str(target_file_path))
                self.subtitles_moved += 1
                
                if self.subtitle_mode == 'subfolder':
                    print(f"[MOVE] Subtitle: {subtitle_path.name} -> {target_base_folder.name}/{self.subtitle_folder_name}/")
                else:
                    print(f"[MOVE] Subtitle: {subtitle_path.name} -> {target_base_folder.name}/")
            
            return True
            
        except Exception as e:
            self.errors += 1
            print(f"[ERROR] Failed to move subtitle {subtitle_path.name}: {e}")
            return False
    
    def process_file(self, file_path: Path) -> bool:
        """
        Process a single file: create folder and move file (and associated subtitles).
        
        Returns: True if successful, False otherwise
        """
        self.files_processed += 1
        
        # Check if it's a video file
        if file_path.suffix.lower() not in VIDEO_EXTENSIONS:
            print(f"[SKIP] Not a video file: {file_path.name}")
            self.files_skipped += 1
            return False
        
        # Parse the filename
        parsed = self.parse_filename(file_path.name)
        if not parsed:
            print(f"[SKIP] Filename doesn't match expected pattern: {file_path.name}")
            self.files_skipped += 1
            return False
        
        title, year, quality_codec = parsed
        folder_name = self.format_folder_name(title, year, quality_codec)
        
        # Find associated subtitle files before moving the video
        subtitle_files = []
        if self.subtitle_mode != 'none':
            subtitle_files = self.find_subtitle_files(file_path)
            if subtitle_files:
                print(f"[INFO] Found {len(subtitle_files)} subtitle file(s) for {file_path.name}")
        
        # Determine target base directory (handles output_dir logic)
        target_base_dir = self.get_target_base_dir(file_path.parent)
        
        # Create target folder path
        target_folder = target_base_dir / folder_name
        
        # Handle existing folder based on configuration
        folder_already_existed = target_folder.exists()
        
        if folder_already_existed:
            if self.existing_action == 'skip':
                print(f"[SKIP] Folder already exists: {folder_name}")
                self.files_skipped += 1
                return False
            elif self.existing_action == 'rename':
                target_folder = self.get_unique_folder_path(target_folder)
                folder_name = target_folder.name
                print(f"[INFO] Using unique folder name: {folder_name}")
                folder_already_existed = False
        
        # Determine final target file path
        target_file_path = target_folder / file_path.name
        
        # Check if file already exists in target folder
        if target_file_path.exists():
            # Get unique filename
            target_file_path = self.get_unique_file_path(target_file_path)
            print(f"[INFO] File already exists, using: {target_file_path.name}")
        
        try:
            if self.dry_run:
                if not folder_already_existed:
                    if self.output_dir:
                        print(f"[DRY RUN] Would create folder: {target_folder}")
                    else:
                        print(f"[DRY RUN] Would create folder: {folder_name}")
                else:
                    print(f"[DRY RUN] Folder exists (merging): {folder_name}")
                print(f"[DRY RUN] Would move: {file_path.name} -> {folder_name}/{target_file_path.name}")
            else:
                # Create the folder if it doesn't exist (including parent dirs if needed)
                if not target_folder.exists():
                    target_folder.mkdir(parents=True, exist_ok=True)
                    self.folders_created += 1
                    if self.output_dir:
                        print(f"[CREATE] Folder: {target_folder}")
                    else:
                        print(f"[CREATE] Folder: {folder_name}")
                elif self.existing_action == 'merge':
                    print(f"[MERGE] Into existing folder: {folder_name}")
                
                # Move the file
                shutil.move(str(file_path), str(target_file_path))
                self.files_moved += 1
                print(f"[MOVE] {file_path.name} -> {folder_name}/{target_file_path.name}")
            
            # Move associated subtitle files
            if subtitle_files and self.subtitle_mode != 'none':
                for subtitle_file in subtitle_files:
                    self.move_subtitle_file(subtitle_file, target_folder)
            
            return True
            
        except Exception as e:
            self.errors += 1
            print(f"[ERROR] Failed to process {file_path.name}: {e}")
            return False
    
    def process_directory(self, directory: Path) -> None:
        """Process all files in a directory."""
        try:
            # Get list of items in directory
            items = list(directory.iterdir())
            
            for item in items:
                if item.is_file():
                    self.process_file(item)
                elif item.is_dir() and self.recursive:
                    print(f"\n[RECURSE] Entering directory: {item.name}")
                    self.process_directory(item)
                    
        except PermissionError:
            print(f"[ERROR] Permission denied: {directory}")
            self.errors += 1
        except Exception as e:
            print(f"[ERROR] Failed to process directory {directory}: {e}")
            self.errors += 1
    
    def run(self) -> None:
        """Run the organizer."""
        if not self.source_dir.exists():
            print(f"[ERROR] Source directory does not exist: {self.source_dir}")
            sys.exit(1)
        
        if not self.source_dir.is_dir():
            print(f"[ERROR] Source path is not a directory: {self.source_dir}")
            sys.exit(1)
        
        # Validate output directory if specified
        if self.output_dir:
            if self.output_dir.exists() and not self.output_dir.is_dir():
                print(f"[ERROR] Output path exists but is not a directory: {self.output_dir}")
                sys.exit(1)
            
            # Warn if output_dir is inside source_dir and recursive is enabled —
            # the script would walk into already-organized folders on the same run
            if self.recursive:
                try:
                    self.output_dir.relative_to(self.source_dir)
                    print("[WARNING] Output directory is inside source directory and recursive mode is enabled.")
                    print("[WARNING] The script may walk into organized folders and attempt to re-process them.")
                    print("[WARNING] Consider using an output directory outside of source, or disable recursive mode.")
                except ValueError:
                    pass  # output_dir is not inside source_dir, no issue
            
            # Create output directory if it doesn't exist (in non-dry-run mode)
            if not self.output_dir.exists():
                if self.dry_run:
                    print(f"[INFO] Output directory would be created: {self.output_dir}")
                else:
                    try:
                        self.output_dir.mkdir(parents=True, exist_ok=True)
                        print(f"[INFO] Created output directory: {self.output_dir}")
                    except Exception as e:
                        print(f"[ERROR] Failed to create output directory: {e}")
                        sys.exit(1)
        
        print("=" * 70)
        print("Cephalosort")
        print("=" * 70)
        print(f"Source directory: {self.source_dir}")
        if self.output_dir:
            print(f"Output directory: {self.output_dir}")
        else:
            print("Output directory: Same as source (in-place organization)")
        print(f"Recursive mode: {self.recursive}")
        print(f"Dry run mode: {self.dry_run}")
        print(f"Existing folder action: {self.existing_action}")
        print(f"Subtitle mode: {self.subtitle_mode}")
        print("=" * 70)
        print()
        
        self.process_directory(self.source_dir)
        
        # Print summary
        print()
        print("=" * 70)
        print("Summary")
        print("=" * 70)
        print(f"Files processed: {self.files_processed}")
        print(f"Files moved: {self.files_moved}")
        print(f"Subtitles moved: {self.subtitles_moved}")
        print(f"Files skipped: {self.files_skipped}")
        print(f"Folders created: {self.folders_created}")
        print(f"Errors: {self.errors}")
        print("=" * 70)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Organize media files into formatted folders",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Process current directory (in-place)
  %(prog)s -r                                 # Process current directory recursively
  %(prog)s -d /path/to/media                  # Process specific directory
  %(prog)s -d /path/to/media -o /path/to/organized  # Move organized folders to different location
  %(prog)s -r -d C:\\Downloads -o D:\\Media   # Process downloads, output to separate drive
  %(prog)s --dry-run                          # Show what would happen without making changes
  %(prog)s --existing merge                   # Merge files into existing folders (default)
  %(prog)s --existing skip                    # Skip files if folder exists
  %(prog)s --existing rename                  # Create new numbered folders
  %(prog)s --subtitles subfolder              # Move subtitles to Subtitles subfolder
  %(prog)s --subtitles same                   # Move subtitles to same folder as video (default)
  %(prog)s --subtitles none                   # Don't move subtitle files

Output Directory Behavior:
  - If not specified: Folders are created in the same location as source files (in-place)
  - If specified: All organized folders are created in the output directory
  - With recursive: Maintains the relative directory structure in the output location
  
  Example with recursive:
    Source: C:\\Downloads\\Movies\\Action\\file.mp4
    Output: D:\\Media
    Result: D:\\Media\\Action\\Title (Year) [Quality]\\file.mp4

Existing Folder Actions:
  skip   - Skip the file if target folder already exists
  merge  - Move file into existing folder (default)
  rename - Create a new folder with numbered suffix, e.g., "Title (2024) [1080p] (2)"

Subtitle Handling:
  same      - Move subtitles to the same folder as the video file
  subfolder - Move subtitles to a 'Subtitles' subfolder (default)
  none      - Don't move subtitle files
  
  Supported subtitle formats: .srt, .sub, .sbv, .ass, .ssa, .vtt, .idx, .sup
  
  The script automatically detects subtitles that match the video filename:
  - Exact match: Movie_2024_1080p_H265.srt
  - With language codes: Movie_2024_1080p_H265.en.srt, Movie_2024_1080p_H265.eng.srt
  - With forced/SDH: Movie_2024_1080p_H265.forced.srt, Movie_2024_1080p_H265.en.forced.srt

Windows Compatibility:
  - Automatically sanitizes folder names for Windows
  - Removes/replaces invalid characters: < > : " / \\ | ? *
  - Handles reserved names (CON, PRN, AUX, etc.)
  - Removes trailing dots and spaces
  - Limits folder name length
        """
    )
    
    parser.add_argument(
        '-d', '--directory',
        default=SOURCE_DIR,
        help=f'Source directory to process (default: {SOURCE_DIR})'
    )
    
    parser.add_argument(
        '-o', '--output',
        default=OUTPUT_DIR,
        help='Output directory for organized folders (default: same as source directory)'
    )
    
    parser.add_argument(
        '-r', '--recursive',
        action='store_true',
        default=RECURSIVE,
        help='Process subdirectories recursively'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=DRY_RUN,
        help='Show what would happen without making changes'
    )
    
    parser.add_argument(
        '--existing',
        choices=['skip', 'merge', 'rename'],
        default=EXISTING_FOLDER_ACTION,
        help='How to handle existing folders (default: %(default)s)'
    )
    
    parser.add_argument(
        '--subtitles',
        choices=['same', 'subfolder', 'none'],
        default=SUBTITLE_MODE,
        help='How to handle subtitle files (default: %(default)s)'
    )
    
    parser.add_argument(
        '--subtitle-folder',
        default=SUBTITLE_FOLDER_NAME,
        help=f'Name of subtitle subfolder when using --subtitles subfolder (default: {SUBTITLE_FOLDER_NAME})'
    )
    
    parser.add_argument(
        '--max-length',
        type=int,
        default=MAX_FOLDER_NAME_LENGTH,
        help=f'Maximum folder name length (default: {MAX_FOLDER_NAME_LENGTH})'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s 1.4'
    )
    
    args = parser.parse_args()
    
    # Create and run organizer
    organizer = MediaOrganizer(
        source_dir=args.directory,
        output_dir=args.output,
        recursive=args.recursive,
        dry_run=args.dry_run,
        existing_action=args.existing,
        max_folder_length=args.max_length,
        subtitle_mode=args.subtitles,
        subtitle_folder_name=args.subtitle_folder
    )
    
    organizer.run()


if __name__ == '__main__':
    main()