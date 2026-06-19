class Protocols:
    WELCOME_MSG = "=========================================\n  WELCOME TO THE HAND CRICKET GAME!   \n=========================================\n"
    HELP_TXT = """
List of Available Commands:
  NAME <your_name>       - Register your name
  TOSS <ODD/EVEN> <1-6> - (Player 1) Choose ODD or EVEN and enter a number 1-6
  TOSS <1-6>            - (Player 2) Enter a number 1-6 for the toss
  DECIDE <BAT/BOWL>     - (Toss Winner) Decide to BAT or BOWL
  PLAY <1-6>            - Enter a number 1-6 to bat or bowl
  CHAT <message>         - Send a chat message to the other player
  EXIT                  - Leave the game
  HELP                  - Show this help message
"""
    PROMPT_NAME = "Please register your name: NAME <your_name>\n"
    PROMPT_TOSS_P1 = "Toss Phase: Choose ODD/EVEN and enter a number (1-6): TOSS <ODD/EVEN> <number>\n"
    PROMPT_TOSS_P2 = "Toss Phase: Enter a number (1-6) to resolve the toss: TOSS <number>\n"
    PROMPT_DECIDE = "You won the toss! Choose to BAT or BOWL: DECIDE <BAT/BOWL>\n"
    PROMPT_PLAY = "Enter your run/guess (1-6): PLAY <number>\n"

    ERROR_INVALID_CMD = "Error: Invalid command. Type HELP for help.\n"
    ERROR_INVALID_VAL = "Error: Invalid value(s) provided. Please try again.\n"
    ERROR_NOT_YOUR_TURN = "Error: It's not your turn, or you must wait for the other player.\n"
    ERROR_ALREADY_REGISTERED = "Error: You have already registered your name.\n"


