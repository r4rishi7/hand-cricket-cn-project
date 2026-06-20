import socket as x
import ssl
import select
import time
import engine
from pathlib import Path
from protocols import Protocols as protocol

class HandCricketServer:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.engine = engine.GameEngine()
        self.player1 = None
        self.player2 = None
        self.player1_name = ""
        self.player2_name = ""
        self.state = "REGISTERING"
        self.p1_toss_choice = None
        self.p1_toss_num = None
        self.p2_toss_num = None
        self.p1_play_num = None
        self.p2_play_num = None
        self.p1_replay = None
        self.p2_replay = None

        # ── Per-socket line-buffers ──────────────────────────────────────
        # TLS (and TCP under it) is a byte stream, not a message stream.
        # Multiple sends from a client can arrive in one recv(), and one
        # send can arrive split across multiple recv()s. We terminate every
        # client message with "\n" (see client.py) and buffer here until we
        # have at least one full line, then process exactly one command at
        # a time. This is the fix for the "messages getting mashed together"
        # bug that looked like an SSL issue but wasn't.
        self._recv_buf = {}  # socket -> str (partial, unterminated data)

        # ── Match logging ────────────────────────────────────────────────
        # game_number is a server-lifetime counter (not reset between
        # connections or PLAY_AGAIN), so match_logs.txt builds up a
        # continuous history of every game ever played:
        #   game1
        #   inn1
        #   Alice bats 5 Bob bowls 3
        #   ...
        #   inn2
        #   ...
        #   result: Alice wins (defended target)
        #   game2
        #   ...
        self.game_number = 0
        self.innings_number = 0
        self.match_log_path = Path(__file__).resolve().parent / "match_logs.txt"

        # ── 45-second "opponent forfeits if they don't respond" timer ───
        # Set whenever one player has submitted PLAY but the other hasn't.
        # Cleared as soon as both have played (or the match/innings ends).
        self.play_deadline = None

        # ── SSL context (server-side identity, no client-cert auth) ─────
        self.ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        cert_path = Path(__file__).parent / "certs" / "server.crt"
        key_path = Path(__file__).parent / "certs" / "server.key"
        self.ssl_context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
        # Pin a sane minimum so handshakes are predictable across client/server.
        self.ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2

    def send_msg(self, player, msg):
        if player:
            try:
                player.sendall(msg.encode())
            except Exception:
                pass

    def broadcast(self, msg):
        self.send_msg(self.player1, msg)
        self.send_msg(self.player2, msg)

    def close_connections(self):
        self.state = "CLOSED"
        self.play_deadline = None
        for player in [self.player1, self.player2]:
            if player:
                try:
                    player.close()
                except Exception:
                    pass
                self._recv_buf.pop(player, None)
        self.player1 = None
        self.player2 = None

    # ── Match log helpers ────────────────────────────────────────────────
    def _log_line(self, line):
        """Append one line to match_logs.txt. Never lets logging crash the game."""
        try:
            with open(self.match_log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:
            print(f"[MatchLog] Failed to write log: {e}")

    def _start_new_game_log(self):
        self.game_number += 1
        self.innings_number = 0
        self._log_line(f"game{self.game_number}")

    # ── 45s forfeit-timer helper ───────────────────────────────────────────
    def _check_play_timeout(self):
        """
        Called every loop tick. If one player has played and the other
        hasn't responded within 45 seconds, the player who responded wins
        the match by default.
        """
        if self.play_deadline is None:
            return
        if self.player1 is None or self.player2 is None:
            self.play_deadline = None
            return
        if self.state not in ("PLAYING_INNINGS_1", "PLAYING_INNINGS_2"):
            self.play_deadline = None
            return
        if time.time() < self.play_deadline:
            return

        if self.p1_play_num is not None and self.p2_play_num is None:
            winner_name = self.player1_name or "Player 1"
            loser_name = self.player2_name or "Player 2"
        elif self.p2_play_num is not None and self.p1_play_num is None:
            winner_name = self.player2_name or "Player 2"
            loser_name = self.player1_name or "Player 1"
        else:
            self.play_deadline = None
            return

        self.broadcast(
            f"\n⏱ Time exceeded! {loser_name} did not respond within 45 seconds.\n"
            f"  {winner_name} wins the match by default!\n\n"
            f"Do you want to play again? Enter: PLAY_AGAIN or EXIT\n"
        )
        self._log_line(f"result: {winner_name} wins (opponent timeout)")
        self.p1_play_num = None
        self.p2_play_num = None
        self.play_deadline = None
        self.state = "GAME_OVER"

    def handle_player_message(self, player, msg):
        parts = msg.strip().split()
        if not parts:
            return
        cmd = parts[0].upper()
        args = parts[1:]

        if cmd == "HELP":
            self.send_msg(player, protocol.HELP_TXT)
            return
        if cmd == "EXIT":
            # ── Abandonment handling ──────────────────────────────────────
            # Whoever sent EXIT forfeits; the other player is declared the
            # winner by default, regardless of what state the match was in.
            exiter_name = self.player1_name if player == self.player1 else self.player2_name
            winner_name = self.player2_name if player == self.player1 else self.player1_name
            if not exiter_name:
                exiter_name = "Player 1" if player == self.player1 else "Player 2"
            if not winner_name:
                winner_name = "Player 2" if player == self.player1 else "Player 1"
            self.broadcast(f"\n{exiter_name} has abandoned the match. {winner_name} wins by default!\n\nClosing connections...\n")
            self._log_line(f"result: {winner_name} wins (opponent abandoned)")
            self.close_connections()
            return
        if cmd == "CHAT":
            idx = msg.upper().find("CHAT")
            chat_msg = msg[idx + 4:].strip()
            if not chat_msg:
                self.send_msg(player, "Error: Message cannot be empty.\n")
                return
            sender_name = "Player 1"
            if player == self.player1:
                if self.player1_name != "":
                    sender_name = self.player1_name
            else:
                sender_name = "Player 2"
                if self.player2_name != "":
                    sender_name = self.player2_name
            print(f"{sender_name}: {chat_msg}")
            self.broadcast(f"\n[CHAT] {sender_name}: {chat_msg}\n")
            return

        if self.state == "REGISTERING":
            if cmd == "NAME":
                if len(args) < 1:
                    self.send_msg(player, protocol.ERROR_INVALID_VAL)
                    return
                name = args[0]
                if player == self.player1:
                    if self.player1_name != "":
                        self.send_msg(player, protocol.ERROR_ALREADY_REGISTERED)
                        return
                    self.player1_name = name
                    self.engine.set_player(name)
                    self.send_msg(self.player1, f"Successfully registered as: {name}\nWaiting for Player 2 to register...\n")
                    self.send_msg(self.player2, f"Player 1 has registered as: {name}\n")
                else:
                    if self.player2_name != "":
                        self.send_msg(player, protocol.ERROR_ALREADY_REGISTERED)
                        return
                    self.player2_name = name
                    self.engine.set_player(name)
                    self.send_msg(self.player2, f"Successfully registered as: {name}\n")
                    self.broadcast(f"Both players registered!\n  Player 1: {self.player1_name}\n  Player 2: {self.player2_name}\n")
                    self._start_new_game_log()
                    self.state = "TOSS"
                    self.send_msg(self.player1, protocol.PROMPT_TOSS_P1)
                    self.send_msg(self.player2, f"Waiting for {self.player1_name} to choose ODD/EVEN for the toss...\n")
            else:
                self.send_msg(player, protocol.ERROR_INVALID_CMD)
            return

        if self.state == "TOSS":
            if cmd == "TOSS":
                if player == self.player1:
                    if len(args) < 2:
                        self.send_msg(player, protocol.ERROR_INVALID_VAL)
                        return
                    choice = args[0].upper()
                    if choice not in ["ODD", "EVEN"]:
                        self.send_msg(player, "Error: Choice must be ODD or EVEN.\n")
                        return
                    try:
                        num = int(args[1])
                    except ValueError:
                        self.send_msg(player, "Error: Number must be an integer.\n")
                        return
                    if num < 1 or num > 6:
                        self.send_msg(player, "Error: Number must be between 1 and 6.\n")
                        return
                    self.p1_toss_choice = choice
                    self.p1_toss_num = num
                    self.send_msg(self.player1, f"You chose {choice} and entered {num}.\nWaiting for {self.player2_name}...\n")
                    self.send_msg(self.player2, protocol.PROMPT_TOSS_P2)
                else:
                    if len(args) < 1:
                        self.send_msg(player, protocol.ERROR_INVALID_VAL)
                        return
                    try:
                        num = int(args[0])
                    except ValueError:
                        self.send_msg(player, "Error: Number must be an integer.\n")
                        return
                    if num < 1 or num > 6:
                        self.send_msg(player, "Error: Number must be between 1 and 6.\n")
                        return
                    if self.p1_toss_choice is None:
                        self.send_msg(player, "Error: Please wait for Player 1 to make their choice first.\n")
                        return
                    self.p2_toss_num = num
                    self.send_msg(self.player2, f"You entered {num}.\n")
                    winner_name = self.engine.resolve_toss(self.p1_toss_choice, self.p1_toss_num, self.p2_toss_num)
                    total = self.p1_toss_num + self.p2_toss_num
                    even_odd = "EVEN" if total % 2 == 0 else "ODD"
                    self.broadcast(f"\nToss Resolution:\n  {self.player1_name} chose {self.p1_toss_choice} and threw {self.p1_toss_num}\n  {self.player2_name} threw {self.p2_toss_num}\n  Total: {total} ({even_odd})\n  WINNER: {winner_name}\n\n")
                    self.state = "TOSS_DECISION"
                    winner_player = self.player1 if winner_name == self.player1_name else self.player2
                    loser_player = self.player2 if winner_name == self.player1_name else self.player1
                    self.send_msg(winner_player, protocol.PROMPT_DECIDE)
                    self.send_msg(loser_player, f"Waiting for {winner_name} to decide to BAT or BOWL...\n")
                return
            else:
                self.send_msg(player, protocol.ERROR_INVALID_CMD)
                return

        if self.state == "TOSS_DECISION":
            if cmd == "DECIDE":
                toss_winner_name = self.engine.toss_winner
                toss_winner_player = self.player1 if toss_winner_name == self.player1_name else self.player2
                if player != toss_winner_player:
                    self.send_msg(player, protocol.ERROR_NOT_YOUR_TURN)
                    return
                if len(args) < 1:
                    self.send_msg(player, protocol.ERROR_INVALID_VAL)
                    return
                choice = args[0].upper()
                if choice not in ["BAT", "BOWL"]:
                    self.send_msg(player, "Error: Choice must be BAT or BOWL.\n")
                    return
                if choice == "BAT":
                    batting_player = toss_winner_name
                else:
                    batting_player = self.player2_name if toss_winner_name == self.player1_name else self.player1_name
                self.engine.set_roles(batting_player)
                self.broadcast(f"\nGame roles decided:\n  Batter: {self.engine.batting_player}\n  Bowler: {self.engine.bowling_player}\n\nLet the game begin!\n")
                self.innings_number = 1
                self._log_line(f"inn{self.innings_number}")
                self.state = "PLAYING_INNINGS_1"
                self.broadcast(protocol.PROMPT_PLAY)
            else:
                self.send_msg(player, protocol.ERROR_INVALID_CMD)
            return

        if self.state == "PLAYING_INNINGS_1":
            if cmd == "PLAY":
                if len(args) < 1:
                    self.send_msg(player, protocol.ERROR_INVALID_VAL)
                    return
                try:
                    num = int(args[0])
                except ValueError:
                    self.send_msg(player, "Error: Number must be an integer.\n")
                    return
                if num < 1 or num > 6:
                    self.send_msg(player, "Error: Number must be between 1 and 6.\n")
                    return
                if player == self.player1:
                    if self.p1_play_num is not None:
                        self.send_msg(player, "Error: You have already played. Waiting for Player 2...\n")
                        return
                    self.p1_play_num = num
                    self.send_msg(player, f"You threw {num}.\n")
                else:
                    if self.p2_play_num is not None:
                        self.send_msg(player, "Error: You have already played. Waiting for Player 1...\n")
                        return
                    self.p2_play_num = num
                    self.send_msg(player, f"You threw {num}.\n")

                # ── 45s forfeit timer: start/keep it running as soon as one
                # side has played and the other hasn't yet ────────────────
                if self.p1_play_num is not None and self.p2_play_num is None:
                    self.play_deadline = time.time() + 45
                    self.send_msg(self.player2, f"\n⏳ {self.player1_name} has played. Respond within 45 seconds or you forfeit the match.\n")
                elif self.p2_play_num is not None and self.p1_play_num is None:
                    self.play_deadline = time.time() + 45
                    self.send_msg(self.player1, f"\n⏳ {self.player2_name} has played. Respond within 45 seconds or you forfeit the match.\n")

                if self.p1_play_num is not None and self.p2_play_num is not None:
                    if self.engine.batting_player == self.player1_name:
                        bat_num, bowl_num = self.p1_play_num, self.p2_play_num
                    else:
                        bat_num, bowl_num = self.p2_play_num, self.p1_play_num
                    is_out, runs_scored = self.engine.play_turn(bat_num, bowl_num)
                    self._log_line(f"{self.engine.batting_player} bats {bat_num} {self.engine.bowling_player} bowls {bowl_num}")
                    self.p1_play_num = None
                    self.p2_play_num = None
                    self.play_deadline = None
                    if is_out:
                        self.broadcast(f"\nOUT! Match update:\n  {self.engine.bowling_player} got {self.engine.batting_player} out!\n  First Innings Score: {self.engine.target - 1} runs.\n  Target for second innings: {self.engine.target} runs.\n\nRoles swapped!\n  New Batter: {self.engine.batting_player}\n  New Bowler: {self.engine.bowling_player}\n\n")
                        self.engine.transition_to_second_innings()  
                        self.innings_number = 2
                        self._log_line(f"inn{self.innings_number}")
                        self.state = "PLAYING_INNINGS_2"
                        self.broadcast("Now batting: " + self.engine.batting_player + " (Player " + str(2 if self.engine.batting_player == self.player2_name else 1) + ")\n")
                        self.broadcast(protocol.PROMPT_PLAY)
                    else:
                        bat_score = self.engine.player1_score if self.engine.batting_player == self.player1_name else self.engine.player2_score
                        self.broadcast(f"\nResult: Batter threw {bat_num}, Bowler threw {bowl_num}.\n  Batter scores {runs_scored} runs!\n  Total Score: {self.engine.batting_player} - {bat_score} runs\n\n")
                        self.broadcast(protocol.PROMPT_PLAY)
            else:
                self.send_msg(player, protocol.ERROR_INVALID_CMD)
            return

        if self.state == "PLAYING_INNINGS_2":
            if cmd == "PLAY":
                if len(args) < 1:
                    self.send_msg(player, protocol.ERROR_INVALID_VAL)
                    return
                try:
                    num = int(args[0])
                except ValueError:
                    self.send_msg(player, "Error: Number must be an integer.\n")
                    return
                if num < 1 or num > 6:
                    self.send_msg(player, "Error: Number must be between 1 and 6.\n")
                    return
                if player == self.player1:
                    if self.p1_play_num is not None:
                        self.send_msg(player, "Error: You have already played. Waiting for Player 2...\n")
                        return
                    self.p1_play_num = num
                    self.send_msg(player, f"You threw {num}.\n")
                else:
                    if self.p2_play_num is not None:
                        self.send_msg(player, "Error: You have already played. Waiting for Player 1...\n")
                        return
                    self.p2_play_num = num
                    self.send_msg(player, f"You threw {num}.\n")

                # ── 45s forfeit timer (same logic as innings 1) ─────────────
                if self.p1_play_num is not None and self.p2_play_num is None:
                    self.play_deadline = time.time() + 45
                    self.send_msg(self.player2, f"\n⏳ {self.player1_name} has played. Respond within 45 seconds or you forfeit the match.\n")
                elif self.p2_play_num is not None and self.p1_play_num is None:
                    self.play_deadline = time.time() + 45
                    self.send_msg(self.player1, f"\n⏳ {self.player2_name} has played. Respond within 45 seconds or you forfeit the match.\n")

                if self.p1_play_num is not None and self.p2_play_num is not None:
                    if self.engine.batting_player == self.player1_name:
                        bat_num, bowl_num = self.p1_play_num, self.p2_play_num
                    else:
                        bat_num, bowl_num = self.p2_play_num, self.p1_play_num
                    is_out, runs_scored = self.engine.play_turn(bat_num, bowl_num)
                    self._log_line(f"{self.engine.batting_player} bats {bat_num} {self.engine.bowling_player} bowls {bowl_num}")
                    self.p1_play_num = None
                    self.p2_play_num = None
                    self.play_deadline = None
                    if is_out:
                        winner = self.engine.end_second_innings_by_out()
                        bat_score = self.engine.player1_score if self.engine.batting_player == self.player1_name else self.engine.player2_score
                        self.broadcast(f"\nOUT! Match update:\n  Batter threw {bat_num}, Bowler threw {bowl_num}.\n  Second Innings Score: {bat_score} runs.\n  Target: {self.engine.target} runs.\n\n========================================= TARGET DEFENDED SUCCESSFULLY=========================================\n  MATCH OVER! WINNER: {winner}\n=========================================\n\nDo you want to play again? Enter: PLAY_AGAIN or EXIT\n")
                        self._log_line(f"result: {winner} wins (defended target)")
                        self.state = "GAME_OVER"
                    else:
                        bat_score = self.engine.player1_score if self.engine.batting_player == self.player1_name else self.engine.player2_score
                        is_over, winner = self.engine.check_second_innings_status()
                        if is_over:
                            self.broadcast(f"\nResult: Batter threw {bat_num}, Bowler threw {bowl_num}.\n  Batter scores {runs_scored} runs!\n  Total Score: {self.engine.batting_player} - {bat_score}/{self.engine.target} runs.\n\n=========================================\n  TARGET CHASED SUCCESSFULLY!\n  MATCH OVER! WINNER: {winner}\n=========================================\n\nDo you want to play again? Enter: PLAY_AGAIN or EXIT\n")
                            self._log_line(f"result: {winner} wins (chased target)")
                            self.state = "GAME_OVER"
                        else:
                            self.broadcast(f"\nResult: Batter threw {bat_num}, Bowler threw {bowl_num}.\n  Batter scores {runs_scored} runs!\n  Current Score: {self.engine.batting_player} - {bat_score}/{self.engine.target} runs.\n  Runs needed to win: {self.engine.target - bat_score} runs.\n\n")
                            self.broadcast(protocol.PROMPT_PLAY)
            else:
                self.send_msg(player, protocol.ERROR_INVALID_CMD)
            return

        if self.state == "GAME_OVER":
            val = msg.strip().upper()
            if val in ["PLAY_AGAIN", "PLAY AGAIN"]:
                if player == self.player1:
                    self.p1_replay = True
                    self.send_msg(player, "You selected Play Again. Waiting for Player 2...\n")
                else:
                    self.p2_replay = True
                    self.send_msg(player, "You selected Play Again. Waiting for Player 1...\n")
                if self.p1_replay and self.p2_replay:
                    self.engine.reset()
                    self.p1_toss_choice = None
                    self.p1_toss_num = None
                    self.p2_toss_num = None
                    self.p1_play_num = None
                    self.p2_play_num = None
                    self.p1_replay = None
                    self.p2_replay = None
                    self.play_deadline = None
                    self.broadcast("\n=========================================\n  STARTING A NEW GAME!\n=========================================\n")
                    self._start_new_game_log()
                    self.state = "TOSS"
                    self.send_msg(self.player1, protocol.PROMPT_TOSS_P1)
                    self.send_msg(self.player2, f"Waiting for {self.player1_name} to choose ODD/EVEN for the toss...\n")
            elif val == "EXIT":
                self.broadcast("Exit selected. Closing connections...\n")
                self.close_connections()
            else:
                self.send_msg(player, "Invalid choice. Please select: PLAY_AGAIN or EXIT\n")
            return

    def _drain_socket(self, sock):
        """
        Read whatever is available from sock, append to its buffer, split
        on '\\n', and return the list of complete messages (without the
        trailing newline). Any trailing partial line stays buffered for
        next time. Returns None if the peer disconnected.
        """
        data = sock.recv(4096)
        if not data:
            return None  # peer closed
        text = data.decode(errors="ignore")
        self._recv_buf[sock] = self._recv_buf.get(sock, "") + text
        lines = self._recv_buf[sock].split("\n")
        # last element is the (possibly empty) unterminated remainder
        self._recv_buf[sock] = lines[-1]
        complete = [l for l in lines[:-1]]
        return complete

    def start(self):
        server_sock = x.socket(x.AF_INET, x.SOCK_STREAM)
        server_sock.setsockopt(x.SOL_SOCKET, x.SO_REUSEADDR, 1)
        server_sock.bind((self.host, self.port))
        server_sock.listen(2)
        print(f"Server started on {self.host}:{self.port}")

        while True:
            try:
                print("Waiting for player 1...")
                raw1, addr1 = server_sock.accept()
                print(f"  TCP connection from {addr1}")
                try:
                    self.player1 = self.ssl_context.wrap_socket(raw1, server_side=True)
                except ssl.SSLError as e:
                    print(f"[SSL] Player 1 handshake failed: {e}")
                    try: raw1.close()
                    except: pass
                    continue
                print("[SSL] Handshake completed with Player 1")

                print("Waiting for player 2...")
                raw2, addr2 = server_sock.accept()
                print(f"  TCP connection from {addr2}")
                try:
                    self.player2 = self.ssl_context.wrap_socket(raw2, server_side=True)
                except ssl.SSLError as e:
                    print(f"[SSL] Player 2 handshake failed: {e}")
                    try: raw2.close()
                    except: pass
                    continue
                print("[SSL] Handshake completed with Player 2")

                self.send_msg(self.player1, protocol.WELCOME_MSG)
                self.send_msg(self.player1, "You are Player 1.\n")
                self.send_msg(self.player2, protocol.WELCOME_MSG)
                self.send_msg(self.player2, "You are Player 2.\n")

                self.player1_name  = ""
                self.player2_name  = ""
                self.state         = "REGISTERING"
                self.p1_toss_choice = None
                self.p1_toss_num   = None
                self.p2_toss_num   = None
                self.p1_play_num   = None
                self.p2_play_num   = None
                self.p1_replay     = None
                self.p2_replay     = None
                self.play_deadline = None

                self.broadcast("Both players connected! Please register your names to begin.\n")
                self.send_msg(self.player1, protocol.PROMPT_NAME)
                self.send_msg(self.player2, protocol.PROMPT_NAME)

                while True:
                    # 1.0s timeout so we periodically wake up even with no
                    # socket activity, to check the 45s forfeit timer below.
                    readable, _, _ = select.select([self.player1, self.player2], [], [], 1.0)
                    disconnect = False
                    for sock in readable:
                        try:
                            messages = self._drain_socket(sock)
                            if messages is None:
                                # ── Abandonment via ungraceful disconnect ──
                                exiter_name = self.player1_name if sock == self.player1 else self.player2_name
                                winner_name = self.player2_name if sock == self.player1 else self.player1_name
                                if not exiter_name:
                                    exiter_name = "Player 1" if sock == self.player1 else "Player 2"
                                if not winner_name:
                                    winner_name = "Player 2" if sock == self.player1 else "Player 1"
                                self.broadcast(f"\n{exiter_name} disconnected / abandoned the match. {winner_name} wins by default!\n")
                                self._log_line(f"result: {winner_name} wins (opponent abandoned)")
                                self.close_connections()
                                disconnect = True
                                break
                            for line in messages:
                                if line.strip():
                                    self.handle_player_message(sock, line)
                                if self.state == "CLOSED":
                                    break
                        except Exception as e:
                            print(f"Error reading from player socket: {e}")
                            self.close_connections()
                            disconnect = True
                            break
                    if disconnect or self.state == "CLOSED":
                        break
                    self._check_play_timeout()
                    if self.state == "CLOSED":
                        break

            except Exception as e:
                print(f"Server error: {e}")
            finally:
                self.close_connections()

def start_server(host, port):
    server = HandCricketServer(host, port)
    server.start()