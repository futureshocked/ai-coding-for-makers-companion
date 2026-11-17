# Chapter 16: build prompts for the serial data plotter

These are the prompts from the chapter, in the order they were used. Before the first one, the agent was given the specification in [`code/documentation/AGENT_SPEC.md`](code/documentation/AGENT_SPEC.md) and the architecture document in [`code/documentation/ARCHITECTURE.md`](code/documentation/ARCHITECTURE.md). The chapter explains what happened after each prompt, including the corrections in between.

## 1. Create the project structure

```text
Based on the spec document in AGENT_SPEC.md, create the project file structure
for the serial plotter project. Create all files listed in the output format
section as empty files. don't write any implementation code yet.
```

## 2. Build the front end

```text
build the front end HTML, CSS and JS files for a dashboard that will
depict the data from the Arduino to the web browser
```

## 3. Add log replay

```text
I'd like to add a new feature that can play back the measurements stored in the
log files inside the log directory. On the front end, the index page should
display the available log files in a drop-down widget, showing human-readable
dates and times rather than raw file names. The user can select one and click a
button titled Replay to draw the plots gradually, the way they would appear if
the data were arriving live from the Arduino, rather than in a single flash. Add
a button titled Live to switch back to the live source. For the back end, make
sensible choices about the implementation. Don't break anything.
```

## 4. Switch to real hardware and write a test sketch

```text
I want to switch the application to real Arduino data over the serial port
instead of mock data. I'm using an Arduino Uno R4 Minima with no sensors
connected. Write a test sketch that generates sample temperature, humidity, and
lux data and sends it over serial in the CSV format the application expects, one
reading per second. Call it serial_plotter_sim.ino.
```

## 5. Write a start script

```text
Write start.sh for Linux and macOS. It should change to the project directory
using the location of the script itself, activate the virtual environment at
venv/bin/activate if that file exists, run python app.py in the background, wait
two seconds, and open http://localhost:5000 in the browser, using xdg-open on
Linux or open on macOS, detected with uname. Exit cleanly if the server fails to
start.
```
