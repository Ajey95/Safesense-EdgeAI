# SOS contact voice messages (optional prototype)

SafeSense can post a spoken alert to up to five Telegram private chats when a
**real, newly received** TX forecast alert reaches the laptop over direct Wi-Fi
or Bluetooth. It never sends an SOS contact message for a synthetic replay,
the board's transport test, or an alert with unknown origin. This is a
playable message in Telegram, **not a phone call**. Telegram accepting a
message does not show whether a person heard it.

## Set up contacts

1. Create a Telegram bot with [BotFather](https://core.telegram.org/bots/features#botfather).
   Keep its token private. Each intended contact must open the bot and send
   `/start` from their own Telegram account.
2. Import the token with `python scripts/sos_token_store.py --import-ui` and
   enter it in the temporary local page. It is encrypted with Windows DPAPI
   for the current account in ignored `data/live/sos_bot_token.dpapi`. The
   `SAFESENSE_TELEGRAM_BOT_TOKEN` environment variable remains an alternative.
   Do not put the token in the repository or paste it into a chat.
3. Run `python -m scripts.sos_voice --list-chats`. It prints the private chat
   IDs that recently messaged the bot. Save one to five approved IDs as
   `{"chat_ids":["12345678"]}` in ignored `data/live/sos_voice_contacts.json`,
   or set `SAFESENSE_SOS_CHAT_IDS` to a comma-separated list in the receiver's
   process environment. Use only chats whose owners agreed to receive alerts.
4. Keep `ffmpeg` on `PATH`. Windows `System.Speech` makes the audio; ffmpeg
   converts it to MP3. Both were locally checked on 2026-10-20.
5. Start the receiver with `--sos-voice`:

   ```powershell
   python -m scripts.direct_laptop_receiver --sos-voice
   python -m scripts.bt_alert_receiver --port COM15 --sos-voice
   ```

   COM15 is only a previous example; check the paired outgoing Bluetooth COM
   port before starting that receiver. Both processes use the same
   `data/live/sos_voice.db` for event/contact deduplication.

The Wi-Fi receiver stores an alert before acknowledging the board and keeps a
durable SOS pending bit. Its separate worker sends after the ACK, and waits if
Telegram is unreachable while the laptop is on a network without internet.
The Bluetooth full-sample path uses the same outbox. The alert-only Bluetooth
frame has a durable receipt journal and attempts delivery after its ACK.

## Test and inspect

After the contacts agree to a test, run:

```powershell
python -m scripts.sos_voice --send-test
python -m scripts.sos_voice --status test-EVENT-ID-FROM-PREVIOUS-COMMAND
```

The test message explicitly says no incident occurred. The returned state
`ACCEPTED_BY_TELEGRAM` means Telegram accepted the voice file; it does not
prove playback. `OUTCOME_UNKNOWN` means a request might have reached Telegram
before a network failure, so the software will not retry it automatically.
The database stores a chat hash and last four digits, not the full chat ID or
bot token.

On 2026-10-20, the `@SafeSenseAjeyaSOSBot` bot was created and configured with
the owner's private chat as the sole recipient. A labelled, no-incident voice
test was accepted by Telegram and appeared in that chat (event
`test-ca610e53-f245-4bc4-9a06-3a40895c41de`). The Wi-Fi and COM15 Bluetooth
receivers were started with `--sos-voice`. This proves delivery of the test
message, not that a real sensor alert or a human response was verified.

This remains a student prototype. Forecast and gas thresholds are not
validated emergency detectors, and Telegram requires internet and enabled
notifications on each recipient's device. Use a separate established emergency
procedure for actual hazards.
