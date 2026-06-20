# 🏏 Hand Cricket — Multiplayer Socket Game

A real-time, two-player implementation of **Hand Cricket** played over a TCP socket connection from the terminal. One player runs the server, two players connect as clients, and the game plays out interactively with toss, batting/bowling, two innings, live chat, and a persistent match history log.

---

## Table of Contents
- [How the Game Works](#how-the-game-works)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Setup](#setup)
- [Running the Game](#running-the-game)
- [In-Game Commands](#in-game-commands)
- [Match Flow Walkthrough](#match-flow-walkthrough)
- [Match Logging](#match-logging)
- [Timeouts & Forfeits](#timeouts--forfeits)
- [Known Issues / TODO](#known-issues--todo)
- [Security Note](#security-note)

---

## How the Game Works

Hand Cricket is a simplified version of cricket played by throwing a number (1–6) instead of bowling/batting a real ball:

1. **Toss** — Player 1 calls ODD or EVEN and throws a number; Player 2 throws a number. If the total is odd/even matching Player 1's call, Player 1 wins the toss — otherwise Player 2 does.
2. **Bat or Bowl** — The toss winner chooses to bat or bowl first.
3. **Innings 1** — On each round, both players simultaneously "throw" a number (1–6).
   - If the **batter's number equals the bowler's number** → the batter is **OUT**. Innings 1 ends, roles swap, and the batter's score becomes the **target** for Innings 2.
   - Otherwise, the batter scores runs equal to the number they threw.
4. **Innings 2** — Same rules, but now the second batter is chasing the target set in Innings 1.
   - If they get OUT before reaching the target → the bowling side **defends** the target and wins.
   - If they reach/exceed the target → the batting side wins by **chasing** the target successfully.
5. **Replay** — After a match ends, both players can choose `PLAY_AGAIN` to start a fresh match, or `EXIT` to disconnect.

---

## Project Structure

```
HAND_CRICKET/
├── main.py            # Entry point — branches into server or client mode
├── server.py           # HandCricketServer — game state machine & networking
├── client.py            # Terminal client — connects, sends/receives messages
├── engine.py            # GameEngine — toss/innings/scoring rules
├── protocols.py          # Protocols — shared prompt/error/help text constants
├── certs/               # TLS certificate + key (server.crt, server.key) — only needed if running the TLS-enabled server
└── match_logs.txt        # Auto-generated, append-only match history (created on first game)
```

> `engine.py`, `protocols.py`, and `main.py` weren't shared in this conversation, so this README describes their behavior based on how `server.py` and `client.py` use them. Adjust if your actual implementation differs.

---

## Requirements

- **Python 3.8+**
- No third-party dependencies — only the standard library is used (`socket`, `select`, `threading`, `queue`, `pathlib`, and optionally `ssl` depending on which version of `server.py`/`client.py` you're running).

---

## Setup

### If using the plain-TCP version (no encryption)
No extra setup needed — just run the scripts directly. Traffic between client and server is **unencrypted**; see [Security Note](#security-note).

### If using the TLS/SSL-enabled version
The server expects a certificate and private key at:
```
certs/server.crt
certs/server.key
```
You can generate a self-signed pair for local/LAN testing with OpenSSL:
```bash
mkdir certs
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout certs/server.key -out certs/server.crt \
  -days 365 -subj "/CN=localhost"
```

> ⚠️ **Check before running:** make sure both `client.py` and `server.py` agree on whether TLS is used. A plain-TCP client cannot connect to a TLS-wrapped server (and vice versa) — the connection will appear to "hang" with no error.

---

## Running the Game

**1. Start the server** (on the host machine):
```bash
python main.py server
```
By default this binds to `0.0.0.0:12345` and waits for two players to connect.

**2. Connect two clients** (in separate terminals, or from two different machines on the same network):
```bash
python main.py client
```
By default this connects to `localhost:12345`.

> If playing across two different machines, the client needs the server's actual LAN IP rather than `localhost`. Check your `main.py`/`client.py` for how host/port are passed in (e.g. command-line arguments, a config value, or hardcoded defaults).

---

## In-Game Commands

| Command | Who sends it | Description |
|---|---|---|
| `NAME <name>` | Both (during registration) | Registers your player name |
| `TOSS <ODD\|EVEN> <1-6>` | Player 1 only | Calls odd/even and throws a number for the toss |
| `TOSS <1-6>` | Player 2 only | Throws their toss number after Player 1 |
| `DECIDE <BAT\|BOWL>` | Toss winner only | Chooses to bat or bowl first |
| `PLAY <1-6>` | Both, each round | Throws a number during an innings |
| `CHAT <message>` | Either, anytime | Sends a chat message to the opponent |
| `PLAY_AGAIN` | Both, after a match ends | Starts a new match with the same opponent |
| `EXIT` | Either, anytime | Forfeits the match — the opponent is declared the winner by default |
| `HELP` | Either, anytime | Displays the help text |

---

## Match Flow Walkthrough

```
Both players connect
        │
        ▼
  Register names (NAME)
        │
        ▼
       Toss (TOSS)
        │
        ▼
  Bat or Bowl decision (DECIDE)
        │
        ▼
     Innings 1 (PLAY, repeated)
        │  (batter gets OUT)
        ▼
     Innings 2 (PLAY, repeated)
        │  (target defended OR chased)
        ▼
      Game Over
        │
   ┌────┴────┐
PLAY_AGAIN   EXIT
   │            │
 New Toss   Connection closed
```

---

## Match Logging

Every game is appended to `match_logs.txt` (created next to `server.py`), building a continuous history across the server's entire runtime — the game counter is never reset, even across reconnects:

```
game1
inn1
RISHI bats 5 RAHUL bowls 4
result: RAHUL wins (opponent timeout)
game2
inn1
RAHUL bats 4 RISHI bowls 5
RAHUL bats 5 RISHI bowls 2
RAHUL bats 4 RISHI bowls 3
RAHUL bats 6 RISHI bowls 6
inn2
RISHI bats 6 RAHUL bowls 1
RISHI bats 6 RAHUL bowls 2
RISHI bats 5 RAHUL bowls 5
result: RAHUL wins (defended target)
```

**Log line meanings:**
- `gameN` — start of a new match (N never resets)
- `innN` — start of innings 1 or 2 within the current match
- `<batter> bats X <bowler> bowls Y` — one resolved ball
- `result: <winner> wins (<reason>)` — match outcome; reason is one of:
  - `defended target` — bowling side got the chaser out
  - `chased target` — batting side reached the target
  - `opponent timeout` — opponent didn't respond within 45 seconds
  - `opponent abandoned` — opponent sent `EXIT` or disconnected

---

## Timeouts & Forfeits

- **45-second forfeit timer:** During gameplay (innings 1 and 2), once one player sends `PLAY` and the other hasn't responded yet, a 45-second countdown starts. The waiting player gets a warning. If time runs out, the player who *did* respond wins the match by default.
- **Abandonment:** If a player sends `EXIT`, or their connection drops unexpectedly, the other player is immediately declared the winner. Both cases broadcast a clear message to both players and are recorded in `match_logs.txt`.

---
