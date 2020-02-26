#!/usr/bin/env python3

import os
import requests
import textwrap
import shutil
import yaml
from getpass import getpass


class FailedConfiguration(Exception):
    """raise this when the yaml configuration phase failed"""


# Quit Session exception for easier error and exiting handling
class QuitSession(Exception):
    """raise this when the user typed /quit in order to leave the session"""


# CONFIG

def create_config(cfg_file):
    """
    Prompts user if they want to create a config, attempts login, then writes to config file

    TODO: consider asking user where to save config file

    TODO: Don't save password in plaintext in file

    """
    answer = None
    while answer not in ["yes", "y", "no", "n"]:
        answer = input("Would you like to create a config now? [y/n]: ").lower().strip()
        if answer in ["yes","y"]:

            email, password = get_user_login()
            auth_token = login(email,password)
            cfg = {"email":email, "password":password, "auth_token":auth_token,"prompt":"> "}
            cfg_file_path = os.path.dirname(os.path.realpath(__file__)) + cfg_file
            try:
                with open(cfg_file_path, 'w+') as cfg_raw:
                    yaml.dump(cfg,cfg_raw)
                    print("wrote to {}".format(cfg_file_path))
            except IOError:
                print("Could not open {}".format(cfg_file_path))
                raise FailedConfiguration

        elif answer in ["no", "n"]:
            print("OK Quitting...")
            exit(1)
        else:
            print("Please enter yes or no.")
    return cfg

def get_user_login():
    """
    Asks user for their email and 'hidden' password
    """
    email = input("What is your email?: ")
    password =  getpass("What is your password?: ")
    return [email, password]

def init_configuration_file():
    cfg_file = "/config.yml"
    cfg_file_paths = [
        os.path.dirname(os.path.realpath(__file__)) + cfg_file,
        os.getenv("HOME") + "/.config/ai-dungeon-cli" + cfg_file,
    ]

    did_read_cfg_file = False

    for file in cfg_file_paths:
        try:
            with open(file, 'r') as cfg_raw:
                cfg = yaml.load(cfg_raw, Loader=yaml.FullLoader)
                did_read_cfg_file = True
                break
        except IOError:
            pass

    if not did_read_cfg_file:
        print("Missing config file at ", end="")
        print(*cfg_file_paths, sep=", ")
        cfg = create_config(cfg_file)
    
    if cfg is None:
        print("config file empty or badly formatted")
        raise FailedConfiguration

    auth_token = None
    if "auth_token" in cfg and cfg["auth_token"]:
        auth_token = cfg["auth_token"]

    email = None
    if "email" in cfg and cfg["email"]:
        email = cfg['email']

    password = None
    if "password" in cfg and cfg["password"]:
        password = cfg['password']

    prompt = "> "
    if "prompt" in cfg and cfg["prompt"]:
        prompt = cfg["prompt"]

    if auth_token is None :
        if email is not None and password is not None:
            # there is no auth token but there is an email and password provided
            auth_token = login(email, password)
        else:
            raise FailedConfiguration
            
    return auth_token, prompt


# FUNCTIONS: AUTH

def login(email, password):
    """
    make a request to the users api and attempt to log in
    if succeeded, save the auth token

    TODO: allow sign up through the cli

    """
    s = requests.Session()
    r = s.post("https://api.aidungeon.io/users",
               json={ 'email': email,
                      'password': password })
    resp = r.json()
    if r.status_code != requests.codes.ok:
        print("Failed to log in using provided credentials. Check your email and password.")
        raise FailedConfiguration
    auth_token = resp['accessToken']
    print("Got access token: {}".format(auth_token))
    return auth_token


# SYSTEM FUNCTIONS


def clear_console():
    if os.name == "nt":
        _ = os.system("cls")
    else:
        _ = os.system("clear")


def display_splash():
    filename = os.path.dirname(os.path.realpath(__file__))
    locale = None
    term = None
    if "LC_ALL" in os.environ:
        locale = os.environ["LC_ALL"]
    if "TERM" in os.environ:
        term = os.environ["TERM"]

    if locale == "C" or (term and term.startswith("vt")):
        filename += "/opening-ascii.txt"
    else:
        filename += "/opening-utf8.txt"

    with open(filename, "r") as splash_image:
        print(splash_image.read())


class AiDungeon:
    def __init__(self, auth_token, prompt):
        self.terminal_size = shutil.get_terminal_size((80, 20))
        self.terminal_width = self.terminal_size.columns
        self.prompt = prompt
        self.prompt_iteration = 0
        self.stop_session = False
        self.user_id = None
        self.session_id = None
        self.public_id = None
        self.story_configuration = {}
        self.session = requests.Session()
        self.session.headers.update(
            {
                # 'cookie': cookie,
                "X-Access-Token": auth_token,
            }
        )

    def print_sentences(self, text):
        print("\n".join(textwrap.wrap(text, self.terminal_width)))

    def choose_selection(self, allowed_values):
        while True:
            choice = input(self.prompt)
            print()

            choice = choice.strip()

            if choice == "/quit":
                raise QuitSession("/quit")

            elif choice in allowed_values.keys():
                choice = allowed_values[choice]
            elif choice in allowed_values.values():
                pass
            else:
                self.print_sentences("Please enter a valid selection.")
                print()
                continue
            break
        return choice

    def make_custom_config(self):

        self.print_sentences(
            "Enter a prompt that describes who you are and the first couple sentences of where you start out ex: "
            "'You are a knight in the kingdom of Larion. You are hunting the evil dragon who has been terrorizing "
            "the kingdom. You enter the forest searching for the dragon and see'"
        )
        print()

        context = input(self.prompt)
        print()

        if context == "/quit":
            raise QuitSession("/quit")

        self.story_configuration = {
            "storyMode": "custom",
            "characterType": None,
            "name": None,
            "customPrompt": context,
            "promptId": None,
        }

    def choose_config(self):
        # Get the configuration for this session
        response = self.session.get("https://api.aidungeon.io/sessions/*/config").json()

        print("Pick a setting...\n")

        mode_select_dict = {}
        for i, (mode, opts) in enumerate(response["modes"].items(), start=1):
            print(str(i) + ") " + mode)
            mode_select_dict[str(i)] = mode
        print()
        selected_mode = self.choose_selection(mode_select_dict)

        if selected_mode == "/quit":
            raise QuitSession("/quit")

        # If the custom option was selected load the custom configuration and don't continue this configuration
        if selected_mode == "custom":
            self.make_custom_config()
            return

        print("Select a character...\n")

        character_select_dict = {}
        for i, (character, opts) in enumerate(
            response["modes"][selected_mode]["characters"].items(), start=1
        ):
            print(str(i) + ") " + character)
            character_select_dict[str(i)] = character
        print()
        selected_character = self.choose_selection(character_select_dict)

        if selected_character == "/quit":
            raise QuitSession("/quit")

        print("Enter your character's name...\n")

        character_name = input(self.prompt)
        print()

        if character_name == "/quit":
            raise QuitSession("/quit")

        self.story_configuration = {
            "storyMode": selected_mode,
            "characterType": selected_character,
            "name": character_name,
            "customPrompt": None,
            "promptId": None,
        }

    def init_story(self):

        print("Generating story... Please wait...\n")

        story_response = self.session.post(
            "https://api.aidungeon.io/sessions", json=self.story_configuration
        ).json()

        self.user_id = story_response["userId"]
        self.session_id = story_response["id"]
        self.public_id = story_response["publicId"]

        story_pitch = story_response["story"][0]["value"]

        self.print_sentences(story_pitch)
        print()

    def process_next_action(self):
        user_input = input(self.prompt)
        print()

        if user_input == "/quit":
            self.stop_session = True

        action_res = self.session.post(
            "https://api.aidungeon.io/sessions/" + str(self.session_id) + "/inputs",
            json={"text": user_input},
        ).json()

        action_res_str = action_res[self.prompt_iteration]["value"]
        self.print_sentences(action_res_str)
        print()

    def start_game(self):
        # Run until /quit is received inside the process_next_action func
        while not self.stop_session:
            self.prompt_iteration += 2
            self.process_next_action()


# MAIN

def main():

    try:
        # Loads the yaml configuration file
        auth_token, prompt = init_configuration_file()

        # Clears the console
        clear_console()

        # Displays the splash image accordingly
        display_splash()

        # Initialize the AiDungeon class with the given auth_token and prompt
        current_run = AiDungeon(auth_token, prompt)

        # Loads the current session configuration
        current_run.choose_config()

        # Initializes the story
        current_run.init_story()

        # Starts the game
        current_run.start_game()

    except FailedConfiguration:
        exit(1)

    except QuitSession:
        current_run.print_sentences("Bye Bye!")
    
    except KeyboardInterrupt:
        print("Received Keyboard Interrupt. Bye Bye...")

    except ConnectionError:
        current_run.print_sentences("Lost connection to the Ai Dungeon servers")


if __name__ == "__main__":
    main()
