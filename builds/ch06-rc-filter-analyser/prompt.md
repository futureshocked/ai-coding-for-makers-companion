# Chapter 6: specification prompt for the RC filter analyser

This is the prompt from the chapter. It applies the four elements from Chapter 4 (task, context, constraints, output format). Paste it into a chat assistant as a single message.

```text
Create a single HTML file with no external libraries or CDN links of any kind.

The tool is an interactive RC low-pass filter analyser.

Inputs:
- Resistance R, entered in kilohms (kΩ). Use a number input with a default value of 1.
- Capacitance C, entered in nanofarads (nF). Use a number input with a default value of 159.

Calculations and display:
1. Convert internally: R_ohms = R × 1000, C_farads = C × 1e-9
2. Calculate the cut-off frequency: fc = 1 / (2π × R_ohms × C_farads)
   Display fc in Hz, rounded to one decimal place, below the inputs.
3. Draw a Bode magnitude plot on an HTML Canvas element (700 × 350 pixels):
   - x-axis: frequency from 1 Hz to 1,000,000 Hz on a logarithmic scale
   - y-axis: magnitude in dB from 0 dB (top) to −40 dB (bottom)
   - Magnitude at each frequency f: M(f) = −10 × log10(1 + (f / fc)²)
   - Draw a vertical dashed line at f = fc and label it with the fc value in Hz
   - Label both axes

The plot and the fc display must update automatically when R or C changes.
Use the input event (not the change event) so updates happen as the user types.

Output only the complete HTML file content, starting with <!DOCTYPE html>.
The file must open correctly in any modern browser without a web server.
```
