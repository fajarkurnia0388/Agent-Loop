# Installation Guide

This guide provides detailed installation instructions for Senior Tools MCP Server across different platforms and AI assistants.

## Table of Contents
- [Prerequisites](#prerequisites)
- [Platform-Specific Setup](#platform-specific-setup)
- [Getting API Keys](#getting-api-keys)
- [MCP Client Configuration](#mcp-client-configuration)
- [Verification](#verification)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### Required Software
- **Python 3.8 or higher**
  - Check version: `python --version` or `python3 --version`
  - Download from: https://www.python.org/downloads/

- **pip** (Python package manager)
  - Usually included with Python
  - Check version: `pip --version`

- **Git** (for cloning the repository)
  - Download from: https://git-scm.com/downloads

### Required API Keys
- **Google Gemini API Key** (required)
  - Free tier available
  - Used for AI improvements and embeddings
  - Get it from: https://makersuite.google.com/app/apikey

- **OpenAI API Key** (optional)
  - Alternative to Gemini for embeddings
  - Get it from: https://platform.openai.com/api-keys

## Platform-Specific Setup

### Windows

1. **Install Python**
   ```powershell
   # Download from python.org or use winget
   winget install Python.Python.3.11
   ```

2. **Clone the Repository**
   ```powershell
   git clone https://github.com/theguy000/AgentLoop.git
   cd AgentLoop
   ```

3. **Create Virtual Environment (Recommended)**
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   ```

4. **Install Dependencies**
   ```powershell
   pip install -r requirements.txt
   ```

5. **Configure Environment**
   ```powershell
   copy .env.example .env
   notepad .env
   ```

### Linux

1. **Install Python and Dependencies**
   ```bash
   # Ubuntu/Debian
   sudo apt update
   sudo apt install python3 python3-pip python3-venv git

   # Fedora
   sudo dnf install python3 python3-pip git

   # Arch
   sudo pacman -S python python-pip git
   ```

2. **Install X11 Development Libraries** (for window control)
   ```bash
   # Ubuntu/Debian
   sudo apt install python3-xlib

   # Fedora
   sudo dnf install python3-xlib

   # Arch
   sudo pacman -S python-xlib
   ```

3. **Clone and Setup**
   ```bash
   git clone https://github.com/theguy000/AgentLoop.git
   cd AgentLoop
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env
   nano .env
   ```

### macOS

1. **Install Homebrew** (if not already installed)
   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

2. **Install Python**
   ```bash
   brew install python@3.11
   ```

3. **Clone and Setup**
   ```bash
   git clone https://github.com/theguy000/AgentLoop.git
   cd AgentLoop
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env
   nano .env
   ```

## Getting API Keys

### Google Gemini API Key

1. Visit https://makersuite.google.com/app/apikey
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy the generated key
5. Add to `.env` file:
   ```bash
   GEMINI_API_KEY=your_actual_api_key_here
   ```

### OpenAI API Key (Optional)

1. Visit https://platform.openai.com/api-keys
2. Sign in or create an account
3. Click "Create new secret key"
4. Copy the key (you won't be able to see it again!)
5. Add to `.env` file:
   ```bash
   OPENAI_API_KEY=your_actual_api_key_here
   EMBEDDING_PROVIDER=openai
   ```

## MCP Client Configuration

### Cursor IDE

1. **Locate Cursor Configuration Directory**
   - Windows: `%APPDATA%\Cursor\User\globalStorage\`
   - Linux: `~/.config/Cursor/User/globalStorage/`
   - macOS: `~/Library/Application Support/Cursor/User/globalStorage/`

2. **Create or Edit `.mcp.json`**
   ```json
   {
     "mcpServers": {
       "senior-tools": {
         "command": "python",
         "args": ["C:/absolute/path/to/simple_answer/senior_tools.py"],
         "cwd": "C:/absolute/path/to/simple_answer"
       }
     }
   }
   ```

   **Important**: Use absolute paths! Replace with your actual installation path.

3. **Restart Cursor**
   - Close all Cursor windows
   - Reopen Cursor
   - The MCP server should start automatically

### Augment IDE

1. **Create `.augment/mcp.json` in your project**
   ```json
   {
     "mcpServers": {
       "senior-tools": {
         "command": "python",
         "args": ["/absolute/path/to/simple_answer/senior_tools.py"],
         "cwd": "/absolute/path/to/simple_answer"
       }
     }
   }
   ```

2. **Restart Augment**

### Windsurf IDE

1. **Create MCP configuration** (similar to Cursor)
   - Check Windsurf documentation for exact configuration location
   - Use the same JSON structure as above

2. **Restart Windsurf**

## Verification

### Test MCP Server Directly

```bash
# Activate virtual environment if using one
source venv/bin/activate  # Linux/macOS
.\venv\Scripts\activate   # Windows

# Run the MCP server
python senior_tools.py
```

You should see:
```
SENIOR_TOOLS MODULE INITIALIZED
FastMCP instance created successfully
```

### Test UI Interface

```bash
python invoke_ui.py "Test message"
```

A feedback dialog should appear.

### Test Cursor Window Control

```bash
# Show debug information
python focus_cursor.py --debug

# Test focusing (make sure Cursor is running)
python focus_cursor.py
```

### Test in AI Assistant

Ask your AI assistant:
```
Can you check if the senior-tools MCP server is available?
```

The AI should be able to list the available tools:
- `memory_save`
- `memory_call`
- `ask_to_leader_project`
- `init_agent_files`
- `get_embedding_cache_stats`

## Troubleshooting

### Common Issues

#### 1. "Module not found" errors

**Solution**: Make sure all dependencies are installed
```bash
pip install -r requirements.txt --upgrade
```

#### 2. "GEMINI_API_KEY not found"

**Solution**: Check your `.env` file
```bash
# Make sure .env exists
ls -la .env  # Linux/macOS
dir .env     # Windows

# Verify content
cat .env     # Linux/macOS
type .env    # Windows
```

#### 3. MCP server not connecting

**Solution**: Check paths in MCP configuration
- Use absolute paths, not relative
- Verify Python executable path: `which python` (Linux/macOS) or `where python` (Windows)
- Check logs in Cursor: View → Output → MCP

#### 4. PyQt5 installation fails

**Solution**: Install system dependencies

**Linux**:
```bash
sudo apt install python3-pyqt5 python3-pyqt5.qtmultimedia libqt5multimedia5-plugins
```

**macOS**:
```bash
brew install pyqt5
```

**Windows**: Usually works with pip, but if issues persist:
```powershell
pip install PyQt5 --no-cache-dir
```

#### 5. Window control not working

**Windows**: Install pywinauto and pywin32
```powershell
pip install pywinauto pywin32
```

**Linux**: Install python-xlib
```bash
sudo apt install python3-xlib
pip install python-xlib
```

**macOS**: Install pyobjc
```bash
pip install pyobjc-framework-Cocoa pyobjc-framework-Quartz
```

#### 6. Permission denied errors

**Solution**: Check file permissions
```bash
# Linux/macOS
chmod +x senior_tools.py
chmod +x focus_cursor.py
chmod +x invoke_ui.py
```

### Getting Help

If you encounter issues not covered here:

1. **Check logs**: Look in `logs/focus_cursor.log`
2. **Enable debug mode**: Set `logging.DEBUG` in senior_tools.py
3. **Test components individually**: Use the test scripts in `tests/`
4. **Open an issue**: Provide error messages and system information

### System Information for Bug Reports

When reporting issues, include:
```bash
# Python version
python --version

# Installed packages
pip list

# Operating system
# Windows
systeminfo | findstr /B /C:"OS Name" /C:"OS Version"

# Linux
uname -a
lsb_release -a

# macOS
sw_vers
```

## Next Steps

After successful installation:

1. **Read the main README.md** for usage examples
2. **Check docs/USAGE.md** for detailed usage instructions
3. **Review docs/API.md** for MCP tool reference
4. **Run tests** to verify everything works: `pytest tests/`

---

**Installation complete!** 🎉 You're ready to use Senior Tools with your AI assistant.

