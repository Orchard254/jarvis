# Dependency Audit Report

## Summary
Consolidated and updated `requirements.txt` with all missing dependencies discovered through static code analysis of the `jarvis/` directory.

## Methodology
1. Scanned all Python files in `jarvis/` for import statements
2. Extracted all third-party package imports
3. Cross-referenced with existing `requirements.txt`
4. Added missing dependencies with appropriate version constraints

## Dependencies Added

### Previously Missing (Now Added)
| Package | Version | Used In | Purpose |
|---------|---------|---------|---------|
| `pydantic` | >=2.0.0 | Core models | Data validation & settings |
| `pyyaml` | >=6.0 | config/config.py | YAML configuration parsing |
| `chromadb` | >=0.4.0 | memory/persistent.py | Vector database for semantic memory |
| `playwright` | >=1.40.0 | tools/web/automation.py | Browser automation |
| `pytesseract` | >=0.3.10 | core/vision.py | OCR text extraction |
| `pygetwindow` | >=0.0.9 | monitoring/ambient.py | Window management |
| `keyring` | >=24.0.0 | security/vault.py | Secure credential storage |
| `aiofiles` | >=23.0.0 | core/react_agent.py | Async file operations |

### Already Present (Verified)
All previously listed dependencies were confirmed as actively used:
- Audio: sounddevice, soundfile, SpeechRecognition, openwakeword, edge-tts, pydub, webrtcvad, noisereduce, pyaudio, pyttsx3
- Vision: Pillow, opencv-python, mss
- System: psutil, pynput, pyautogui
- Web: beautifulsoup4
- Data: numpy, scipy, wikipedia, yfinance
- Platform: requests, python-dotenv
- Testing: pytest, pytest-mock
- Windows-specific: pycaw, comtypes

## Organization
Dependencies are now organized by category:
1. **Core Dependencies** - Fundamental libraries
2. **LLM & AI** - Model inference & vector storage
3. **Audio Processing** - STT, TTS, wake word detection
4. **Vision & Screen** - Image processing, OCR, screenshots
5. **System Control** - Automation, window management
6. **Web & Browser** - Scraping, browser automation
7. **Data & Utilities** - Data manipulation, external APIs
8. **Security** - Credential management
9. **Testing** - Test frameworks
10. **Windows-specific** - Platform-specific audio control

## Version Constraints
All dependencies now have explicit minimum versions to ensure:
- Compatibility across environments
- Access to required features
- Security patches applied
- Reproducible installations

## Installation
```bash
pip install -r requirements.txt
playwright install  # Required for browser automation
```

## Notes
- All imports verified through AST parsing - no syntax errors detected
- No unused dependencies found in requirements.txt
- All dependencies in requirements.txt are actively imported in codebase
- Platform-specific dependencies properly marked with environment markers
