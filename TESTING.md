# Testing checklist

Everything below is written as something you type into the assistant (run with `run.bat`,
`python main.py`, or PyCharm). Pick any of them in any order. Marked ⚠ items change something
on your PC (a confirmation box will appear first - that's the point).

## 0. Run it

```powershell
# from the project folder - use run.bat so the RIGHT interpreter is used
.\run.bat
# (or explicitly)
C:\Users\srava\Desktop\Python\.venv\RealAssistant\Scripts\python.exe main.py
```

> Running plain `python main.py` may pick a different Python that's missing libraries.
> The app prints which interpreter it's using, and warns about anything missing.

You should see `Starting up...`, an `[apps] indexed N shortcuts.` line, and `Ready.`.

## 1. Conversation & personality
- [ ] `hey` -> short, casual, no "as an AI", no emojis
- [ ] `what can you do?` -> brief, human, doesn't list tools like a robot
- [ ] `tell me a joke` -> one line, a bit dry
- [ ] `who are you?` -> stays in character (a person helping, not a language model)

## 2. Memory
- [ ] `I'm Sravanth and I hate mornings` -> later a `[memory] learned: ...` line may appear
- [ ] `what do you know about me?` -> repeats the facts it picked up
- [ ] `forget that I hate mornings` -> confirms it forgot
- [ ] Close and reopen -> `what do you know about me?` still knows the rest

## 3. Apps, windows
- [ ] `open chrome` / `open telegram` / `open notepad`
- [ ] `open ampcast` -> app opens **and** its console output does NOT leak into the chat
- [ ] `what apps do I have?` and `list apps with "code"`
- [ ] `which windows are open?`
- [ ] `bring chrome to the front`
- [ ] `snap chrome to the left`, then `right`, then `maximize`
- [ ] `list my chrome profiles`
- [ ] `open chrome with the Sravanth profile` (use one of your profile names)
- [ ] ⚠ `close notepad` -> answer the confirmation by voice/typing (see section 9)

## 4. Web & info
- [ ] `who won the last F1 race?` -> uses look_up and answers in its own words
- [ ] `open youtube.com`
- [ ] `search for best budget headphones`
- [ ] `what's the weather?` (and `weather in London`)
- [ ] `give me my briefing`

## 5. Files
- [ ] `what's in my downloads?`
- [ ] `find files with "invoice"` (or any name you know)
- [ ] `find files that mention "voiceStra"`
- [ ] `read C:\Users\srava\Desktop\RealAssistant\README.md` -> summarises/returns it
- [ ] `read this page <paste a news url>` -> reads it back
- [ ] ⚠ `move the Animal Farm pdf into a Books folder` -> should **move** it (create the folder first), NOT delete it
- [ ] `copy that file to the desktop` -> makes a copy, no confirmation needed
- [ ] `rename that file to something else`
- [ ] ⚠ `organize my downloads` -> confirm box, then files sorted into folders
- [ ] ⚠ `undo that` -> files put back

## 6. Reminders & notes
- [ ] `remind me in 1 minute to stretch` -> wait, a `*** Reminder ***` line appears
- [ ] `remind me at 7pm to call mom`
- [ ] `list my reminders`
- [ ] `cancel reminder <id>`
- [ ] `note that the wifi password is on the router`
- [ ] `what are my notes?` / `search notes for wifi`
- [ ] ⚠ `delete the note about wifi`

## 7. Media, display, power
- [ ] `set volume to 25` then `volume up`
- [ ] `mute`
- [ ] `pause the music` / `next track`
- [ ] `what's my battery?`
- [ ] `set brightness to 50` (may say the display doesn't support it - fine)
- [ ] ⚠ `lock my pc`
- [ ] ⚠ `shut down in 2 minutes` -> confirm box, then Windows' own countdown appears
- [ ] ⚠ `cancel shutdown` -> countdown stops

## 8. System awareness
- [ ] `how's my system doing?`
- [ ] `what's using the most memory?`
- [ ] `check my internet`
- [ ] `how long has this pc been on?`

## 9. Safety (the important ones)
- [ ] Any ⚠ action shows a **native confirmation box** and does nothing until you click Yes
- [ ] Click **No** on a shutdown prompt -> it says it was cancelled and nothing happens
- [ ] Set `"confirm_mode": "chat"` in `settings.json`, restart, then a ⚠ action asks in the
      chat instead - answer `yes` / `no` by typing (this is the voice-friendly path)
- [ ] `what have you done recently?` -> audit log of actions

## 10. Multi-step
- [ ] `open notepad and set the volume to 40` -> does both in one go, one short confirmation
- [ ] `find my downloads and tell me what's in them` -> chains tools

## 11. Packaging
- [ ] Build: `python build.py` -> `dist\RealAssistant.exe`
- [ ] Copy `.env` next to the exe, run it -> same behaviour as `python main.py`

## 12. Voice (offline)
- [ ] Run `\run.bat voice`, press **Enter**, say *"open notepad"* -> it opens and replies out loud
- [ ] If it hears nothing, run `python mic_test.py` -> check the level and the printed transcript
- [ ] Say *"shut down in 2 minutes"* -> it asks out loud -> say **"yes"** -> then ⚠`cancel shutdown`
- [ ] `list your voices` / `use the Zira voice` -> voice changes after restart
- [ ] See `VOICE_GUIDE.md` for adding your own custom voice

## What "good" looks like

- Replies are short and human; it never says it's an AI
- Tool actions happen silently, then one natural line tells you the result
- Failures are friendly ("looks like Telegram isn't installed..."), never stack traces
- Anything destructive asks first
- It remembers things across restarts, and doesn't invent facts

## Found something odd?

Tell me the exact thing you typed and what happened. That's the fastest path to a fix.
