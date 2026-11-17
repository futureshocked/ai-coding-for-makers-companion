# Chapter 6: build a calculator in a browser

A single-file RC low-pass filter analyser. Enter resistance in kilohms and capacitance in nanofarads; it shows the cut-off frequency and draws a Bode magnitude plot that updates as you type.

## Files

| File | What it is |
|---|---|
| [`rc_filter_analyser.html`](rc_filter_analyser.html) | The finished tool. No server, no libraries, no internet connection needed. |
| [`prompt.md`](prompt.md) | The specification prompt from the chapter, which produced the tool. |

## Run it

Download `rc_filter_analyser.html` and double-click it, or drag it into any modern browser.

## Check it

With the defaults (1 kΩ, 159 nF) the cut-off frequency should read close to 1000 Hz, and the plot should cross −3 dB at the dashed line. Try 10 kΩ and 15.9 nF: the answer should be the same, because only the product R × C matters.

## Try it yourself

Paste the prompt into a chat assistant in a fresh session. Expect the first version to need at least one correction; the chapter walks through the one it needed.
