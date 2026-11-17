# Install the tools

You need different tools for different builds. Install what the build you are working on needs; the table shows which.

| Tool | Ch 6 calculator | Ch 16 serial plotter | Ch 22 datasheet Q&A | Ch 29 booking system |
|---|---|---|---|---|
| A modern web browser | ✓ | ✓ | ✓ | ✓ |
| Git | | ✓ | ✓ | ✓ |
| Python 3.10 or newer | | ✓ | ✓ | ✓ |
| A code editor (VS Code recommended) | | ✓ | ✓ | ✓ |
| An AI coding assistant | optional | ✓ | ✓ | ✓ |
| Arduino IDE | | optional (for real hardware) | | |
| Docker | | | | ✓ |

## 1. Git

- **Windows:** install Git for Windows from <https://git-scm.com/download/win>. Accept the defaults.
- **macOS:** run `git --version` in Terminal. If Git is missing, macOS offers to install the Command Line Tools; accept.
- **Linux (Debian, Ubuntu):** `sudo apt install git`

Then tell Git who you are (this is stored in every commit you make):

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

## 2. Python

- **Windows:** install from <https://www.python.org/downloads/>. On the first installer screen, tick **Add python.exe to PATH**.
- **macOS:** install from <https://www.python.org/downloads/>, or with Homebrew: `brew install python`.
- **Linux (Debian, Ubuntu):** `sudo apt install python3 python3-venv python3-pip`

Check it works with `python3 --version` (on Windows, `python --version`).

Every Python build in this repository runs inside its own virtual environment, so its packages don't collide with other projects. From the folder that holds the project's `requirements.txt`:

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Run `source venv/bin/activate` (or the Windows equivalent) again each time you open a new terminal to work on the project.

## 3. A code editor

The book uses Visual Studio Code: <https://code.visualstudio.com/>. Install the **Python** extension from Microsoft when VS Code suggests it.

## 4. An AI coding assistant

The book's builds used a terminal coding agent (Claude Code) and a VS Code extension (Cline). Any capable coding agent works with the prompts in this repository. Follow the current installation instructions on the tool's own website, since these change often. The book's tool chapters and the resources page list the options: <https://ai.techexplorations.com/resources/>.

## 5. Arduino IDE (serial plotter, optional)

You only need this to send real data from a board. The serial plotter runs on simulated data without one.

1. Install the Arduino IDE from <https://www.arduino.cc/en/software>.
2. Install the board package for your board (the book used an Arduino Uno R4 Minima: **Tools → Board → Boards Manager**, search for "UNO R4").
3. Open the sketch, select your board and port under **Tools**, and upload.

## 6. Docker (booking system)

The booking system uses PostgreSQL, which is easiest to run in Docker during development, and it is deployed as Docker containers.

- **Windows and macOS:** install Docker Desktop from <https://www.docker.com/products/docker-desktop/>.
- **Linux:** follow <https://docs.docker.com/engine/install/> for your distribution, then add yourself to the `docker` group so you can run it without `sudo`.

Check it works with `docker run hello-world`.
