# Build Instructions - Harmonic Playlist Generator v3.0

**Creating a distributable Windows installer for end users**

This guide explains how to build a **professional Windows installer** that allows users to install HPG with one click, including Desktop icon and Start Menu entries.

---

## Quick Start (3 Simple Steps)

### Option A: Full Installer (Recommended)

```bash
# Step 1: Build executable
build.bat

# Step 2: Create icon (see Icon section below)

# Step 3: Build installer
build_installer.bat
```

**Result:** `installer_output\HPG_v3.0_Setup.exe` (~300-500 MB)

### Option B: Standalone Executable

```bash
# Just build the .exe
build.bat
```

**Result:** `HarmonicPlaylistGenerator.exe` (~300-500 MB)

---

## Prerequisites

### Required Software

1. **Python 3.9+** (3.11 recommended)
   - Download: https://www.python.org/downloads/
   - ✅ During installation: Check "Add Python to PATH"

2. **PyInstaller** (installed automatically by build.bat)
   - Bundled with build script
   - No manual installation needed

3. **Inno Setup 6** (only for installer, optional)
   - Download: https://jrsoftware.org/isdl.php
   - Only needed if you want professional installer
   - Free and open-source

### Optional (for best results)

- **Visual Studio Build Tools** (for compiling some dependencies)
  - Download: https://visualstudio.microsoft.com/downloads/
  - Select "Desktop development with C++"
  - Only needed if PyInstaller has compilation issues

---

## Detailed Build Process

### Part 1: Build Executable

#### What happens during build?

```
build.bat does:
  1. Check Python installation
  2. Activate/create virtual environment
  3. Install PyInstaller
  4. Clean previous builds
  5. Build standalone .exe (2-5 minutes)
  6. Move executable to root folder
  7. Clean up temporary files
```

#### Running the build:

```bash
# Double-click or run in CMD:
build.bat

# Or from PowerShell:
cmd /c build.bat
```

#### Expected output:

```
========================================================
  Harmonic Playlist Generator v3.0 - BUILD SCRIPT
========================================================

[1/6] Python found
[2/6] Activating virtual environment...
[3/6] Installing PyInstaller...
[SUCCESS] PyInstaller ready
[4/6] Cleaning previous builds...
[SUCCESS] Cleaned
[5/6] Building executable (this may take 2-5 minutes)...
[INFO] Please wait...
[SUCCESS] Build complete!
[6/6] Finalizing...
[SUCCESS] Executable: HarmonicPlaylistGenerator.exe

========================================================
  BUILD SUCCESSFUL!
========================================================

  Executable: HarmonicPlaylistGenerator.exe
  Size: ~300-500 MB (includes all dependencies)
```

#### Troubleshooting build issues:

**Problem:** "Python not found"
```bash
# Solution: Install Python and add to PATH
# Or run from activated virtual environment:
venv\Scripts\activate
python build.py
```

**Problem:** "PyInstaller failed"
```bash
# Solution 1: Clean and retry
rmdir /s /q build dist
build.bat

# Solution 2: Install manually
pip install --upgrade pyinstaller
pyinstaller --clean HPG.spec
```

**Problem:** Missing modules
```bash
# Solution: Install all dependencies
pip install -r requirements.txt
build.bat
```

---

### Part 2: Create Application Icon

#### Quick Method: Use Default Icon

PyInstaller will use Python's default icon if `icon.ico` is missing.

#### Professional Method: Create Custom Icon

**Option A: Online Icon Generator (Easiest)**
1. Go to: https://favicon.io/favicon-converter/
2. Upload your logo/image (PNG, JPG)
3. Download generated ICO file
4. Rename to `icon.ico`
5. Place in project root

**Option B: GIMP (Free Software)**
```
1. Install GIMP: https://www.gimp.org/downloads/
2. Open your image in GIMP
3. Scale to 256x256: Image → Scale Image
4. Export as ICO: File → Export As → icon.ico
5. Place in project root
```

**Option C: Use Existing Icons**
```
Search for free music/DJ icons:
- https://www.flaticon.com/ (free icons)
- https://icons8.com/ (free icons)
- Download as PNG, convert to ICO using online tools
```

#### Icon Specifications:
- **Format:** .ico (Windows Icon)
- **Size:** 256x256 pixels (recommended)
- **Filename:** `icon.ico`
- **Location:** Project root folder

---

### Part 3: Build Windows Installer (Optional)

#### Why use an installer?

✅ **Professional appearance**
✅ **Desktop icon automatically created**
✅ **Start Menu integration**
✅ **Add/Remove Programs entry**
✅ **Uninstaller included**
✅ **Custom installation messages**

#### Running the installer build:

```bash
# Double-click or run in CMD:
build_installer.bat
```

#### Expected output:

```
========================================================
  HPG v3.0 - INSTALLER BUILD SCRIPT
========================================================

[1/4] Executable found: HarmonicPlaylistGenerator.exe
[2/4] Inno Setup found
[3/4] Output directory ready
[4/4] Building installer...
[INFO] This may take 1-2 minutes...

========================================================
  INSTALLER BUILD SUCCESSFUL!
========================================================

  Installer: installer_output\HPG_v3.0_Setup.exe
  Size: ~300-500 MB (standalone installer)

  Features:
  - One-click installation
  - Desktop icon
  - Start Menu entry
  - Uninstaller
  - Professional UI
```

#### Testing the installer:

```
1. Run: installer_output\HPG_v3.0_Setup.exe
2. Follow installation wizard
3. Verify Desktop icon created
4. Verify Start Menu entry: Start → HPG
5. Launch app from Desktop
6. Test uninstaller: Control Panel → Add/Remove Programs
```

---

## File Structure After Build

```
HarmonicPlaylistGenkopie_V2.0/
├── build.bat                        # Main build script
├── build_installer.bat              # Installer build script
├── HPG.spec                         # PyInstaller configuration
├── version_info.txt                 # Windows properties
├── installer.iss                    # Inno Setup configuration
├── icon.ico                         # Application icon (create this!)
├── LICENSE                          # MIT License
│
├── HarmonicPlaylistGenerator.exe    # Built executable (300-500 MB)
│
├── installer_output/                # Installer output folder
│   └── HPG_v3.0_Setup.exe          # Final installer (300-500 MB)
│
├── build/                           # Temporary (deleted after build)
├── dist/                            # Temporary (deleted after build)
└── venv/                            # Virtual environment
```

---

## Distribution

### What to distribute?

**Option A: Full Installer (Best for end users)**
- File: `installer_output\HPG_v3.0_Setup.exe`
- Size: ~300-500 MB
- Users: Double-click → Install → Done

**Option B: Standalone Executable**
- File: `HarmonicPlaylistGenerator.exe`
- Size: ~300-500 MB
- Users: Double-click → Run immediately
- No installation needed

**Option C: Both**
- Offer installer for most users
- Offer portable .exe for advanced users

### Distribution Checklist

```
☐ Test installer on clean Windows 10/11 machine
☐ Test executable on clean Windows 10/11 machine
☐ Verify Desktop icon works
☐ Verify Start Menu entry works
☐ Verify uninstaller works
☐ Test with sample music files
☐ Verify Rekordbox integration works (if available)
☐ Create README.txt for distribution
☐ Create CHANGELOG.txt with v3.0 features
☐ Compress with ZIP or 7-Zip (optional)
☐ Upload to distribution platform
```

---

## Advanced Configuration

### Customizing PyInstaller Build

Edit `HPG.spec` to customize:

```python
# Change executable name
name='YourCustomName',

# Add/remove modules
hiddenimports=[
    'your_custom_module',
],

# Exclude modules to reduce size
excludes=[
    'matplotlib',  # Not needed
    'pandas',      # Not needed
],

# Enable UPX compression (may cause issues)
upx=True,  # Default: True

# Add console window for debugging
console=True,  # Default: False
```

### Customizing Installer

Edit `installer.iss` to customize:

```ini
; Change installation folder
DefaultDirName={autopf}\YourCustomFolder

; Change start menu name
DefaultGroupName=Your Custom Name

; Add custom files
[Files]
Source: "custom_file.txt"; DestDir: "{app}"

; Add custom icons
[Icons]
Name: "{group}\Custom"; Filename: "{app}\custom.exe"

; Run post-install script
[Run]
Filename: "{app}\post_install.bat"; Flags: runhidden
```

---

## Optimization Tips

### Reduce Executable Size

1. **Exclude unused libraries** (in HPG.spec):
   ```python
   excludes=[
       'matplotlib',
       'pandas',
       'IPython',
       'jupyter',
   ]
   ```

2. **Use UPX compression** (may cause antivirus warnings):
   ```python
   upx=True,
   upx_exclude=[],
   ```

3. **Remove test files before build**:
   ```bash
   rmdir /s /q tests
   rmdir /s /q .pytest_cache
   ```

### Improve Build Speed

1. **Use SSD** for build directory
2. **Close antivirus** during build (temporarily)
3. **Use --onefile** only when necessary
4. **Cache dependencies** in virtual environment

---

## Troubleshooting

### Common Issues

**Issue:** Executable crashes on startup
```
Solution 1: Add missing modules to hiddenimports
Solution 2: Build with console=True to see errors
Solution 3: Test in clean virtual environment
```

**Issue:** Antivirus flags executable
```
Solution 1: Disable UPX compression (upx=False)
Solution 2: Submit to antivirus vendors (false positive)
Solution 3: Sign executable with code signing certificate ($$)
```

**Issue:** Large executable size (>1 GB)
```
Solution 1: Exclude unnecessary modules
Solution 2: Use --exclude-module matplotlib pandas
Solution 3: Use onedir mode instead of onefile
```

**Issue:** Missing DLL errors
```
Solution 1: Install Visual C++ Redistributable:
https://aka.ms/vs/17/release/vc_redist.x64.exe

Solution 2: Include DLLs in build:
binaries=[('path/to/dll', '.')],
```

---

## Production Deployment

### Professional Distribution

1. **Code Signing** (Optional but recommended for professional apps)
   - Buy certificate: ~$100-400/year
   - Sign exe: `signtool sign /f cert.pfx /p password app.exe`
   - Benefits: No antivirus warnings, trusted by Windows

2. **Create installer with updates**
   - Add auto-update functionality
   - Check GitHub releases for new versions
   - Download and install updates automatically

3. **Crash reporting**
   - Integrate Sentry or similar
   - Automatic crash reports
   - User analytics (optional)

4. **Logging**
   - Add logging to file
   - Help users troubleshoot issues
   - Include log viewer in app

---

## Testing Checklist

### Before Release

```
☐ Build on clean machine (VM recommended)
☐ Test on Windows 10 (various versions)
☐ Test on Windows 11
☐ Test with/without Rekordbox installed
☐ Test with sample music files (WAV, MP3, FLAC, AIFF)
☐ Test all 10 playlist strategies
☐ Test M3U8 export
☐ Test Rekordbox XML export
☐ Test multi-core processing (check CPU usage)
☐ Test cache functionality
☐ Verify no crashes
☐ Verify no error dialogs
☐ Test uninstaller
☐ Test Desktop icon
☐ Test Start Menu entry
☐ Verify file associations (optional)
☐ Test with non-admin user account
☐ Check executable size (should be 300-500 MB)
☐ Check installer size (should be 300-500 MB)
```

---

## Support

### Getting Help

- **Build issues**: Check this guide first
- **PyInstaller issues**: https://pyinstaller.org/en/stable/
- **Inno Setup issues**: https://jrsoftware.org/isinfo.php
- **App issues**: See main README.md

### Useful Links

- **PyInstaller Documentation**: https://pyinstaller.org/en/stable/
- **Inno Setup Documentation**: https://jrsoftware.org/ishelp/
- **Python Packaging Guide**: https://packaging.python.org/
- **Windows Code Signing**: https://learn.microsoft.com/en-us/windows/win32/seccrypto/cryptography-tools

---

## Summary

### For Developers:
```bash
1. Edit code in main.py, hpg_core/
2. Test: python main.py
3. Build: build.bat
4. Test exe: HarmonicPlaylistGenerator.exe
5. Build installer: build_installer.bat
6. Test installer: installer_output\HPG_v3.0_Setup.exe
7. Distribute: Upload installer to users
```

### For End Users:
```
1. Download: HPG_v3.0_Setup.exe
2. Run installer
3. Follow wizard
4. Launch from Desktop icon
5. Enjoy!
```

---

**Build Time:** ~5-7 minutes total (build + installer)
**Result:** Professional Windows installer ready for distribution
**Maintenance:** Re-build after any code changes
