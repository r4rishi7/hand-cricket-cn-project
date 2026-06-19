class GameEngine:
    def __init__(self):
        self.player1 = ""
        self.player2 = ""
        self.player1_score = 0
        self.player2_score = 0
        self.winner = ""
        self.toss_winner = ""
        self.target = 0
        self.batting_player = ""
        self.bowling_player = ""

    def reset(self):
        self.player1_score = 0
        self.player2_score = 0
        self.winner = ""
        self.toss_winner = ""
        self.target = 0
        self.batting_player = ""
        self.bowling_player = ""

    def set_player(self, player):
        if self.player1 == "":
            self.player1 = player
            return 1
        elif self.player2 == "":
            self.player2 = player
            return 2
        else:
            return 0  # Both players already set

    def get_player1(self):
        return self.player1

    def get_player2(self):
        return self.player2

    def resolve_toss(self, player1_choice, player1_run, player2_run):
        total = player1_run + player2_run
        is_even = (total % 2 == 0)
        p1_won = (is_even and player1_choice.upper() == "EVEN") or (not is_even and player1_choice.upper() == "ODD")
        self.toss_winner = self.player1 if p1_won else self.player2
        return self.toss_winner

    def set_roles(self, batting_player):
        self.batting_player = batting_player
        self.bowling_player = self.player2 if batting_player == self.player1 else self.player1

    def play_turn(self, bat_run, bowl_run):
        # Returns (is_out, runs_scored)
        if bat_run == bowl_run:
            return True, 0
        else:
            if self.batting_player == self.player1:
                self.player1_score += bat_run
            else:
                self.player2_score += bat_run
            return False, bat_run

    def transition_to_second_innings(self):
        first_innings_score = self.player1_score if self.batting_player == self.player1 else self.player2_score
        self.target = first_innings_score + 1
        # Swap roles
        self.batting_player, self.bowling_player = self.bowling_player, self.batting_player

    def check_second_innings_status(self):
        # Returns (is_over, winner_name)
        batting_score = self.player1_score if self.batting_player == self.player1 else self.player2_score
        if batting_score >= self.target:
            self.winner = self.batting_player
            return True, self.winner
        return False, ""

    def end_second_innings_by_out(self):
        batting_score = self.player1_score if self.batting_player == self.player1 else self.player2_score
        bowling_score = self.player1_score if self.bowling_player == self.player1 else self.player2_score
        if batting_score > bowling_score:
            self.winner = self.batting_player
        elif bowling_score > batting_score:
            self.winner = self.bowling_player
        else:
            self.winner = "Draw"
        return self.winner

        