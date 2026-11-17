# Chapter 22: build prompts for the datasheet Q&A tool

The prompts from the chapter, in order. Between the first and second, the conversation produced the specification in [`code/documents/specification.md`](code/documents/specification.md), which the second prompt hands to the coding agent.

## 1. Apply the runtime-LLM decision test

```text
I want to build a tool that lets me upload a PDF datasheet for an electronic
component and then ask questions about it in plain English, things like "What
is the maximum supply voltage?" or "How do I configure the SPI interface?"
Before we plan the architecture, apply a decision test to confirm a runtime
LLM is the right choice. The test has three questions: 

One, can a simpler function produce the output reliably? 

Two, does the output require synthesis from unstructured text in a
 way that varies with the input? 

Three, can the application absorb variable latency and per-call cost
 without breaking 
the user experience? 

Walk me through the test for this project.
```

## 2. Scaffold the application from the specification

```text
Read the specification for a new application, that is in "specification.md" inside the "documents" folder. 

Proceed to setup the scaffolding for the application. Create all files and folders listed in the file structure. 

In this session, we will implement the goals in S1, but not yet. Right now, only work on the scaffolding. don't work on S2, S3, or S4.
```

The specification splits the work into four stages, S1 to S4. Each later session asked the agent to implement the next stage, in the same pattern as the prompt above.
